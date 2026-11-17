"""Modbus TCP server simulating an AutomationDirect CLICK PLC.

Incoming Modbus requests are reverse-mapped to PLC addresses and
routed to a user-supplied DataProvider.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import itertools
import math
import os
import socket
import struct
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
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

# A store is a provider address and its value, or the Modbus address of a spare word or of a
# gap coil and its value.
_Store = tuple[str | int, PlcValue]

# The register after XD8 and the one after YD8. No address names them; a read gives 0 and a
# write is refused.
_PAST_XD_YD = frozenset(
    MODBUS_MAPPINGS[bank].base + BANKS[bank].max_addr + 1 for bank in ("XD", "YD")
)


@dataclass(frozen=True)
class _ServerMemory:
    """What the server keeps itself, so a DataProvider never sees it.

    ``words`` and ``coils`` are the unnamed YD registers and the X and Y gap coils a client
    wrote, by Modbus address; no PLC address names them. ``nan_words`` holds the two registers of
    each DF a client wrote as a NaN, by PLC address. A NaN that goes through a Python float can
    come back with other bits (Python 3.11 to 3.13 and 3.15 set a signalling NaN's quiet bit;
    3.14 keeps it), so the server answers with the registers as written for as long as the
    provider holds that NaN.

    Where Python sets the quiet bit, two NaNs that differ only in that bit give the same Python
    float, so a provider change from one to the other can't be seen, and the registers as
    written win.
    """

    words: dict[int, int] = field(default_factory=dict)
    coils: dict[int, bool] = field(default_factory=dict)
    nan_words: dict[str, tuple[int, int]] = field(default_factory=dict)


def _same_float(value: PlcValue, other: float) -> bool:
    """True if ``value`` is a float with the same bits as ``other``, NaN payload included."""
    return isinstance(value, float) and struct.pack("<d", value) == struct.pack("<d", other)


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

    The answer echoes the request.
    """
    fields = _unpack(">HH", data)
    if fields is None or fields[1] not in (0x0000, 0xFF00):
        return _exception(function_code, _ILLEGAL_VALUE)
    address, value = fields
    if (rc := context.setValues(5, address, [value == 0xFF00])) is not None:
        return _exception(function_code, rc)
    return struct.pack(">BHH", function_code, address, value)


