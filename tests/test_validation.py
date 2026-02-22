"""Tests for pyclickplc.validation module."""

import math

import pytest

from pyclickplc.banks import DataType
from pyclickplc.validation import (
    FORBIDDEN_CHARS,
    SYSTEM_NICKNAME_TYPES,
    assert_runtime_value,
    validate_comment,
    validate_initial_value,
    validate_nickname,
)

# ==============================================================================
# validate_nickname
# ==============================================================================


class TestValidateNickname:
    def test_empty_valid(self):
        assert validate_nickname("") == (True, "")

    def test_simple_valid(self):
        assert validate_nickname("Input1") == (True, "")

    def test_max_length(self):
        name = "a" * 24
        assert validate_nickname(name) == (True, "")

    def test_too_long(self):
        name = "a" * 25
        valid, error = validate_nickname(name)
        assert valid is False
        assert "Too long" in error

    def test_starts_with_underscore(self):
        valid, error = validate_nickname("_invalid")
        assert valid is False
        assert "Cannot start with _" in error

    def test_system_allows_underscore(self):
        assert validate_nickname("_IO1_Module_Error", is_system=True) == (True, "")
        assert validate_nickname("_SystemName", is_system=True) == (True, "")

    def test_system_still_enforces_other_rules(self):
        # Length still enforced for system nicknames
        valid, error = validate_nickname("_" + "a" * 24, is_system=True)
        assert valid is False
        assert "Too long" in error

        # Reserved keywords still enforced
        valid, error = validate_nickname("log", is_system=True)
        assert valid is False
        assert "Reserved" in error

    def test_system_nickname_types_constant(self):
        assert SYSTEM_NICKNAME_TYPES == {"SC", "SD", "X"}

    def test_reserved_keywords_case_insensitive(self):
        for keyword in ("log", "LOG", "Log", "sin", "SIN", "and", "or", "pi"):
            valid, error = validate_nickname(keyword)
            assert valid is False, f"{keyword} should be rejected"
            assert "Reserved" in error

    def test_forbidden_chars(self):
        for char in FORBIDDEN_CHARS:
            valid, error = validate_nickname(f"test{char}name")
            assert valid is False, f"Char {char!r} should be rejected"
            assert "Invalid" in error

    def test_space_allowed(self):
        assert validate_nickname("my input") == (True, "")

    def test_no_uniqueness_check(self):
        # This function does NOT check uniqueness
        assert validate_nickname("duplicate") == (True, "")


# ==============================================================================
# validate_comment
# ==============================================================================


class TestValidateComment:
    def test_empty_valid(self):
        assert validate_comment("") == (True, "")

    def test_max_length(self):
        comment = "a" * 128
        assert validate_comment(comment) == (True, "")

    def test_too_long(self):
        comment = "a" * 129
        valid, error = validate_comment(comment)
        assert valid is False
        assert "Too long" in error

    def test_block_tags_not_rejected(self):
        # Length-only validation -- block tags are NOT rejected here
        assert validate_comment("[Block:MyBlock]") == (True, "")
        assert validate_comment("[Block:Dup]") == (True, "")


# ==============================================================================
# validate_initial_value
# ==============================================================================


class TestValidateInitialValue:
    def test_empty_valid_all_types(self):
        for dt in DataType:
            assert validate_initial_value("", dt) == (True, "")

    # --- BIT ---
    def test_bit_valid(self):
        assert validate_initial_value("0", DataType.BIT) == (True, "")
        assert validate_initial_value("1", DataType.BIT) == (True, "")

    def test_bit_invalid(self):
        valid, error = validate_initial_value("2", DataType.BIT)
        assert valid is False
        assert "0 or 1" in error

    # --- INT ---
    def test_int_valid(self):
        assert validate_initial_value("0", DataType.INT) == (True, "")
        assert validate_initial_value("-32768", DataType.INT) == (True, "")
        assert validate_initial_value("32767", DataType.INT) == (True, "")

    def test_int_out_of_range(self):
        valid, error = validate_initial_value("32768", DataType.INT)
        assert valid is False
        assert "Range" in error

    def test_int_not_number(self):
        valid, error = validate_initial_value("abc", DataType.INT)
        assert valid is False
        assert "integer" in error

    # --- INT2 ---
    def test_int2_valid(self):
        assert validate_initial_value("0", DataType.INT2) == (True, "")
        assert validate_initial_value("-2147483648", DataType.INT2) == (True, "")
        assert validate_initial_value("2147483647", DataType.INT2) == (True, "")

    def test_int2_out_of_range(self):
        valid, error = validate_initial_value("2147483648", DataType.INT2)
        assert valid is False
        assert "Range" in error

    # --- FLOAT ---
    def test_float_valid(self):
        assert validate_initial_value("0.0", DataType.FLOAT) == (True, "")
        assert validate_initial_value("1.5", DataType.FLOAT) == (True, "")
        assert validate_initial_value("-1.5E+10", DataType.FLOAT) == (True, "")

    def test_float_invalid(self):
        valid, error = validate_initial_value("notanumber", DataType.FLOAT)
        assert valid is False
        assert "number" in error

    # --- HEX ---
    def test_hex_valid(self):
        assert validate_initial_value("0000", DataType.HEX) == (True, "")
        assert validate_initial_value("FFFF", DataType.HEX) == (True, "")
        assert validate_initial_value("1A2B", DataType.HEX) == (True, "")
        assert validate_initial_value("ff", DataType.HEX) == (True, "")

    def test_hex_too_long(self):
        valid, error = validate_initial_value("12345", DataType.HEX)
        assert valid is False
        assert "4 hex" in error

    def test_hex_invalid_chars(self):
        valid, error = validate_initial_value("GHIJ", DataType.HEX)
        assert valid is False
        assert "hex" in error

    # --- TXT ---
    def test_txt_valid(self):
        assert validate_initial_value("A", DataType.TXT) == (True, "")
        assert validate_initial_value(" ", DataType.TXT) == (True, "")

    def test_txt_too_long(self):
        valid, error = validate_initial_value("AB", DataType.TXT)
        assert valid is False
        assert "single char" in error

    def test_txt_non_ascii(self):
        valid, error = validate_initial_value("\u00e9", DataType.TXT)
        assert valid is False
        assert "ASCII" in error


# ==============================================================================
# assert_runtime_value
# ==============================================================================


class TestAssertRuntimeValue:
    def test_reject_bool_for_int(self):
        with pytest.raises(ValueError, match="DS1 value must be int"):
            assert_runtime_value(DataType.INT, True, bank="DS", index=1)

    def test_reject_non_finite_float(self):
        with pytest.raises(ValueError, match="DF1 value must be a finite float32"):
            assert_runtime_value(DataType.FLOAT, math.nan, bank="DF", index=1)

    def test_reject_overflow_float32(self):
        with pytest.raises(ValueError, match="DF1 value must be a finite float32"):
            assert_runtime_value(DataType.FLOAT, 1e100, bank="DF", index=1)

    def test_reject_invalid_txt(self):
        with pytest.raises(ValueError, match="TXT1 TXT value must be blank or a single ASCII"):
            assert_runtime_value(DataType.TXT, "AB", bank="TXT", index=1)

    def test_allow_blank_txt(self):
        assert_runtime_value(DataType.TXT, "", bank="TXT", index=1)
