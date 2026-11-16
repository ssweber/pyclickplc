"""Modbus TCP server simulating an AutomationDirect CLICK PLC.

Incoming Modbus requests are reverse-mapped to PLC addresses and
routed to a user-supplied DataProvider.
"""

from __future__ import annotations

import asyncio
import errno
import itertools
import socket
import struct
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast, runtime_checkable

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


# The function codes a CLICK answers from its memory; the context refuses any other with 01.
_CLICK_FUNCTION_CODES = frozenset({1, 2, 3, 4, 5, 6, 15, 16})

# Modbus exception codes.
_ILLEGAL_FUNCTION = 0x01
_ILLEGAL_ADDRESS = 0x02
_ILLEGAL_VALUE = 0x03
_DEVICE_FAILURE = 0x04

# A store is a provider address and its value, or a spare word's Modbus address and its value.
_Store = tuple[str | int, PlcValue]


def _unpack(fmt: str, data: bytes) -> tuple[int, ...] | None:
    """Unpack the fixed fields at the start of a request, or None if it is too short."""
    if len(data) < struct.calcsize(fmt):
        return None
    return struct.unpack_from(fmt, data)


# ==============================================================================
# Requests
# ==============================================================================


def _exception(function_code: int, code: int) -> bytes:
    """An exception response: the function code with its high bit set, then the code."""
    return bytes([function_code | 0x80, code])