def _write_register(context: _ClickDeviceContext, function_code: int, data: bytes) -> bytes:
    """FC 06. The answer echoes the request."""
    fields = _unpack(">HH", data)
    if fields is None:
        return _exception(function_code, _ILLEGAL_VALUE)
    address, value = fields
    if (rc := context.setValues(6, address, [value])) is not None:
        return _exception(function_code, rc)
    return struct.pack(">BHH", function_code, address, value)


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

    def __init__(self, provider: DataProvider, memory: _ServerMemory | None = None) -> None:
        self.provider = provider
        self.memory = _ServerMemory() if memory is None else memory

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
            df_words: dict[str, tuple[int, int]] = {}
            if func_code in (5, 15):
                plan = self._plan_coils(address, values)
            elif func_code == 6:
                plan = self._plan_registers(address, [values[0]], df_words)
            else:
                plan = self._plan_registers(address, values, df_words)
            if isinstance(plan, int):
                return plan
            return self._commit(plan, coils=func_code in (5, 15), df_words=df_words)
        except Exception:
            return _DEVICE_FAILURE

    def _commit(
        self, plan: list[_Store], *, coils: bool, df_words: dict[str, tuple[int, int]]
    ) -> int | None:
        """Store a checked plan, putting the old values back if the provider fails midway.

        An int address in the plan is a gap coil if ``coils``, else a spare word.
        ``df_words`` holds the two registers written to each DF in the plan.
        """
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
        for modbus_addr, value in plan:
            if not isinstance(modbus_addr, int):
                continue
            if coils:
                self.memory.coils[modbus_addr] = bool(value)
            else:
                self.memory.words[modbus_addr] = int(value)
        for plc_addr, words in df_words.items():
            if math.isnan(cast(float, unpack_value(list(words), DataType.FLOAT))):
                self.memory.nan_words[plc_addr] = words
            else:
                self.memory.nan_words.pop(plc_addr, None)
        return None

    def _read_words(self, plc_addr: str, data_type: DataType) -> list[int]:
        """The registers of a value the provider holds.

        A DF that still holds the NaN a client wrote gives the registers as written.
        """
        value = self.provider.read(plc_addr)
        if data_type == DataType.FLOAT:
            words = self.memory.nan_words.get(plc_addr)
            if words is not None and _same_float(
                value, cast(float, unpack_value(list(words), DataType.FLOAT))
            ):
                return list(words)
        return pack_value(value, data_type)

    # --- Coil helpers ---

    def _get_coils(self, address: int, count: int) -> list[bool] | int:
        result: list[bool] = []
        for i in range(count):
            mapped = modbus_to_plc(address + i, is_coil=True)
            if mapped is None:
                # A gap between X or Y slots reads what a client wrote to it, OFF until then.
                # An address outside every bank is refused.
                if not _in_sparse_coil_span(address + i):
                    return _ILLEGAL_ADDRESS
                result.append(self.memory.coils.get(address + i, False))
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
                if not _in_sparse_coil_span(address + i):
                    return _ILLEGAL_ADDRESS
                # A gap between X or Y slots keeps what a client writes to it.
                plan.append((address + i, bool(val)))
                continue
            bank, index = mapped
            # An X input takes a write too. Whatever drives the inputs may write it again.
            if bank != "X" and not _is_address_writable(bank, index):
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
                if reg_addr not in _PAST_XD_YD:
                    return _ILLEGAL_ADDRESS
                result.append(0)
                i += 1
                continue

            bank, index, reg_position = mapped
            if _is_unnamed_word(bank, index):
                result.append(self.memory.words.get(reg_addr, 0))
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

            data_type = BANKS[bank].data_type
            if data_type == DataType.BIT:
                result.append(int(bool(self.provider.read(plc_addr))))
                i += 1
                continue

            regs = self._read_words(plc_addr, data_type)

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
        self,
        address: int,
        values: list[int] | list[bool],
        df_words: dict[str, tuple[int, int]],
    ) -> list[_Store] | int:
        """Resolve a register write into (address, value) stores without storing any.

        Puts the two registers each DF will hold in ``df_words``.
        """
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
                continue
            if reg_position == 0 and i + 1 < len(values):
                regs = [reg_val, int(values[i + 1])]
                if not 0 <= regs[1] <= 0xFFFF:
                    return _ILLEGAL_VALUE
                i += 2
            else:
                # Half a value: keep the other register as stored.
                regs = self._read_words(plc_addr, data_type)
                regs[reg_position] = reg_val
                i += 1
            plan.append((plc_addr, unpack_value(regs, data_type)))
            if data_type == DataType.FLOAT:
                df_words[plc_addr] = (regs[0], regs[1])

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
# How many connections may wait to be accepted, as asyncio's create_server allows.
_BACKLOG = 100
# As asyncio's create_server: SO_REUSEADDR on POSIX, so a port whose closed connections wait
# in TIME_WAIT can be listened on again. On Windows it would let two sockets share a port.
_REUSE_ADDRESS = os.name == "posix" and sys.platform != "cygwin"
# The errors that mean the system is out of sockets or memory for now; accepting waits, then
# tries again, as asyncio does.
_OUT_OF_RESOURCES = frozenset(
    {
        errno.EMFILE,
        errno.ENFILE,
        errno.ENOBUFS,
        errno.ENOMEM,
        # Windows gives 10024 when a process has no more sockets.
        getattr(errno, "WSAEMFILE", errno.EMFILE),
    }
)
_ACCEPT_RETRY_DELAY = 1.0


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


def _resolve(future: asyncio.Future[None]) -> None:
    if not future.done():
        future.set_result(None)


def _can_watch(loop: asyncio.AbstractEventLoop, sock: socket.socket) -> bool:
    """True if the loop can watch the socket for reading, as selector loops can and asyncio's
    Proactor loop can't."""
    try:
        loop.add_reader(sock, _ignore)
    except NotImplementedError:
        return False
    loop.remove_reader(sock)
    return True


