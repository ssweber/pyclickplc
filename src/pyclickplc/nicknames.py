"""CSV read/write for CLICK PLC address nicknames.

Reads and writes the nickname CSV that CLICK Programming Software exports and
imports, using AddressRecord as the data model.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, TypeVar, cast, overload

from .addresses import AddressNormalizerMixin, AddressRecord, get_addr_key, parse_address
from .banks import (
    BANKS,
    DEFAULT_RETENTIVE,
    MEMORY_TYPE_BASES,
    MEMORY_TYPE_TO_DATA_TYPE,
    DataType,
    is_valid_address,
)

# CSV column names (matching CLICK software export format)
CSV_COLUMNS = ["Address", "Data Type", "Nickname", "Initial Value", "Retentive", "Address Comment"]

# CLICK exports a Text initial value bare, even a comma or a double quote, which
# breaks CSV parsing. The value is one character between the always-quoted
# Nickname and Retentive, so such a row is found by position and requoted.
_CLICK_RAW_TXT_ROW = re.compile(
    r'^(?P<head>[^,\r\n]+,(?:TEXT|TXT),"(?:[^"\r\n]|"")*",)'
    r'(?P<char>[,"])'
    r'(?P<tail>,(?:Yes|No),"(?:[^"\r\n]|"")*")(?=\r?$)',
    re.MULTILINE | re.IGNORECASE,
)


def _requote_click_raw_txt(text: str) -> str:
    """Quote a bare comma or double quote Text initial value in CLICK's export."""
    if text.split("\n", 1)[0].rstrip("\r") != ",".join(CSV_COLUMNS):
        return text

    def requote(match: re.Match[str]) -> str:
        char = match["char"].replace('"', '""')
        return f'{match["head"]}"{char}"{match["tail"]}'

    return _CLICK_RAW_TXT_ROW.sub(requote, text)


# Data type string to code mapping
DATA_TYPE_STR_TO_CODE: dict[str, int] = {
    "BIT": 0,
    "INT": 1,
    "INT2": 2,
    "FLOAT": 3,
    "HEX": 4,
    "TXT": 6,
    "TEXT": 6,  # Alias
}

# Data type code to string mapping (for saving csv)
DATA_TYPE_CODE_TO_STR: dict[int, str] = {
    0: "BIT",
    1: "INT",
    2: "INT2",
    3: "FLOAT",
    4: "HEX",
    6: "TEXT",
}

_DefaultT = TypeVar("_DefaultT")


class AddressLookupView(AddressNormalizerMixin):
    """Address-indexed view over an AddressRecordMap."""

    def __init__(self, records: AddressRecordMap) -> None:
        self._records = records

    def __getitem__(self, address: str) -> AddressRecord:
        normalized = self._normalize_address(address)
        if normalized is None:
            raise KeyError(address)
        self._records._ensure_indexes()
        if normalized not in self._records._address_index:
            raise KeyError(address)
        return self._records._address_index[normalized]

    def __contains__(self, address: object) -> bool:
        if not isinstance(address, str):
            return False
        normalized = self._normalize_address(address)
        if normalized is None:
            return False
        self._records._ensure_indexes()
        return normalized in self._records._address_index

    def get(self, address: str, default: Any = None) -> AddressRecord | Any:
        try:
            return self[address]
        except KeyError:
            return default


class TagLookupView:
    """Case-insensitive nickname-indexed view over an AddressRecordMap."""

    def __init__(self, records: AddressRecordMap) -> None:
        self._records = records

    def __getitem__(self, nickname: str) -> AddressRecord:
        self._records._ensure_indexes()
        if self._records._tag_collision_error is not None:
            raise ValueError(self._records._tag_collision_error)
        lowered = nickname.lower()
        if lowered not in self._records._tag_index:
            raise KeyError(nickname)
        return self._records._tag_index[lowered]

    def __contains__(self, nickname: object) -> bool:
        if not isinstance(nickname, str):
            return False
        self._records._ensure_indexes()
        if self._records._tag_collision_error is not None:
            raise ValueError(self._records._tag_collision_error)
        return nickname.lower() in self._records._tag_index

    def get(self, nickname: str, default: Any = None) -> AddressRecord | Any:
        try:
            return self[nickname]
        except KeyError:
            return default


