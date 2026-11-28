"""Modbus TCP server simulating an AutomationDirect CLICK PLC.

The server maps each incoming Modbus request back to a PLC address and passes it to a
user-supplied DataProvider.
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

from ._cp1252 import txt_byte_to_char
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

__all__ = [
    "PlcValue",
    "DataProvider",
    "MemoryDataProvider",
    "ServerClientInfo",
    "ClickServer",
]

# ==============================================================================
# DataProvider Protocol
# ==============================================================================

PlcValue = bool | int | float | str
"""A value that a `DataProvider` reads or writes."""


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
        """Return the value at *address*. This method calls ``read``."""
        return self.read(address)

    def set(self, address: str, value: PlcValue) -> None:
        """Set *address* to *value*. This method calls ``write``."""
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
    """Return True for an XD or YD register that has no address name (MDB 3, 5, ..., 15).

    XDn is at MDB 2n, so each odd register above XD0u has no name. A CLICK stores what a client
    writes to such a register, but the value drives no X or Y. This module calls such a register
    a spare word. If you format one as an address, you get the address of the register before it.
    """
    return bank in ("XD", "YD") and index >= 3 and index % 2 == 1


# The function codes that a CLICK answers from its memory. The context refuses any other code
# with exception 01. A C2-03CPU in RUN was observed to refuse FC 7, FC 8 sub-function 0,
# FC 11, 12, 20, 24 and FC 43 MEI type 14 the same way. It answered FC 17 (report server id)
# with `11 09 00 ff 00 08 00 c6 03 c0 00`. FF is the run indicator. 00 c6 is 198, the module
# ID of the C2-03CPU in _module_catalog. No one knows what the other bytes mean. The
# maintainer chose to keep exception 01 for FC 17.
_CLICK_FUNCTION_CODES = frozenset({1, 2, 3, 4, 5, 6, 15, 16})

# Modbus exception codes.
_ILLEGAL_FUNCTION = 0x01
_ILLEGAL_ADDRESS = 0x02
_ILLEGAL_VALUE = 0x03
_DEVICE_FAILURE = 0x04

# A pending write. It pairs a target with the value to write there. The target is either a
# PLC address, which the provider stores, or an int Modbus address, which the server stores
# itself. An int target is a spare word (see _is_unnamed_word) or a gap coil. A gap coil is a
# coil between X or Y slots that no address names. _plan_coils and _plan_registers build a
# list of pending writes, called a plan, and _commit writes it.
_Store = tuple[str | int, PlcValue]

# The register after XD8 and the register after YD8. No address names them. A read returns 0
# and a write is refused.
_PAST_XD_YD = frozenset(
    MODBUS_MAPPINGS[bank].base + BANKS[bank].max_addr + 1 for bank in ("XD", "YD")
)


@dataclass(frozen=True)
class _ServerMemory:
    """The values that the server stores itself. A DataProvider never sees them.

    ``words`` and ``coils`` map a Modbus address to what a client wrote to an unnamed YD
    register or to an X or Y gap coil. No PLC address names them. ``nan_words`` maps the PLC
    address of each DF that a client wrote as a NaN to the two registers that the client wrote.

    A NaN that passes through a Python float can come back with different bits. Python 3.11 to
    3.13 and 3.15 set the quiet bit of a signalling NaN. Python 3.14 leaves it as it is. So while
    the provider still returns that NaN, the server answers a read with the registers that the
    client wrote.

    Where Python sets the quiet bit, two NaNs that differ only in that bit become the same
    Python float. If the provider's value changes from one to the other, the server can't tell.
    It answers with the registers that the client wrote.
    """

    words: dict[int, int] = field(default_factory=dict)
    coils: dict[int, bool] = field(default_factory=dict)
    nan_words: dict[str, tuple[int, int]] = field(default_factory=dict)


def _same_float(value: PlcValue, other: float) -> bool:
    """Return True if ``value`` is a float with the same bits as ``other``, NaN payload included."""
    return isinstance(value, float) and struct.pack("<d", value) == struct.pack("<d", other)


def _unpack(fmt: str, data: bytes) -> tuple[int, ...] | None:
    """Return the fixed fields at the start of a request, or None if the request is too short."""
    if len(data) < struct.calcsize(fmt):
        return None
    return struct.unpack_from(fmt, data)


# ==============================================================================
# Requests
# ==============================================================================


def _exception(function_code: int, code: int) -> bytes:
    """Return an exception response: the function code with its high bit set, then the code."""
    return bytes([function_code | 0x80, code])


def _pack_bits(bits: list[bool]) -> bytes:
    """Pack bits into bytes. The first bit goes in the low bit of the first byte."""
    packed = bytearray((len(bits) + 7) // 8)
    for i, bit in enumerate(bits):
        if bit:
            packed[i // 8] |= 1 << (i % 8)
    return bytes(packed)


def _read(context: _ClickDeviceContext, function_code: int, data: bytes) -> bytes:
    """Answer FC 1 to 4 by reading ``count`` coils or registers from ``address``."""
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
    """Answer FC 05. A value other than 0x0000 or 0xFF00 gets exception 03 and stores nothing.

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
    """Answer FC 06. The answer echoes the request."""
    fields = _unpack(">HH", data)
    if fields is None:
        return _exception(function_code, _ILLEGAL_VALUE)
    address, value = fields
    if (rc := context.setValues(6, address, [value])) is not None:
        return _exception(function_code, rc)
    return struct.pack(">BHH", function_code, address, value)


