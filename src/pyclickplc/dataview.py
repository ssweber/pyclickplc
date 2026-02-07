"""DataView model and CDV file I/O for CLICK PLC DataView files.

Provides the DataviewRow dataclass, type code mappings, CDV file read/write,
and value conversion functions between CDV storage, native Python types,
and UI display strings.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .addresses import format_address_display, parse_address


# Type codes used in CDV files to identify address types
class TypeCode:
    """Type codes for CDV file format."""

    BIT = 768
    INT = 0
    INT2 = 256
    HEX = 3
    FLOAT = 257
    TXT = 1024


# Map memory type prefixes to their type codes
MEMORY_TYPE_TO_CODE: dict[str, int] = {
    "X": TypeCode.BIT,
    "Y": TypeCode.BIT,
    "C": TypeCode.BIT,
    "T": TypeCode.BIT,
    "CT": TypeCode.BIT,
    "SC": TypeCode.BIT,
    "DS": TypeCode.INT,
    "TD": TypeCode.INT,
    "SD": TypeCode.INT,
    "DD": TypeCode.INT2,
    "CTD": TypeCode.INT2,
    "DH": TypeCode.HEX,
    "XD": TypeCode.HEX,
    "YD": TypeCode.HEX,
    "DF": TypeCode.FLOAT,
    "TXT": TypeCode.TXT,
}

# Reverse mapping: type code to list of memory types
CODE_TO_MEMORY_TYPES: dict[int, list[str]] = {
    TypeCode.BIT: ["X", "Y", "C", "T", "CT", "SC"],
    TypeCode.INT: ["DS", "TD", "SD"],
    TypeCode.INT2: ["DD", "CTD"],
    TypeCode.HEX: ["DH", "XD", "YD"],
    TypeCode.FLOAT: ["DF"],
    TypeCode.TXT: ["TXT"],
}

# SC addresses that are writable (most SC are read-only system controls)
WRITABLE_SC: frozenset[int] = frozenset({50, 51, 53, 55, 60, 61, 65, 66, 67, 75, 76, 120, 121})

# SD addresses that are writable (most SD are read-only system data)
WRITABLE_SD: frozenset[int] = frozenset(
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

# Max rows in a dataview
MAX_DATAVIEW_ROWS = 100


def get_type_code_for_address(address: str) -> int | None:
    """Get the type code for an address.

    Args:
        address: Address string like "X001", "DS1"

    Returns:
        Type code or None if address is invalid.
    """
    try:
        memory_type, _ = parse_address(address)
    except ValueError:
        return None
    return MEMORY_TYPE_TO_CODE.get(memory_type)


def is_address_writable(address: str) -> bool:
    """Check if an address is writable (can have a New Value set).

    Most addresses are writable, but SC and SD have specific writable addresses.
    XD and YD are read-only.

    Args:
        address: Address string like "X001", "SC50"

    Returns:
        True if the address can have a New Value written to it.
    """
    try:
        memory_type, mdb_address = parse_address(address)
    except ValueError:
        return False

    # XD and YD are read-only
    if memory_type in ("XD", "YD"):
        return False

    # SC has specific writable addresses
    if memory_type == "SC":
        return mdb_address in WRITABLE_SC

    # SD has specific writable addresses
    if memory_type == "SD":
        return mdb_address in WRITABLE_SD

    # All other addresses are writable
    return True


@dataclass
class DataviewRow:
    """Represents a single row in a CLICK DataView.

    A dataview row contains an address to monitor and optionally a new value
    to write to that address. The nickname and comment are display-only
    fields populated from SharedAddressData.
    """

    # Core data (stored in CDV file)
    address: str = ""  # e.g., "X001", "DS1", "CTD250"
    type_code: int = 0  # Type code for the address
    new_value: str = ""  # Optional new value to write

    # Display-only fields (populated from SharedAddressData)
    nickname: str = field(default="", compare=False)
    comment: str = field(default="", compare=False)

    @property
    def is_empty(self) -> bool:
        """Check if this row is empty (no address set)."""
        return not self.address.strip()

    @property
    def is_writable(self) -> bool:
        """Check if this address can have a New Value written to it."""
        return is_address_writable(self.address)

    @property
    def memory_type(self) -> str | None:
        """Get the memory type prefix (X, Y, DS, etc.) or None if invalid."""
        try:
            mem_type, _ = parse_address(self.address)
            return mem_type
        except ValueError:
            return None

    @property
    def address_number(self) -> str | None:
        """Get the address number as a display string, or None if invalid."""
        try:
            memory_type, mdb_address = parse_address(self.address)
        except ValueError:
            return None
        # Return the display address portion (strip the memory type prefix)
        display = format_address_display(memory_type, mdb_address)
        return display[len(memory_type) :]

    def update_type_code(self) -> bool:
        """Update the type code based on the current address.

        Returns:
            True if type code was updated, False if address is invalid.
        """
        code = get_type_code_for_address(self.address)
        if code is not None:
            self.type_code = code
            return True
        return False

    def clear(self) -> None:
        """Clear all fields in this row."""
        self.address = ""
        self.type_code = 0
        self.new_value = ""
        self.nickname = ""
        self.comment = ""


def create_empty_dataview(count: int = MAX_DATAVIEW_ROWS) -> list[DataviewRow]:
    """Create a new empty dataview with the specified number of rows.

    Args:
        count: Number of rows to create (default MAX_DATAVIEW_ROWS).

    Returns:
        List of empty DataviewRow objects.
    """
    return [DataviewRow() for _ in range(count)]


# --- Value Conversion Functions ---
#
# Two layers of conversion:
#   1. storage <-> datatype:  CDV file strings <-> native Python types
#   2. datatype <-> display:  native Python types <-> UI-friendly strings
#
# The storage layer handles CDV encoding (sign extension, IEEE 754, etc.).
# The display layer handles presentation (hex formatting, float precision, etc.).


def storage_to_datatype(value: str, type_code: int) -> int | float | bool | str | None:
    """Convert a CDV storage string to its native Python type.

    Args:
        value: The raw value string from the CDV file.
        type_code: The type code (TypeCode.BIT, TypeCode.INT, etc.)

    Returns:
        Native Python value (bool for BIT, int for INT/INT2/HEX,
        float for FLOAT, str for TXT), or None if empty/invalid.
    """
    if not value:
        return None

    try:
        if type_code == TypeCode.BIT:
            return value == "1"

        elif type_code == TypeCode.INT:
            # Stored as unsigned 32-bit with sign extension → signed 16-bit
            unsigned_val = int(value)
            val_16bit = unsigned_val & 0xFFFF
            if val_16bit >= 0x8000:
                val_16bit -= 0x10000
            return val_16bit

        elif type_code == TypeCode.INT2:
            # Stored as unsigned 32-bit → signed 32-bit
            unsigned_val = int(value)
            if unsigned_val >= 0x80000000:
                unsigned_val -= 0x100000000
            return unsigned_val

        elif type_code == TypeCode.HEX:
            return int(value)

        elif type_code == TypeCode.FLOAT:
            # Stored as IEEE 754 32-bit integer representation → float
            int_val = int(value)
            bytes_val = struct.pack(">I", int_val & 0xFFFFFFFF)
            return struct.unpack(">f", bytes_val)[0]

        elif type_code == TypeCode.TXT:
            code = int(value)
            return chr(code) if 0 < code < 128 else ""

        else:
            return None

    except (ValueError, struct.error):
        return None


def datatype_to_storage(value: int | float | bool | str | None, type_code: int) -> str:
    """Convert a native Python value to CDV storage format.

    Args:
        value: The native Python value (bool, int, or float).
        type_code: The type code (TypeCode.BIT, TypeCode.INT, etc.)

    Returns:
        Value formatted for CDV file storage, or "" if None.
    """
    if value is None:
        return ""

    try:
        if type_code == TypeCode.BIT:
            return "1" if value else "0"

        elif type_code == TypeCode.INT:
            # Signed 16-bit → unsigned 32-bit with sign extension
            signed_val = int(value)
            signed_val = max(-32768, min(32767, signed_val))
            if signed_val < 0:
                return str(signed_val + 0x100000000)
            return str(signed_val)

        elif type_code == TypeCode.INT2:
            # Signed 32-bit → unsigned 32-bit
            signed_val = int(value)
            signed_val = max(-2147483648, min(2147483647, signed_val))
            if signed_val < 0:
                return str(signed_val + 0x100000000)
            return str(signed_val)

        elif type_code == TypeCode.HEX:
            return str(int(value))

        elif type_code == TypeCode.FLOAT:
            # Float → IEEE 754 bytes → unsigned 32-bit integer string
            float_val = float(value)
            bytes_val = struct.pack(">f", float_val)
            int_val = struct.unpack(">I", bytes_val)[0]
            return str(int_val)

        elif type_code == TypeCode.TXT:
            if isinstance(value, str):
                return str(ord(value)) if value else "0"
            return str(int(value))

        else:
            return ""

    except (ValueError, struct.error):
        return ""


def datatype_to_display(value: int | float | bool | str | None, type_code: int) -> str:
    """Convert a native Python value to a UI-friendly display string.

    Args:
        value: The native Python value (bool, int, or float).
        type_code: The type code (TypeCode.BIT, TypeCode.INT, etc.)

    Returns:
        Human-readable display string, or "" if None.
    """
    if value is None:
        return ""

    try:
        if type_code == TypeCode.BIT:
            return "1" if value else "0"

        elif type_code in (TypeCode.INT, TypeCode.INT2):
            return str(int(value))

        elif type_code == TypeCode.HEX:
            return format(int(value), "04X")

        elif type_code == TypeCode.FLOAT:
            return f"{float(value):.7G}"

        elif type_code == TypeCode.TXT:
            if isinstance(value, str):
                return value if value else ""
            code = int(value)
            if 32 <= code <= 126:
                return chr(code)
            return str(code)

        else:
            return str(value)

    except (ValueError, TypeError):
        return ""


def display_to_datatype(value: str, type_code: int) -> int | float | bool | str | None:
    """Convert a UI display string to its native Python type.

    Args:
        value: The human-readable display string.
        type_code: The type code (TypeCode.BIT, TypeCode.INT, etc.)

    Returns:
        Native Python value (bool for BIT, int for INT/INT2/HEX,
        float for FLOAT, str for TXT), or None if empty/invalid.
    """
    if not value:
        return None

    try:
        if type_code == TypeCode.BIT:
            return value in ("1", "True", "true", "ON", "on")

        elif type_code in (TypeCode.INT, TypeCode.INT2):
            return int(value)

        elif type_code == TypeCode.HEX:
            hex_val = value.strip()
            if hex_val.lower().startswith("0x"):
                hex_val = hex_val[2:]
            return int(hex_val, 16)

        elif type_code == TypeCode.FLOAT:
            return float(value)

        elif type_code == TypeCode.TXT:
            if len(value) == 1:
                return value
            code = int(value)
            return chr(code) if 0 < code < 128 else ""

        else:
            return None

    except (ValueError, TypeError):
        return None


# =============================================================================
# CDV File I/O
# =============================================================================


def load_cdv(path: Path | str) -> tuple[list[DataviewRow], bool, str]:
    """Load a CDV file.

    Args:
        path: Path to the CDV file.

    Returns:
        Tuple of (rows, has_new_values, header) where:
        - rows: List of DataviewRow objects (always MAX_DATAVIEW_ROWS length)
        - has_new_values: True if the dataview has new values set
        - header: The original header line from the file

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file format is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CDV file not found: {path}")

    # Read file with UTF-16 encoding
    content = path.read_text(encoding="utf-16")
    lines = content.strip().split("\n")

    if not lines:
        raise ValueError(f"Empty CDV file: {path}")

    # Parse header line - preserve the original
    header = lines[0].strip()
    header_parts = [p.strip() for p in header.split(",")]
    if len(header_parts) < 1:
        raise ValueError(f"Invalid CDV header: {header}")

    # First value: 0 = no new values, -1 = has new values
    try:
        has_new_values = int(header_parts[0]) == -1
    except ValueError:
        has_new_values = False

    # Parse data rows
    rows = create_empty_dataview()
    data_lines = lines[1 : MAX_DATAVIEW_ROWS + 1]

    for i, line in enumerate(data_lines):
        if i >= MAX_DATAVIEW_ROWS:
            break

        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]

        # Empty row: ",0" or just ","
        if not parts[0]:
            continue

        # Parse address
        address = parts[0]
        rows[i].address = address

        # Parse type code
        if len(parts) > 1 and parts[1]:
            try:
                rows[i].type_code = int(parts[1])
            except ValueError:
                # Try to infer from address
                code = get_type_code_for_address(address)
                rows[i].type_code = code if code is not None else 0
        else:
            # Infer type code from address
            code = get_type_code_for_address(address)
            rows[i].type_code = code if code is not None else 0

        # Parse new value (if present and has_new_values flag is set)
        if len(parts) > 2 and parts[2]:
            rows[i].new_value = parts[2]

    return rows, has_new_values, header


