"""Modbus protocol mapping layer for CLICK PLCs.

Maps PLC addresses to/from Modbus coil/register addresses,
and packs/unpacks Python values into Modbus registers.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .banks import BANKS, DataType

# ==============================================================================
# DataType-derived constants
# ==============================================================================

# Number of Modbus registers per value for each DataType
MODBUS_WIDTH: dict[DataType, int] = {
    DataType.BIT: 1,
    DataType.INT: 1,
    DataType.INT2: 2,
    DataType.FLOAT: 2,
    DataType.HEX: 1,
    DataType.TXT: 1,
}

# Whether the DataType is signed
MODBUS_SIGNED: dict[DataType, bool] = {
    DataType.INT: True,
    DataType.INT2: True,
    DataType.HEX: False,
    DataType.FLOAT: False,
}

# struct format characters for numeric types
STRUCT_FORMATS: dict[DataType, str] = {
    DataType.INT: "h",
    DataType.INT2: "i",
    DataType.FLOAT: "f",
    DataType.HEX: "H",
}

# ==============================================================================
# ModbusMapping
# ==============================================================================


@dataclass(frozen=True)
class ModbusMapping:
    """Modbus address mapping configuration for a PLC memory bank."""

    bank: str
    base: int
    function_codes: frozenset[int]
    is_coil: bool
    width: int = 1
    signed: bool = True
    writable: frozenset[int] | None = None

    @property
    def is_writable(self) -> bool:
        """True if any write FC (5, 6, 15, 16) is in function_codes."""
        return bool(self.function_codes & {5, 6, 15, 16})


# ==============================================================================
# Writable subsets (Modbus-specific, distinct from dataview.py)
# ==============================================================================

# SC: Modbus-writable subset (excludes 50/51 which are ladder-only)
_MODBUS_WRITABLE_SC: frozenset[int] = frozenset({53, 55, 60, 61, 65, 66, 67, 75, 76, 120, 121})

# SD: Modbus-writable subset
_MODBUS_WRITABLE_SD: frozenset[int] = frozenset(
    {
        29,
        31,
        32,
        34,
        35,
        36,
        40,
        41,
        42,
        50,
        51,
        60,
        61,
        106,
        107,
        108,
        112,
        113,
        114,
        140,
        141,
        142,
        143,
        144,
        145,
        146,
        147,
        214,
        215,
    }
)

# ==============================================================================
# MODBUS_MAPPINGS — all 16 banks
# ==============================================================================

MODBUS_MAPPINGS: dict[str, ModbusMapping] = {
    # --- Coil banks ---
    "X": ModbusMapping("X", 0, frozenset({2}), is_coil=True),
    "Y": ModbusMapping("Y", 8192, frozenset({1, 5, 15}), is_coil=True),
    "C": ModbusMapping("C", 16384, frozenset({1, 5, 15}), is_coil=True),
    "T": ModbusMapping("T", 45056, frozenset({2}), is_coil=True),
    "CT": ModbusMapping("CT", 49152, frozenset({2}), is_coil=True),
    "SC": ModbusMapping("SC", 61440, frozenset({2}), is_coil=True, writable=_MODBUS_WRITABLE_SC),
    # --- Register banks ---
    "DS": ModbusMapping("DS", 0, frozenset({3, 6, 16}), is_coil=False, width=1, signed=True),
    "DD": ModbusMapping("DD", 16384, frozenset({3, 6, 16}), is_coil=False, width=2, signed=True),
    "DH": ModbusMapping("DH", 24576, frozenset({3, 6, 16}), is_coil=False, width=1, signed=False),
    "DF": ModbusMapping("DF", 28672, frozenset({3, 6, 16}), is_coil=False, width=2, signed=False),
    "TXT": ModbusMapping("TXT", 36864, frozenset({3, 6, 16}), is_coil=False, width=1, signed=False),
    "TD": ModbusMapping("TD", 45056, frozenset({3, 6, 16}), is_coil=False, width=1, signed=True),
    "CTD": ModbusMapping("CTD", 49152, frozenset({3, 6, 16}), is_coil=False, width=2, signed=True),
    "XD": ModbusMapping("XD", 57344, frozenset({4}), is_coil=False, width=1, signed=False),
    "YD": ModbusMapping("YD", 57856, frozenset({3, 6, 16}), is_coil=False, width=1, signed=False),
    "SD": ModbusMapping(
        "SD",
        61440,
        frozenset({4}),
        is_coil=False,
        width=1,
        signed=False,
        writable=_MODBUS_WRITABLE_SD,
    ),
}

# Split mappings by type for reverse lookups
_COIL_MAPPINGS: list[tuple[str, ModbusMapping]] = [
    (k, v) for k, v in MODBUS_MAPPINGS.items() if v.is_coil
]
_REGISTER_MAPPINGS: list[tuple[str, ModbusMapping]] = [
    (k, v) for k, v in MODBUS_MAPPINGS.items() if not v.is_coil
]

# ==============================================================================
# Sparse coil helpers (private)
# ==============================================================================

# X/Y sparse ranges from BankConfig
_SPARSE_RANGES_OPT = BANKS["X"].valid_ranges
assert _SPARSE_RANGES_OPT is not None
_SPARSE_RANGES: tuple[tuple[int, int], ...] = _SPARSE_RANGES_OPT


def _sparse_plc_to_coil(base: int, index: int) -> int:
    """Forward map sparse PLC index to coil address.

    Uses the formula from CLICKDEVICE_SPEC:
    - CPU slot 1 (001-016): base + index - 1
    - CPU slot 2 (021-036): base + 16 + (index - 21)
    - Expansion (101+):     base + 32 * hundred + (unit - 1)
    """
    if index <= 16:
        return base + index - 1
    if index <= 36:
        return base + 16 + (index - 21)
    hundred = index // 100
    unit = index % 100
    return base + 32 * hundred + (unit - 1)


def _sparse_coil_to_plc(bank: str, base: int, coil: int) -> tuple[str, int] | None:
    """Reverse map coil address to (bank, index) or None for gaps.

    Uses the formula from CLICKSERVER_SPEC:
    - offset < 16:  CPU slot 1 -> *001-*016
    - offset < 32:  CPU slot 2 -> *021-*036
    - else:         expansion  -> hundred*100 + unit
    """
    offset = coil - base
    if offset < 0:
        return None

    if offset < 16:
        return bank, offset + 1
    if offset < 32:
        return bank, 21 + (offset - 16)

    # Expansion slots
    hundred = offset // 32
    unit = (offset % 32) + 1
    if unit > 16:
        return None  # Gap
    index = hundred * 100 + unit
    # Validate against known ranges
    if not any(lo <= index <= hi for lo, hi in _SPARSE_RANGES):
        return None
    return bank, index


# Total coil address space for sparse banks
# Last valid slot is 8xx (hundred=8), max offset = 8*32 + 15 = 271
_SPARSE_COIL_SPAN = 8 * 32 + 16  # 272

# Coil spans for non-sparse banks
_COIL_SPANS: dict[str, int] = {
    "C": BANKS["C"].max_addr,  # 2000
    "T": BANKS["T"].max_addr,  # 500
    "CT": BANKS["CT"].max_addr,  # 250
    "SC": BANKS["SC"].max_addr,  # 1000
}

# ==============================================================================
# Forward mapping: plc_to_modbus
# ==============================================================================


def plc_to_modbus(bank: str, index: int) -> tuple[int, int]:
    """Map PLC address to (modbus_address, register_count).

    Args:
        bank: Bank name (e.g. "X", "DS", "XD")
        index: MDB index (e.g. 1 for X001, 0 for XD0, 2 for XD1)

    Returns:
        Tuple of (modbus_address, register_count)

    Raises:
        ValueError: If bank or index is invalid
    """
    mapping = MODBUS_MAPPINGS.get(bank)
    if mapping is None:
        raise ValueError(f"Unknown bank: {bank!r}")

    if not _is_valid_index(bank, index):
        raise ValueError(f"Invalid address: {bank}{index}")

    if mapping.is_coil:
        bank_cfg = BANKS[bank]
        if bank_cfg.valid_ranges is not None:
            # Sparse coils (X/Y)
            return _sparse_plc_to_coil(mapping.base, index), 1
        # Standard coils
        return mapping.base + (index - 1), 1

    # TXT is packed two chars per register.
    if bank == "TXT":
        return mapping.base + ((index - 1) // 2), 1

    # Registers: 0-based banks (XD/YD) use base + index,
    # 1-based banks use base + width * (index - 1)
    bank_cfg = BANKS[bank]
    if bank_cfg.min_addr == 0:
        return mapping.base + index, 1
    return mapping.base + mapping.width * (index - 1), mapping.width


def _is_valid_index(bank: str, index: int) -> bool:
    """Check if index is valid for the given bank."""
    bank_cfg = BANKS[bank]
    if bank_cfg.valid_ranges is not None:
        return any(lo <= index <= hi for lo, hi in bank_cfg.valid_ranges)
    return bank_cfg.min_addr <= index <= bank_cfg.max_addr


# ==============================================================================
# Reverse mapping: modbus_to_plc
# ==============================================================================


def modbus_to_plc(address: int, is_coil: bool) -> tuple[str, int] | None:
    """Reverse map Modbus address to (bank, display_index) or None.

    Args:
        address: Raw Modbus coil or register address
        is_coil: True for coil address space, False for register space

    Returns:
        Tuple of (bank_name, display_index) or None if unmapped
    """
    if is_coil:
        return _reverse_coil(address)
    return _reverse_register(address)


def _reverse_coil(address: int) -> tuple[str, int] | None:
    """Reverse map a Modbus coil address to (bank, index)."""
    for bank, mapping in _COIL_MAPPINGS:
        bank_cfg = BANKS[bank]
        if bank_cfg.valid_ranges is not None:
            # Sparse bank (X/Y)
            if mapping.base <= address < mapping.base + _SPARSE_COIL_SPAN:
                return _sparse_coil_to_plc(bank, mapping.base, address)
        else:
            span = _COIL_SPANS[bank]
            if mapping.base <= address < mapping.base + span:
                return bank, address - mapping.base + 1
    return None


def _reverse_register(address: int) -> tuple[str, int] | None:
    """Reverse map a Modbus register address to (bank, mdb_index)."""
    for bank, mapping in _REGISTER_MAPPINGS:
        bank_cfg = BANKS[bank]
        max_mdb = bank_cfg.max_addr
        if bank_cfg.min_addr == 0:
            # 0-based banks (XD/YD): contiguous, base + mdb_index
            end = mapping.base + max_mdb + 1
            if mapping.base <= address < end:
                return bank, address - mapping.base
            continue

        if bank == "TXT":
            # TXT packs two addresses per register. Return the odd base index
            # of the pair represented by this register.
            txt_register_count = (max_mdb + 1) // 2
            end = mapping.base + txt_register_count
            if mapping.base <= address < end:
                return bank, (address - mapping.base) * 2 + 1
            continue

        # Standard 1-based register banks
        end = mapping.base + mapping.width * max_mdb
        if mapping.base <= address < end:
            offset = address - mapping.base
            if offset % mapping.width != 0:
                return None  # Mid-value register
            return bank, offset // mapping.width + 1
    return None


def modbus_to_plc_register(address: int) -> tuple[str, int, int] | None:
    """Extended reverse register mapping.

    Unlike modbus_to_plc(is_coil=False), this does NOT return None for
    mid-value registers of width-2 types. Instead it returns the
    reg_position (0 or 1) within the value.

    Needed by the server for FC 06 on width-2 types (read-modify-write).

    Returns:
        (bank, mdb_index, reg_position) or None if unmapped
    """
    for bank, mapping in _REGISTER_MAPPINGS:
        bank_cfg = BANKS[bank]
        max_mdb = bank_cfg.max_addr
        if bank_cfg.min_addr == 0:
            # 0-based banks (XD/YD): contiguous, width=1
            end = mapping.base + max_mdb + 1
            if mapping.base <= address < end:
                return bank, address - mapping.base, 0
            continue

        if bank == "TXT":
            # TXT packs two addresses per register. For a register address,
            # return the odd base index of the pair.
            txt_register_count = (max_mdb + 1) // 2
            end = mapping.base + txt_register_count
            if mapping.base <= address < end:
                return bank, (address - mapping.base) * 2 + 1, 0
            continue

        # Standard 1-based register banks
        end = mapping.base + mapping.width * max_mdb
        if mapping.base <= address < end:
            offset = address - mapping.base
            index = offset // mapping.width + 1
            reg_position = offset % mapping.width
            return bank, index, reg_position
    return None


# ==============================================================================
# Pack / Unpack
# ==============================================================================


def pack_value(value: bool | int | float | str, data_type: DataType) -> list[int]:
    """Pack a Python value into Modbus register(s).

    Args:
        value: The value to pack
        data_type: The DataType determining the encoding

    Returns:
        List of 16-bit register values

    Raises:
        ValueError: If data_type is BIT (coils don't use register packing)
    """
    if data_type == DataType.BIT:
        raise ValueError("BIT values use coils, not registers")

    if data_type == DataType.TXT:
        return [ord(str(value)) & 0xFFFF]

    fmt = STRUCT_FORMATS[data_type]
    raw = struct.pack(f"<{fmt}", value)

    if len(raw) == 2:
        return [struct.unpack("<H", raw)[0]]

    # 4-byte types: [low_word, high_word]
    lo, hi = struct.unpack("<HH", raw)
    return [lo, hi]


def unpack_value(registers: list[int], data_type: DataType) -> int | float | str:
    """Unpack Modbus register(s) into a Python value.

    Args:
        registers: List of 16-bit register values
        data_type: The DataType determining the decoding

    Returns:
        The unpacked Python value
    """
    if data_type == DataType.TXT:
        return chr(registers[0] & 0xFF)

    fmt = STRUCT_FORMATS[data_type]

    if len(registers) == 1:
        raw = struct.pack("<H", registers[0])
    else:
        # 2-register types: [low_word, high_word]
        raw = struct.pack("<HH", registers[0], registers[1])

    return struct.unpack(f"<{fmt}", raw)[0]