def _write_coils(context: _ClickDeviceContext, function_code: int, data: bytes) -> bytes:
    """Answer FC 15. If the byte count disagrees with the count or with the data, the answer is
    exception 03.

    The context answers 03 for a count outside 1 to 1968. Both checks run before anything is
    stored, so a bad request stores nothing.
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
    """Answer FC 16. If the byte count disagrees with the count or with the data, the answer is
    exception 03.

    The context answers 03 for a count outside 1 to 123. Both checks run before anything is
    stored, so a bad request stores nothing.
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
    """Return the response PDU for a request PDU (function code, then data). Never raises.

    A request that is too short for its function code, or that has a bad value, gets an
    exception response. An error that nothing else caught gets exception 04.
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

    When ``getValues`` or ``setValues`` refuses a request, it returns a Modbus exception code
    as an ``int``.
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

        A refused request leaves the provider unchanged. The server checks every target and
        reads every old value before it writes anything. If a provider ``write`` raises
        partway through, the server writes the old values back. If the provider's ``read``
        raises for an address in the request, the whole request fails with exception 04.
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
        """Write a checked plan. Return None, or exception 04 if a provider ``write`` raises.

        After a provider ``write`` raises, write the old values back. An int target in the
        plan is a gap coil if ``coils`` is set, and a spare word otherwise.
        ``df_words`` holds the two registers that each DF in the plan will hold.
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
        """Return the registers for a value that the provider holds.

        If a DF still holds the NaN that a client wrote, return the registers as written.
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
                # A read of a gap between X or Y slots returns what a client wrote there, or
                # OFF if none did. A read of an address outside every bank is refused.
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
                # The server stores a write to a gap between X or Y slots itself. A later read
                # returns the value.
                plan.append((address + i, bool(val)))
                continue
            bank, index = mapped
            # MODBUS_MAPPINGS makes X read only, but a client may write an X input too. Whatever
            # drives the inputs may overwrite the value later.
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
                # pack_value raises for a value that is not one character of the table.
                # getValues then answers exception 04, the same as for a bad value in another bank.
                low_byte = pack_value(self.provider.read(low_addr), DataType.TXT)[0]
                high_byte = pack_value(self.provider.read(high_addr), DataType.TXT)[0]
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
        """Return the plan for a register write, or an exception code if the write is refused.

        This method writes nothing. It puts the two registers that each DF will hold in
        ``df_words``.
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
                plan.append(
                    (_format_plc_address("TXT", txt_base_index), txt_byte_to_char(reg_val & 0xFF))
                )
                plan.append(
                    (_format_plc_address("TXT", txt_base_index + 1), txt_byte_to_char(reg_val >> 8))
                )
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
                # The client wrote one register of a two-register value. Keep the other
                # register as it is stored.
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
# The shortest frame is a function code and no data. The longest well-formed request is FC15 or
# FC16 with a byte count of 255. It holds the unit id, function code, address, count, byte count
# and 255 data bytes. A write that is too large for a CLICK but no longer than this gets
# exception 03. A frame with a length outside these bounds closes the connection.
_MIN_LENGTH = 2
_MAX_LENGTH = 262
# How long a closing connection may take to send its pending answers before the server drops it.
_CLOSE_TIMEOUT = 1.0
# How many ports start() tries for port 0 on a host with several addresses.
_PORT_ATTEMPTS = 5
# The errors that mean another socket holds the port. Windows returns 10013 for a port it
# reserves.
_PORT_TAKEN = frozenset({errno.EADDRINUSE, errno.EACCES, getattr(errno, "WSAEACCES", errno.EACCES)})
# How many connections may wait to be accepted. asyncio's create_server allows the same.
_BACKLOG = 100
# Set SO_REUSEADDR on POSIX only, as asyncio's create_server does. It lets a port whose closed
# connections wait in TIME_WAIT be listened on again. On Windows it would let two sockets share
# a port.
_REUSE_ADDRESS = os.name == "posix" and sys.platform != "cygwin"
# The errors that mean the system is out of sockets or memory for the moment. After one of
# them, the server waits _ACCEPT_RETRY_DELAY seconds and then accepts again. asyncio does the
# same.
_OUT_OF_RESOURCES = frozenset(
    {
        errno.EMFILE,
        errno.ENFILE,
        errno.ENOBUFS,
        errno.ENOMEM,
        # Windows returns 10024 when a process has no more sockets.
        getattr(errno, "WSAEMFILE", errno.EMFILE),
    }
)
_ACCEPT_RETRY_DELAY = 1.0


