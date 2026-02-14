"""Async Modbus TCP client driver for AutomationDirect CLICK PLCs.

Provides ClickClient with bank accessors, address interface, and tag interface.
"""

from __future__ import annotations

from collections.abc import Coroutine, Iterator, Mapping
from typing import Any, ClassVar, Generic, Literal, TypeAlias, TypeVar, cast, overload

from pymodbus.client import AsyncModbusTcpClient

from .addresses import format_address_display, normalize_address, parse_address
from .banks import BANKS
from .modbus import (
    MODBUS_MAPPINGS,
    pack_value,
    plc_to_modbus,
    unpack_value,
)
from .nicknames import DATA_TYPE_CODE_TO_STR, read_csv
from .validation import assert_runtime_value

PlcValue = bool | int | float | str
TValue_co = TypeVar("TValue_co", bound=PlcValue, covariant=True)

BoolBankName: TypeAlias = Literal["X", "Y", "C", "T", "CT", "SC"]
IntBankName: TypeAlias = Literal["DS", "DD", "DH", "TD", "CTD", "SD", "XD", "YD"]
FloatBankName: TypeAlias = Literal["DF"]
StrBankName: TypeAlias = Literal["TXT"]

BoolBankAttr: TypeAlias = Literal["x", "X", "y", "Y", "c", "C", "t", "T", "ct", "CT", "sc", "SC"]
IntBankAttr: TypeAlias = Literal[
    "ds",
    "DS",
    "dd",
    "DD",
    "dh",
    "DH",
    "td",
    "TD",
    "ctd",
    "CTD",
    "sd",
    "SD",
    "xd",
    "XD",
    "yd",
    "YD",
]
FloatBankAttr: TypeAlias = Literal["df", "DF"]
StrBankAttr: TypeAlias = Literal["txt", "TXT"]

# ==============================================================================
# ModbusResponse
# ==============================================================================


