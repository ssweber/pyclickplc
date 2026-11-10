"""Modbus TCP server simulating an AutomationDirect CLICK PLC.

Incoming Modbus requests are reverse-mapped to PLC addresses and
routed to a user-supplied DataProvider.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pymodbus.constants import ExcCodes
from pymodbus.datastore import ModbusDeviceContext, ModbusServerContext
from pymodbus.pdu import ExceptionResponse, ModbusPDU
from pymodbus.pdu.bit_message import WriteSingleCoilRequest
from pymodbus.server import ModbusTcpServer

from .addresses import AddressNormalizerMixin, format_address_display, parse_address
from .banks import BANKS, DataType
from .modbus import (
    MAX_READ_COILS,
    MAX_READ_REGISTERS,
    MAX_WRITE_COILS,
    MAX_WRITE_REGISTERS,
    MODBUS_MAPPINGS,
    _in_sparse_coil_span,
    modbus_to_plc,
    modbus_to_plc_register,
    pack_value,
    unpack_value,
)
from .validation import assert_runtime_value

# ==============================================================================
# DataProvider Protocol
# ==============================================================================

PlcValue = bool | int | float | str


@runtime_checkable
class DataProvider(Protocol):
    """Backend protocol for PLC value storage."""

    def read(self, address: str) -> PlcValue: ...
    def write(self, address: str, value: PlcValue) -> None: ...


# ==============================================================================
# MemoryDataProvider
# ==============================================================================

# Default values by DataType
_DEFAULTS: dict[DataType, PlcValue] = {
    DataType.BIT: False,
    DataType.INT: 0,
    DataType.INT2: 0,
    DataType.FLOAT: 0.0,
    DataType.HEX: 0,
    DataType.TXT: "\x00",
}


class MemoryDataProvider(AddressNormalizerMixin):
    """In-memory DataProvider for testing and simple use cases."""

    def __init__(self) -> None:
        self._data: dict[str, PlcValue] = {}

    def _normalize(self, address: str) -> tuple[str, str, int]:
        """Normalize address and return (normalized, bank, index)."""
        normalized = self._normalize_address_strict(address)
        bank, index = parse_address(normalized)
        return normalized, bank, index

    def _default(self, bank: str) -> PlcValue:
        """Get default value for a bank."""
        data_type = BANKS[bank].data_type
        return _DEFAULTS[data_type]

    def read(self, address: str) -> PlcValue:
        normalized, bank, _index = self._normalize(address)
        return self._data.get(normalized, self._default(bank))

    def write(self, address: str, value: PlcValue) -> None:
        normalized, bank, index = self._normalize(address)
        assert_runtime_value(BANKS[bank].data_type, value, bank=bank, index=index)
        self._data[normalized] = value

    def get(self, address: str) -> PlcValue:
        """Synchronous read convenience."""
        return self.read(address)

    def set(self, address: str, value: PlcValue) -> None:
        """Synchronous write convenience."""
        self.write(address, value)

    def bulk_set(self, values: Mapping[str, PlcValue]) -> None:
        """Set multiple values at once."""
        for address, value in values.items():
            self.set(address, value)


@dataclass(frozen=True)
class ServerClientInfo:
    """Connected client metadata exposed by ClickServer."""

    client_id: str
    peer: str


# ==============================================================================
# _ClickDeviceContext
# ==============================================================================


def _is_address_writable(bank: str, index: int) -> bool:
    """Check if a PLC address is writable via Modbus."""
    mapping = MODBUS_MAPPINGS[bank]
    if mapping.writable is not None:
        return index in mapping.writable
    return mapping.is_writable


def _format_plc_address(bank: str, index: int) -> str:
    """Format a PLC address string for DataProvider calls."""
    return format_address_display(bank, index)


def _is_unnamed_word(bank: str, index: int) -> bool:
    """True for an XD or YD register that no address names (MDB 3, 5, ..., 15).

    XDn sits at MDB 2n, so the odd registers above XD0u have no name. A CLICK keeps each one
    as a spare word that drives no X or Y. Formatting one gives the register before it.
    """
    return bank in ("XD", "YD") and index >= 3 and index % 2 == 1


# A store is a provider address and its value, or a spare word's Modbus address and its value.
_Store = tuple[str | int, PlcValue]


class _StrictWriteCoilRequest(WriteSingleCoilRequest):
    """FC 05 that refuses a value other than 0x0000 or 0xFF00.

    pymodbus turns any non-zero value into True before the datastore sees it.
    """

    raw_value = 0

    def decode(self, data: bytes) -> None:
        super().decode(data)
        self.raw_value = struct.unpack(">H", data[2:4])[0]

    async def datastore_update(self, context: ModbusServerContext, device_id: int) -> ModbusPDU:
        if self.raw_value not in (0x0000, 0xFF00):
            return ExceptionResponse(self.function_code, ExcCodes.ILLEGAL_VALUE)
        return await super().datastore_update(context, device_id)


class _ClickDeviceContext(ModbusDeviceContext):
    """Custom pymodbus context routing Modbus requests to a DataProvider."""

    def __init__(self, provider: DataProvider, spare_words: dict[int, int] | None = None) -> None:
        self.provider = provider
        # The unnamed YD registers keep what a client writes to them, by Modbus address.
        self.spare_words: dict[int, int] = {} if spare_words is None else spare_words
        super().__init__()

    def reset(self) -> None:
        """Required by base class."""

    def validate(self, func_code: int, address: int, count: int = 1) -> bool:  # noqa: ARG002
        """Accept all addresses; get/setValues answer the exceptions."""
        return True

    def getValues(
        self, func_code: int, address: int, count: int = 1
    ) -> list[int] | list[bool] | ExcCodes:
        """Read values from the DataProvider."""
        # pymodbus 3.12 never calls validate(), so each request is checked here.
        if func_code in (1, 2) and not 1 <= count <= MAX_READ_COILS:
            return ExcCodes.ILLEGAL_VALUE
        if func_code in (3, 4) and not 1 <= count <= MAX_READ_REGISTERS:
            return ExcCodes.ILLEGAL_VALUE
        try:
            if func_code in (1, 2, 5, 15):
                return self._get_coils(address, count)
            return self._get_registers(address, count)
        except Exception:
            return ExcCodes.DEVICE_FAILURE

    def setValues(
        self, func_code: int, address: int, values: list[int] | list[bool]
    ) -> ExcCodes | None:
        """Write values to the DataProvider.

        A refused request leaves the provider unchanged. Every target is checked and read
        first, so the provider can put the old values back. A provider whose ``read`` raises
        for an address in the request fails the whole request with exception 04.
        """
        try:
            if func_code in (5, 15):
                plan = self._plan_coils(address, values)
            elif func_code == 6:
                plan = self._plan_registers(address, [values[0]])
            else:
                plan = self._plan_registers(address, values)
            if isinstance(plan, ExcCodes):
                return plan
            return self._commit(plan)
        except Exception:
            return ExcCodes.DEVICE_FAILURE

    def _commit(self, plan: list[_Store]) -> ExcCodes | None:
        """Store a checked plan, putting the old values back if the provider fails midway."""
        stores = [(plc_addr, value) for plc_addr, value in plan if isinstance(plc_addr, str)]
        old = [self.provider.read(plc_addr) for plc_addr, _ in stores]
        done = 0
        try:
            for plc_addr, value in stores:
                self.provider.write(plc_addr, value)
                done += 1
        except Exception:
            for (plc_addr, _), previous in zip(stores[:done], old[:done], strict=True):
                try:
                    self.provider.write(plc_addr, previous)
                except Exception:
                    pass
            return ExcCodes.DEVICE_FAILURE
        for reg_addr, value in plan:
            if isinstance(reg_addr, int):
                self.spare_words[reg_addr] = int(value)
        return None

    # --- Coil helpers ---

    def _get_coils(self, address: int, count: int) -> list[bool] | ExcCodes:
        result: list[bool] = []
        for i in range(count):
            mapped = modbus_to_plc(address + i, is_coil=True)
            if mapped is None:
                # A CLICK reads a gap between X or Y slots as OFF and refuses the rest.
                if not _in_sparse_coil_span(address + i):
                    return ExcCodes.ILLEGAL_ADDRESS
                result.append(False)
            else:
                bank, index = mapped
                plc_addr = _format_plc_address(bank, index)
                val = self.provider.read(plc_addr)
                result.append(bool(val))
        return result

    def _plan_coils(self, address: int, values: list[int] | list[bool]) -> list[_Store] | ExcCodes:
        if not 1 <= len(values) <= MAX_WRITE_COILS:
            return ExcCodes.ILLEGAL_VALUE
        plan: list[_Store] = []
        for i, val in enumerate(values):
            mapped = modbus_to_plc(address + i, is_coil=True)
            if mapped is None:
                if len(values) == 1 or not _in_sparse_coil_span(address + i):
                    return ExcCodes.ILLEGAL_ADDRESS
                continue  # FC 15 skips a gap between X or Y slots.
            bank, index = mapped
            if not _is_address_writable(bank, index):
                return ExcCodes.ILLEGAL_ADDRESS
            plan.append((_format_plc_address(bank, index), bool(val)))
        return plan

    # --- Register helpers ---

    def _get_registers(self, address: int, count: int) -> list[int] | ExcCodes:
        result: list[int] = []
        i = 0
        while i < count:
            reg_addr = address + i
            mapped = modbus_to_plc_register(reg_addr)
            if mapped is None:
                return ExcCodes.ILLEGAL_ADDRESS

            bank, index, reg_position = mapped
            if _is_unnamed_word(bank, index):
                result.append(self.spare_words.get(reg_addr, 0))
                i += 1
                continue
            mapping = MODBUS_MAPPINGS[bank]
            plc_addr = _format_plc_address(bank, index)

            # Handle TXT: 2 chars per register
            if bank == "TXT":
                # TXT packs 2 addresses per register
                # Odd TXT index = low byte, even = high byte
                txt_base_index = (index - 1) // 2 * 2 + 1  # Base of pair
                low_addr = _format_plc_address("TXT", txt_base_index)
                high_addr = _format_plc_address("TXT", txt_base_index + 1)
                low_val = self.provider.read(low_addr)
                high_val = self.provider.read(high_addr)
                low_text = str(low_val)
                high_text = str(high_val)
                low_byte = ord(low_text) & 0xFF if low_text else 0
                high_byte = ord(high_text) & 0xFF if high_text else 0
                result.append(low_byte | (high_byte << 8))
                i += 1
                continue

            # Read the PLC value
            val = self.provider.read(plc_addr)

            # Pack the value
            data_type = BANKS[bank].data_type
            if data_type == DataType.BIT:
                result.append(int(bool(val)))
                i += 1
                continue

            regs = pack_value(val, data_type)

            if mapping.width == 1:
                result.append(regs[0])
                i += 1
            else:
                # Width-2: might only need one register
                if reg_position == 0:
                    # Starting at first register of pair
                    remaining = count - i
                    if remaining >= 2:
                        result.extend(regs)
                        i += 2
                    else:
                        result.append(regs[0])
                        i += 1
                else:
                    # Starting at second register of pair
                    result.append(regs[1])
                    i += 1
        return result

    def _plan_registers(
        self, address: int, values: list[int] | list[bool]
    ) -> list[_Store] | ExcCodes:
        """Resolve a register write into (address, value) stores without storing any."""
        if not 1 <= len(values) <= MAX_WRITE_REGISTERS:
            return ExcCodes.ILLEGAL_VALUE
        plan: list[_Store] = []
        i = 0
        while i < len(values):
            mapped = modbus_to_plc_register(address + i)
            if mapped is None:
                return ExcCodes.ILLEGAL_ADDRESS

            bank, index, reg_position = mapped
            mapping = MODBUS_MAPPINGS[bank]
            if not _is_address_writable(bank, index):
                return ExcCodes.ILLEGAL_ADDRESS

            plc_addr = _format_plc_address(bank, index)
            data_type = BANKS[bank].data_type
            reg_val = int(values[i])
            if not 0 <= reg_val <= 0xFFFF:
                return ExcCodes.ILLEGAL_VALUE

            if _is_unnamed_word(bank, index):
                plan.append((address + i, reg_val))
                i += 1
                continue

            if bank == "TXT":
                txt_base_index = (index - 1) // 2 * 2 + 1
                plan.append((_format_plc_address("TXT", txt_base_index), chr(reg_val & 0xFF)))
                plan.append((_format_plc_address("TXT", txt_base_index + 1), chr(reg_val >> 8)))
                i += 1
                continue

            if mapping.width == 1:
                plan.append((plc_addr, unpack_value([reg_val], data_type)))
                i += 1
            elif reg_position == 0 and i + 1 < len(values):
                regs = [reg_val, int(values[i + 1])]
                if not 0 <= regs[1] <= 0xFFFF:
                    return ExcCodes.ILLEGAL_VALUE
                plan.append((plc_addr, unpack_value(regs, data_type)))
                i += 2
            else:
                # Half a value: keep the other register as stored.
                current_regs = pack_value(self.provider.read(plc_addr), data_type)
                current_regs[reg_position] = reg_val
                plan.append((plc_addr, unpack_value(current_regs, data_type)))
                i += 1

        for plc_addr, value in plan:
            if not isinstance(plc_addr, str):
                continue
            bank, index = parse_address(plc_addr)
            try:
                assert_runtime_value(BANKS[bank].data_type, value, bank=bank, index=index)
            except ValueError:
                return ExcCodes.ILLEGAL_VALUE
        return plan


# ==============================================================================
# ClickServer
# ==============================================================================


class ClickServer:
    """Modbus TCP server simulating a CLICK PLC."""

    def __init__(
        self,
        provider: DataProvider,
        host: str = "localhost",
        port: int = 502,
    ) -> None:
        """Create a ClickServer.

        Args:
            provider: Backend that stores and retrieves PLC values.
            host: Interface to bind (default ``"localhost"``).
            port: Modbus TCP port (default 502).
        """
        self.provider = provider
        self.host = host
        self.port = port
        self._server: ModbusTcpServer | None = None
        self._spare_words: dict[int, int] = {}

    @staticmethod
    def _format_peer(connection: Any) -> str:
        """Best-effort peer formatting from a pymodbus active connection."""
        transport = getattr(connection, "transport", None)
        if transport is None:
            return "unknown"
        peer = transport.get_extra_info("peername")
        if isinstance(peer, tuple) and len(peer) >= 2:
            return f"{peer[0]}:{peer[1]}"
        if peer:
            return str(peer)
        return "unknown"

    def is_running(self) -> bool:
        """Return True when the underlying listener transport is active."""
        return bool(self._server is not None and self._server.is_active())

    def list_clients(self) -> list[ServerClientInfo]:
        """Return the currently connected Modbus TCP clients."""
        if self._server is None:
            return []
        clients: list[ServerClientInfo] = []
        for client_id, connection in self._server.active_connections.items():
            clients.append(
                ServerClientInfo(client_id=client_id, peer=self._format_peer(connection))
            )
        return clients

    def disconnect_client(self, client_id: str) -> bool:
        """Disconnect a single client by pymodbus connection id."""
        if self._server is None:
            return False
        connection = self._server.active_connections.get(client_id)
        if connection is None:
            return False
        connection.close()
        return True

    def disconnect_all_clients(self) -> int:
        """Disconnect all connected clients and return how many were closed."""
        if self._server is None:
            return 0
        active = list(self._server.active_connections.values())
        for connection in active:
            connection.close()
        return len(active)

    async def start(self) -> None:
        """Start the Modbus TCP server."""
        context = _ClickDeviceContext(self.provider, self._spare_words)
        server_context = ModbusServerContext(devices=context, single=True)
        self._server = ModbusTcpServer(
            context=server_context,
            address=(self.host, self.port),
            custom_pdu=[_StrictWriteCoilRequest],
        )
        await self._server.serve_forever(background=True)

    async def stop(self) -> None:
        """Stop the server gracefully."""
        if self._server is not None:
            await self._server.shutdown()
            self._server = None

    async def serve_forever(self) -> None:
        """Start the server and block until stopped."""
        context = _ClickDeviceContext(self.provider, self._spare_words)
        server_context = ModbusServerContext(devices=context, single=True)
        self._server = ModbusTcpServer(
            context=server_context,
            address=(self.host, self.port),
            custom_pdu=[_StrictWriteCoilRequest],
        )
        await self._server.serve_forever(background=False)

    async def __aenter__(self) -> ClickServer:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.stop()