def _format_peer(transport: asyncio.BaseTransport | None) -> str:
    """Return a connection's peer as ``host:port``."""
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
    """Return True if the loop can watch the socket for reading.

    Selector loops can. asyncio's Proactor loop can't.
    """
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
        # shut() stops watching a socket before it closes it. So a closed socket has no reader to
        # remove.
        if sock.fileno() != -1:
            loop.remove_reader(sock)


class _Connection(asyncio.Protocol):
    """Serves one client: reads Modbus TCP frames and answers each in the order received.

    A frame may arrive in pieces, or several frames may arrive in one read. A frame whose
    protocol id is not 0 is not Modbus. The connection drops it without an answer and goes on
    to the next frame. If the length field is outside 2 to 262, there is no way to find the
    next frame, so the connection closes.
    """

    def __init__(self, listener: _Listener, client_id: str, sock: socket.socket) -> None:
        self.listener = listener
        self.client_id = client_id
        # The accepted socket. If the event loop closes before this connection does, the
        # listener's abandon() closes the socket.
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
        # If the listener shut while asyncio was making this connection, close the connection.
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
        # asyncio calls this when the answers waiting to go to the client fill the write buffer.
        # That happens when a client sends requests and does not read the answers. The server
        # then stops reading from the client and stops answering it until the buffer drains. So
        # the server never buffers more than one read of the client's requests.
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
            # The length field alone says where a frame ends, whatever the function code.
            end = 6 + length
            if len(buffer) < end:
                return
            pdu = bytes(buffer[_MBAP.size : end])
            del buffer[:end]
            if protocol_id != 0:
                continue
            response = _answer(self.listener.context, pdu)
            # A CLICK answers every unit id. The response echoes the unit id and the transaction
            # id.
            header = _MBAP.pack(transaction_id, 0, len(response) + 1, unit_id)
            transport.write(header + response)

    def close(self) -> None:
        """Close the connection, and drop it if it has not closed within _CLOSE_TIMEOUT."""
        self._buffer.clear()
        if self.transport is None or self.lost.done():
            return
        self.transport.close()
        if self._abort_timer is None:
            # If the client does not read, its answers stay in the write buffer, and the
            # transport's close() waits to send them. So this timer aborts the connection after
            # _CLOSE_TIMEOUT seconds.
            self._abort_timer = self.lost.get_loop().call_later(_CLOSE_TIMEOUT, self.abort)

    def abort(self) -> None:
        if self.transport is not None:
            self.transport.abort()


