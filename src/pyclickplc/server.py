"""Modbus TCP server simulating an AutomationDirect CLICK PLC.

Incoming Modbus requests are reverse-mapped to PLC addresses and
routed to a user-supplied DataProvider.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pymodbus.constants import ExcCodes
from pymodbus.datastore import ModbusBaseDeviceContext, ModbusServerContext
from pymodbus.server import ModbusTcpServer

from .addresses import format_address_display, parse_address
from .banks import BANKS, DataType
from .modbus import (
    MODBUS_MAPPINGS,
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


class MemoryDataProvider:
    """In-memory DataProvider for testing and simple use cases."""

    def __init__(self) -> None:
        self._data: dict[str, PlcValue] = {}

    def _normalize(self, address: str) -> tuple[str, str, int]:
        """Normalize address and return (normalized, bank, index)."""
        bank, index = parse_address(address)
        normalized = format_address_display(bank, index)
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

    def bulk_set(self, values: dict[str, PlcValue]) -> None:
        """Set multiple values at once."""
        for address, value in values.items():
            self.set(address, value)


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


class _ClickDeviceContext(ModbusBaseDeviceContext):
    """Custom pymodbus context routing Modbus requests to a DataProvider."""

    def __init__(self, provider: DataProvider) -> None:
        self.provider = provider
        super().__init__()

    def reset(self) -> None:
        """Required by base class."""

    def validate(self, func_code: int, address: int, count: int = 1) -> bool:  # noqa: ARG002
        """Accept all addresses; errors are handled in get/setValues."""
        return True

    def getValues(self, func_code: int, address: int, count: int = 1) -> list[int] | list[bool]:
        """Read values from the DataProvider."""
        try:
            if func_code in (1, 2, 5, 15):
                return self._get_coils(address, count)
            return self._get_registers(address, count)
        except Exception:
            return []

    def setValues(
        self, func_code: int, address: int, values: list[int] | list[bool]
    ) -> ExcCodes | None:
        """Write values to the DataProvider."""
        try:
            if func_code in (5, 15):
                return self._set_coils(address, values)
            if func_code == 6:
                return self._set_single_register(address, values[0])
            # FC 16
            return self._set_registers(address, values)
        except Exception:
            return ExcCodes.DEVICE_FAILURE

    # --- Coil helpers ---

    def _get_coils(self, address: int, count: int) -> list[bool]:
        result: list[bool] = []
        for i in range(count):
            mapped = modbus_to_plc(address + i, is_coil=True)
            if mapped is None:
                result.append(False)
            else:
                bank, index = mapped
                plc_addr = _format_plc_address(bank, index)
                val = self.provider.read(plc_addr)
                result.append(bool(val))
        return result

    def _set_coils(self, address: int, values: list[int] | list[bool]) -> ExcCodes | None:
        for i, val in enumerate(values):
            mapped = modbus_to_plc(address + i, is_coil=True)
            if mapped is None:
                if len(values) == 1:
                    return ExcCodes.ILLEGAL_ADDRESS
                continue  # FC 15: skip gaps silently
            bank, index = mapped
            # Check writability
            if not _is_address_writable(bank, index):
                return ExcCodes.ILLEGAL_ADDRESS
            plc_addr = _format_plc_address(bank, index)
            self.provider.write(plc_addr, bool(val))
        return None

    # --- Register helpers ---

    def _get_registers(self, address: int, count: int) -> list[int]:
        result: list[int] = []
        i = 0
        while i < count:
            reg_addr = address + i
            mapped = modbus_to_plc_register(reg_addr)
            if mapped is None:
                result.append(0)
                i += 1
                continue

            bank, index, reg_position = mapped
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

    def _set_single_register(self, address: int, value: int) -> ExcCodes | None:
        """Handle FC 06: write single register."""
        mapped = modbus_to_plc_register(address)
        if mapped is None:
            return ExcCodes.ILLEGAL_ADDRESS

        bank, index, reg_position = mapped
        mapping = MODBUS_MAPPINGS[bank]

        # Check writability
        if not _is_address_writable(bank, index):
            return ExcCodes.ILLEGAL_ADDRESS

        plc_addr = _format_plc_address(bank, index)
        data_type = BANKS[bank].data_type

        # Handle TXT
        if bank == "TXT":
            low_byte = value & 0xFF
            high_byte = (value >> 8) & 0xFF
            txt_base_index = (index - 1) // 2 * 2 + 1
            low_addr = _format_plc_address("TXT", txt_base_index)
            high_addr = _format_plc_address("TXT", txt_base_index + 1)
            self.provider.write(low_addr, chr(low_byte))
            self.provider.write(high_addr, chr(high_byte))
            return None

        if mapping.width == 1:
            unpacked = unpack_value([value], data_type)
            self.provider.write(plc_addr, unpacked)
        else:
            # Width-2: read-modify-write
            current = self.provider.read(plc_addr)
            current_regs = pack_value(current, data_type)
            current_regs[reg_position] = value
            unpacked = unpack_value(current_regs, data_type)
            self.provider.write(plc_addr, unpacked)
        return None

    def _set_registers(self, address: int, values: list[int] | list[bool]) -> ExcCodes | None:
        """Handle FC 16: write multiple registers."""
        i = 0
        while i < len(values):
            reg_addr = address + i
            mapped = modbus_to_plc_register(reg_addr)
            if mapped is None:
                return ExcCodes.ILLEGAL_ADDRESS

            bank, index, reg_position = mapped
            mapping = MODBUS_MAPPINGS[bank]

            # Check writability
            if not _is_address_writable(bank, index):
                return ExcCodes.ILLEGAL_ADDRESS

            plc_addr = _format_plc_address(bank, index)
            data_type = BANKS[bank].data_type

            # Handle TXT
            if bank == "TXT":
                reg_val = int(values[i])
                low_byte = reg_val & 0xFF
                high_byte = (reg_val >> 8) & 0xFF
                txt_base_index = (index - 1) // 2 * 2 + 1
                low_addr = _format_plc_address("TXT", txt_base_index)
                high_addr = _format_plc_address("TXT", txt_base_index + 1)
                self.provider.write(low_addr, chr(low_byte))
                self.provider.write(high_addr, chr(high_byte))
                i += 1
                continue

            if mapping.width == 1:
                unpacked = unpack_value([int(values[i])], data_type)
                self.provider.write(plc_addr, unpacked)
                i += 1
            else:
                # Width-2
                if reg_position == 0 and i + 1 < len(values):
                    # Complete pair
                    regs = [int(values[i]), int(values[i + 1])]
                    unpacked = unpack_value(regs, data_type)
                    self.provider.write(plc_addr, unpacked)
                    i += 2
                else:
                    # Partial: read-modify-write
                    current = self.provider.read(plc_addr)
                    current_regs = pack_value(current, data_type)
                    current_regs[reg_position] = int(values[i])
                    unpacked = unpack_value(current_regs, data_type)
                    self.provider.write(plc_addr, unpacked)
                    i += 1
        return None


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
        self.provider = provider
        self.host = host
        self.port = port
        self._server: ModbusTcpServer | None = None

    async def start(self) -> None:
        """Start the Modbus TCP server."""
        context = _ClickDeviceContext(self.provider)
        server_context = ModbusServerContext(devices=context, single=True)
        self._server = ModbusTcpServer(
            context=server_context,
            address=(self.host, self.port),
        )
        await self._server.serve_forever(background=True)

    async def stop(self) -> None:
        """Stop the server gracefully."""
        if self._server is not None:
            await self._server.shutdown()
            self._server = None

    async def serve_forever(self) -> None:
        """Start the server and block until stopped."""
        context = _ClickDeviceContext(self.provider)
        server_context = ModbusServerContext(devices=context, single=True)
        self._server = ModbusTcpServer(
            context=server_context,
            address=(self.host, self.port),
        )
        await self._server.serve_forever(background=False)

    async def __aenter__(self) -> ClickServer:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.stop()