class ModbusResponse(Mapping[str, TValue_co], Generic[TValue_co]):
    """Immutable mapping with normalized PLC address keys.

    Keys are stored in canonical uppercase form (``DS1``, ``X001``).
    Look-ups normalise the key automatically, so ``response["ds1"]``
    and ``response["DS1"]`` both work.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, TValue_co]) -> None:
        self._data = data

    # -- Mapping interface --------------------------------------------------

    def __getitem__(self, key: str) -> TValue_co:
        normalized = normalize_address(key)
        if normalized is not None and normalized in self._data:
            return self._data[normalized]
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        normalized = normalize_address(key)
        return normalized is not None and normalized in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    # -- Comparison ---------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ModbusResponse):
            return self._data == other._data
        if isinstance(other, dict):
            if len(other) != len(self._data):
                return False
            normalized: dict[str, object] = {}
            for k, v in other.items():
                nk = normalize_address(k) if isinstance(k, str) else None
                if nk is None:
                    return False
                normalized[nk] = v
            return self._data == normalized
        return NotImplemented

    def __repr__(self) -> str:
        return f"ModbusResponse({self._data!r})"


# ==============================================================================
# Constants
# ==============================================================================

# Map bank name -> data type string for validation
_DATA_TYPE_STR: dict[str, str] = {
    "X": "bool",
    "Y": "bool",
    "C": "bool",
    "T": "bool",
    "CT": "bool",
    "SC": "bool",
    "DS": "int16",
    "DD": "int32",
    "DH": "hex",
    "DF": "float",
    "TXT": "str",
    "TD": "int16",
    "CTD": "int32",
    "SD": "int16",
    "XD": "hex",
    "YD": "hex",
}

# ==============================================================================
# Tag loading
# ==============================================================================


def _load_tags(filepath: str) -> dict[str, dict[str, str]]:
    """Load tags from nicknames CSV using nicknames.read_csv."""
    records = read_csv(filepath)
    tags: dict[str, dict[str, str]] = {}
    for r in records.values():
        if r.nickname and not r.nickname.startswith("_"):
            tags[r.nickname] = {
                "address": r.display_address,
                "type": DATA_TYPE_CODE_TO_STR.get(r.data_type, ""),
                "comment": r.comment,
            }
    # Sort by address
    return dict(sorted(tags.items(), key=lambda item: item[1]["address"]))


# ==============================================================================
# AddressAccessor
# ==============================================================================


def _format_bank_address(bank: str, index: int) -> str:
    """Format address string for return dicts."""
    return format_address_display(bank, index)


class AddressAccessor(Generic[TValue_co]):
    """Provides read/write access to a specific PLC memory bank."""

    def __init__(self, plc: ClickClient, bank: str) -> None:
        self._plc = plc
        self._bank = bank
        self._mapping = MODBUS_MAPPINGS[bank]
        self._bank_cfg = BANKS[bank]

    async def read(self, start: int, end: int | None = None) -> ModbusResponse[TValue_co]:
        """Read single value or range (inclusive).

        Always returns a ModbusResponse, even for a single address.
        Use ``await plc.ds[1]`` for a bare value.
        """
        bank = self._bank

        if end is None:
            # Single value → wrap in ModbusResponse
            value = await self._read_single(start)
            key = _format_bank_address(bank, start)
            return ModbusResponse({key: value})

        if end <= start:
            raise ValueError("End address must be greater than start address.")

        # Range read
        if bank == "TXT":
            return await self._read_txt_range(start, end)
        if self._bank_cfg.valid_ranges is not None:
            return await self._read_sparse_range(start, end)
        return await self._read_range(start, end)

    async def _read_single(self, index: int) -> TValue_co:
        """Read a single PLC address."""
        bank = self._bank
        self._validate_index(index)

        if bank == "TXT":
            return cast(TValue_co, await self._read_txt(index))

        if self._mapping.is_coil:
            addr, _ = plc_to_modbus(bank, index)
            result = await self._plc._read_coils(addr, 1, bank)
            return cast(TValue_co, result[0])

        addr, count = plc_to_modbus(bank, index)
        regs = await self._plc._read_registers(addr, count, bank)
        return cast(TValue_co, unpack_value(regs, self._bank_cfg.data_type))

    async def _read_range(self, start: int, end: int) -> ModbusResponse[TValue_co]:
        """Read a contiguous range."""
        bank = self._bank
        self._validate_index(start)
        self._validate_index(end)
        result: dict[str, TValue_co] = {}

        if self._mapping.is_coil:
            addr_start, _ = plc_to_modbus(bank, start)
            addr_end, _ = plc_to_modbus(bank, end)
            count = addr_end - addr_start + 1
            bits = await self._plc._read_coils(addr_start, count, bank)
            for i, idx in enumerate(range(start, end + 1)):
                key = _format_bank_address(bank, idx)
                result[key] = cast(TValue_co, bits[i])
        else:
            addr_start, _ = plc_to_modbus(bank, start)
            addr_end, count_last = plc_to_modbus(bank, end)
            total_regs = (addr_end + count_last) - addr_start
            regs = await self._plc._read_registers(addr_start, total_regs, bank)
            width = self._mapping.width
            data_type = self._bank_cfg.data_type
            for i, idx in enumerate(range(start, end + 1)):
                offset = i * width
                val = unpack_value(regs[offset : offset + width], data_type)
                key = _format_bank_address(bank, idx)
                result[key] = cast(TValue_co, val)

        return ModbusResponse(result)

    async def _read_sparse_range(self, start: int, end: int) -> ModbusResponse[TValue_co]:
        """Read a sparse (X/Y) range, skipping gaps."""
        bank = self._bank
        # Enumerate valid addresses in [start, end]
        valid_addrs: list[int] = []
        ranges = self._bank_cfg.valid_ranges
        assert ranges is not None
        for lo, hi in ranges:
            for a in range(max(lo, start), min(hi, end) + 1):
                valid_addrs.append(a)

        if not valid_addrs:
            raise ValueError(f"No valid {bank} addresses in range {start}-{end}")

        # Read the full coil span
        addr_first, _ = plc_to_modbus(bank, valid_addrs[0])
        addr_last, _ = plc_to_modbus(bank, valid_addrs[-1])
        count = addr_last - addr_first + 1
        bits = await self._plc._read_coils(addr_first, count, bank)

        result: dict[str, TValue_co] = {}
        for a in valid_addrs:
            addr, _ = plc_to_modbus(bank, a)
            bit_idx = addr - addr_first
            key = _format_bank_address(bank, a)
            result[key] = cast(TValue_co, bits[bit_idx])

        return ModbusResponse(result)

    async def _read_txt(self, index: int) -> str:
        """Read a single TXT address."""
        # TXT packs 2 chars per register: odd index = low byte, even = high byte
        reg_index = (index - 1) // 2
        reg_addr = MODBUS_MAPPINGS["TXT"].base + reg_index
        regs = await self._plc._read_registers(reg_addr, 1, "TXT")
        reg_val = regs[0]
        if index % 2 == 1:
            # Odd: low byte
            return chr(reg_val & 0xFF)
        else:
            # Even: high byte
            return chr((reg_val >> 8) & 0xFF)

    async def _read_txt_range(self, start: int, end: int) -> ModbusResponse[TValue_co]:
        """Read a range of TXT addresses."""
        self._validate_index(start)
        self._validate_index(end)
        # Compute register range
        first_reg = (start - 1) // 2
        last_reg = (end - 1) // 2
        reg_base = MODBUS_MAPPINGS["TXT"].base
        regs = await self._plc._read_registers(
            reg_base + first_reg, last_reg - first_reg + 1, "TXT"
        )

        result: dict[str, TValue_co] = {}
        for idx in range(start, end + 1):
            reg_offset = (idx - 1) // 2 - first_reg
            reg_val = regs[reg_offset]
            if idx % 2 == 1:
                ch = chr(reg_val & 0xFF)
            else:
                ch = chr((reg_val >> 8) & 0xFF)
            result[_format_bank_address("TXT", idx)] = cast(TValue_co, ch)

        return ModbusResponse(result)

    async def write(
        self,
        start: int,
        data: bool | int | float | str | list[bool] | list[int] | list[float] | list[str],
    ) -> None:
        """Write single value or list of consecutive values."""
        if isinstance(data, list):
            await self._write_list(start, data)
        else:
            await self._write_single(start, data)

    async def _write_single(self, index: int, value: bool | int | float | str) -> None:
        """Write a single value."""
        bank = self._bank
        self._validate_index(index)
        self._validate_writable(index)
        self._validate_value(index, value)

        if bank == "TXT":
            await self._write_txt(index, str(value))
            return

        if self._mapping.is_coil:
            addr, _ = plc_to_modbus(bank, index)
            await self._plc._write_coils(addr, [bool(value)])
            return

        addr, count = plc_to_modbus(bank, index)
        regs = pack_value(value, self._bank_cfg.data_type)
        await self._plc._write_registers(addr, regs)

    async def _write_list(self, start: int, values: list) -> None:
        """Write a list of consecutive values."""
        bank = self._bank

        if bank == "TXT":
            # Write TXT as string chars
            for i, v in enumerate(values):
                idx = start + i
                self._validate_index(idx)
                self._validate_writable(idx)
                self._validate_value(idx, v)
                await self._write_txt(idx, str(v))
            return

        # Validate all addresses and values first
        for i, v in enumerate(values):
            idx = start + i
            self._validate_index(idx)
            self._validate_writable(idx)
            self._validate_value(idx, v)

        if self._mapping.is_coil:
            if self._bank_cfg.valid_ranges is not None:
                await self._write_sparse_coils(start, values)
            else:
                addr, _ = plc_to_modbus(bank, start)
                await self._plc._write_coils(addr, [bool(v) for v in values])
        else:
            addr, _ = plc_to_modbus(bank, start)
            data_type = self._bank_cfg.data_type
            all_regs: list[int] = []
            for v in values:
                all_regs.extend(pack_value(v, data_type))
            await self._plc._write_registers(addr, all_regs)

    async def _write_sparse_coils(self, start: int, values: list) -> None:
        """Write coils over a sparse (X/Y) range, padding gaps with False."""
        bank = self._bank
        ranges = self._bank_cfg.valid_ranges
        assert ranges is not None

        # Build list of valid addresses
        end_index = start + len(values) - 1
        valid_addrs: list[int] = []
        for lo, hi in ranges:
            for a in range(max(lo, start), min(hi, end_index) + 1):
                valid_addrs.append(a)

        if not valid_addrs:
            return

        # Map values to valid addresses
        value_map = dict(zip(valid_addrs, [bool(v) for v in values], strict=False))

        addr_first, _ = plc_to_modbus(bank, valid_addrs[0])
        addr_last, _ = plc_to_modbus(bank, valid_addrs[-1])
        total_coils = addr_last - addr_first + 1

        # Build coil data with False padding for gaps
        coil_data: list[bool] = []
        for i in range(total_coils):
            coil_addr = addr_first + i
            from .modbus import modbus_to_plc

            mapped = modbus_to_plc(coil_addr, is_coil=True)
            if mapped is not None and mapped[1] in value_map:
                coil_data.append(value_map[mapped[1]])
            else:
                coil_data.append(False)

        await self._plc._write_coils(addr_first, coil_data)

    async def _write_txt(self, index: int, char: str) -> None:
        """Write a single TXT character, preserving the twin byte."""
        reg_index = (index - 1) // 2
        reg_addr = MODBUS_MAPPINGS["TXT"].base + reg_index

        # Read current register to preserve the other byte
        regs = await self._plc._read_registers(reg_addr, 1, "TXT")
        reg_val = regs[0]
        byte_val = ord(char) & 0xFF if char else 0

        if index % 2 == 1:
            # Odd: low byte
            new_val = (reg_val & 0xFF00) | byte_val
        else:
            # Even: high byte
            new_val = (reg_val & 0x00FF) | (byte_val << 8)

        await self._plc._write_registers(reg_addr, [new_val])

    def _validate_index(self, index: int) -> None:
        """Validate address index for this bank."""
        bank = self._bank
        cfg = self._bank_cfg
        if cfg.valid_ranges is not None:
            if not any(lo <= index <= hi for lo, hi in cfg.valid_ranges):
                raise ValueError(f"{bank} address must be *01-*16.")
        else:
            if index < cfg.min_addr or index > cfg.max_addr:
                raise ValueError(f"{bank} must be in [{cfg.min_addr}, {cfg.max_addr}]")

    def _validate_writable(self, index: int) -> None:
        """Validate that the address is writable."""
        mapping = self._mapping
        if mapping.writable is not None:
            # Bank has a specific writable subset (SC, SD)
            if index not in mapping.writable:
                raise ValueError(f"{self._bank}{index} is not writable.")
        elif not mapping.is_writable:
            raise ValueError(f"{self._bank}{index} is not writable.")

    def _validate_value(self, index: int, value: bool | int | float | str) -> None:
        """Validate runtime write value for this bank and index."""
        assert_runtime_value(self._bank_cfg.data_type, value, bank=self._bank, index=index)

    def __repr__(self) -> str:
        return f"<AddressAccessor({self._bank}, max={self._bank_cfg.max_addr})>"

    def __getitem__(self, key: int) -> Coroutine[Any, Any, TValue_co]:
        """Enable ``await plc.ds[1]`` syntax for single-value reads."""
        if isinstance(key, slice):
            raise TypeError("Slicing is not supported. Use read(start, end) for range reads.")
        return self._read_single(key)


# ==============================================================================
# AddressInterface
# ==============================================================================


class AddressInterface:
    """String-based access to raw PLC addresses."""

    def __init__(self, plc: ClickClient) -> None:
        self._plc = plc

    async def read(self, address: str) -> ModbusResponse[PlcValue]:
        """Read by address string. Supports 'df1' or 'df1-df10'."""
        if "-" in address:
            parts = address.split("-", 1)
            bank1, start = parse_address(parts[0])
            bank2, end = parse_address(parts[1])
            if bank1 != bank2:
                raise ValueError("Inter-bank ranges are unsupported.")
            if end <= start:
                raise ValueError("End address must be greater than start address.")
            accessor = self._plc._get_accessor(bank1)
            return await accessor.read(start, end)

        bank, index = parse_address(address)
        accessor = self._plc._get_accessor(bank)
        return await accessor.read(index)

    async def write(
        self,
        address: str,
        data: bool | int | float | str | list,
    ) -> None:
        """Write by address string."""
        bank, index = parse_address(address)
        accessor = self._plc._get_accessor(bank)
        await accessor.write(index, data)


# ==============================================================================
# TagInterface
# ==============================================================================


class TagInterface:
    """Access PLC values via tag nicknames."""

    def __init__(self, plc: ClickClient) -> None:
        self._plc = plc

    async def read(self, tag_name: str | None = None) -> dict[str, PlcValue] | PlcValue:
        """Read single tag or all tags."""
        tags = self._plc.tags
        if tag_name is not None:
            if tag_name not in tags:
                available = list(tags.keys())[:5]
                raise KeyError(f"Tag '{tag_name}' not found. Available: {available}")
            tag_info = tags[tag_name]
            resp = await self._plc.addr.read(tag_info["address"])
            # Single-address read → extract the lone value
            return next(iter(resp.values()))

        if not tags:
            raise ValueError("No tags loaded. Provide a tag file or specify a tag name.")

        all_tags: dict[str, PlcValue] = {}
        for name, info in tags.items():
            resp = await self._plc.addr.read(info["address"])
            all_tags[name] = next(iter(resp.values()))
        return all_tags

    async def write(
        self,
        tag_name: str,
        data: bool | int | float | str | list,
    ) -> None:
        """Write value by tag name."""
        tags = self._plc.tags
        if tag_name not in tags:
            available = list(tags.keys())[:5]
            raise KeyError(f"Tag '{tag_name}' not found. Available: {available}")
        tag_info = tags[tag_name]
        await self._plc.addr.write(tag_info["address"], data)

    def read_all(self) -> dict[str, dict[str, str]]:
        """Return a copy of all tag definitions (synchronous)."""
        return dict(self._plc.tags)


# ==============================================================================
# ClickClient
# ==============================================================================


class ClickClient:
    """Async Modbus TCP driver for CLICK PLCs."""

    data_types: ClassVar[dict[str, str]] = _DATA_TYPE_STR

    def __init__(
        self,
        host: str,
        port: int = 502,
        tag_filepath: str = "",
        timeout: int = 1,
        device_id: int = 1,
    ) -> None:
        # Backwards compatibility for legacy "host:port" first argument.
        if ":" in host and port == 502:
            host, port_str = host.rsplit(":", 1)
            port = int(port_str)

        if not (1 <= port <= 65535):
            raise ValueError("port must be in [1, 65535]")
        if not (0 <= device_id <= 247):
            raise ValueError("device_id must be in [0, 247]")

        self._client = AsyncModbusTcpClient(host, port=port, timeout=timeout)
        self._device_id = device_id
        self._accessors: dict[str, AddressAccessor[PlcValue]] = {}
        self.tags: dict[str, dict[str, str]] = {}
        self.addr = AddressInterface(self)
        self.tag = TagInterface(self)

        if tag_filepath:
            self.tags = _load_tags(tag_filepath)

    async def _call_modbus(self, method: Any, /, **kwargs: Any) -> Any:
        """Call pymodbus methods with device_id, falling back to legacy slave."""
        try:
            return await method(device_id=self._device_id, **kwargs)
        except TypeError as exc:
            if "device_id" not in str(exc):
                raise
            return await method(slave=self._device_id, **kwargs)

    @overload
    def _get_accessor(self, bank: BoolBankName) -> AddressAccessor[bool]: ...

    @overload
    def _get_accessor(self, bank: IntBankName) -> AddressAccessor[int]: ...

    @overload
    def _get_accessor(self, bank: FloatBankName) -> AddressAccessor[float]: ...

    @overload
    def _get_accessor(self, bank: StrBankName) -> AddressAccessor[str]: ...

    @overload
    def _get_accessor(self, bank: str) -> AddressAccessor[PlcValue]: ...

    def _get_accessor(self, bank: str) -> AddressAccessor[PlcValue]:
        """Get or create an AddressAccessor for a bank."""
        bank_upper = bank.upper()
        if bank_upper not in MODBUS_MAPPINGS:
            raise AttributeError(f"'{bank}' is not a supported address type.")
        if bank_upper not in self._accessors:
            self._accessors[bank_upper] = cast(
                AddressAccessor[PlcValue], AddressAccessor(self, bank_upper)
            )
        return self._accessors[bank_upper]

    @overload
    def __getattr__(self, name: BoolBankAttr) -> AddressAccessor[bool]: ...

    @overload
    def __getattr__(self, name: IntBankAttr) -> AddressAccessor[int]: ...

    @overload
    def __getattr__(self, name: FloatBankAttr) -> AddressAccessor[float]: ...

    @overload
    def __getattr__(self, name: StrBankAttr) -> AddressAccessor[str]: ...

    def __getattr__(self, name: str) -> AddressAccessor[PlcValue]:
        if name.startswith("_"):
            raise AttributeError(name)
        upper = name.upper()
        if upper not in MODBUS_MAPPINGS:
            raise AttributeError(f"'{name}' is not a supported address type.")
        return self._get_accessor(upper)

    async def __aenter__(self) -> ClickClient:
        await self._client.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        self._client.close()

    # --- Internal Modbus wrappers ---

    async def _read_coils(self, address: int, count: int, bank: str) -> list[bool]:
        """Read coils using appropriate function code."""
        mapping = MODBUS_MAPPINGS[bank]
        if 2 in mapping.function_codes:
            result = await self._call_modbus(
                self._client.read_discrete_inputs, address=address, count=count
            )
        else:
            result = await self._call_modbus(self._client.read_coils, address=address, count=count)
        if result.isError():
            raise OSError(f"Modbus read error at coil {address}: {result}")
        return list(result.bits[:count])

    async def _write_coils(self, address: int, values: list[bool]) -> None:
        """Write coils."""
        if len(values) == 1:
            result = await self._call_modbus(
                self._client.write_coil, address=address, value=values[0]
            )
        else:
            result = await self._call_modbus(
                self._client.write_coils, address=address, values=values
            )
        if result.isError():
            raise OSError(f"Modbus write error at coil {address}: {result}")

    async def _read_registers(self, address: int, count: int, bank: str) -> list[int]:
        """Read registers using appropriate function code."""
        mapping = MODBUS_MAPPINGS[bank]
        if 4 in mapping.function_codes:
            result = await self._call_modbus(
                self._client.read_input_registers, address=address, count=count
            )
        else:
            result = await self._call_modbus(
                self._client.read_holding_registers, address=address, count=count
            )
        if result.isError():
            raise OSError(f"Modbus read error at register {address}: {result}")
        return list(result.registers[:count])

    async def _write_registers(self, address: int, values: list[int]) -> None:
        """Write registers."""
        if len(values) == 1:
            result = await self._call_modbus(
                self._client.write_register, address=address, value=values[0]
            )
        else:
            result = await self._call_modbus(
                self._client.write_registers, address=address, values=values
            )
        if result.isError():
            raise OSError(f"Modbus write error at register {address}: {result}")
