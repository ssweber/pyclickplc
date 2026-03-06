"""DataView model and CDV file I/O for CLICK PLC DataView files.

Provides the DataViewRecord dataclass, CDV file read/write,
value conversion functions between CDV storage, native Python types,
UI display strings, and CDV verification helpers.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from .addresses import format_address_display, normalize_address, parse_address
from .banks import MEMORY_TYPE_TO_DATA_TYPE, DataType
from .validation import (
    FLOAT_MAX,
    FLOAT_MIN,
    INT2_MAX,
    INT2_MIN,
    INT_MAX,
    INT_MIN,
    assert_runtime_value,
    validate_initial_value,
)


# Type codes used in CDV files to identify address types
class _CdvStorageCode:
    """Type codes for CDV file format."""

    BIT = 768
    INT = 0
    INT2 = 256
    HEX = 3
    FLOAT = 257
    TXT = 1024


_CDV_CODE_TO_DATA_TYPE: dict[int, DataType] = {
    _CdvStorageCode.BIT: DataType.BIT,
    _CdvStorageCode.INT: DataType.INT,
    _CdvStorageCode.INT2: DataType.INT2,
    _CdvStorageCode.HEX: DataType.HEX,
    _CdvStorageCode.FLOAT: DataType.FLOAT,
    _CdvStorageCode.TXT: DataType.TXT,
}
_DATA_TYPE_TO_CDV_CODE: dict[DataType, int] = {v: k for k, v in _CDV_CODE_TO_DATA_TYPE.items()}


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
DataViewValue: TypeAlias = bool | int | float | str | None


def get_data_type_for_address(address: str) -> DataType | None:
    """Get the DataType for an address.

    Args:
        address: Address string like "X001", "DS1"

    Returns:
        DataType or None if address is invalid.
    """
    try:
        memory_type, _ = parse_address(address)
    except ValueError:
        return None
    data_type = MEMORY_TYPE_TO_DATA_TYPE.get(memory_type)
    return DataType(data_type) if data_type is not None else None


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
class DataViewRecord:
    """Represents a single row in a CLICK DataView.

    A dataview row contains an address to monitor and optionally a new value
    to write to that address. The nickname and comment are display-only
    fields populated from SharedAddressData.
    For user-facing creation from display addresses, prefer
    ``make_dataview_record(...)``.
    """

    # Core data (stored in CDV file)
    address: str = ""  # e.g., "X001", "DS1", "CTD250"
    data_type: DataType | None = None  # DataType for the address
    new_value: DataViewValue = None  # Native Python value for optional write

    # Display-only fields (populated from SharedAddressData)
    nickname: str = field(default="", compare=False)
    comment: str = field(default="", compare=False)

    @classmethod
    def from_address(
        cls,
        address: str,
        *,
        new_value: DataViewValue = None,
    ) -> DataViewRecord:
        """Build a DataViewRecord from a display address string."""
        normalized = normalize_address(address)
        if normalized is None:
            raise ValueError(f"Invalid address format: {address!r}")

        data_type = get_data_type_for_address(normalized)
        if new_value is not None:
            if not is_address_writable(normalized):
                raise ValueError(f"Read-only address: {normalized}")
            if data_type is None:
                raise ValueError(f"Cannot infer data type for address: {normalized}")
            bank, index = parse_address(normalized)
            assert_runtime_value(data_type, new_value, bank=bank, index=index)

        return cls(
            address=normalized,
            data_type=data_type,
            new_value=new_value,
        )

    def __repr__(self) -> str:
        """Return a concise, user-friendly representation."""
        parts: list[str] = []

        if self.address.strip():
            parts.append(f"address={self.address!r}")
        if self.data_type is not None:
            try:
                data_type_name = DataType(self.data_type).name
            except ValueError:
                data_type_name = str(self.data_type)
            parts.append(f"data_type={data_type_name!r}")
        if self.new_value is not None:
            parts.append(f"new_value={self.new_value!r}")
        if self.nickname != "":
            parts.append(f"nickname={self.nickname!r}")
        if self.comment != "":
            parts.append(f"comment={self.comment!r}")

        if not parts:
            return "DataViewRecord()"
        return f"DataViewRecord({', '.join(parts)})"

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

    def update_data_type(self) -> bool:
        """Update the DataType based on the current address.

        Returns:
            True if data_type was updated, False if address is invalid.
        """
        data_type = get_data_type_for_address(self.address)
        if data_type is not None:
            self.data_type = data_type
            return True
        return False

    def clear(self) -> None:
        """Clear all fields in this row."""
        self.address = ""
        self.data_type = None
        self.new_value = None
        self.nickname = ""
        self.comment = ""


def make_dataview_record(
    address: str,
    *,
    new_value: DataViewValue = None,
) -> DataViewRecord:
    """Create a DataViewRecord from a display address with inferred defaults."""
    return DataViewRecord.from_address(
        address,
        new_value=new_value,
    )


def create_empty_dataview(count: int = MAX_DATAVIEW_ROWS) -> list[DataViewRecord]:
    """Create a new empty dataview with the specified number of rows.

    Args:
        count: Number of rows to create (default MAX_DATAVIEW_ROWS).

    Returns:
        List of empty DataViewRecord objects.
    """
    return [DataViewRecord() for _ in range(count)]


# --- Value Conversion Functions ---
#
# Two layers of conversion:
#   1. storage <-> datatype:  CDV file strings <-> native Python types
#   2. datatype <-> display:  native Python types <-> UI-friendly strings
#
# The storage layer handles CDV encoding (sign extension, IEEE 754, etc.).
# The display layer handles presentation (hex formatting, float precision, etc.).


def storage_to_datatype(value: str, data_type: DataType) -> int | float | bool | str | None:
    """Convert a CDV storage string to its native Python type.

    Args:
        value: The raw value string from the CDV file.
        data_type: DataType for conversion.

    Returns:
        Native Python value (bool for BIT, int for INT/INT2/HEX,
        float for FLOAT, str for TXT), or None if empty/invalid.
    """
    if not value:
        return None

    try:
        if data_type == DataType.BIT:
            return value == "1"

        if data_type == DataType.INT:
            # Stored as unsigned 32-bit with sign extension -> signed 16-bit
            unsigned_val = int(value)
            val_16bit = unsigned_val & 0xFFFF
            if val_16bit >= 0x8000:
                val_16bit -= 0x10000
            return val_16bit

        if data_type == DataType.INT2:
            # Stored as unsigned 32-bit -> signed 32-bit
            unsigned_val = int(value)
            if unsigned_val >= 0x80000000:
                unsigned_val -= 0x100000000
            return unsigned_val

        if data_type == DataType.HEX:
            return int(value)

        if data_type == DataType.FLOAT:
            # Stored as IEEE 754 32-bit integer representation -> float
            int_val = int(value)
            bytes_val = struct.pack(">I", int_val & 0xFFFFFFFF)
            return struct.unpack(">f", bytes_val)[0]

        if data_type == DataType.TXT:
            code = int(value)
            return chr(code) if 0 < code < 128 else ""

        return None

    except (ValueError, struct.error):
        return None


def datatype_to_storage(value: int | float | bool | str | None, data_type: DataType) -> str:
    """Convert a native Python value to CDV storage format.

    Args:
        value: The native Python value (bool, int, or float).
        data_type: DataType for conversion.

    Returns:
        Value formatted for CDV file storage, or "" if None.
    """
    if value is None:
        return ""

    try:
        if data_type == DataType.BIT:
            return "1" if value else "0"

        if data_type == DataType.INT:
            # Signed 16-bit -> unsigned 32-bit with sign extension
            signed_val = int(value)
            signed_val = max(-32768, min(32767, signed_val))
            if signed_val < 0:
                return str(signed_val + 0x100000000)
            return str(signed_val)

        if data_type == DataType.INT2:
            # Signed 32-bit -> unsigned 32-bit
            signed_val = int(value)
            signed_val = max(-2147483648, min(2147483647, signed_val))
            if signed_val < 0:
                return str(signed_val + 0x100000000)
            return str(signed_val)

        if data_type == DataType.HEX:
            return str(int(value))

        if data_type == DataType.FLOAT:
            # Float -> IEEE 754 bytes -> unsigned 32-bit integer string
            float_val = float(value)
            bytes_val = struct.pack(">f", float_val)
            int_val = struct.unpack(">I", bytes_val)[0]
            return str(int_val)

        if data_type == DataType.TXT:
            if isinstance(value, str):
                return str(ord(value)) if value else "0"
            return str(int(value))

        return ""

    except (ValueError, struct.error):
        return ""


def datatype_to_display(value: int | float | bool | str | None, data_type: DataType) -> str:
    """Convert a native Python value to a UI-friendly display string.

    Args:
        value: The native Python value (bool, int, or float).
        data_type: DataType for conversion.

    Returns:
        Human-readable display string, or "" if None.
    """
    if value is None:
        return ""

    try:
        if data_type == DataType.BIT:
            return "1" if value else "0"

        if data_type in (DataType.INT, DataType.INT2):
            return str(int(value))

        if data_type == DataType.HEX:
            return format(int(value), "04X")

        if data_type == DataType.FLOAT:
            return f"{float(value):.7G}"

        if data_type == DataType.TXT:
            if isinstance(value, str):
                return value if value else ""
            code = int(value)
            if 32 <= code <= 126:
                return chr(code)
            return str(code)

        return str(value)

    except (ValueError, TypeError):
        return ""


def display_to_datatype(value: str, data_type: DataType) -> int | float | bool | str | None:
    """Convert a UI display string to its native Python type.

    Args:
        value: The human-readable display string.
        data_type: DataType for conversion.

    Returns:
        Native Python value (bool for BIT, int for INT/INT2/HEX,
        float for FLOAT, str for TXT), or None if empty/invalid.
    """
    if not value:
        return None

    try:
        if data_type == DataType.BIT:
            return value in ("1", "True", "true", "ON", "on")

        if data_type in (DataType.INT, DataType.INT2):
            return int(value)

        if data_type == DataType.HEX:
            hex_val = value.strip()
            if hex_val.lower().startswith("0x"):
                hex_val = hex_val[2:]
            return int(hex_val, 16)

        if data_type == DataType.FLOAT:
            return float(value)

        if data_type == DataType.TXT:
            if len(value) == 1:
                return value
            code = int(value)
            return chr(code) if 0 < code < 128 else ""

        return None

    except (ValueError, TypeError):
        return None


def validate_new_value(display_str: str, data_type: DataType) -> tuple[bool, str]:
    """Validate a user-entered display string for the New Value column."""
    if not display_str:
        return True, ""
    return validate_initial_value(display_str, data_type)


# =============================================================================
# CDV File I/O
# =============================================================================


@dataclass(frozen=True)
class DisplayParseResult:
    """Result object for non-throwing display -> native parsing."""

    ok: bool
    value: DataViewValue = None
    error: str = ""


def _default_cdv_header(has_new_values: bool) -> str:
    return f"{-1 if has_new_values else 0},0,0"


def _rows_snapshot(rows: list[DataViewRecord]) -> list[tuple[str, DataType | None, DataViewValue]]:
    return [(row.address, row.data_type, row.new_value) for row in rows]


def _coerce_for_compare(value: DataViewValue, data_type: DataType) -> DataViewValue:
    if value is None:
        return None

    if data_type == DataType.BIT:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            if value in (0, 1):
                return bool(value)
            return None
        if isinstance(value, float):
            if value.is_integer() and int(value) in (0, 1):
                return bool(int(value))
            return None
        return None

    if data_type in (DataType.INT, DataType.INT2, DataType.HEX):
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            return None
        return None

    if data_type == DataType.FLOAT:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    if data_type == DataType.TXT:
        if isinstance(value, str):
            return value
        if isinstance(value, int) and 0 <= value <= 127:
            return chr(value)
        return None

    return value


def _values_equal_for_data_type(
    expected: DataViewValue,
    actual: DataViewValue,
    data_type: DataType | None,
) -> bool:
    if expected is None and actual is None:
        return True
    if data_type is None:
        return expected == actual

    expected_norm = _coerce_for_compare(expected, data_type)
    actual_norm = _coerce_for_compare(actual, data_type)

    if expected_norm is None or actual_norm is None:
        return expected == actual

    if data_type == DataType.FLOAT:
        return abs(float(expected_norm) - float(actual_norm)) <= 1e-6

    return expected_norm == actual_norm


def _row_placeholder(rows: list[DataViewRecord], index: int) -> DataViewRecord:
    return rows[index] if index < len(rows) else DataViewRecord()


@dataclass
class DataViewFile:
    """CDV file model with row data in native Python types."""

    rows: list[DataViewRecord] = field(default_factory=create_empty_dataview)
    has_new_values: bool = False
    header: str = "0,0,0"
    path: Path | None = None
    _original_bytes: bytes | None = field(default=None, repr=False, compare=False)
    _original_rows: list[tuple[str, DataType | None, DataViewValue]] = field(
        default_factory=list,
        repr=False,
        compare=False,
    )
    _original_has_new_values: bool | None = field(default=None, repr=False, compare=False)
    _original_header: str | None = field(default=None, repr=False, compare=False)
    _row_storage_tokens: list[str | None] = field(default_factory=list, repr=False, compare=False)

    @staticmethod
    def value_to_display(value: DataViewValue, data_type: DataType | None) -> str:
        """Render a native value as a display string."""
        if data_type is None:
            return ""
        return datatype_to_display(value, data_type)

    @staticmethod
    def validate_display(display_str: str, data_type: DataType | None) -> tuple[bool, str]:
        """Validate display text for a target data type."""
        if data_type is None:
            return False, "No address set"
        return validate_new_value(display_str, data_type)

    @staticmethod
    def try_parse_display(display_str: str, data_type: DataType | None) -> DisplayParseResult:
        """Parse a display string to a native value without raising."""
        if not display_str:
            return DisplayParseResult(ok=True, value=None)
        ok, error = DataViewFile.validate_display(display_str, data_type)
        if not ok or data_type is None:
            return DisplayParseResult(ok=False, error=error)
        native = display_to_datatype(display_str, data_type)
        if native is None:
            return DisplayParseResult(ok=False, error="Invalid value")
        return DisplayParseResult(ok=True, value=native)

    @staticmethod
    def validate_row_display(row: DataViewRecord, display_str: str) -> tuple[bool, str]:
        """Validate a user edit for a specific row."""
        if not row.is_writable:
            return False, "Read-only address"
        return DataViewFile.validate_display(display_str, row.data_type)

    @staticmethod
    def set_row_new_value_from_display(row: DataViewRecord, display_str: str) -> None:
        """Strictly set a row's native new_value from a display string."""
        ok, error = DataViewFile.validate_row_display(row, display_str)
        if not ok:
            raise ValueError(error)
        parsed = DataViewFile.try_parse_display(display_str, row.data_type)
        if not parsed.ok:
            raise ValueError(parsed.error)
        row.new_value = parsed.value

    @classmethod
    def load(cls, path: Path | str) -> DataViewFile:
        """Load a CDV file and parse new values into native Python types."""
        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"CDV file not found: {path_obj}")

        raw_bytes = path_obj.read_bytes()
        content = raw_bytes.decode("utf-16")
        lines = content.splitlines()
        if not lines:
            raise ValueError(f"Empty CDV file: {path_obj}")

        header = lines[0].strip()
        header_parts = [p.strip() for p in header.split(",")]
        if len(header_parts) < 1:
            raise ValueError(f"Invalid CDV header: {header}")

        try:
            has_new_values = int(header_parts[0]) == -1
        except ValueError:
            has_new_values = False

        rows = create_empty_dataview()
        row_storage_tokens: list[str | None] = [None] * MAX_DATAVIEW_ROWS

        for i, raw_line in enumerate(lines[1 : MAX_DATAVIEW_ROWS + 1]):
            line = raw_line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split(",")]
            if not parts[0]:
                continue

            row = rows[i]
            row.address = parts[0]

            if len(parts) > 1 and parts[1]:
                try:
                    cdv_code = int(parts[1])
                    row.data_type = _CDV_CODE_TO_DATA_TYPE.get(cdv_code)
                except ValueError:
                    row.data_type = None

            if row.data_type is None:
                row.data_type = get_data_type_for_address(row.address)

            if len(parts) > 2 and parts[2]:
                row_storage_tokens[i] = parts[2]
                if row.data_type is None:
                    row.new_value = parts[2]
                else:
                    row.new_value = storage_to_datatype(parts[2], row.data_type)

        dataview = cls(
            rows=rows,
            has_new_values=has_new_values,
            header=header,
            path=path_obj,
        )
        dataview._original_bytes = raw_bytes
        dataview._original_rows = _rows_snapshot(rows)
        dataview._original_has_new_values = has_new_values
        dataview._original_header = header
        dataview._row_storage_tokens = row_storage_tokens
        return dataview

    def _is_pristine(self) -> bool:
        if self._original_bytes is None:
            return False
        if self._original_has_new_values is None or self._original_header is None:
            return False
        return (
            self.header == self._original_header
            and self.has_new_values == self._original_has_new_values
            and _rows_snapshot(self.rows) == self._original_rows
        )

    def _header_with_current_flag(self) -> str:
        header = self.header or _default_cdv_header(self.has_new_values)
        parts = [p.strip() for p in header.split(",")]
        if not parts:
            return _default_cdv_header(self.has_new_values)
        parts[0] = "-1" if self.has_new_values else "0"
        return ",".join(parts)

    def save(self, path: Path | str | None = None) -> None:
        """Save CDV back to disk, converting native values at the file boundary."""
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("No path provided for save")

        self.has_new_values = any(
            row.new_value is not None for row in self.rows[:MAX_DATAVIEW_ROWS] if not row.is_empty
        )
        self.header = self._header_with_current_flag()

        if self._is_pristine():
            target.write_bytes(self._original_bytes or b"")
            self.path = target
            return

        lines: list[str] = [self.header]
        rows_to_save = list(self.rows[:MAX_DATAVIEW_ROWS])
        while len(rows_to_save) < MAX_DATAVIEW_ROWS:
            rows_to_save.append(DataViewRecord())

        new_storage_tokens: list[str | None] = []
        for row in rows_to_save:
            if row.is_empty:
                lines.append(",0")
                new_storage_tokens.append(None)
                continue

            data_type = (
                row.data_type
                if row.data_type is not None
                else get_data_type_for_address(row.address)
            )
            cdv_code = (
                _CdvStorageCode.INT if data_type is None else _DATA_TYPE_TO_CDV_CODE[data_type]
            )

            if row.new_value is not None:
                if data_type is None:
                    storage_value = str(row.new_value)
                else:
                    storage_value = datatype_to_storage(row.new_value, data_type)
                lines.append(f"{row.address},{cdv_code},{storage_value}")
                new_storage_tokens.append(storage_value)
            else:
                lines.append(f"{row.address},{cdv_code}")
                new_storage_tokens.append(None)

        content = "\n".join(lines) + "\n"
        encoded = content.encode("utf-16")
        target.write_bytes(encoded)
        self.path = target
        self._original_bytes = encoded
        self._original_rows = _rows_snapshot(self.rows)
        self._original_has_new_values = self.has_new_values
        self._original_header = self.header
        self._row_storage_tokens = new_storage_tokens

    def verify(self, path: Path | str | None = None) -> list[str]:
        """Compare this in-memory dataview to a CDV file on disk."""
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("No path provided for verify")

        disk = DataViewFile.load(target)
        issues: list[str] = []

        for i in range(MAX_DATAVIEW_ROWS):
            expected = _row_placeholder(self.rows, i)
            actual = _row_placeholder(disk.rows, i)
            row_num = i + 1

            if expected.address != actual.address:
                issues.append(
                    f"CDV {target.name} row {row_num}: address mismatch "
                    f"(memory={expected.address!r}, file={actual.address!r})"
                )
                continue

            if expected.is_empty and actual.is_empty:
                continue

            if expected.data_type != actual.data_type:
                issues.append(
                    f"CDV {target.name} row {row_num}: data_type mismatch "
                    f"(memory={expected.data_type}, file={actual.data_type})"
                )
                continue

            compare_type = expected.data_type or actual.data_type
            if not _values_equal_for_data_type(expected.new_value, actual.new_value, compare_type):
                issues.append(
                    f"CDV {target.name} row {row_num}: new_value mismatch "
                    f"(memory={expected.new_value!r}, file={actual.new_value!r})"
                )

        if self.has_new_values != disk.has_new_values:
            issues.append(
                f"CDV {target.name}: has_new_values mismatch "
                f"(memory={self.has_new_values}, file={disk.has_new_values})"
            )

        return issues


