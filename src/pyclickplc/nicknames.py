"""CSV read/write for CLICK PLC address nicknames.

Provides functions to read and write address data in CLICK software CSV format
(user-facing) and MDB-dump CSV format, using AddressRecord as the data model.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .addresses import AddressRecord, get_addr_key, parse_address
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


def read_csv(path: str | Path) -> dict[int, AddressRecord]:
    """Read a user-format CSV file into AddressRecords.

    The user CSV has columns: Address, Data Type, Nickname, Initial Value,
    Retentive, Address Comment.

    Args:
        path: Path to the CSV file.

    Returns:
        Dict mapping addr_key (int) to AddressRecord.
    """
    result: dict[int, AddressRecord] = {}

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


def write_csv(path: str | Path, records: dict[int, AddressRecord]) -> int:
    """Write AddressRecords to a user-format CSV file.

    Only records with content (nickname, comment, non-default initial value
    or retentive) are written. Records are sorted by memory type order then
    address.

    Args:
        path: Path to write the CSV file.
        records: Dict mapping addr_key to AddressRecord.

    Returns:
        Number of rows written.
    """
    # Collect records with content, sorted by memory type order and address
    rows_to_write = sorted(
        (r for r in records.values() if r.has_content),
        key=lambda r: (MEMORY_TYPE_BASES.get(r.memory_type, 0xFFFFFFFF), r.address),
    )

    with open(path, "w", newline="", encoding="utf-8") as csvfile:
        # Write header manually (matching CLICK format)
        csvfile.write(",".join(CSV_COLUMNS) + "\n")

        def format_quoted(text):
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