class _Listener:
    """Owns the listening sockets of a ClickServer, the tasks that accept their clients, and the
    connections.

    A listener opens once and shuts once. ``start()`` makes a new listener rather than open an
    old one again. ``shut()`` never awaits. So the listener is shut even if something cancels
    the code that called ``shut()``. ``wait_closed()`` changes nothing. It only waits.

    A client is in ``accepted`` from the moment it is accepted until its connection is made. So
    ``shut()`` and ``abandon()`` can close a client at any stage of making its connection.
    """

    port: int

    def __init__(self, context: _ClickDeviceContext, client_ids: Iterator[int]) -> None:
        self.context = context
        self.connections: dict[str, _Connection] = {}
        # Maps each accepted client socket to its _Connection. The value is None until
        # connect_accepted_socket creates the connection. connection_made removes the entry.
        self.accepted: dict[socket.socket, _Connection | None] = {}
        self.sockets: list[socket.socket] = []
        self.attached = False
        self.closed = False
        # Resolves when start() has finished with this listener, whether or not it is listening.
        self.opened: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._client_ids = client_ids
        # One task for each listening socket, accepting its clients one after another.
        self._serving: list[asyncio.Task[None]] = []
        # On a loop that can't watch sockets, each of those tasks waits on a loop.sock_accept
        # task. This set holds those accept tasks. An accept task stays here until the task that
        # waits on it has taken its result.
        self._accepting: set[asyncio.Task[tuple[socket.socket, Any]]] = set()

    def _new_connection(self, client: socket.socket) -> _Connection:
        connection = _Connection(self, str(next(self._client_ids)), client)
        self.accepted[client] = connection
        return connection

    def open_connections(self) -> list[_Connection]:
        return [connection for connection in self.connections.values() if connection.is_open]

    def attach(self, sockets: list[socket.socket]) -> bool:
        """Accept clients on the sockets that start() bound.

        If the listener has shut, close the sockets and return False.
        """
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

        If an accept fails, as it does for a client that reset before it was accepted, the
        loop skips it and the socket goes on listening.
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
        """Accept a client on a loop that can watch sockets, and return it.

        The client goes into ``accepted`` as soon as it is accepted.
        """
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
        """Accept a client through ``loop.sock_accept`` and return it, or None if cancelled."""
        accepting = loop.create_task(loop.sock_accept(sock))
        self._accepting.add(accepting)
        # The accept task's first step is already scheduled, so _watch runs right after it, in
        # the same iteration of the event loop.
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
        """Pass the client of an accept task to ``_take`` as soon as the accept completes.

        The accept task waits on a future. When that future completes, its result holds the
        client socket until the task wakes up and takes it. If the task is cancelled in between,
        the client socket is lost and never closed. On the Proactor loop this happens when an
        accept completes in the same iteration of the event loop as a stop() or a cancel. So
        this method adds a callback to the future. The Proactor loop completes the future
        while it polls for I/O. asyncio queues the future's callbacks with ``call_soon``, and
        the loop runs them later in the same iteration. The loop stops only after an iteration
        ends, so the callback runs even if stop() was called.
        """
        if accepting.done():
            self._took(accepting)
            return
        # asyncio has no public way to get the future that a task awaits.
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
        """Add a client that was just accepted to ``accepted``.

        If the listener has shut, close the client instead.
        """
        if self.closed:
            client.close()
        else:
            self.accepted.setdefault(client, None)

    async def _connect(self, client: socket.socket) -> None:
        """Make the connection for an accepted client.

        Close the client instead if the listener has shut or the connection can't be made.
        """
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
        """Stop listening and close every connection, without waiting.

        A second call does nothing. Each connection that has not closed after _CLOSE_TIMEOUT
        is dropped.
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
        # Close each accepted client that has no connection yet. A client whose connection is
        # being made is closed in connection_made, which sees that the listener has shut.
        for client, connection in list(self.accepted.items()):
            if connection is None:
                del self.accepted[client]
                client.close()
        loop = self.opened.get_loop()
        for sock in self.sockets:
            if sock.fileno() != -1:
                # On a selector loop, stop watching the socket before closing it. Do not leave
                # that to the cancelled accept, which runs later. Other loops have no readers.
                with contextlib.suppress(NotImplementedError):
                    loop.remove_reader(sock)
            sock.close()

    def abandon(self) -> None:
        """Close the sockets of a listener whose event loop has closed.

        This method does not call into the closed loop.
        """
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
        # If the caller is cancelled, asyncio.wait does not cancel the futures that it waits on.
        await asyncio.wait([self.opened])
        tasks = [*self._serving, *self._accepting]
        if tasks:
            await asyncio.wait(tasks, timeout=2 * _CLOSE_TIMEOUT)
        pending = [connection.lost for connection in self.connections.values()]
        if pending:
            await asyncio.wait(pending, timeout=2 * _CLOSE_TIMEOUT)


class _Run:
    """One run of a ClickServer, from a start() to the stop() that ends it.

    If start() replaces a listener that stopped listening on its own, the run continues.
    ``ended`` resolves to None when the run was stopped. It resolves to the error when start()
    could not listen again.
    """

    def __init__(self, listener: _Listener) -> None:
        self.listener = listener
        self.ended: asyncio.Future[BaseException | None] = (
            asyncio.get_running_loop().create_future()
        )

    def loop_closed(self) -> bool:
        """Return True once the event loop that the run started on has closed."""
        return self.ended.get_loop().is_closed()


def _free_port(addresses: list[tuple[Any, ...]]) -> int | None:
    """Bind a socket to port 0 and return the port the system gave it.

    Use the first address in ``addresses`` where a socket can be made and bound. ``addresses``
    are ``getaddrinfo`` results. Return None when no address works, as for ``::1`` on a host
    with IPv6 turned off.
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
    """Return the reason that a bind failed, in the words that create_server uses on this Python.

    Before Python 3.12.5, create_server uses only the error's ``strerror``. From 3.12.5 on, it
    uses the whole error, including the errno.
    """
    if sys.version_info >= (3, 12, 5):
        return str(exc).lower()
    return (exc.strerror or str(exc)).lower()


