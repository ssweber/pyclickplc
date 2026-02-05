"""PLC memory bank configuration and address validation.

Defines the 16 memory banks of AutomationDirect CLICK PLCs with their
address ranges, data types, and interleaving relationships.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# ==============================================================================
# Data Types
# ==============================================================================


class DataType(IntEnum):
    """DataType mapping from MDB database."""

    BIT = 0  # C, CT, SC, T, X, Y - values: "0" or "1"
    INT = 1  # DS, SD, TD - 16-bit signed: -32768 to 32767
    INT2 = 2  # CTD, DD - 32-bit signed: -2147483648 to 2147483647
    FLOAT = 3  # DF - float: -3.4028235E+38 to 3.4028235E+38
    HEX = 4  # DH, XD, YD - hex string: "0000" to "FFFF"
    TXT = 6  # TXT - single ASCII character


# Display names for DataType values
DATA_TYPE_DISPLAY: dict[int, str] = {
    DataType.BIT: "BIT",
    DataType.INT: "INT",
    DataType.INT2: "INT2",
    DataType.FLOAT: "FLOAT",
    DataType.HEX: "HEX",
    DataType.TXT: "TXT",
}

# Hint text for initial value fields by DataType
DATA_TYPE_HINTS: dict[int, str] = {
    DataType.BIT: "0 or 1 (checkbox)",
    DataType.INT: "Range: `-32768` to `32767`",
    DataType.INT2: "Range: `-2147483648` to `2147483647`",
    DataType.FLOAT: "Range: `-3.4028235E+38` to `3.4028235E+38`",
    DataType.HEX: "Range: '0000' to 'FFFF'",
    DataType.TXT: "Single ASCII char: eg 'A'",
}


# ==============================================================================
# Bank Configuration
# ==============================================================================


# X/Y sparse address ranges: 10 hardware slots of 16 addresses each
_SPARSE_RANGES: tuple[tuple[int, int], ...] = (
    (1, 16),
    (21, 36),
    (101, 116),
    (121, 136),
    (201, 216),
    (221, 236),
    (301, 316),
    (321, 336),
    (801, 816),
    (821, 836),
)


@dataclass(frozen=True)
class BankConfig:
    """Configuration for a single PLC memory bank."""

    name: str
    min_addr: int
    max_addr: int
    data_type: DataType
    valid_ranges: tuple[tuple[int, int], ...] | None = None  # None = contiguous
    interleaved_with: str | None = None


BANKS: dict[str, BankConfig] = {
    "X": BankConfig("X", 1, 816, DataType.BIT, valid_ranges=_SPARSE_RANGES),
    "Y": BankConfig("Y", 1, 816, DataType.BIT, valid_ranges=_SPARSE_RANGES),
    "C": BankConfig("C", 1, 2000, DataType.BIT),
    "T": BankConfig("T", 1, 500, DataType.BIT, interleaved_with="TD"),
    "CT": BankConfig("CT", 1, 250, DataType.BIT, interleaved_with="CTD"),
    "SC": BankConfig("SC", 1, 1000, DataType.BIT),
    "DS": BankConfig("DS", 1, 4500, DataType.INT),
    "DD": BankConfig("DD", 1, 1000, DataType.INT2),
    "DH": BankConfig("DH", 1, 500, DataType.HEX),
    "DF": BankConfig("DF", 1, 500, DataType.FLOAT),
    "XD": BankConfig("XD", 0, 16, DataType.HEX),
    "YD": BankConfig("YD", 0, 16, DataType.HEX),
    "TD": BankConfig("TD", 1, 500, DataType.INT, interleaved_with="T"),
    "CTD": BankConfig("CTD", 1, 250, DataType.INT2, interleaved_with="CT"),
    "SD": BankConfig("SD", 1, 1000, DataType.INT),
    "TXT": BankConfig("TXT", 1, 1000, DataType.TXT),
}


# ==============================================================================
# Derived Constants
# ==============================================================================


# DataType by memory type (derived from BANKS)
MEMORY_TYPE_TO_DATA_TYPE: dict[str, int] = {name: b.data_type for name, b in BANKS.items()}

# Types that only hold bit values
BIT_ONLY_TYPES: frozenset[str] = frozenset(
    name for name, b in BANKS.items() if b.data_type == DataType.BIT
)


# ==============================================================================
# Legacy Dicts (for addr_key system and ClickNick compatibility)
# ==============================================================================


# Base values for AddrKey calculation (Primary Key in MDB)
MEMORY_TYPE_BASES: dict[str, int] = {
    "X": 0x0000000,
    "Y": 0x1000000,
    "C": 0x2000000,
    "T": 0x3000000,
    "CT": 0x4000000,
    "SC": 0x5000000,
    "DS": 0x6000000,
    "DD": 0x7000000,
    "DH": 0x8000000,
    "DF": 0x9000000,
    "XD": 0xA000000,
    "YD": 0xB000000,
    "TD": 0xC000000,
    "CTD": 0xD000000,
    "SD": 0xE000000,
    "TXT": 0xF000000,
}

# Reverse mapping: type_index -> memory_type
_INDEX_TO_TYPE: dict[int, str] = {v >> 24: k for k, v in MEMORY_TYPE_BASES.items()}

# Default retentive values by memory type (from CLICK documentation)
DEFAULT_RETENTIVE: dict[str, bool] = {
    "X": False,
    "Y": False,
    "C": False,
    "T": False,
    "CT": True,  # Counters are retentive by default
    "SC": False,  # Can't change
    "DS": True,  # Data registers are retentive by default
    "DD": True,
    "DH": True,
    "DF": True,
    "XD": False,  # Can't change
    "YD": False,  # Can't change
    "TD": False,  # See note
    "CTD": True,  # See note
    "SD": False,  # Can't change
    "TXT": True,
}

# Canonical set of interleaved type pairs
INTERLEAVED_TYPE_PAIRS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"T", "TD"}),
        frozenset({"CT", "CTD"}),
    }
)

# Bidirectional lookup for interleaved pairs
INTERLEAVED_PAIRS: dict[str, str] = {
    "T": "TD",
    "TD": "T",
    "CT": "CTD",
    "CTD": "CT",
}

# Memory types that share retentive with their paired type
PAIRED_RETENTIVE_TYPES: dict[str, str] = {"TD": "T", "CTD": "CT"}

# Memory types where InitialValue/Retentive cannot be edited
NON_EDITABLE_TYPES: frozenset[str] = frozenset({"SC", "SD", "XD", "YD"})


# ==============================================================================
# Address Validation
# ==============================================================================


def is_valid_address(bank_name: str, address: int) -> bool:
    """Check if an address is valid for the given bank.

    Uses valid_ranges for sparse banks (X/Y), simple min/max for contiguous banks.

    Args:
        bank_name: The bank name (e.g., "X", "DS")
        address: The address number to validate

    Returns:
        True if the address is valid for the bank
    """
    bank = BANKS.get(bank_name)
    if bank is None:
        return False

    if bank.valid_ranges is not None:
        return any(lo <= address <= hi for lo, hi in bank.valid_ranges)

    return bank.min_addr <= address <= bank.max_addr


# ==============================================================================
# Runtime Assertions
# ==============================================================================

assert set(BANKS) == set(MEMORY_TYPE_BASES), "BANKS and MEMORY_TYPE_BASES keys must match"
assert set(BANKS) == set(DEFAULT_RETENTIVE), "BANKS and DEFAULT_RETENTIVE keys must match"