def save_cdv(
    path: Path | str,
    rows: list[DataviewRow],
    has_new_values: bool,
    header: str | None = None,
) -> None:
    """Save a CDV file.

    Args:
        path: Path to save the CDV file.
        rows: List of DataviewRow objects (may exceed MAX_DATAVIEW_ROWS).
        has_new_values: True if any rows have new values set.
        header: Original header line to preserve. If None, uses default format.

    Note:
        Only the first MAX_DATAVIEW_ROWS (100) rows are saved to maintain
        file format compatibility. Overflow rows (index 100+) are not persisted.
    """
    path = Path(path)

    # Build content
    lines: list[str] = []

    # Header line - use original if provided, otherwise build default
    if header is not None:
        lines.append(header)
    else:
        header_flag = -1 if has_new_values else 0
        lines.append(f"{header_flag},0,0")

    # Data rows - only save first MAX_DATAVIEW_ROWS
    rows_to_save = list(rows[:MAX_DATAVIEW_ROWS])

    # Pad with empty rows if needed to always have exactly 100 lines
    while len(rows_to_save) < MAX_DATAVIEW_ROWS:
        rows_to_save.append(DataviewRow())

    for row in rows_to_save:
        if row.is_empty:
            lines.append(",0")
        else:
            if row.new_value:
                lines.append(f"{row.address},{row.type_code},{row.new_value}")
            else:
                lines.append(f"{row.address},{row.type_code}")

    # Join with newlines and add trailing newline
    content = "\n".join(lines) + "\n"

    # Write with UTF-16 encoding (includes BOM automatically)
    path.write_text(content, encoding="utf-16")