def _bind(addresses: list[tuple[Any, ...]], port: int) -> list[socket.socket]:
    """Bind a non-blocking socket to each address on ``port``, as asyncio's create_server does.

    ``addresses`` are ``getaddrinfo`` results. The function skips an address where a socket
    can't be made, and an address that the host does not have (EADDRNOTAVAIL). On any other
    error it closes every socket it made.

    Raises:
        OSError: An address could not be bound, or the function skipped every address.
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
        # The server's only lifecycle state. No change to it spans an await. So a cancel, or
        # another call that runs during an await, never sees a change half made.
        self._run: _Run | None = None
        self._memory = _ServerMemory()
        # Client ids count up across runs, so an old id never names a newer client.
        self._client_ids = itertools.count(1)

    @property
    def _server(self) -> _Listener | None:
        """Return the current run's listener once it has its sockets, or None."""
        run = self._run
        if run is None or not run.listener.attached or run.loop_closed():
            return None
        return run.listener

    @property
    def bound_port(self) -> int | None:
        """Return the port the server listens on, or None when it is not listening.

        It is None whenever ``is_running()`` returns False.
        """
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
        """Disconnect the client with this ``client_id``.

        Return True if that client was connected, and False otherwise.
        """
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

        The method awaits nothing once the first socket is made. So a cancel can't leave
        behind a socket that nothing will close.
        """
        loop = asyncio.get_running_loop()
        host = self.host or None
        # Resolve the host in a task of its own. create_server does the same. Awaiting a task
        # always yields to the event loop, so other calls get to run before start() binds.
        found = await loop.create_task(
            loop.getaddrinfo(host, self.port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE)
        )
        if not found:
            raise OSError(f"getaddrinfo({host!r}) returned empty list")
        addresses = list(dict.fromkeys(found))
        if self.port != 0 or len({(address[0], address[4][0]) for address in addresses}) < 2:
            return _bind(addresses, self.port)
        # Binding each address to port 0 would give each address a different port. So ask the
        # system for a free port on the first address that can be bound, and then listen on
        # that port on every address.
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
        """Return the current run, or None.

        If the run's event loop has closed, drop the run and close its sockets without calling
        into that loop. This happens when a server started in one asyncio.run() is never
        stopped.

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
            raise RuntimeError("ClickServer is running on another event loop. Stop it there.")
        return run

    def _end(self, run: _Run, reason: BaseException | None) -> None:
        """End a run. Clear ``self._run`` if it still holds the run, and shut the run's listener.

        This never waits. ``ended`` is resolved first, so serve_forever() returns even if
        closing the listener raises.
        """
        if not run.ended.done():
            run.ended.set_result(reason)
        if self._run is run:
            self._run = None
        run.listener.shut()

    async def start(self) -> None:
        """Start the Modbus TCP server.

        If the server stopped listening on its own (``is_running()`` returns False although you
        did not call ``stop()``), ``start()`` closes the old listener and its clients, then
        listens again. If you cancel ``start()`` before it returns, the server stays stopped.
        If you call ``stop()`` while ``start()`` is still running, ``start()`` returns without
        listening.

        Raises:
            RuntimeError: The server is already listening, can't listen on its host and port,
                or runs on another event loop.
        """
        await self._start()

    async def _start(self) -> _Run:
        while (run := self._current_run()) is not None:
            listener = run.listener
            if not listener.opened.done():
                # Another start() is opening this listener. Wait for it, then check the result.
                await asyncio.wait([listener.opened])
                if self._run is not run and run.ended.done() and run.ended.result() is None:
                    # A stop() ended the run while this call waited. That stop() applies to this
                    # call too, so return without listening.
                    return run
                continue
            if listener.is_listening():
                raise RuntimeError("ClickServer is already running")
            break  # It stopped listening on its own. Replace it and keep the run.
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
                # Nothing is awaited between making the sockets and attaching them. So a
                # cancel can't leave behind sockets that nothing will close.
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

        If you cancel ``stop()``, the server has still stopped. A client that has not closed
        after 1 s is dropped. If you call ``stop()`` while ``start()`` is running, the server
        stops what that ``start()`` opens.

        Raises:
            RuntimeError: The server runs on another event loop. Stop it on that loop.
        """
        run = self._current_run()
        if run is None:
            return
        listener = run.listener
        self._end(run, None)
        await listener.wait_closed()

    async def serve_forever(self) -> None:
        """Start the server and block until ``stop()``.

        If the server stopped listening on its own and ``start()`` replaces the listener, this
        call keeps serving. If you cancel this call, the server stops.

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