def _ignore() -> None:
    pass


async def _readable(loop: asyncio.AbstractEventLoop, sock: socket.socket) -> None:
    """Wait until a listening socket has a client to accept."""
    ready: asyncio.Future[None] = loop.create_future()
    loop.add_reader(sock, _resolve, ready)
    try:
        await ready
    finally:
        # shut() stops watching a socket before it closes it.
        if sock.fileno() != -1:
            loop.remove_reader(sock)


class _Connection(asyncio.Protocol):
    """One client: reads Modbus TCP frames and answers each in the order received.

    A frame may arrive in pieces, or with others in one read. A frame whose protocol id is
    not 0 is not Modbus and is dropped unanswered; the frames after it are answered. A length
    field outside 2 to 262 leaves no way to find the next frame, so the connection is closed.
    """

    def __init__(self, listener: _Listener, client_id: str, sock: socket.socket) -> None:
        self.listener = listener
        self.client_id = client_id
        # The accepted socket, which the listener closes if the event loop closes first.
        self.sock = sock
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
        self.listener.accepted.pop(self.sock, None)
        self.listener.connections[self.client_id] = self
        # A connection the listener was making when it shut is closed as it arrives.
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
    """The listening sockets of a ClickServer, the tasks that accept their clients, and the
    connections.

    A listener opens once and shuts once. ``shut()`` never waits, so whatever cancels the
    code that called it, the listener is shut; ``wait_closed()`` only waits.

    A client is kept in ``accepted`` from the moment it is accepted until its connection is
    made, so ``shut()`` and ``abandon()`` close it however far its connection had got.
    """

    port: int

    def __init__(self, context: _ClickDeviceContext, client_ids: Iterator[int]) -> None:
        self.context = context
        self.connections: dict[str, _Connection] = {}
        # Each client accepted and not yet connected, with its connection once it is being made.
        self.accepted: dict[socket.socket, _Connection | None] = {}
        self.sockets: list[socket.socket] = []
        self.attached = False
        self.closed = False
        # Done once start() has finished with this listener, listening or not.
        self.opened: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._client_ids = client_ids
        # One task for each listening socket, accepting its clients one after another.
        self._serving: list[asyncio.Task[None]] = []
        # On a loop that can't watch sockets, the accept each of those tasks waits on, kept
        # until the task has taken its result.
        self._accepting: set[asyncio.Task[tuple[socket.socket, Any]]] = set()

    def _new_connection(self, client: socket.socket) -> _Connection:
        connection = _Connection(self, str(next(self._client_ids)), client)
        self.accepted[client] = connection
        return connection

    def open_connections(self) -> list[_Connection]:
        return [connection for connection in self.connections.values() if connection.is_open]

    def attach(self, sockets: list[socket.socket]) -> bool:
        """Take the sockets start() bound and accept clients on them; a shut listener closes
        them, giving False."""
        if self.closed:
            for sock in sockets:
                sock.close()
            return False
        self.sockets = sockets
        self.attached = True
        self.port = int(sockets[0].getsockname()[1])
        loop = asyncio.get_running_loop()
        for sock in sockets:
            sock.listen(_BACKLOG)
            self._serving.append(loop.create_task(self._serve(sock)))
        return True

    def is_listening(self) -> bool:
        return (
            self.attached
            and not self.closed
            and all(sock.fileno() != -1 for sock in self.sockets)
            and not any(task.done() for task in self._serving)
        )

    async def _serve(self, sock: socket.socket) -> None:
        """Accept the clients of one listening socket until the listener shuts.

        A failed accept, as for a client that reset before it was accepted, is passed over;
        the socket goes on listening.
        """
        loop = asyncio.get_running_loop()
        # A loop that can't watch sockets (Proactor) accepts through sock_accept.
        accept = self._accept_when_ready if _can_watch(loop, sock) else self._accept_on_completion
        while not self.closed:
            try:
                client = await accept(loop, sock)
            except OSError as error:
                if self.closed or sock.fileno() == -1:
                    return
                if error.errno in _OUT_OF_RESOURCES:
                    await asyncio.sleep(_ACCEPT_RETRY_DELAY)
                continue
            if client is None:
                return
            await self._connect(client)

    async def _accept_when_ready(
        self, loop: asyncio.AbstractEventLoop, sock: socket.socket
    ) -> socket.socket:
        """Accept a client on a loop that can watch sockets, keeping it as it is accepted."""
        while True:
            try:
                client, _address = sock.accept()
            except (BlockingIOError, InterruptedError):
                await _readable(loop, sock)
            else:
                self._take(client)
                return client

    async def _accept_on_completion(
        self, loop: asyncio.AbstractEventLoop, sock: socket.socket
    ) -> socket.socket | None:
        """Accept a client through ``loop.sock_accept``; None if the accept was cancelled."""
        accepting = loop.create_task(loop.sock_accept(sock))
        self._accepting.add(accepting)
        # Runs right after the accept's first step, in the same loop step.
        loop.call_soon(self._watch, accepting)
        # asyncio.wait leaves the accept alone when this task is cancelled.
        await asyncio.wait([accepting])
        self._accepting.discard(accepting)
        if accepting.cancelled():
            return None
        client, _address = accepting.result()
        self._take(client)
        return client

    def _watch(self, accepting: asyncio.Task[tuple[socket.socket, Any]]) -> None:
        """Keep the client of an accept as soon as the accept has it.

        An accept's task holds its client in the future it awaits until the task wakes, and a
        cancel in between drops the client unclosed. That happens on the Proactor loop to an
        accept that completes in the same loop step as a stop() or a cancel, so the client is
        kept from that future: its callbacks run in the step it completes in, before the loop
        can stop.
        """
        if accepting.done():
            self._took(accepting)
            return
        # asyncio gives no public way to the future a task awaits.
        waiting = getattr(accepting, "_fut_waiter", None)
        if isinstance(waiting, asyncio.Future):
            waiting.add_done_callback(self._took)

    def _took(self, accept: asyncio.Future[Any]) -> None:
        if accept.cancelled() or accept.exception() is not None:
            return
        result = accept.result()
        if isinstance(result, tuple) and result and isinstance(result[0], socket.socket):
            self._take(result[0])

    def _take(self, client: socket.socket) -> None:
        """Keep a client just accepted; a listener that has shut closes it."""
        if self.closed:
            client.close()
        else:
            self.accepted.setdefault(client, None)

    async def _connect(self, client: socket.socket) -> None:
        """Make a connection of an accepted client."""
        if self.closed:
            self.accepted.pop(client, None)
            client.close()
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.connect_accepted_socket(lambda: self._new_connection(client), client)
        except OSError:
            # The client went away before its connection was made.
            self.accepted.pop(client, None)
            client.close()

    def shut(self) -> None:
        """Stop listening and close every connection, without waiting; a second call does
        nothing. Each connection is dropped after _CLOSE_TIMEOUT if it has not closed by then.
        """
        if self.closed:
            return
        self.closed = True
        try:
            self._stop_accepting()
        finally:
            for connection in list(self.connections.values()):
                connection.close()

    def _stop_accepting(self) -> None:
        for accepting in self._accepting:
            accepting.cancel()
        for task in self._serving:
            task.cancel()
        # A client whose connection is being made is closed as the connection is made.
        for client, connection in list(self.accepted.items()):
            if connection is None:
                del self.accepted[client]
                client.close()
        loop = self.opened.get_loop()
        for sock in self.sockets:
            if sock.fileno() != -1:
                # A selector loop stops watching the socket now, before it is closed, rather
                # than once the cancelled accept has run; other loops have no readers.
                with contextlib.suppress(NotImplementedError):
                    loop.remove_reader(sock)
            sock.close()

    def abandon(self) -> None:
        """Close the sockets of a listener whose event loop has closed, without that loop."""
        self.closed = True
        sockets = [*self.sockets, *self.accepted]
        sockets += [connection.sock for connection in self.connections.values()]
        for sock in sockets:
            sock.close()
        self._accepting.clear()
        self.accepted.clear()
        self.connections.clear()

    def finish_opening(self) -> None:
        if not self.opened.done():
            self.opened.set_result(None)

    async def wait_closed(self) -> None:
        """Wait for start() to finish with this listener, then for its accepts to end and its
        connections to close."""
        # asyncio.wait never cancels what it waits on, so a cancelled caller leaves all alone.
        await asyncio.wait([self.opened])
        tasks = [*self._serving, *self._accepting]
        if tasks:
            await asyncio.wait(tasks, timeout=2 * _CLOSE_TIMEOUT)
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


