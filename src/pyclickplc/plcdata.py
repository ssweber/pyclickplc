"""Read / write Click PLC 'Read Data from PLC' CSV dump files.

The Click Programming Software can export a full snapshot of PLC memory
via Data > Read Data from PLC > Save to File, and reload it via
Data > Write Data into PLC > Load from File.  This module handles both
directions.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from .addresses import format_address_display
from .banks import BANKS, DataType

_SECTION_START = re.compile(r"^<(\w+)=START>$")
_SECTION_END = re.compile(r"^</(\w+)=END>$")
_ROW_ADDR = re.compile(r"^([A-Z]+)(\d+)$")

# Section order matches Click Programming Software export
_SECTION_ORDER: tuple[str, ...] = (
    "X",
    "Y",
    "C",
    "T",
    "CT",
    "DS",
    "DD",
    "DH",
    "DF",
    "TD",
    "CTD",
    "TXT",
)

# X/Y layout: base unit row covers 1-16 + 21-36, expansion rows cover 1-16
_XY_HEADER_OFFSETS = list(range(1, 17)) + list(range(21, 37))
_XY_BASE_OFFSETS = _XY_HEADER_OFFSETS  # 32 columns for first row
_XY_EXPANSION_OFFSETS = list(range(1, 17))  # 16 columns for expansion rows
_XY_ROW_STARTS = (1, 101, 201, 301, 401, 501, 601, 701, 801)

# Standard banks: 10 addresses per row
_STD_STRIDE = 10
_STD_HEADER_OFFSETS = list(range(1, _STD_STRIDE + 1))

# Defaults per data type (used by skip_default)
_DEFAULTS: dict[DataType, bool | int | float | str] = {
    DataType.BIT: False,
    DataType.INT: 0,
    DataType.INT2: 0,
    DataType.HEX: 0,
    DataType.FLOAT: 0.0,
    DataType.TXT: "",
}


def _parse_value(raw: str, data_type: DataType) -> bool | int | float | str:
    """Convert a raw CSV cell to a native Python value."""
    if data_type == DataType.BIT:
        return raw.strip() == "1"
    if data_type in (DataType.INT, DataType.INT2):
        return int(raw)
    if data_type == DataType.FLOAT:
        return float(raw)
    if data_type == DataType.HEX:
        return int(raw, 16)
    if data_type == DataType.TXT:
        return raw
    return raw  # pragma: no cover


def read_plc_data(
    path: str | Path,
    *,
    skip_default: bool = False,
) -> dict[str, bool | int | float | str]:
    """Parse a Click PLC 'Read Data from PLC' CSV dump.

    Args:
        path: Path to the CSV file exported from Click Programming Software
              via Data > Read Data from PLC > Save to File.
        skip_default: If *True*, omit addresses whose value equals the bank
              default (``False`` for bits, ``0`` for ints, ``0.0`` for floats,
              ``""`` for text).

    Returns:
        Dict mapping normalised address strings (e.g. ``"X001"``, ``"DS1"``)
        to native Python values (``bool`` for bits, ``int`` for INT/INT2/HEX,
        ``float`` for FLOAT, ``str`` for TXT).
    """
    text = Path(path).read_text()
    lines = text.splitlines()

    result: dict[str, bool | int | float | str] = {}
    bank_name: str | None = None
    col_offsets: list[int] = []
    data_type: DataType | None = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Section start
        m = _SECTION_START.match(line)
        if m:
            bank_name = m.group(1)
            cfg = BANKS.get(bank_name)
            data_type = cfg.data_type if cfg else None
            col_offsets = []
            continue

        # Section end
        if _SECTION_END.match(line):
            bank_name = None
            col_offsets = []
            data_type = None
            continue

        if bank_name is None or data_type is None:
            continue

        # Strip the single trailing comma that the format always appends
        parts = line[:-1].split(",") if line.endswith(",") else line.split(",")

        # Header row
        if parts[0] == "Address":
            col_offsets = [int(x) for x in parts[1:] if x.strip()]
            continue

        # Data row
        m = _ROW_ADDR.match(parts[0])
        if not m:
            continue

        prefix = m.group(1)
        start_num = int(m.group(2))
        values = parts[1:]

        for i, raw in enumerate(values):
            if i >= len(col_offsets):
                break
            raw = raw.strip()
            if not raw:
                if data_type == DataType.TXT:
                    value: bool | int | float | str = ""
                else:
                    continue
            else:
                value = _parse_value(raw, data_type)

            if skip_default and value == _DEFAULTS.get(data_type):
                continue

            addr_num = start_num + col_offsets[i] - 1
            address = format_address_display(prefix, addr_num)
            result[address] = value

    return result


def _format_value(value: bool | int | float | str, data_type: DataType) -> str:
    """Format a native Python value as a CSV cell."""
    if data_type == DataType.BIT:
        return "1" if value else "0"
    if data_type in (DataType.INT, DataType.INT2):
        return str(int(value))
    if data_type == DataType.FLOAT:
        return f"{float(value):.8f}"
    if data_type == DataType.HEX:
        return format(int(value), "x")
    if data_type == DataType.TXT:
        return str(value) if value else ""
    return str(value)  # pragma: no cover


def write_plc_data(
    path: str | Path,
    data: Mapping[str, bool | int | float | str],
    *,
    banks: Iterable[str] | None = None,
) -> None:
    """Write a Click PLC data CSV that can be loaded via Write Data into PLC.

    Args:
        path: Output file path.
        data: Dict mapping normalised address strings (e.g. ``"X001"``,
              ``"DS1"``) to native Python values — the same format
              :func:`read_plc_data` returns.
        banks: Bank names to include (e.g. ``["DS", "DF"]``).  *None*
              (default) writes every bank present in *data*.  Pass
              :data:`ALL_BANKS` to force a full dump with defaults.
    """
    if banks is not None:
        selected = list(banks)
    else:
        # Infer banks from data keys
        selected = []
        seen: set[str] = set()
        for addr in data:
            m = _ROW_ADDR.match(addr.split()[0] if " " in addr else addr)
            if not m:
                # Normalised X/Y addresses like "X001" — strip digits
                prefix = re.match(r"^([A-Z]+)", addr)
                bank = prefix.group(1) if prefix else None
            else:
                bank = m.group(1)
            if bank and bank in BANKS and bank not in seen:
                seen.add(bank)
                selected.append(bank)
        # Sort to match canonical section order
        order = {name: i for i, name in enumerate(_SECTION_ORDER)}
        selected.sort(key=lambda b: order.get(b, len(order)))

    lines: list[str] = []

    for i, bank_name in enumerate(selected):
        cfg = BANKS[bank_name]
        dt = cfg.data_type

        if i > 0:
            lines.append("")  # blank line between sections

        lines.append(f"<{bank_name}=START>")

        if bank_name in ("X", "Y"):
            hdr = ",".join(str(c) for c in _XY_HEADER_OFFSETS)
            lines.append(f"Address,{hdr},")

            for j, start in enumerate(_XY_ROW_STARTS):
                offsets = _XY_BASE_OFFSETS if j == 0 else _XY_EXPANSION_OFFSETS
                vals: list[str] = []
                for off in offsets:
                    addr = format_address_display(bank_name, start + off - 1)
                    vals.append(_format_value(data.get(addr, _DEFAULTS[dt]), dt))
                lines.append(f"{bank_name}{start},{','.join(vals)},")
        else:
            hdr = ",".join(str(c) for c in _STD_HEADER_OFFSETS)
            lines.append(f"Address,{hdr},")

            for start in range(cfg.min_addr, cfg.max_addr + 1, _STD_STRIDE):
                vals = []
                for off in range(1, _STD_STRIDE + 1):
                    addr_num = start + off - 1
                    if addr_num > cfg.max_addr:
                        break
                    addr = format_address_display(bank_name, addr_num)
                    vals.append(_format_value(data.get(addr, _DEFAULTS[dt]), dt))
                lines.append(f"{bank_name}{start},{','.join(vals)},")

        lines.append(f"</{bank_name}=END>")

    lines.append("")  # trailing newline
    Path(path).write_text("\n".join(lines))
