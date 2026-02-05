"""Address parsing, formatting, and the AddressRecord data model.

Provides addr_key calculations, XD/YD helpers, address display formatting,
and the AddressRecord frozen dataclass for representing PLC addresses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .banks import (
    _INDEX_TO_TYPE,
    BANKS,
    DATA_TYPE_DISPLAY,
    DEFAULT_RETENTIVE,
    MEMORY_TYPE_BASES,
    NON_EDITABLE_TYPES,
    DataType,
    is_valid_address,
)

# ==============================================================================
# AddrKey Functions
# ==============================================================================


def get_addr_key(memory_type: str, address: int) -> int:
    """Calculate AddrKey from memory type and MDB address.

    Args:
        memory_type: The memory type (X, Y, C, etc.)
        address: The MDB address number

    Returns:
        The AddrKey value used as primary key in MDB

    Raises:
        KeyError: If memory_type is not recognized
    """
    return MEMORY_TYPE_BASES[memory_type] + address


def parse_addr_key(addr_key: int) -> tuple[str, int]:
    """Parse an AddrKey back to memory type and MDB address.

    Args:
        addr_key: The AddrKey value from MDB

    Returns:
        Tuple of (memory_type, mdb_address)

    Raises:
        KeyError: If the type index is not recognized
    """
    type_index = addr_key >> 24
    address = addr_key & 0xFFFFFF
    return _INDEX_TO_TYPE[type_index], address


# ==============================================================================
# XD/YD Helpers
# ==============================================================================


def is_xd_yd_upper_byte(memory_type: str, mdb_address: int) -> bool:
    """Check if an XD/YD MDB address is for an upper byte (only XD0u/YD0u at MDB 1)."""
    if memory_type in ("XD", "YD"):
        return mdb_address == 1
    return False


def is_xd_yd_hidden_slot(memory_type: str, mdb_address: int) -> bool:
    """Check if an XD/YD MDB address is a hidden slot (odd addresses > 1)."""
    if memory_type in ("XD", "YD"):
        return mdb_address >= 3 and mdb_address % 2 == 1
    return False


def xd_yd_mdb_to_display(mdb_address: int) -> int:
    """Convert XD/YD MDB address to display address number.

    MDB 0 -> 0 (XD0), MDB 1 -> 0 (XD0u), MDB 2 -> 1, ..., MDB 16 -> 8.
    """
    if mdb_address <= 1:
        return 0
    return mdb_address // 2


def xd_yd_display_to_mdb(display_addr: int, upper_byte: bool = False) -> int:
    """Convert XD/YD display address to MDB address.

    Args:
        display_addr: The display address (0-8)
        upper_byte: True for XD0u/YD0u (only valid for display_addr=0)

    Returns:
        The MDB address
    """
    if display_addr == 0:
        return 1 if upper_byte else 0
    return display_addr * 2


# ==============================================================================
# Address Display Functions
# ==============================================================================


def format_address_display(memory_type: str, mdb_address: int) -> str:
    """Format a memory type and MDB address as a display string.

    X/Y are 3-digit zero-padded. XD/YD use special encoding. Others are unpadded.
    """
    if memory_type in ("XD", "YD"):
        if mdb_address == 0:
            return f"{memory_type}0"
        elif mdb_address == 1:
            return f"{memory_type}0u"
        else:
            display_addr = mdb_address // 2
            return f"{memory_type}{display_addr}"
    if memory_type in ("X", "Y"):
        return f"{memory_type}{mdb_address:03d}"
    return f"{memory_type}{mdb_address}"


def parse_address_display(address_str: str) -> tuple[str, int] | None:
    """Parse a display address string to memory type and MDB address.

    Lenient: returns None on invalid input.
    For XD/YD, returns MDB address: "XD1" -> ("XD", 2).

    Args:
        address_str: Address string like "X001", "XD0", "XD0u", "XD8"

    Returns:
        Tuple of (memory_type, mdb_address) or None if invalid
    """
    if not address_str:
        return None

    address_str = address_str.strip().upper()

    match = re.match(r"^([A-Z]+)(\d+)(U?)$", address_str)
    if not match:
        return None

    memory_type = match.group(1)
    display_addr = int(match.group(2))
    is_upper = match.group(3) == "U"

    if memory_type not in MEMORY_TYPE_BASES:
        return None

    if memory_type in ("XD", "YD"):
        if is_upper and display_addr != 0:
            return None  # Invalid: XD1u, XD2u, etc. don't exist
        return memory_type, xd_yd_display_to_mdb(display_addr, is_upper)

    return memory_type, display_addr


def parse_address(address_str: str) -> tuple[str, int]:
    """Parse an address string to (bank_name, display_address).

    Strict: raises ValueError on invalid input.
    Returns display/logical address, NOT MDB encoding.
    For XD/YD: "XD1" -> ("XD", 1), unlike parse_address_display which returns ("XD", 2).

    Args:
        address_str: Address string like "X001", "DS100", "XD1"

    Returns:
        Tuple of (bank_name, display_address)

    Raises:
        ValueError: If the address string is invalid
    """
    if not address_str or not address_str.strip():
        raise ValueError(f"Empty address: {address_str!r}")

    address_str = address_str.strip().upper()

    match = re.match(r"^([A-Z]+)(\d+)(U?)$", address_str)
    if not match:
        raise ValueError(f"Invalid address format: {address_str!r}")

    bank_name = match.group(1)
    addr_num = int(match.group(2))
    is_upper = match.group(3) == "U"

    if bank_name not in BANKS:
        raise ValueError(f"Unknown bank: {bank_name!r}")

    if bank_name in ("XD", "YD"):
        if is_upper and addr_num != 0:
            raise ValueError(f"Invalid upper byte address: {address_str!r}")
        # Return display address directly (not MDB encoding)
        # For XD/YD, valid display addresses are 0-8 (plus 0u)
        if is_upper:
            return bank_name, 0  # XD0u -> display addr 0
        if addr_num < 0 or addr_num > 8:
            raise ValueError(f"Address out of range: {address_str!r}")
        return bank_name, addr_num

    if not is_valid_address(bank_name, addr_num):
        raise ValueError(f"Address out of range: {address_str!r}")

    return bank_name, addr_num


def normalize_address(address: str) -> str | None:
    """Normalize an address string to its canonical display form.

    E.g., "x1" -> "X001", "xd0u" -> "XD0u".

    Returns:
        The normalized display address, or None if address is invalid.
    """
    parsed = parse_address_display(address)
    if not parsed:
        return None
    memory_type, mdb_address = parsed
    return format_address_display(memory_type, mdb_address)


# ==============================================================================
# AddressRecord Data Model
# ==============================================================================


@dataclass(frozen=True)
class AddressRecord:
    """Immutable record for a single PLC address.

    Simpler than ClickNick's AddressRow -- omits all UI validation state.
    """

    # --- Identity ---
    memory_type: str  # 'X', 'Y', 'C', etc.
    address: int  # MDB address (1, 2, 3... or 0 for XD/YD)

    # --- Content ---
    nickname: str = ""
    comment: str = ""
    initial_value: str = ""
    retentive: bool = False

    # --- Metadata ---
    data_type: int = DataType.BIT
    used: bool | None = None  # None = unknown

    @property
    def addr_key(self) -> int:
        """Get the AddrKey for this record."""
        return get_addr_key(self.memory_type, self.address)

    @property
    def display_address(self) -> str:
        """Get the display string for this address."""
        return format_address_display(self.memory_type, self.address)

    @property
    def data_type_display(self) -> str:
        """Get human-readable data type name."""
        return DATA_TYPE_DISPLAY.get(self.data_type, "")

    @property
    def is_default_retentive(self) -> bool:
        """Return True if retentive matches the default for this memory_type."""
        default = DEFAULT_RETENTIVE.get(self.memory_type, False)
        return self.retentive == default

    @property
    def is_default_initial_value(self) -> bool:
        """Return True if the initial value is the default for its data type."""
        return (
            self.initial_value == ""
            or self.data_type != DataType.TXT
            and str(self.initial_value) == "0"
        )

    @property
    def has_content(self) -> bool:
        """True if record has any user-defined content worth saving."""
        return (
            self.nickname != ""
            or self.comment != ""
            or not self.is_default_initial_value
            or not self.is_default_retentive
        )

    @property
    def can_edit_initial_value(self) -> bool:
        """True if initial value can be edited for this memory type."""
        return self.memory_type not in NON_EDITABLE_TYPES

    @property
    def can_edit_retentive(self) -> bool:
        """True if retentive setting can be edited for this memory type."""
        return self.memory_type not in NON_EDITABLE_TYPES