def read_cdv(path: Path | str) -> DataViewFile:
    """Read a CDV file into a DataViewFile model."""
    return DataViewFile.load(path)


def write_cdv(path: Path | str, dataview: DataViewFile | Iterable[DataViewRecord]) -> None:
    """Write a DataViewFile or list of DataViewRecords to a CDV path."""
    if not isinstance(dataview, DataViewFile):
        dataview = DataViewFile(rows=list(dataview))
    dataview.save(path)


def _validate_cdv_new_value(
    new_value: str,
    data_type: DataType,
    address: str,
    filename: str,
    row_num: int,
) -> list[str]:
    """Validate CDV new_value storage and logical ranges for a row."""
    issues: list[str] = []
    prefix = f"CDV {filename} row {row_num}: {address}"

    try:
        if data_type == DataType.BIT:
            if new_value not in ("0", "1"):
                issues.append(f"{prefix} new_value '{new_value}' invalid for BIT (must be 0 or 1)")
            return issues

        if data_type == DataType.INT:
            raw = int(new_value)
            if raw < 0 or raw > 0xFFFFFFFF:
                issues.append(f"{prefix} new_value '{new_value}' out of range for INT storage")
                return issues
            converted = storage_to_datatype(new_value, data_type)
            if not isinstance(converted, int):
                issues.append(f"{prefix} new_value '{new_value}' failed to convert to INT")
                return issues
            if converted < INT_MIN or converted > INT_MAX:
                issues.append(
                    f"{prefix} new_value converts to {converted}, "
                    f"outside INT range ({INT_MIN} to {INT_MAX})"
                )
            return issues

        if data_type == DataType.INT2:
            raw = int(new_value)
            if raw < 0 or raw > 0xFFFFFFFF:
                issues.append(f"{prefix} new_value '{new_value}' out of range for INT2 storage")
                return issues
            converted = storage_to_datatype(new_value, data_type)
            if not isinstance(converted, int):
                issues.append(f"{prefix} new_value '{new_value}' failed to convert to INT2")
                return issues
            if converted < INT2_MIN or converted > INT2_MAX:
                issues.append(
                    f"{prefix} new_value converts to {converted}, "
                    f"outside INT2 range ({INT2_MIN} to {INT2_MAX})"
                )
            return issues

        if data_type == DataType.HEX:
            raw = int(new_value)
            if raw < 0 or raw > 0xFFFF:
                issues.append(f"{prefix} new_value '{new_value}' out of range for HEX (0-65535)")
            return issues

        if data_type == DataType.FLOAT:
            raw = int(new_value)
            if raw < 0 or raw > 0xFFFFFFFF:
                issues.append(f"{prefix} new_value '{new_value}' invalid for FLOAT storage")
                return issues
            converted = storage_to_datatype(new_value, data_type)
            if not isinstance(converted, float):
                issues.append(f"{prefix} new_value '{new_value}' failed to convert to FLOAT")
                return issues
            if converted < FLOAT_MIN or converted > FLOAT_MAX:
                issues.append(f"{prefix} new_value converts to {converted}, outside FLOAT range")
            return issues

        if data_type == DataType.TXT:
            raw = int(new_value)
            if raw < 0 or raw > 127:
                issues.append(
                    f"{prefix} new_value '{new_value}' out of range for TXT (0-127 ASCII)"
                )
            return issues

    except ValueError:
        issues.append(f"{prefix} new_value '{new_value}' is not a valid number")

    return issues


