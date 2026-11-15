"""Read / write Click PLC 'Read Data from PLC' CSV dump files.

The Click Programming Software can export a full snapshot of PLC memory
via PLC > Read Data from PLC... > All > Save, and reload it via
PLC > Write Data into PLC > File Select.  This module handles both
directions.
"""

from __future__ import annotations

import math
import re
import string
import struct
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

from .addresses import format_address_display, parse_address
from .banks import BANKS, DataType, is_valid_address

_SECTION_START = re.compile(r"^<(\w+)=START>$")
_SECTION_END = re.compile(r"^</(\w+)=END>$")

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

# CLICK writes a DF value it can't show as a number (a NaN or an infinity) as this.
_DF_ERROR = "Err-Format"

# CLICK writes a DF value in fixed point with 8 decimals, and with no more than 40 digits
# in all (3e38 has one decimal). It keeps as many leading digits as fit in an unsigned
# 64-bit integer and writes zeros after them: 20 for 1e30, 19 for 3e38.
_DF_DECIMALS = 8
_DF_MAX_DIGITS = 40
_DF_KEPT_LIMIT = 2**64

# CLICK writes a TXT space, control character or byte above 0x7E as "$" and its code in
# uppercase hex without leading zeros ("$20", "$D", "$C8"), and other characters plain.
_TXT_ESCAPE = re.compile(r"\$([0-9A-Fa-f]{1,2})")
# The characters a CLICK dump shows plain. Other printable ASCII (such as "," "$" '"')
# raises on write until a CLICK dump shows its form.
_TXT_PLAIN = frozenset(string.ascii_letters + string.digits + "+-.")

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
        return math.nan if raw == _DF_ERROR else float(raw)
    if data_type == DataType.HEX:
        return int(raw, 16)
    if data_type == DataType.TXT:
        escaped = _TXT_ESCAPE.fullmatch(raw)
        return chr(int(escaped.group(1), 16)) if escaped else raw
    return raw  # pragma: no cover


def read_plc_data(
    path: str | Path,
    *,
    skip_default: bool = False,
) -> dict[str, bool | int | float | str]:
    """Parse a Click PLC 'Read Data from PLC' CSV dump.

    Args:
        path: Path to the CSV file exported from Click Programming Software
              via PLC > Read Data from PLC... > All > Save.
        skip_default: If *True*, omit addresses whose value equals the bank
              default (``False`` for bits, ``0`` for ints, ``0.0`` for floats,
              ``""`` for text).

    Returns:
        Dict mapping normalized address strings (e.g. ``"X001"``, ``"DS1"``)
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

        # Data row: its first address, then one cell per header offset
        try:
            prefix, start_num = parse_address(parts[0])
        except ValueError:
            continue
        values = parts[1:]

        for i, raw in enumerate(values):
            if i >= len(col_offsets):
                break
            addr_num = start_num + col_offsets[i] - 1
            if not is_valid_address(prefix, addr_num):
                continue
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

            result[format_address_display(prefix, addr_num)] = value

    return result


def _format_float(value: bool | int | float | str, addr: str) -> str:
    """Format a DF value as CLICK does: the float32 value in CLICK's fixed point."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{addr} value {number} has no number form in a CLICK data file.")
    try:
        (single,) = struct.unpack("<f", struct.pack("<f", number))
    except OverflowError:
        raise ValueError(f"{addr} value {number} is outside the float32 range.") from None
    exact = Decimal(single)
    decimals = min(_DF_DECIMALS, _DF_MAX_DIGITS - len(str(int(abs(exact)))))
    with localcontext() as ctx:
        ctx.prec = _DF_MAX_DIGITS + _DF_DECIMALS
        exponent = -_DF_DECIMALS
        while abs(exact).scaleb(-exponent) >= _DF_KEPT_LIMIT:
            exponent += 1
        rounded = exact.quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_EVEN)
    return f"{rounded:.{decimals}f}"


def _format_text(value: bool | int | float | str, addr: str) -> str:
    """Format a TXT value as CLICK does: plain, or ``$`` and its code in hex."""
    if value == "" or value == "\x00":
        return ""
    if not isinstance(value, str) or len(value) != 1 or ord(value) > 0xFF:
        raise ValueError(f"{addr} value {value!r} is not a single character with code 0..255.")
    if value in _TXT_PLAIN:
        return value
    code = ord(value)
    if code <= 0x20 or code >= 0x7F:
        return f"${code:X}"
    raise ValueError(
        f"{addr} value {value!r}: the form CLICK writes for this character is not known."
    )


def _format_value(value: bool | int | float | str, data_type: DataType, addr: str) -> str:
    """Format a native Python value as a CSV cell."""
    if data_type == DataType.BIT:
        return "1" if value else "0"
    if data_type in (DataType.INT, DataType.INT2):
        return str(int(value))
    if data_type == DataType.FLOAT:
        return _format_float(value, addr)
    if data_type == DataType.HEX:
        return format(int(value), "x")
    if data_type == DataType.TXT:
        return _format_text(value, addr)
    return str(value)  # pragma: no cover


def write_plc_data(
    path: str | Path,
    data: Mapping[str, bool | int | float | str],
    *,
    banks: Iterable[str] | None = None,
) -> None:
    """Write a Click PLC data CSV to load via PLC > Write Data into PLC > File Select.

    Args:
        path: Output file path.
        data: Dict mapping normalized address strings (e.g. ``"X001"``,
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
            try:
                bank, _ = parse_address(addr)
            except ValueError:
                continue
            if bank not in seen:
                seen.add(bank)
                selected.append(bank)
        # Sort to match canonical section order
        order = {name: i for i, name in enumerate(_SECTION_ORDER)}
        selected.sort(key=lambda b: order.get(b, len(order)))

    lines: list[str] = []

    for bank_name in selected:
        cfg = BANKS[bank_name]
        dt = cfg.data_type

        lines.append(f"<{bank_name}=START>")

        if bank_name in ("X", "Y"):
            hdr = ",".join(str(c) for c in _XY_HEADER_OFFSETS)
            lines.append(f"Address,{hdr},")

            for j, start in enumerate(_XY_ROW_STARTS):
                offsets = _XY_BASE_OFFSETS if j == 0 else _XY_EXPANSION_OFFSETS
                vals: list[str] = []
                for off in offsets:
                    addr = format_address_display(bank_name, start + off - 1)
                    vals.append(_format_value(data.get(addr, _DEFAULTS[dt]), dt, addr))
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
                    vals.append(_format_value(data.get(addr, _DEFAULTS[dt]), dt, addr))
                lines.append(f"{bank_name}{start},{','.join(vals)},")

        # CLICK follows every section, the last one too, with a blank line.
        lines.append(f"</{bank_name}=END>")
        lines.append("")

    # Every cell is ASCII once TXT is escaped; CLICK ends every line with CRLF.
    Path(path).write_bytes("".join(f"{line}\r\n" for line in lines).encode("ascii"))