def _pack_bits(bits: list[bool]) -> bytes:
    """Pack bits into bytes, the first bit in the low bit of the first byte."""
    packed = bytearray((len(bits) + 7) // 8)
    for i, bit in enumerate(bits):
        if bit:
            packed[i // 8] |= 1 << (i % 8)
    return bytes(packed)


def _read(context: _ClickDeviceContext, function_code: int, data: bytes) -> bytes:
    """FC 1 to 4: read ``count`` coils or registers from ``address``."""
    fields = _unpack(">HH", data)
    if fields is None:
        return _exception(function_code, _ILLEGAL_VALUE)
    address, count = fields
    values = context.getValues(function_code, address, count)
    if isinstance(values, int):
        return _exception(function_code, values)
    if function_code in (1, 2):
        payload = _pack_bits(cast("list[bool]", values))
    else:
        payload = struct.pack(f">{len(values)}H", *values)
    return bytes([function_code, len(payload)]) + payload


def _write_coil(context: _ClickDeviceContext, function_code: int, data: bytes) -> bytes:
    """FC 05. A value other than 0x0000 or 0xFF00 gets exception 03 and stores nothing.

    The answer holds the value read back after the write.
    """
    fields = _unpack(">HH", data)
    if fields is None or fields[1] not in (0x0000, 0xFF00):
        return _exception(function_code, _ILLEGAL_VALUE)
    address, value = fields
    if (rc := context.setValues(5, address, [value == 0xFF00])) is not None:
        return _exception(function_code, rc)
    values = context.getValues(5, address, 1)
    if isinstance(values, int):
        return _exception(function_code, values)
    return struct.pack(">BHH", function_code, address, 0xFF00 if values[0] else 0x0000)


def _write_register(context: _ClickDeviceContext, function_code: int, data: bytes) -> bytes:
    """FC 06. The answer holds the value read back after the write."""
    fields = _unpack(">HH", data)
    if fields is None:
        return _exception(function_code, _ILLEGAL_VALUE)
    address, value = fields
    if (rc := context.setValues(6, address, [value])) is not None:
        return _exception(function_code, rc)
    values = context.getValues(6, address, 1)
    if isinstance(values, int):
        return _exception(function_code, values)
    return struct.pack(">BHH", function_code, address, values[0])


def _write_coils(context: _ClickDeviceContext, function_code: int, data: bytes) -> bytes:
    """FC 15. A byte count that disagrees with the count or with the data gets exception 03.

    The context refuses a count outside 1 to 1968 with 03, so every bad request stores nothing.
    """
    fields = _unpack(">HHB", data)
    if fields is None:
        return _exception(function_code, _ILLEGAL_VALUE)
    address, count, byte_count = fields
    payload = data[5:]
    if byte_count != (count + 7) // 8 or len(payload) != byte_count:
        return _exception(function_code, _ILLEGAL_VALUE)
    values = [bool(payload[i // 8] >> (i % 8) & 1) for i in range(count)]
    if (rc := context.setValues(15, address, values)) is not None:
        return _exception(function_code, rc)
    return struct.pack(">BHH", function_code, address, count)


def _write_registers(context: _ClickDeviceContext, function_code: int, data: bytes) -> bytes:
    """FC 16. A byte count that disagrees with the count or with the data gets exception 03.

    The context refuses a count outside 1 to 123 with 03, so every bad request stores nothing.
    """
    fields = _unpack(">HHB", data)
    if fields is None:
        return _exception(function_code, _ILLEGAL_VALUE)
    address, count, byte_count = fields
    payload = data[5:]
    if byte_count != 2 * count or len(payload) != byte_count:
        return _exception(function_code, _ILLEGAL_VALUE)
    values = list(struct.unpack(f">{count}H", payload))
    if (rc := context.setValues(16, address, values)) is not None:
        return _exception(function_code, rc)
    return struct.pack(">BHH", function_code, address, count)


_Handler = Callable[["_ClickDeviceContext", int, bytes], bytes]

# One handler for each of _CLICK_FUNCTION_CODES. Every other code gets exception 01.
_HANDLERS: dict[int, _Handler] = {
    1: _read,
    2: _read,
    3: _read,
    4: _read,
    5: _write_coil,
    6: _write_register,
    15: _write_coils,
    16: _write_registers,
}


def _answer(context: _ClickDeviceContext, pdu: bytes) -> bytes:
    """The response PDU for a request PDU (function code, then data). Never raises.

    A request too short for its function code, or with a bad value, gets an exception
    response, and so does an error nothing else caught (exception 04).
    """
    function_code = pdu[0]
    handler = _HANDLERS.get(function_code)
    if handler is None:
        return _exception(function_code, _ILLEGAL_FUNCTION)
    try:
        return handler(context, function_code, pdu[1:])
    except Exception:
        return _exception(function_code, _DEVICE_FAILURE)


class _ClickDeviceContext:
    """Routes Modbus requests to a DataProvider.

    ``getValues`` and ``setValues`` give a Modbus exception code as an ``int`` when they
    refuse a request.
    """

    def __init__(self, provider: DataProvider, spare_words: dict[int, int] | None = None) -> None:
        self.provider = provider
        # The unnamed YD registers keep what a client writes to them, by Modbus address.
        self.spare_words: dict[int, int] = {} if spare_words is None else spare_words

    def getValues(
        self, func_code: int, address: int, count: int = 1
    ) -> list[int] | list[bool] | int:
        """Read values from the DataProvider."""
        if func_code not in _CLICK_FUNCTION_CODES:
            return _ILLEGAL_FUNCTION
        if func_code in (1, 2) and not 1 <= count <= MAX_READ_COILS:
            return _ILLEGAL_VALUE
        if func_code in (3, 4) and not 1 <= count <= MAX_READ_REGISTERS:
            return _ILLEGAL_VALUE
        try:
            if func_code in (1, 2, 5, 15):
                return self._get_coils(address, count)
            return self._get_registers(address, count)
        except Exception:
            return _DEVICE_FAILURE

    def setValues(self, func_code: int, address: int, values: list[int] | list[bool]) -> int | None:
        """Write values to the DataProvider.

        A refused request leaves the provider unchanged. Every target is checked and read
        first, so the provider can put the old values back. A provider whose ``read`` raises
        for an address in the request fails the whole request with exception 04.
        """
        if func_code not in _CLICK_FUNCTION_CODES:
            return _ILLEGAL_FUNCTION
        try:
            if func_code in (5, 15):
                plan = self._plan_coils(address, values)
            elif func_code == 6:
                plan = self._plan_registers(address, [values[0]])
            else:
                plan = self._plan_registers(address, values)
            if isinstance(plan, int):
                return plan
            return self._commit(plan)
        except Exception:
            return _DEVICE_FAILURE

    def _commit(self, plan: list[_Store]) -> int | None:
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
            return _DEVICE_FAILURE
        for reg_addr, value in plan:
            if isinstance(reg_addr, int):
                self.spare_words[reg_addr] = int(value)
        return None

    # --- Coil helpers ---

    def _get_coils(self, address: int, count: int) -> list[bool] | int:
        result: list[bool] = []
        for i in range(count):
            mapped = modbus_to_plc(address + i, is_coil=True)
            if mapped is None:
                # A CLICK reads a gap between X or Y slots as OFF and refuses the rest.
                if not _in_sparse_coil_span(address + i):
                    return _ILLEGAL_ADDRESS
                result.append(False)
            else:
                bank, index = mapped
                plc_addr = _format_plc_address(bank, index)
                val = self.provider.read(plc_addr)
                result.append(bool(val))
        return result

    def _plan_coils(self, address: int, values: list[int] | list[bool]) -> list[_Store] | int:
        if not 1 <= len(values) <= MAX_WRITE_COILS:
            return _ILLEGAL_VALUE
        plan: list[_Store] = []
        for i, val in enumerate(values):
            mapped = modbus_to_plc(address + i, is_coil=True)
            if mapped is None:
                if len(values) == 1 or not _in_sparse_coil_span(address + i):
                    return _ILLEGAL_ADDRESS
                continue  # FC 15 skips a gap between X or Y slots.
            bank, index = mapped
            if not _is_address_writable(bank, index):
                return _ILLEGAL_ADDRESS
            plan.append((_format_plc_address(bank, index), bool(val)))
        return plan

    # --- Register helpers ---

    def _get_registers(self, address: int, count: int) -> list[int] | int:
        result: list[int] = []
        i = 0
        while i < count:
            reg_addr = address + i
            mapped = modbus_to_plc_register(reg_addr)
            if mapped is None:
                return _ILLEGAL_ADDRESS

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

    def _plan_registers(self, address: int, values: list[int] | list[bool]) -> list[_Store] | int:
        """Resolve a register write into (address, value) stores without storing any."""
        if not 1 <= len(values) <= MAX_WRITE_REGISTERS:
            return _ILLEGAL_VALUE
        plan: list[_Store] = []
        i = 0
        while i < len(values):
            mapped = modbus_to_plc_register(address + i)
            if mapped is None:
                return _ILLEGAL_ADDRESS

            bank, index, reg_position = mapped
            mapping = MODBUS_MAPPINGS[bank]
            if not _is_address_writable(bank, index):
                return _ILLEGAL_ADDRESS

            plc_addr = _format_plc_address(bank, index)
            data_type = BANKS[bank].data_type
            reg_val = int(values[i])
            if not 0 <= reg_val <= 0xFFFF:
                return _ILLEGAL_VALUE

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
                    return _ILLEGAL_VALUE
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
                return _ILLEGAL_VALUE
        return plan


# ==============================================================================
# Connections
# ==============================================================================

# The Modbus TCP (MBAP) header: transaction id, protocol id, length and unit id. The length
# counts the unit id and the PDU after it.
_MBAP = struct.Struct(">HHHB")
# The shortest frame holds a function code and no data. The longest well-formed request is
# FC15 or FC16 with a one-byte byte count of 255: unit id, function code, address, count, byte
# count and 255 data bytes. Up to there, a write too large for a CLICK gets exception 03.
_MIN_LENGTH = 2
_MAX_LENGTH = 262
# How long a closed connection may take to send what it holds before it is dropped.
_CLOSE_TIMEOUT = 1.0
# How many ports start() tries for port 0 on a host with several addresses.
_PORT_ATTEMPTS = 5
# The errors that mean another socket holds the port; Windows gives 10013 for a port it reserves.
_PORT_TAKEN = frozenset({errno.EADDRINUSE, errno.EACCES, getattr(errno, "WSAEACCES", errno.EACCES)})


def _format_peer(transport: asyncio.BaseTransport | None) -> str:
    """A connection's peer as ``host:port``."""
    if transport is None:
        return "unknown"
    peer = transport.get_extra_info("peername")
    if isinstance(peer, tuple) and len(peer) >= 2:
        return f"{peer[0]}:{peer[1]}"
    if peer:
        return str(peer)
    return "unknown"


class _Connection(asyncio.Protocol):
    """One client: reads Modbus TCP frames and answers each in the order received.

    A frame may arrive in pieces, or with others in one read. A frame whose protocol id is
    not 0 is not Modbus and is dropped unanswered; the frames after it are answered. A length
    field outside 2 to 262 leaves no way to find the next frame, so the connection is closed.
    """

    def __init__(self, listener: _Listener, client_id: str) -> None:
        self.listener = listener
        self.client_id = client_id
        self.transport: asyncio.Transport | None = None
        self.lost: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._buffer = bytearray()
        self._paused = False
        self._abort_timer: asyncio.TimerHandle | None = None

    @property
    def is_open(self) -> bool:
        return self.transport is not None and not self.transport.is_closing()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = cast(asyncio.Transport, transport)
        self.listener.connections[self.client_id] = self
        # On Windows, an accept that completes after the listener shut still makes a connection.
        if self.listener.closed:
            self.close()

    def connection_lost(self, exc: Exception | None) -> None:
        self._buffer.clear()
        if self._abort_timer is not None:
            self._abort_timer.cancel()
        self.listener.connections.pop(self.client_id, None)
        if not self.lost.done():
            self.lost.set_result(None)

    def pause_writing(self) -> None:
        # A client that sends requests without reading the answers is neither read nor
        # answered until it reads, so the server holds one read of requests at most.
        self._paused = True
        if self.transport is not None:
            self.transport.pause_reading()

    def resume_writing(self) -> None:
        self._paused = False
        if self.transport is not None:
            self.transport.resume_reading()
        self._answer_frames()

    def data_received(self, data: bytes) -> None:
        if not self.is_open:
            return
        self._buffer += data
        self._answer_frames()

    def _answer_frames(self) -> None:
        """Answer each whole frame in the buffer, until writing pauses or the connection closes."""
        buffer = self._buffer
        while not self._paused and len(buffer) >= _MBAP.size:
            transport = self.transport
            if transport is None or transport.is_closing():
                return
            transaction_id, protocol_id, length, unit_id = _MBAP.unpack_from(buffer)
            if not _MIN_LENGTH <= length <= _MAX_LENGTH:
                self.close()
                return
            # Only the length ends a frame; pymodbus took 9 bytes for length 2 if 9 had arrived.
            end = 6 + length
            if len(buffer) < end:
                return
            pdu = bytes(buffer[_MBAP.size : end])
            del buffer[:end]
            if protocol_id != 0:
                continue
            response = _answer(self.listener.context, pdu)
            # A CLICK answers every unit id; the response echoes it and the transaction id.
            header = _MBAP.pack(transaction_id, 0, len(response) + 1, unit_id)
            transport.write(header + response)

    def close(self) -> None:
        """Close the connection, and drop it if it has not closed within _CLOSE_TIMEOUT."""
        self._buffer.clear()
        if self.transport is None or self.lost.done():
            return
        self.transport.close()
        if self._abort_timer is None:
            # A client that does not read keeps answers waiting, and close() waits for them.
            self._abort_timer = self.lost.get_loop().call_later(_CLOSE_TIMEOUT, self.abort)

    def abort(self) -> None:
        if self.transport is not None:
            self.transport.abort()


class _Listener:
    """The listening sockets of a ClickServer and their connections.

    A listener opens once and shuts once. ``shut()`` never waits, so whatever cancels the
    code that called it, the listener is shut; ``wait_closed()`` only waits.
    """

    # The asyncio.Server. Named ``transport`` because pyrung reads the bound port through
    # ``ClickServer._server.transport.sockets``; drop the name once pyrung uses ``bound_port``.
    transport: asyncio.Server
    port: int

    def __init__(self, context: _ClickDeviceContext, client_ids: Iterator[int]) -> None:
        self.context = context
        self.connections: dict[str, _Connection] = {}
        self.attached = False
        self.closed = False
        # Done once start() has finished with this listener, listening or not.
        self.opened: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._client_ids = client_ids

    def new_connection(self) -> _Connection:
        return _Connection(self, str(next(self._client_ids)))

    def open_connections(self) -> list[_Connection]:
        return [connection for connection in self.connections.values() if connection.is_open]

    def attach(self, transport: asyncio.Server) -> bool:
        """Take the asyncio.Server start() made; a shut listener closes it, giving False."""
        if self.closed:
            transport.close()
            return False
        self.transport = transport
        self.attached = True
        self.port = int(transport.sockets[0].getsockname()[1])
        return True

    def is_listening(self) -> bool:
        # On Windows, a client that resets before asyncio has accepted it makes asyncio close
        # the listening socket, while the asyncio.Server still says it is serving.
        return (
            self.attached
            and not self.closed
            and self.transport.is_serving()
            and all(sock.fileno() != -1 for sock in self.transport.sockets)
        )

    def shut(self) -> None:
        """Stop listening and close every connection, without waiting; a second call does
        nothing. Each connection is dropped after _CLOSE_TIMEOUT if it has not closed by then.
        """
        if self.closed:
            return
        self.closed = True
        try:
            if self.attached:
                self.transport.close()
        finally:
            for connection in list(self.connections.values()):
                connection.close()

    def abandon(self) -> None:
        """Close the sockets of a listener whose event loop has closed, without that loop."""
        self.closed = True
        sockets: list[socket.socket] = []
        listening = getattr(self.transport, "_sockets", None) if self.attached else None
        if isinstance(listening, list):
            sockets += listening
            # The asyncio.Server then lists no sockets. Emptied, not set to None as its own
            # close() does: with None, from Python 3.13 each of its transports collected later
            # asks it to wake its waiters again, and the second time asyncio raises.
            listening.clear()
        for connection in self.connections.values():
            sock = getattr(connection.transport, "_sock", None)
            if isinstance(sock, socket.socket):
                sockets.append(sock)
        for sock in sockets:
            sock.close()
        self.connections.clear()

    def finish_opening(self) -> None:
        if not self.opened.done():
            self.opened.set_result(None)

    async def wait_closed(self) -> None:
        """Wait for start() to finish with this listener, then for its connections to close."""
        # asyncio.wait never cancels what it waits on, so a cancelled caller leaves both alone.
        await asyncio.wait([self.opened])
        pending = [connection.lost for connection in self.connections.values()]
        if pending:
            await asyncio.wait(pending, timeout=2 * _CLOSE_TIMEOUT)


class _Run:
    """One run of a ClickServer, from a start() to the stop() that ends it.

    A start() that replaces a listener that stopped listening on its own keeps the run.
    ``ended`` gives None when the run was stopped, or the error that ended it when start()
    could not listen again.
    """

    def __init__(self, listener: _Listener) -> None:
        self.listener = listener
        self.ended: asyncio.Future[BaseException | None] = (
            asyncio.get_running_loop().create_future()
        )

    def loop_closed(self) -> bool:
        """True once the event loop the run started on has closed."""
        return self.ended.get_loop().is_closed()


def _free_port(addresses: list[tuple[Any, ...]]) -> int | None:
    """The port the system gives a socket bound to port 0, on the first address that takes one.

    ``addresses`` are ``getaddrinfo`` results; None when no address takes a socket, as for
    ``::1`` on a host with IPv6 turned off.
    """
    for family, kind, proto, _canonname, sockaddr in addresses:
        try:
            with socket.socket(family, kind, proto) as sock:
                sock.bind(sockaddr)
                return int(sock.getsockname()[1])
        except OSError:
            continue
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
        """Create a ClickServer.

        Args:
            provider: Backend that stores and retrieves PLC values.
            host: Interface to bind (default ``"localhost"``).
            port: Modbus TCP port (default 502). Use 0 to let the system pick a free port,
                then read it from ``bound_port``.
        """
        self.provider = provider
        self.host = host
        self.port = port
        # The only lifecycle state. Every change to it is made before the next await, so a
        # cancel or another call at any await finds it whole.
        self._run: _Run | None = None
        self._spare_words: dict[int, int] = {}
        # Client ids count up across runs, so an old id never names a newer client.
        self._client_ids = itertools.count(1)

    @property
    def _server(self) -> _Listener | None:
        """The current run's listener once it has its sockets, or None."""
        # pyrung reads the bound port through ``_server.transport.sockets``.
        run = self._run
        if run is None or not run.listener.attached or run.loop_closed():
            return None
        return run.listener

    @property
    def bound_port(self) -> int | None:
        """The port the server listens on, or None when it is not listening
        (``is_running()`` gives False)."""
        listener = self._server
        if listener is None or not listener.is_listening():
            return None
        return listener.port

    def is_running(self) -> bool:
        """Return True while the server is listening."""
        listener = self._server
        return listener is not None and listener.is_listening()

    def list_clients(self) -> list[ServerClientInfo]:
        """Return the currently connected Modbus TCP clients."""
        listener = self._server
        if listener is None:
            return []
        return [
            ServerClientInfo(
                client_id=connection.client_id, peer=_format_peer(connection.transport)
            )
            for connection in listener.open_connections()
        ]

    def disconnect_client(self, client_id: str) -> bool:
        """Disconnect one client by its ``client_id``; False if no such client is connected."""
        listener = self._server
        if listener is None:
            return False
        connection = listener.connections.get(client_id)
        if connection is None or not connection.is_open:
            return False
        connection.close()
        return True

    def disconnect_all_clients(self) -> int:
        """Disconnect all connected clients and return how many were closed."""
        listener = self._server
        if listener is None:
            return 0
        connections = listener.open_connections()
        for connection in connections:
            connection.close()
        return len(connections)

    async def _listen(self, protocol_factory: Callable[[], _Connection]) -> asyncio.Server:
        """Listen on every address the host resolves to, all on one port."""
        loop = asyncio.get_running_loop()
        host = self.host or None
        if self.port != 0:
            return await loop.create_server(protocol_factory, host, self.port, start_serving=False)
        addresses = await loop.getaddrinfo(
            host, 0, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
        )
        if len({(address[0], address[4][:2]) for address in addresses}) < 2:
            return await loop.create_server(protocol_factory, host, 0, start_serving=False)
        # Port 0 would give each address its own port, so take the port the system gives the
        # first address that takes one and listen on that port on every address.
        error: OSError | None = None
        for _attempt in range(_PORT_ATTEMPTS):
            port = _free_port(addresses)
            if port is None:
                return await loop.create_server(protocol_factory, host, 0, start_serving=False)
            try:
                return await loop.create_server(protocol_factory, host, port, start_serving=False)
            except OSError as exc:
                if exc.errno not in _PORT_TAKEN:
                    raise
                error = exc
        raise RuntimeError(
            f"Could not listen on {self.host}:0: no port was free on all its addresses ({error})"
        ) from error

    def _current_run(self) -> _Run | None:
        """The run in the slot, or None.

        A run whose event loop has closed, as when a server started in one asyncio.run() is
        never stopped, is dropped and its sockets closed without calling into that loop.

        Raises:
            RuntimeError: The server runs on another event loop that has not closed.
        """
        run = self._run
        if run is None:
            return None
        if run.loop_closed():
            self._run = None
            run.listener.abandon()
            return None
        if run.ended.get_loop() is not asyncio.get_running_loop():
            raise RuntimeError("ClickServer is running on another event loop; stop it there")
        return run

    def _end(self, run: _Run, reason: BaseException | None) -> None:
        """End a run: empty the slot if it still holds the run, and shut its listener.

        Never waits. ``ended`` is resolved first, so serve_forever() returns even if closing
        the listener raises.
        """
        if not run.ended.done():
            run.ended.set_result(reason)
        if self._run is run:
            self._run = None
        run.listener.shut()

    async def start(self) -> None:
        """Start the Modbus TCP server.

        A server that has stopped listening on its own (``is_running()`` gives False before
        ``stop()``) is started again: the old listener and its clients are closed first.
        A ``start()`` cancelled before it returns leaves the server stopped, and one that a
        ``stop()`` overtakes returns without listening.

        Raises:
            RuntimeError: The server is already listening, can't listen on its host and port,
                or runs on another event loop.
        """
        await self._start()

    async def _start(self) -> _Run:
        while (run := self._current_run()) is not None:
            listener = run.listener
            if not listener.opened.done():
                # Another start() is opening this listener; see how it went.
                await asyncio.wait([listener.opened])
                if self._run is not run and run.ended.done() and run.ended.result() is None:
                    # A stop() ended the run while this call waited: it stopped this call too.
                    return run
                continue
            if listener.is_listening():
                raise RuntimeError("ClickServer is already running")
            break  # It stopped listening on its own: replace it, keeping the run.
        new = _Listener(_ClickDeviceContext(self.provider, self._spare_words), self._client_ids)
        old: _Listener | None = None
        if run is None:
            run = self._run = _Run(new)
        else:
            old, run.listener = run.listener, new
        try:
            if old is not None:
                old.shut()
                # Its clients close before the new listener opens, as they would for stop().
                await old.wait_closed()
            if not new.closed:
                # No await between the sockets being made and attached: a cancel can't
                # leave a listener nobody owns.
                transport = await self._listen(new.new_connection)
                if new.attach(transport):
                    await transport.start_serving()
        except BaseException as exc:
            if isinstance(exc, OSError):
                error = RuntimeError(f"Could not listen on {self.host}:{self.port}: {exc}")
                self._end(run, error)
                raise error from exc
            self._end(run, exc)
            raise
        finally:
            new.finish_opening()
        return run

    async def stop(self) -> None:
        """Stop the server, closing every connection.

        A stop() that is cancelled has still stopped the server; a client that has not closed
        after 1 s is dropped. A stop() during a start() stops what that start() opens.

        Raises:
            RuntimeError: The server runs on another event loop; stop it on that loop.
        """
        run = self._current_run()
        if run is None:
            return
        listener = run.listener
        self._end(run, None)
        await listener.wait_closed()

    async def serve_forever(self) -> None:
        """Start the server and block until ``stop()``.

        A ``start()`` that replaces a listener that stopped on its own keeps this call
        serving. Cancelling the call stops the server.

        Raises:
            RuntimeError: The server is already listening, can't listen on its host and port,
                runs on another event loop, or stopped listening on its own and ``start()``
                could not listen again.
        """
        run = await self._start()
        try:
            await asyncio.wait([run.ended])
        except asyncio.CancelledError:
            self._end(run, None)
            await run.listener.wait_closed()
            raise
        await run.listener.wait_closed()
        reason = run.ended.result()
        if reason is not None:
            raise RuntimeError(
                "ClickServer stopped listening and could not listen again"
            ) from reason

    async def __aenter__(self) -> ClickServer:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.stop()