def check_cdv_file(path: Path | str) -> list[str]:
    """Validate a single CDV file and return issue strings."""
    issues: list[str] = []
    path = Path(path)
    filename = path.name

    try:
        dataview = DataViewFile.load(path)
    except Exception as exc:  # pragma: no cover - exercised by caller tests
        return [f"CDV {filename}: Error loading file - {exc}"]

    for i, row in enumerate(dataview.rows):
        if row.is_empty:
            continue

        row_num = i + 1
        raw_new_value = (
            dataview._row_storage_tokens[i] if i < len(dataview._row_storage_tokens) else None
        )

        try:
            memory_type, _mdb_address = parse_address(row.address)
        except ValueError:
            issues.append(f"CDV {filename} row {row_num}: Invalid address format '{row.address}'")
            continue

        if memory_type not in MEMORY_TYPE_TO_DATA_TYPE:
            issues.append(f"CDV {filename} row {row_num}: Unknown memory type '{memory_type}'")
            continue

        expected_data_type = get_data_type_for_address(row.address)
        if expected_data_type is not None and row.data_type != expected_data_type:
            issues.append(
                f"CDV {filename} row {row_num}: Data type mismatch for {row.address} "
                f"(has {row.data_type}, expected {expected_data_type})"
            )

        if raw_new_value:
            if row.data_type is None:
                issues.append(
                    f"CDV {filename} row {row_num}: {row.address} has new_value but no data_type set"
                )
            else:
                issues.extend(
                    _validate_cdv_new_value(
                        raw_new_value,
                        row.data_type,
                        row.address,
                        filename,
                        row_num,
                    )
                )
            if not is_address_writable(row.address):
                issues.append(
                    f"CDV {filename} row {row_num}: {row.address} has new_value "
                    f"but address is not writable"
                )

    return issues


def verify_cdv(
    path: Path | str,
    rows: list[DataViewRecord],
    has_new_values: bool | None = None,
) -> list[str]:
    """Verify in-memory rows against a CDV file using native value comparison."""
    has_values = has_new_values
    if has_values is None:
        has_values = any(
            row.new_value is not None for row in rows[:MAX_DATAVIEW_ROWS] if not row.is_empty
        )

    dataview = DataViewFile(
        rows=rows,
        has_new_values=has_values,
        header=_default_cdv_header(has_values),
        path=Path(path),
    )
    return dataview.verify(path)
