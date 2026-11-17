"""Tests for pyclickplc.validation module."""

import math

import pytest

from pyclickplc.banks import DataType
from pyclickplc.validation import (
    FORBIDDEN_CHARS,
    SYSTEM_NICKNAME_TYPES,
    assert_runtime_value,
    validate_click_name,
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

    @pytest.mark.parametrize(
        "name",
        [" Pump", "Pump ", "  Spaced Nick  ", " ", "\tPump", "Pump\t", "Pump\x0b", "\x0cPump"],
    )
    def test_leading_or_trailing_whitespace_invalid(self, name):
        # CLICK strips whitespace from both ends, so "Pump " and "Pump" would be one nickname
        assert validate_nickname(name) == (False, "Cannot start or end with a space")

    @pytest.mark.parametrize("char", [chr(code) for code in range(0x21)])
    def test_any_edge_code_up_to_0x20_invalid(self, char):
        assert validate_nickname(char + "Pump") == (
            False,
            "Cannot start or end with a space",
        )
        assert validate_nickname("Pump" + char) == (
            False,
            "Cannot start or end with a space",
        )

    def test_inner_spaces_valid(self):
        assert validate_nickname("Inner  Two") == (True, "")

    def test_starts_with_underscore(self):
        valid, error = validate_nickname("_invalid")
        assert valid is False
        assert "Cannot start with _" in error

    def test_non_system_rejects_leading_underscore(self):
        valid, error = validate_nickname("_SystemName")
        assert valid is False
        assert "Cannot start with _" in error

    def test_system_allows_forbidden_chars(self):
        # SC nicknames contain /
        assert validate_nickname("Comm/Port_1", system_bank="SC") == (True, "")
        # SD nicknames contain ( and )
        assert validate_nickname("_Fixed_Scan_Time(ms)", system_bank="SD") == (
            True,
            "",
        )

    def test_non_system_rejects_sc_sd_punctuation(self):
        valid, error = validate_nickname("Comm/Port_1")
        assert valid is False
        assert "Invalid" in error

    def test_x_system_requires_io_prefix(self):
        valid, error = validate_nickname("_SystemName", system_bank="X")
        assert valid is False
        assert "_IO<number>" in error

    def test_x_system_rejects_forbidden_chars(self):
        valid, error = validate_nickname("_IO1.Module", system_bank="X")
        assert valid is False
        assert "Invalid" in error

    def test_x_system_allows_io_style_name(self):
        assert validate_nickname("_IO1_Module_Error", system_bank="X") == (True, "")

    def test_system_still_enforces_length_and_reserved(self):
        # Length still enforced for system nicknames
        valid, error = validate_nickname("_" + "a" * 24, system_bank="SC")
        assert valid is False
        assert "Too long" in error

        # Reserved keywords still enforced
        valid, error = validate_nickname("log", system_bank="SC")
        assert valid is False
        assert "Reserved" in error

    def test_system_nickname_types_constant(self):
        assert SYSTEM_NICKNAME_TYPES == {"SC", "SD", "X"}

    def test_reserved_keywords_case_insensitive(self):
        for keyword in ("log", "LOG", "Log", "sin", "SIN", "and", "or", "pi"):
            valid, error = validate_nickname(keyword)
            assert valid is False, f"{keyword} should be rejected"
            assert "Reserved" in error

    @pytest.mark.parametrize(
        "name",
        ["MAX", "Max", "max", "MIN", "ABS", "abs", "RAND", "MDN", "AVG", "LOG", "Log", "log"],
    )
    def test_click4_refused_names(self, name):
        # CLICK 4.00's Address Picker and CSV import refuse these names. PLCType.ini lists MAX,
        # MIN, MDN, AVG, RAND and ABS under [NGWORD] WORD in 4.00 only. pyclickplc refuses them
        # for CLICK 3 projects too, because a CLICK 3 project that uses one of these names
        # breaks when CLICK 4 opens it.
        assert validate_nickname(name) == (False, "Reserved keyword")

    @pytest.mark.parametrize("name", ["MAXIMUM", "Max_Speed", "Speed"])
    def test_click4_accepted_names(self, name):
        # CLICK 4.00 stores these names. It refuses a reserved word only as the whole name.
        assert validate_nickname(name) == (True, "")

    def test_click4_names_refused_for_system_banks(self):
        # The reserved-word check runs after the bank rules, so SC still refuses these names.
        assert validate_nickname("MAX", system_bank="SC") == (False, "Reserved keyword")

    def test_comma_refused(self):
        # CLICK refuses `A,B` as a "reserved character". In every CLICK version, PLCType.ini
        # lists `,` under [NGWORD] `All =`.
        assert validate_nickname("A,B") == (False, "Invalid: ,")

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

    @pytest.mark.parametrize(
        "comment",
        [" note", "note ", "  spaced comment  ", "\tnote", "note\t", "\x0bnote", "note\x0c"],
    )
    def test_leading_or_trailing_whitespace_invalid(self, comment):
        assert validate_comment(comment) == (False, "Cannot start or end with a space")

    def test_inner_tab_valid(self):
        # CLICK stores a tab inside a comment
        assert validate_comment("inner\ttab") == (True, "")

    def test_inner_spaces_valid(self):
        assert validate_comment("two  words") == (True, "")

    def test_block_tags_not_rejected(self):
        # validate_comment checks only the length and the ends of a comment. It does not reject a
        # block tag.
        assert validate_comment("[Block:MyBlock]") == (True, "")
        assert validate_comment("[Block:Dup]") == (True, "")


# ==============================================================================
# validate_click_name
# ==============================================================================


class TestValidateClickName:
    @pytest.mark.parametrize(
        "name", ["A", "A" * 24, "Line 1", "Line_1", "Line-1", " Line 1 ", "a" * 24 + "  "]
    )
    def test_valid(self, name):
        assert validate_click_name(name) == (True, "")

    @pytest.mark.parametrize(
        "name,error",
        [
            ("", "Name is required."),
            ("   ", "Name is required."),
            ("A" * 25, "Name is too long (25/24)."),
            ("Line/1", "Use only letters, numbers, spaces, underscores, and hyphens."),
            ("Line.1", "Use only letters, numbers, spaces, underscores, and hyphens."),
            ("Line@1", "Use only letters, numbers, spaces, underscores, and hyphens."),
            ("Line\t1", "Use only letters, numbers, spaces, underscores, and hyphens."),
            ("Línea", "Use only letters, numbers, spaces, underscores, and hyphens."),
            ("Line١", "Use only letters, numbers, spaces, underscores, and hyphens."),
        ],
    )
    def test_invalid(self, name, error):
        assert validate_click_name(name) == (False, error)


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
    @pytest.mark.parametrize("char", ["A", " ", "\t", "\x0b", "\x0c"])
    def test_txt_valid(self, char):
        # A Text value may be a space, tab, VT or FF. write_csv quotes it, so CLICK stores it.
        assert validate_initial_value(char, DataType.TXT) == (True, "")

    @pytest.mark.parametrize(
        ("value", "data_type"),
        [
            (" 5", DataType.INT),
            ("5 ", DataType.INT),
            ("\t5", DataType.INT),
            (" 5 ", DataType.INT2),
            (" 1.5", DataType.FLOAT),
            ("1.5\t", DataType.FLOAT),
            (" FF", DataType.HEX),
            ("1 ", DataType.BIT),
            ("5\x0c", DataType.INT),
            ("\x0b5", DataType.INT),
            (" ", DataType.INT),
        ],
    )
    def test_number_with_edge_whitespace_invalid(self, value, data_type):
        # CLICK refuses " 5" when it is quoted and strips the space when it is unquoted.
        # int(" 5") accepts it.
        assert validate_initial_value(value, data_type) == (
            False,
            "Cannot start or end with a space",
        )

    # --- Number forms in CLICK's import ---
    # CLICK's import was tried with the INT and FLOAT cases except 1_0.5, and with HEX 0x1F
    # and 1F. The INT2 cases, 1_0.5 and the other HEX cases were not tried. They assume that
    # CLICK treats them as it treats the cases that were tried.
    @pytest.mark.parametrize(
        ("value", "data_type"),
        [
            ("+5", DataType.INT),
            ("+5", DataType.INT2),
            ("+5", DataType.FLOAT),
            ("1e3", DataType.FLOAT),
            (".5", DataType.FLOAT),
            ("1F", DataType.HEX),
        ],
    )
    def test_number_forms_click_takes(self, value, data_type):
        assert validate_initial_value(value, data_type) == (True, "")

    @pytest.mark.parametrize("value", ["1e3", ".5"])
    def test_int_refuses_exponent_and_bare_decimal(self, value):
        # CLICK refuses these as INT and accepts them as FLOAT
        assert validate_initial_value(value, DataType.INT) == (False, "Must be integer")
        assert validate_initial_value(value, DataType.INT2) == (False, "Must be integer")

    @pytest.mark.parametrize(
        ("value", "data_type"),
        [
            ("1_000", DataType.INT),
            ("1_000", DataType.INT2),
            ("1_000", DataType.FLOAT),
            ("1_0.5", DataType.FLOAT),
            ("1_F", DataType.HEX),
        ],
    )
    def test_underscore_invalid(self, value, data_type):
        # int() and float() accept digit-group underscores. CLICK refuses them.
        assert validate_initial_value(value, data_type) == (False, "Cannot contain _")

    @pytest.mark.parametrize("value", ["0x1F", "0X1F", "0x1", "+0x1"])
    def test_hex_prefix_invalid(self, value):
        # int("0x1F", 16) accepts the prefix. CLICK refuses it.
        assert validate_initial_value(value, DataType.HEX) == (False, "Cannot start with 0x")

    @pytest.mark.parametrize(
        ("value", "data_type"),
        [
            ("\xa05", DataType.INT),
            ("5\xa0", DataType.INT),
            ("\xa01.5", DataType.FLOAT),
            ("　5", DataType.INT),
            ("5　", DataType.INT2),
            ("٥", DataType.INT),
            ("５", DataType.INT),
            ("٥", DataType.FLOAT),
            ("５", DataType.FLOAT),
            ("１F", DataType.HEX),
        ],
    )
    def test_number_with_non_ascii_invalid(self, value, data_type):
        # int() and float() accept Unicode digits and strip Unicode spaces.
        # CLICK refuses them from a file without a BOM, which is what write_csv writes.
        assert validate_initial_value(value, data_type) == (False, "Must be ASCII")

    @pytest.mark.parametrize(
        ("value", "data_type", "error"),
        [
            ("١", DataType.BIT, "Must be 0 or 1"),
            ("é", DataType.INT, "Must be integer"),
            ("_1", DataType.INT, "Must be integer"),
            ("1_", DataType.FLOAT, "Must be number"),
            ("0x1FF", DataType.HEX, "Max 4 hex digits"),
        ],
    )
    def test_already_invalid_keeps_its_message(self, value, data_type, error):
        # validate_initial_value checks for non-ASCII, an underscore and a 0x prefix only after
        # the value passes the type check. A value that fails gets the type check's message.
        assert validate_initial_value(value, data_type) == (False, error)

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


class TestValidateInitialValueNonFinite:
    @pytest.mark.parametrize("text", ["nan", "NaN", "inf", "-inf"])
    def test_float_rejects_non_finite(self, text):
        assert validate_initial_value(text, DataType.FLOAT) == (False, "Must be a finite number")

    def test_float_overflow_keeps_range_message(self):
        assert validate_initial_value("1e39", DataType.FLOAT) == (False, "Out of float range")


class TestAssertRuntimeValue:
    def test_reject_bool_for_int(self):
        with pytest.raises(ValueError, match="DS1 value must be int"):
            assert_runtime_value(DataType.INT, True, bank="DS", index=1)

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_allow_non_finite_float(self, value):
        assert_runtime_value(DataType.FLOAT, value, bank="DF", index=1)

    def test_reject_non_finite_float_when_strict(self):
        with pytest.raises(ValueError, match="DF1 value must be a finite float32"):
            assert_runtime_value(
                DataType.FLOAT, math.nan, bank="DF", index=1, allow_non_finite=False
            )

    def test_overflow_message_gives_range(self):
        with pytest.raises(ValueError, match=r"DF1 value must fit in a float32 \(-3\.4028235E\+38"):
            assert_runtime_value(DataType.FLOAT, 1e100, bank="DF", index=1)

    def test_huge_int_raises_value_error(self):
        with pytest.raises(ValueError, match="DF1 value must fit in a float32"):
            assert_runtime_value(DataType.FLOAT, 10**400, bank="DF", index=1)

    def test_reject_bool_for_float(self):
        with pytest.raises(ValueError, match="DF1 value must be a float32"):
            assert_runtime_value(DataType.FLOAT, True, bank="DF", index=1)

    def test_reject_overflow_float32(self):
        with pytest.raises(ValueError, match="DF1 value must fit in a float32"):
            assert_runtime_value(DataType.FLOAT, 1e100, bank="DF", index=1)

    def test_reject_invalid_txt(self):
        with pytest.raises(
            ValueError, match="TXT1 TXT value must be blank or a single character with code 0..255"
        ):
            assert_runtime_value(DataType.TXT, "AB", bank="TXT", index=1)

    @pytest.mark.parametrize("char", ["", chr(200), "ÿ"])
    def test_allow_txt_byte_above_127(self, char):
        assert_runtime_value(DataType.TXT, char, bank="TXT", index=1)

    def test_reject_txt_above_ff(self):
        with pytest.raises(ValueError, match="TXT1 TXT value must be blank"):
            assert_runtime_value(DataType.TXT, "Ā", bank="TXT", index=1)

    def test_allow_blank_txt(self):
        assert_runtime_value(DataType.TXT, "", bank="TXT", index=1)