def _reason(exc: OSError) -> str:
    """Why a bind failed, worded as create_server words it on the running Python.

    create_server gives the bare reason before Python 3.12.5 and the whole error, errno
    included, from 3.12.5 on.
    """
    if sys.version_info >= (3, 12, 5):
        return str(exc).lower()
    return (exc.strerror or str(exc)).lower()


def _bind(addresses: list[tuple[Any, ...]], port: int) -> list[socket.socket]:
    """Bind a non-blocking socket to each address on ``port``, as asyncio's create_server does.

    ``addresses`` are ``getaddrinfo`` results. An address that takes no socket, or that the
    host does not have (EADDRNOTAVAIL), is passed over. On any other error every socket made
    is closed.

    Raises:
        OSError: An address could not be bound, or none took a socket.
    """
    sockets: list[socket.socket] = []
    bound = False
    try:
        for family, kind, proto, _canonname, sockaddr in addresses:
            try:
                sock = socket.socket(family, kind, proto)
            except OSError:
                continue
            sockets.append(sock)
            if _REUSE_ADDRESS:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            if family == socket.AF_INET6 and hasattr(socket, "IPPROTO_IPV6"):
                # Listen on IPv6 only, so that a socket for an IPv4 address can share the port.
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, True)
            address = (sockaddr[0], port, *sockaddr[2:])
            try:
                sock.bind(address)
            except OSError as exc:
                if exc.errno == errno.EADDRNOTAVAIL:
                    sockets.pop()
                    sock.close()
                    continue
                raise OSError(
                    exc.errno,
                    f"error while attempting to bind on address {address!r}: {_reason(exc)}",
                ) from None
        if not sockets:
            raise OSError(
                f"could not bind on any address out of {[address[4] for address in addresses]!r}"
            )
        for sock in sockets:
            sock.setblocking(False)
        bound = True
    finally:
        if not bound:
            for sock in sockets:
                sock.close()
    return sockets


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
        self._memory = _ServerMemory()
        # Client ids count up across runs, so an old id never names a newer client.
        self._client_ids = itertools.count(1)

    @property
    def _server(self) -> _Listener | None:
        """The current run's listener once it has its sockets, or None."""
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

    async def _listen(self) -> list[socket.socket]:
        """Bind a socket to every address the host resolves to, all on one port.

        Nothing is awaited once the first socket is made, so a cancel can't leave one unowned.
        """
        loop = asyncio.get_running_loop()
        host = self.host or None
        # Resolved in a task of its own, as create_server does, so start() always lets other
        # calls run before it binds.
        found = await loop.create_task(
            loop.getaddrinfo(host, self.port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE)
        )
        if not found:
            raise OSError(f"getaddrinfo({host!r}) returned empty list")
        addresses = list(dict.fromkeys(found))
        if self.port != 0 or len({(address[0], address[4][0]) for address in addresses}) < 2:
            return _bind(addresses, self.port)
        # Port 0 would give each address its own port, so take the port the system gives the
        # first address that takes one and listen on that port on every address.
        error: OSError | None = None
        for _attempt in range(_PORT_ATTEMPTS):
            port = _free_port(addresses)
            if port is None:
                return _bind(addresses, 0)
            try:
                return _bind(addresses, port)
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
        new = _Listener(_ClickDeviceContext(self.provider, self._memory), self._client_ids)
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
                new.attach(await self._listen())
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