class AddressRecordMap(dict[int, AddressRecord]):
    """Address record mapping with helper lookup views."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._address_index: dict[str, AddressRecord] = {}
        self._tag_index: dict[str, AddressRecord] = {}
        self._tag_collision_error: str | None = None
        self._index_dirty = True
        # The columns of the file it was read from; empty when not read from a file
        self.columns: tuple[str, ...] = ()
        self.addr = AddressLookupView(self)
        self.tag = TagLookupView(self)

    def _mark_dirty(self) -> None:
        self._index_dirty = True

    def _ensure_indexes(self) -> None:
        if not self._index_dirty:
            return
        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        address_index: dict[str, AddressRecord] = {}
        tag_index: dict[str, AddressRecord] = {}
        first_seen_tag: dict[str, tuple[str, str]] = {}
        collisions: list[tuple[str, str, str, str, str]] = []

        for record in self.values():
            address_index[record.display_address] = record
            nickname = record.nickname.strip()
            if nickname == "":
                continue
            key = nickname.lower()
            if key in first_seen_tag:
                first_nickname, first_address = first_seen_tag[key]
                collisions.append(
                    (key, first_nickname, first_address, nickname, record.display_address)
                )
                continue
            first_seen_tag[key] = (nickname, record.display_address)
            tag_index[key] = record

        if collisions:
            parts = []
            for key, first_nickname, first_address, nickname, address in collisions[:5]:
                parts.append(
                    f"{key!r}: {first_nickname!r}@{first_address} conflicts with {nickname!r}@{address}"
                )
            extra = f" (+{len(collisions) - 5} more)" if len(collisions) > 5 else ""
            self._tag_collision_error = (
                "Case-insensitive duplicate tag nickname(s) in AddressRecordMap: "
                + "; ".join(parts)
                + extra
            )
        else:
            self._tag_collision_error = None

        self._address_index = address_index
        self._tag_index = tag_index
        self._index_dirty = False

    # -- mutation hooks -----------------------------------------------------
    def __setitem__(self, key: int, value: AddressRecord) -> None:
        super().__setitem__(key, value)
        self._mark_dirty()

    def __delitem__(self, key: int) -> None:
        super().__delitem__(key)
        self._mark_dirty()

    def clear(self) -> None:
        super().clear()
        self._mark_dirty()

    @overload
    def pop(self, key: object) -> AddressRecord: ...

    @overload
    def pop(self, key: object, default: _DefaultT) -> AddressRecord | _DefaultT: ...

    def pop(self, key: object, default: Any = ...) -> Any:
        typed_key = cast(int, key)
        if default is ...:
            value = super().pop(typed_key)
        else:
            value = super().pop(typed_key, default)
        self._mark_dirty()
        return value

    def popitem(self) -> tuple[int, AddressRecord]:
        value = super().popitem()
        self._mark_dirty()
        return value

    def setdefault(self, key: int, default: Any = None) -> Any:
        value = super().setdefault(key, default)
        self._mark_dirty()
        return value

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        self._mark_dirty()


# Retentive as CLICK writes it (Yes) and as a spreadsheet may (True, 1)
_RETENTIVE_ON = frozenset({"yes", "true", "1"})

# A nickname CSV must have these columns unless the caller asks for fewer
REQUIRED_COLUMNS = ("Address", "Nickname")


def _is_blank(row: Mapping[str | None, str | list[str] | None]) -> bool:
    """A row with nothing in any cell, such as a spreadsheet's trailing ``,,,,,``."""
    cells = [
        cell for value in row.values() for cell in (value if isinstance(value, list) else [value])
    ]
    return not any((cell or "").strip() for cell in cells)


def _initial_value(raw: str, data_type: int) -> str:
    """A Text initial value is kept as written (a space is a value); others are trimmed."""
    return raw if data_type == DataType.TXT else raw.strip()