def export_cdv(
    path: Path | str,
    rows: list[DataviewRow],
    has_new_values: bool,
    header: str | None = None,
) -> None:
    """Export a CDV file to a new location.

    This is identical to save_cdv but semantically indicates exporting
    rather than saving to the original location.

    Args:
        path: Path to export the CDV file.
        rows: List of DataviewRow objects.
        has_new_values: True if any rows have new values set.
        header: Original header line to preserve. If None, uses default format.
    """
    save_cdv(path, rows, has_new_values, header)


def get_dataview_folder(project_path: Path | str) -> Path | None:
    """Get the DataView folder for a CLICK project.

    The DataView folder is located at: {project_path}/CLICK ({unique_id})/DataView
    where {unique_id} is a hex identifier like "00010A98".

    Args:
        project_path: Path to the CLICK project folder.

    Returns:
        Path to the DataView folder, or None if not found.
    """
    project_path = Path(project_path)
    if not project_path.is_dir():
        return None

    # Look for CLICK (*) subdirectory
    for child in project_path.iterdir():
        if child.is_dir() and child.name.startswith("CLICK ("):
            dataview_path = child / "DataView"
            if dataview_path.is_dir():
                return dataview_path

    return None


def list_cdv_files(dataview_folder: Path | str) -> list[Path]:
    """List all CDV files in a DataView folder.

    Args:
        dataview_folder: Path to the DataView folder.

    Returns:
        List of Path objects for each CDV file, sorted by name.
    """
    folder = Path(dataview_folder)
    if not folder.is_dir():
        return []

    return sorted(folder.glob("*.cdv"), key=lambda p: p.stem.lower())
