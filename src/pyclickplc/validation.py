"""Validation functions for PLC address data.

This module validates nicknames, comments, initial values, and PLC and DataView names
against CLICK PLC rules.
"""

from __future__ import annotations

import math
import re
import struct

from .banks import (
    DataType,
)

# ==============================================================================
# Constants
# ==============================================================================

NICKNAME_MAX_LENGTH = 24
COMMENT_MAX_LENGTH = 128

# A PLC or DataView name may contain letters, digits, spaces, underscores and hyphens.
CLICK_NAME_MAX_LENGTH = 24
CLICK_NAME_PATTERN = re.compile(r"[A-Za-z0-9_\- ]+")

# The memory types whose nicknames may start with _. A name that starts with _ is one that
# the PLC system generated. SC and SD addresses have names that the system presets. X
# addresses get generated names for feedback signals, such as _IO1_Module_Error, when an
# analog input card is installed.
SYSTEM_NICKNAME_TYPES: frozenset[str] = frozenset({"SC", "SD", "X"})

# The characters that a nickname may not contain. A space is allowed. A comma (,), a hyphen
# (-) and a period (.) are not.
FORBIDDEN_CHARS: frozenset[str] = frozenset(",%\"<>!#$&'()*+-./:;=?@[\\]^`{|}~")

RESERVED_NICKNAMES: frozenset[str] = frozenset(
    {
        "log",
        "sum",
        "sin",
        "asin",
        "rad",
        "cos",
        "acos",
        "sqrt",
        "deg",
        "tan",
        "atan",
        "ln",
        "pi",
        "mod",
        "and",
        "or",
        "xor",
        "lsh",
        "rsh",
        "lro",
        "rro",
        # CLICK 4.00 adds these to its reserved list. validate_nickname rejects them for a
        # CLICK 3 project too.
        "max",
        "min",
        "mdn",
        "avg",
        "rand",
        "abs",
    }
)

# Value ranges for validation
INT_MIN = -32768
INT_MAX = 32767
INT2_MIN = -2147483648
INT2_MAX = 2147483647
FLOAT_MIN = -3.4028235e38
FLOAT_MAX = 3.4028235e38

_EDGE_WHITESPACE_ERROR = "Cannot start or end with a space"

# The types whose initial value is parsed with Python's int() or float(). Those functions
# accept forms that CLICK refuses, such as 1_000, so validate_initial_value checks these
# types further.
_NUMBER_TYPES: frozenset[int] = frozenset(
    {DataType.INT, DataType.INT2, DataType.FLOAT, DataType.HEX}
)
# int(value, 16) accepts a 0x prefix, with or without a sign before it. CLICK refuses a hex
# value such as "0x1F".
_HEX_PREFIX = re.compile(r"[+-]?0[xX]")


def _has_edge_whitespace(text: str) -> bool:
    """Return True if *text* starts or ends with a space, tab or other code up to 0x20.

    When CLICK imports a nickname or a comment, it drops a space or tab from either end, even
    if the value is quoted. It drops a space, tab, VT or FF from either end of an unquoted Text
    value. It refuses a quoted number with a space or tab at either end, and it strips a space
    from either end of an unquoted number. For the other codes up to 0x20, this code assumes
    that CLICK behaves like Delphi's ``Trim``, which drops every code up to 0x20. The
    assumption rests on CLICK appearing to be a Delphi program.
    """
    return bool(text) and (text[0] <= " " or text[-1] <= " ")


# ==============================================================================
# Validation Functions
# ==============================================================================


