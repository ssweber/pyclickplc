"""Validation functions for PLC address data.

Validates nicknames, comments, and initial values against CLICK PLC rules.
"""

from __future__ import annotations

import math
import struct

from .banks import (
    DataType,
)

# ==============================================================================
# Constants
# ==============================================================================

NICKNAME_MAX_LENGTH = 24
COMMENT_MAX_LENGTH = 128

# Characters forbidden in nicknames
# Note: Space is allowed, hyphen (-) and period (.) are forbidden
FORBIDDEN_CHARS: frozenset[str] = frozenset("%\"<>!#$&'()*+-./:;=?@[\\]^`{|}~")

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
    }
)

# Value ranges for validation
INT_MIN = -32768
INT_MAX = 32767
INT2_MIN = -2147483648
INT2_MAX = 2147483647
FLOAT_MIN = -3.4028235e38
FLOAT_MAX = 3.4028235e38


# ==============================================================================
# Validation Functions
# ==============================================================================


def validate_nickname(nickname: str) -> tuple[bool, str]:
    """Validate nickname format (length, characters, reserved words).

    Does NOT check uniqueness -- that is application-specific.

    Args:
        nickname: The nickname to validate

    Returns:
        Tuple of (is_valid, error_message) - error_message is "" if valid
    """
    if nickname == "":
        return True, ""  # Empty is valid (just means unassigned)

    if len(nickname) > NICKNAME_MAX_LENGTH:
        return False, f"Too long ({len(nickname)}/24)"

    if nickname.startswith("_"):
        return False, "Cannot start with _"

    if nickname.lower() in RESERVED_NICKNAMES:
        return False, "Reserved keyword"

    invalid_chars = set(nickname) & FORBIDDEN_CHARS
    if invalid_chars:
        chars_display = "".join(sorted(invalid_chars)[:3])
        return False, f"Invalid: {chars_display}"

    return True, ""


def validate_comment(comment: str) -> tuple[bool, str]:
    """Validate comment length.

    Does NOT check block tag uniqueness -- that requires blocks.py context.

    Args:
        comment: The comment to validate

    Returns:
        Tuple of (is_valid, error_message) - error_message is "" if valid
    """
    if comment == "":
        return True, ""  # Empty is valid

    if len(comment) > COMMENT_MAX_LENGTH:
        return False, f"Too long ({len(comment)}/128)"

    return True, ""


def validate_initial_value(
    initial_value: str,
    data_type: int,
) -> tuple[bool, str]:
    """Validate an initial value against the data type rules.

    Args:
        initial_value: The initial value string to validate
        data_type: The DataType number (0=bit, 1=int, 2=int2, 3=float, 4=hex, 6=txt)

    Returns:
        Tuple of (is_valid, error_message) - error_message is "" if valid
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
) -> None:
    """Assert runtime write value validity for a specific PLC address.

    Raises ValueError with a deterministic, actionable message on invalid values.
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
            raise ValueError(f"{target} value must be a finite float32.")
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ValueError(f"{target} value must be a finite float32.")
        try:
            struct.pack("<f", numeric_value)
        except (OverflowError, struct.error) as exc:
            raise ValueError(f"{target} value must be a finite float32.") from exc
        return

    if data_type == DataType.TXT:
        if type(value) is not str:
            raise ValueError(f"{target} TXT value must be blank or a single ASCII character.")
        if value == "":
            return
        if len(value) != 1 or ord(value) > 127:
            raise ValueError(f"{target} TXT value must be blank or a single ASCII character.")
        return
