"""CSV read/write for CLICK PLC address nicknames.

Provides functions to read and write address data in CLICK software CSV format
(user-facing) and MDB-dump CSV format, using AddressRecord as the data model.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from .addresses import AddressNormalizerMixin, AddressRecord, get_addr_key, parse_address
from .banks import BANKS, DEFAULT_RETENTIVE, MEMORY_TYPE_BASES, MEMORY_TYPE_TO_DATA_TYPE, DataType

# CSV column names (matching CLICK software export format)
CSV_COLUMNS = ["Address", "Data Type", "Nickname", "Initial Value", "Retentive", "Address Comment"]

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

    def pop(self, key: int, default: Any = ...):
        if default is ...:
            value = super().pop(key)
        else:
            value = super().pop(key, default)
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


def read_csv(path: str | Path) -> AddressRecordMap:
    """Read a user-format CSV file into AddressRecords.

    The user CSV has columns: Address, Data Type, Nickname, Initial Value,
    Retentive, Address Comment.

    Args:
        path: Path to the CSV file.

    Returns:
        AddressRecordMap keyed by addr_key (int) with ``.addr`` and ``.tag`` views.
    """
    result = AddressRecordMap()
    seen_nicknames: dict[str, tuple[str, str, int]] = {}

    with open(path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            addr_str = row.get("Address", "").strip()
            if not addr_str:
                continue

            try:
                mem_type, mdb_address = parse_address(addr_str)
            except ValueError:
                continue

            if mem_type not in BANKS:
                continue

            # Get data type (default based on memory type)
            default_data_type = MEMORY_TYPE_TO_DATA_TYPE.get(mem_type, 0)
            data_type_str = row.get("Data Type", "").strip().upper()
            data_type = DATA_TYPE_STR_TO_CODE.get(data_type_str, default_data_type)

            # Get retentive
            default_retentive = DEFAULT_RETENTIVE.get(mem_type, False)
            retentive_str = row.get("Retentive", "").strip()
            retentive = retentive_str.lower() == "yes" if retentive_str else default_retentive

            # Get other fields
            nickname = row.get("Nickname", "").strip()
            comment = row.get("Address Comment", "").strip()
            initial_value = row.get("Initial Value", "").strip()

            if nickname:
                key = nickname.lower()
                if key in seen_nicknames:
                    first_nickname, first_address, first_line = seen_nicknames[key]
                    raise ValueError(
                        "Case-insensitive duplicate nickname in CSV at "
                        f"line {reader.line_num}: {nickname!r} at {addr_str} "
                        f"conflicts with {first_nickname!r} at {first_address} "
                        f"(line {first_line})."
                    )
                seen_nicknames[key] = (nickname, addr_str, reader.line_num)

            addr_key = get_addr_key(mem_type, mdb_address)

            record = AddressRecord(
                memory_type=mem_type,
                address=mdb_address,
                nickname=nickname,
                comment=comment,
                initial_value=initial_value,
                retentive=retentive,
                data_type=data_type,
            )

            result[addr_key] = record

    return result


def write_csv(
    path: str | Path,
    records: Mapping[int, AddressRecord] | Iterable[AddressRecord],
) -> int:
    """Write AddressRecords to a user-format CSV file.

    Only records with content (nickname, comment, non-default initial value
    or retentive) are written. Records are sorted by memory type order then
    address.

    Args:
        path: Path to write the CSV file.
        records: Address records to write. Accepts a mapping keyed by addr_key
            or any iterable of AddressRecord values.

    Returns:
        Number of rows written.
    """
    # Collect records with content, sorted by memory type order and address
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

    with open(path, "w", newline="", encoding="utf-8") as csvfile:
        # Write header manually (matching CLICK format)
        csvfile.write(",".join(CSV_COLUMNS) + "\n")

        def format_quoted(text: str | None) -> str:
            if text is None:
                return '""'
            escaped_text = str(text).replace('"', '""')
            return f'"{escaped_text}"'

        for record in rows_to_write:
            data_type_str = DATA_TYPE_CODE_TO_STR.get(record.data_type, "")

            # Format initial value: use "0" for numeric types when empty, "" for TXT
            if record.initial_value:
                initial_value_str = str(record.initial_value)
            elif record.data_type == DataType.TXT:
                initial_value_str = ""
            else:
                initial_value_str = "0"

            line_parts = [
                record.display_address,
                data_type_str,
                format_quoted(record.nickname),
                initial_value_str,
                "Yes" if record.retentive else "No",
                format_quoted(record.comment),
            ]

            csvfile.write(",".join(line_parts) + "\n")

    return len(rows_to_write)