def read_csv(path: str | Path, *, required: Iterable[str] = REQUIRED_COLUMNS) -> AddressRecordMap:
    """Read a nickname CSV file into AddressRecords.

    The CSV has columns: Address, Data Type, Nickname, Initial Value,
    Retentive, Address Comment. A UTF-8 byte order mark is accepted. Nickname,
    Address Comment and a Text initial value are kept as written, spaces
    included. A Text initial value may be quoted, or bare as CLICK exports it,
    even when it is a comma or a double quote. Retentive is on for ``Yes``,
    ``True`` or ``1`` in any case. Blank rows are skipped. A nickname that
    repeats does not fail the read; looking it up through ``.tag`` raises.

    The columns the file had are in the result's ``columns``; a missing
    optional column, or a blank cell in it, leaves its default (a blank Data
    Type is the bank's own).

    Raises:
        ValueError: If a *required* column is missing, a row's Address is not
            a CLICK address, its Data Type is not one CLICK writes (BIT, INT,
            INT2, FLOAT, HEX, TEXT; TXT is accepted too), or the file is not
            UTF-8 or not CSV. The message names the file and, for a row, its
            line.

    Args:
        path: Path to the CSV file.
        required: Columns the file must have. Defaults to Address and Nickname.

    Returns:
        AddressRecordMap keyed by addr_key (int) with ``.addr`` and ``.tag`` views.
    """
    name = Path(path).name
    result = AddressRecordMap()

    try:
        with open(path, newline="", encoding="utf-8-sig") as csvfile:
            text = _requote_click_raw_txt(csvfile.read())
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} is not UTF-8 text: {exc}") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    try:
        columns = tuple(reader.fieldnames or ())
        missing = [column for column in required if column not in columns]
        if missing:
            raise ValueError(f"{name} is missing required column(s): {', '.join(missing)}")
        result.columns = columns

        for row in reader:
            if _is_blank(row):
                continue
            addr_str = row.get("Address") or ""
            try:
                mem_type, mdb_address = parse_address(addr_str)
            except ValueError:
                raise ValueError(
                    f"{name} line {reader.line_num}: Address {addr_str!r} is not a CLICK address"
                ) from None

            data_type_str = (row.get("Data Type") or "").strip()
            if not data_type_str:
                data_type = MEMORY_TYPE_TO_DATA_TYPE[mem_type]
            elif data_type_str.upper() in DATA_TYPE_STR_TO_CODE:
                data_type = DataType(DATA_TYPE_STR_TO_CODE[data_type_str.upper()])
            else:
                raise ValueError(
                    f"{name} line {reader.line_num}: Data Type {data_type_str!r} is not a "
                    f"CLICK data type"
                )

            retentive_str = (row.get("Retentive") or "").strip()
            retentive = (
                retentive_str.lower() in _RETENTIVE_ON
                if retentive_str
                else DEFAULT_RETENTIVE.get(mem_type, False)
            )

            result[get_addr_key(mem_type, mdb_address)] = AddressRecord(
                memory_type=mem_type,
                address=mdb_address,
                nickname=row.get("Nickname") or "",
                comment=row.get("Address Comment") or "",
                initial_value=_initial_value(row.get("Initial Value") or "", data_type),
                retentive=retentive,
                data_type=data_type,
            )
    except csv.Error as exc:
        raise ValueError(f"{name} line {reader.line_num}: {exc}") from exc

    return result


def _format_csv(
    records: Mapping[int, AddressRecord] | Iterable[AddressRecord],
) -> tuple[str, int]:
    """The nickname CSV text for *records*, and how many rows it holds."""
    record_iter: Iterable[AddressRecord]
    if isinstance(records, Mapping):
        record_iter = cast(Iterable[AddressRecord], records.values())
    else:
        record_iter = records

    rows_to_write = [record for record in record_iter if record.has_content]
    rows_to_write.sort(
        key=lambda record: (
            MEMORY_TYPE_BASES.get(record.memory_type, 0xFFFFFFFF),
            record.address,
        )
    )

    def format_quoted(text: str) -> str:
        return '"' + text.replace('"', '""') + '"'

    lines = [",".join(CSV_COLUMNS)]
    for record in rows_to_write:
        # A defaulted numeric is written "0", as CLICK does; Text's default is empty
        if record.initial_value:
            initial_value_str = str(record.initial_value)
            if record.data_type == DataType.TXT and any(
                char in initial_value_str for char in ',"\r\n'
            ):
                initial_value_str = format_quoted(initial_value_str)
        elif record.data_type == DataType.TXT:
            initial_value_str = ""
        else:
            initial_value_str = "0"

        lines.append(
            ",".join(
                [
                    record.display_address,
                    DATA_TYPE_CODE_TO_STR.get(record.data_type, ""),
                    format_quoted(record.nickname),
                    initial_value_str,
                    "Yes" if record.retentive else "No",
                    format_quoted(record.comment),
                ]
            )
        )

    return "".join(line + "\r\n" for line in lines), len(rows_to_write)