def validate_nickname(nickname: str, *, system_bank: str | None = None) -> tuple[bool, str]:
    """Validate nickname format (length, characters, reserved words).

    A nickname with a leading or trailing space, tab or other character up to 0x20 is
    invalid. CLICK strips those characters, so "Pump " and "Pump" would be one nickname.
    Does NOT check uniqueness -- that is application-specific.

    Args:
        nickname: The nickname to validate
        system_bank: Optional system bank context:
            - "SC"/"SD": allows any punctuation and a leading underscore, as in the
              PLC's system names
            - "X": allows only system names that start with _IO and a digit, such as
              _IO1_Module_Error
            - None: standard user nickname rules

    Returns:
        Tuple of (is_valid, error_message) - error_message is "" if valid
    """
    if nickname == "":
        return True, ""  # Empty is valid (just means unassigned)

    if len(nickname) > NICKNAME_MAX_LENGTH:
        return False, f"Too long ({len(nickname)}/24)"

    if _has_edge_whitespace(nickname):
        return False, _EDGE_WHITESPACE_ERROR

    def _forbidden_char_error() -> str:
        invalid_chars = set(nickname) & FORBIDDEN_CHARS
        if invalid_chars:
            chars_display = "".join(sorted(invalid_chars)[:3])
            return f"Invalid: {chars_display}"
        return ""

    bank = system_bank.upper() if system_bank else None

    if bank in {"SC", "SD"}:
        # SC and SD system names may contain any punctuation and may start with _.
        pass
    elif bank == "X":
        # X system names are PLC auto-generated feedback aliases (_IO...).
        if not nickname.startswith("_IO") or len(nickname) == 3 or not nickname[3].isdigit():
            return False, "X system names must start with _IO<number>"
        invalid_error = _forbidden_char_error()
        if invalid_error:
            return False, invalid_error
    else:
        # Standard user nickname rules.
        if nickname.startswith("_"):
            return False, "Cannot start with _"
        invalid_error = _forbidden_char_error()
        if invalid_error:
            return False, invalid_error

    if nickname.lower() in RESERVED_NICKNAMES:
        return False, "Reserved keyword"

    return True, ""


def validate_comment(comment: str) -> tuple[bool, str]:
    """Validate comment length and edge whitespace.

    A comment with a leading or trailing space, tab or other character up to 0x20 is
    invalid. CLICK's nickname CSV import drops a space or tab from either end of a comment.
    So if you write such a comment with ``write_csv`` and import the file, CLICK stores a
    different comment. For the other codes up to 0x20, this function assumes that the
    import drops them too. The import keeps a tab inside the comment.

    CLICK 4.00's Address Picker was observed to store a tab at either end of a comment when
    another program set the editor's text with that tab. A tab typed into the editor never
    reached it. So a CLICK project may hold a comment that this function rejects.

    Does NOT check that a block name is unique. That check needs the comments of the
    other addresses. Use ``is_block_name_available`` in ``blocks.py`` for it.

    Args:
        comment: The comment to validate

    Returns:
        Tuple of (is_valid, error_message) - error_message is "" if valid
    """
    if comment == "":
        return True, ""  # Empty is valid

    if len(comment) > COMMENT_MAX_LENGTH:
        return False, f"Too long ({len(comment)}/128)"

    if _has_edge_whitespace(comment):
        return False, _EDGE_WHITESPACE_ERROR

    return True, ""


def validate_click_name(name: str) -> tuple[bool, str]:
    """Validate a PLC or DataView name.

    Leading and trailing whitespace is ignored. What remains must be 1 to 24
    letters, digits, spaces, underscores and hyphens.

    Args:
        name: The name to validate

    Returns:
        Tuple of (is_valid, error_message) - error_message is "" if valid
    """
    name = name.strip()
    if not name:
        return False, "Name is required."
    if len(name) > CLICK_NAME_MAX_LENGTH:
        return False, f"Name is too long ({len(name)}/{CLICK_NAME_MAX_LENGTH})."
    if not CLICK_NAME_PATTERN.fullmatch(name):
        return False, "Use only letters, numbers, spaces, underscores, and hyphens."
    return True, ""


def validate_initial_value(
    initial_value: str,
    data_type: int,
) -> tuple[bool, str]:
    """Validate an initial value against the data type rules.

    A value of any type but Text is invalid if it starts or ends with a space, tab or other
    character up to 0x20. CLICK's import refuses such a value if it is quoted, and strips the
    character if the value is unquoted. A Text value may be a space or a tab.

    Python's ``int()`` and ``float()`` accept some INT, INT2, FLOAT and HEX forms that
    CLICK's import refuses. This function rejects them. They are a non-ASCII character (an
    Arabic-Indic or fullwidth digit, a no-break space), an underscore (``1_000``) and a
    ``0x`` prefix on a hex value. CLICK accepts ``+5``. For a float it also accepts ``1e3``
    and ``.5``.

    Args:
        initial_value: The initial value string to validate
        data_type: The DataType number (0=bit, 1=int, 2=int2, 3=float, 4=hex, 6=txt)

    Returns:
        Tuple of (is_valid, error_message) - error_message is "" if valid
    """
    if data_type != DataType.TXT and _has_edge_whitespace(initial_value):
        return False, _EDGE_WHITESPACE_ERROR
    valid, error = _validate_typed_value(initial_value, data_type)
    if not valid or data_type not in _NUMBER_TYPES:
        return valid, error
    if not initial_value.isascii():
        return False, "Must be ASCII"
    if "_" in initial_value:
        return False, "Cannot contain _"
    if data_type == DataType.HEX and _HEX_PREFIX.match(initial_value):
        return False, "Cannot start with 0x"
    return True, ""