def format_csv(records: Mapping[int, AddressRecord] | Iterable[AddressRecord]) -> str:
    """Return the nickname CSV text that ``write_csv`` writes for *records*.

    For a caller that writes the file itself: encode it as UTF-8 without a
    byte order mark and write it unchanged (lines already end in CRLF).
    """
    return _format_csv(records)[0]


def write_csv(
    path: str | Path,
    records: Mapping[int, AddressRecord] | Iterable[AddressRecord],
) -> int:
    """Write AddressRecords to a nickname CSV file.

    Only records with content (nickname, comment, non-default initial value
    or retentive) are written. Records are sorted by memory type order then
    address. Lines end in CRLF and a Text initial value is bare, as in CLICK's
    export. A Text initial value holding a comma, double quote or line break is
    quoted: CLICK exports a comma or double quote bare but can only import it
    quoted.

    Args:
        path: Path to write the CSV file.
        records: Address records to write. Accepts a mapping keyed by addr_key
            or any iterable of AddressRecord values.

    Returns:
        Number of rows written.
    """
    text, count = _format_csv(records)
    with open(path, "w", newline="", encoding="utf-8") as csvfile:
        csvfile.write(text)
    return count


def read_mdb_csv(path: str | Path) -> AddressRecordMap:
    """Read CLICK's ``Address.csv`` into AddressRecords.

    CLICK writes this file beside its project database, as UTF-8 with a byte
    order mark, with columns AddrKey, MemoryType, Address, DataType, Nickname,
    Use, InitialValue, Retentive, Comment. Address is the MDB address (XD1 is
    2), and DataType, Use and Retentive are numbers. Only rows with content
    are kept. A row whose MemoryType or Address pyclickplc does not know is
    skipped.

    Args:
        path: Path to the Address.csv file.

    Returns:
        AddressRecordMap keyed by addr_key (int) with ``.addr`` and ``.tag`` views.
        ``used`` is True or False from the Use column, None where it is blank.
    """
    result = AddressRecordMap()

    with open(path, newline="", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)
        result.columns = tuple(reader.fieldnames or ())
        for row in reader:
            mem_type = (row.get("MemoryType") or "").strip()
            if mem_type not in BANKS:
                continue
            try:
                address = int(row.get("Address") or "")
            except ValueError:
                continue
            if mem_type in ("XD", "YD"):
                if not BANKS[mem_type].min_addr <= address <= BANKS[mem_type].max_addr:
                    continue
            elif not is_valid_address(mem_type, address):
                continue

            try:
                data_type = DataType(int(row.get("DataType") or ""))
            except ValueError:
                data_type = MEMORY_TYPE_TO_DATA_TYPE[mem_type]

            retentive_raw = (row.get("Retentive") or "").strip()
            retentive = (
                retentive_raw == "1" if retentive_raw else DEFAULT_RETENTIVE.get(mem_type, False)
            )
            used_raw = (row.get("Use") or "").strip()

            record = AddressRecord(
                memory_type=mem_type,
                address=address,
                nickname=row.get("Nickname") or "",
                comment=row.get("Comment") or "",
                initial_value=_initial_value(row.get("InitialValue") or "", data_type),
                retentive=retentive,
                data_type=data_type,
                used=used_raw == "1" if used_raw else None,
            )
            if record.has_content:
                result[get_addr_key(mem_type, address)] = record

    return result