def _validate_typed_value(initial_value: str, data_type: int) -> tuple[bool, str]:
    """Validate *initial_value* against *data_type*, without the import rules.

    The import rules are the extra checks that ``validate_initial_value`` makes because
    CLICK's nickname import refuses some values. They reject a space or other code up to 0x20
    at either end of a value that is not Text. They also reject a non-ASCII character, an
    underscore or a hex ``0x`` prefix in a number. A DataView new value that is not Text is
    converted to a number and is not written as text. So ``validate_new_value`` makes only
    this check for such a value.
    """
    if initial_value == "":
        return True, ""  # Empty is valid (means no initial value set)

    if data_type == DataType.BIT:
        if initial_value not in ("0", "1"):
            return False, "Must be 0 or 1"
        return True, ""

    elif data_type == DataType.INT:
        try:
            val = int(initial_value)
            if val < INT_MIN or val > INT_MAX:
                return False, f"Range: {INT_MIN} to {INT_MAX}"
            return True, ""
        except ValueError:
            return False, "Must be integer"

    elif data_type == DataType.INT2:
        try:
            val = int(initial_value)
            if val < INT2_MIN or val > INT2_MAX:
                return False, f"Range: {INT2_MIN} to {INT2_MAX}"
            return True, ""
        except ValueError:
            return False, "Must be integer"

    elif data_type == DataType.FLOAT:
        try:
            val = float(initial_value)
            if not math.isfinite(val):
                return False, "Must be a finite number"
            if val < FLOAT_MIN or val > FLOAT_MAX:
                return False, "Out of float range"
            return True, ""
        except ValueError:
            return False, "Must be number"

    elif data_type == DataType.HEX:
        if len(initial_value) > 4:
            return False, "Max 4 hex digits"
        try:
            val = int(initial_value, 16)
            if val < 0 or val > 0xFFFF:
                return False, "Range: 0000 to FFFF"
            return True, ""
        except ValueError:
            return False, "Must be hex (0-9, A-F)"

    elif data_type == DataType.TXT:
        if len(initial_value) != 1:
            return False, "Must be single char"
        if ord(initial_value) > 127:
            return False, "Must be ASCII"
        return True, ""

    # Unknown data type
    return True, ""


def assert_runtime_value(
    data_type: DataType,
    value: object,
    *,
    bank: str,
    index: int,
    allow_non_finite: bool = True,
) -> None:
    """Raise ``ValueError`` if *value* cannot be written to an address of *data_type*.

    *bank* and *index* name the address in the message. The message also says which values
    the address accepts. A DF accepts +inf, -inf and NaN unless ``allow_non_finite`` is False.
    """
    target = f"{bank}{index}"

    if data_type == DataType.BIT:
        if type(value) is not bool:
            raise ValueError(f"{target} value must be bool.")
        return

    if data_type == DataType.INT:
        if type(value) is not int or value < INT_MIN or value > INT_MAX:
            raise ValueError(f"{target} value must be int in [{INT_MIN}, {INT_MAX}].")
        return

    if data_type == DataType.INT2:
        if type(value) is not int or value < INT2_MIN or value > INT2_MAX:
            raise ValueError(f"{target} value must be int in [{INT2_MIN}, {INT2_MAX}].")
        return

    if data_type == DataType.HEX:
        if type(value) is not int or value < 0 or value > 0xFFFF:
            raise ValueError(f"{target} must be WORD (0..65535).")
        return

    if data_type == DataType.FLOAT:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{target} value must be a float32.")
        try:
            numeric_value = float(value)
            if not math.isfinite(numeric_value):
                if allow_non_finite:
                    return
                raise ValueError(f"{target} value must be a finite float32.")
            struct.pack("<f", numeric_value)
        except (OverflowError, struct.error) as exc:
            raise ValueError(
                f"{target} value must fit in a float32 ({FLOAT_MIN:.7E}..{FLOAT_MAX:.7E})."
            ) from exc
        return

    if data_type == DataType.TXT:
        if type(value) is not str:
            raise ValueError(
                f"{target} TXT value must be blank or a single character with code 0..255."
            )
        if value == "":
            return
        if len(value) != 1 or ord(value) > 0xFF:
            raise ValueError(
                f"{target} TXT value must be blank or a single character with code 0..255."
            )
        return
