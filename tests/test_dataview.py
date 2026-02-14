"""Tests for pyclickplc.dataview - DataView model and CDV file I/O."""

import pytest

from pyclickplc.banks import DataType
from pyclickplc.dataview import (
    MAX_DATAVIEW_ROWS,
    WRITABLE_SC,
    WRITABLE_SD,
    DataviewRow,
    _CdvStorageCode,
    check_cdv_file,
    create_empty_dataview,
    datatype_to_display,
    datatype_to_storage,
    display_to_datatype,
    get_data_type_for_address,
    is_address_writable,
    load_cdv,
    save_cdv,
    storage_to_datatype,
    validate_new_value,
)


class TestGetDataTypeForAddress:
    """Tests for get_data_type_for_address function."""

    def test_bit_addresses(self):
        assert get_data_type_for_address("X001") == DataType.BIT
        assert get_data_type_for_address("Y001") == DataType.BIT
        assert get_data_type_for_address("C1") == DataType.BIT
        assert get_data_type_for_address("T1") == DataType.BIT
        assert get_data_type_for_address("CT1") == DataType.BIT
        assert get_data_type_for_address("SC1") == DataType.BIT

    def test_int_addresses(self):
        assert get_data_type_for_address("DS1") == DataType.INT
        assert get_data_type_for_address("TD1") == DataType.INT
        assert get_data_type_for_address("SD1") == DataType.INT

    def test_int2_addresses(self):
        assert get_data_type_for_address("DD1") == DataType.INT2
        assert get_data_type_for_address("CTD1") == DataType.INT2

    def test_hex_addresses(self):
        assert get_data_type_for_address("DH1") == DataType.HEX
        assert get_data_type_for_address("XD0") == DataType.HEX
        assert get_data_type_for_address("YD0") == DataType.HEX

    def test_float_addresses(self):
        assert get_data_type_for_address("DF1") == DataType.FLOAT

    def test_txt_addresses(self):
        assert get_data_type_for_address("TXT1") == DataType.TXT

    def test_invalid_address(self):
        assert get_data_type_for_address("INVALID") is None
        assert get_data_type_for_address("") is None


class TestIsAddressWritable:
    """Tests for is_address_writable function."""

    def test_regular_addresses_writable(self):
        assert is_address_writable("X001") is True
        assert is_address_writable("Y001") is True
        assert is_address_writable("C1") is True
        assert is_address_writable("DS1") is True
        assert is_address_writable("DD1") is True
        assert is_address_writable("DF1") is True

    def test_xd_yd_readonly(self):
        assert is_address_writable("XD0") is False
        assert is_address_writable("XD0u") is False
        assert is_address_writable("YD0") is False
        assert is_address_writable("YD8") is False

    def test_sc_writable_addresses(self):
        for addr in WRITABLE_SC:
            assert is_address_writable(f"SC{addr}") is True

    def test_sc_readonly_addresses(self):
        assert is_address_writable("SC1") is False
        assert is_address_writable("SC100") is False

    def test_sd_writable_addresses(self):
        for addr in WRITABLE_SD:
            assert is_address_writable(f"SD{addr}") is True

    def test_sd_readonly_addresses(self):
        assert is_address_writable("SD1") is False
        assert is_address_writable("SD100") is False

    def test_invalid_address(self):
        assert is_address_writable("INVALID") is False
        assert is_address_writable("") is False


class TestDataviewRow:
    """Tests for DataviewRow dataclass."""

    def test_default_values(self):
        row = DataviewRow()
        assert row.address == ""
        assert row.data_type is None
        assert row.new_value == ""
        assert row.nickname == ""
        assert row.comment == ""

    def test_is_empty(self):
        row = DataviewRow()
        assert row.is_empty is True

        row.address = "X001"
        assert row.is_empty is False

        row.address = "   "
        assert row.is_empty is True

    def test_is_writable(self):
        row = DataviewRow(address="X001")
        assert row.is_writable is True

        row.address = "XD0"
        assert row.is_writable is False

    def test_memory_type(self):
        row = DataviewRow(address="DS100")
        assert row.memory_type == "DS"

        row.address = ""
        assert row.memory_type is None

    def test_address_number(self):
        row = DataviewRow(address="DS100")
        assert row.address_number == "100"

        row.address = "XD0u"
        assert row.address_number == "0u"

    def test_update_data_type(self):
        row = DataviewRow(address="DS100")
        assert row.update_data_type() is True
        assert row.data_type == DataType.INT

        row.address = "INVALID"
        assert row.update_data_type() is False

    def test_clear(self):
        row = DataviewRow(
            address="X001",
            data_type=DataType.BIT,
            new_value="1",
            nickname="Test",
            comment="Comment",
        )
        row.clear()
        assert row.address == ""
        assert row.data_type is None
        assert row.new_value == ""
        assert row.nickname == ""
        assert row.comment == ""


class TestCreateEmptyDataview:
    """Tests for create_empty_dataview function."""

    def test_creates_correct_count(self):
        rows = create_empty_dataview()
        assert len(rows) == MAX_DATAVIEW_ROWS

    def test_all_rows_empty(self):
        rows = create_empty_dataview()
        assert all(row.is_empty for row in rows)

    def test_rows_are_independent(self):
        rows = create_empty_dataview()
        rows[0].address = "X001"
        assert rows[1].address == ""


class TestStorageToDatatype:
    """Tests for storage_to_datatype: CDV string -> native Python type."""

    def test_bit_values(self):
        assert storage_to_datatype("1", DataType.BIT) is True
        assert storage_to_datatype("0", DataType.BIT) is False

    def test_int_positive(self):
        assert storage_to_datatype("0", DataType.INT) == 0
        assert storage_to_datatype("100", DataType.INT) == 100
        assert storage_to_datatype("32767", DataType.INT) == 32767

    def test_int_negative(self):
        assert storage_to_datatype("4294934528", DataType.INT) == -32768
        assert storage_to_datatype("4294967295", DataType.INT) == -1
        assert storage_to_datatype("65535", DataType.INT) == -1

    def test_int2_positive(self):
        assert storage_to_datatype("0", DataType.INT2) == 0
        assert storage_to_datatype("100", DataType.INT2) == 100
        assert storage_to_datatype("2147483647", DataType.INT2) == 2147483647

    def test_int2_negative(self):
        assert storage_to_datatype("2147483648", DataType.INT2) == -2147483648
        assert storage_to_datatype("4294967294", DataType.INT2) == -2
        assert storage_to_datatype("4294967295", DataType.INT2) == -1

    def test_hex_values(self):
        assert storage_to_datatype("65535", DataType.HEX) == 65535
        assert storage_to_datatype("255", DataType.HEX) == 255
        assert storage_to_datatype("0", DataType.HEX) == 0

    def test_float_values(self):
        assert storage_to_datatype("0", DataType.FLOAT) == 0.0
        assert storage_to_datatype("1065353216", DataType.FLOAT) == 1.0
        val = storage_to_datatype("1078523331", DataType.FLOAT)
        assert val == pytest.approx(3.14, abs=1e-5)
        val = storage_to_datatype("4286578685", DataType.FLOAT)
        assert isinstance(val, (int, float))
        assert val < 0

    def test_txt_values(self):
        assert storage_to_datatype("48", DataType.TXT) == "0"
        assert storage_to_datatype("65", DataType.TXT) == "A"
        assert storage_to_datatype("90", DataType.TXT) == "Z"
        assert storage_to_datatype("32", DataType.TXT) == " "

    def test_empty_value(self):
        assert storage_to_datatype("", DataType.INT) is None
        assert storage_to_datatype("", DataType.HEX) is None
        assert storage_to_datatype("", DataType.BIT) is None

    def test_invalid_value(self):
        assert storage_to_datatype("abc", DataType.INT) is None


class TestDatatypeToStorage:
    """Tests for datatype_to_storage: native Python type -> CDV string."""

    def test_bit_values(self):
        assert datatype_to_storage(True, DataType.BIT) == "1"
        assert datatype_to_storage(False, DataType.BIT) == "0"
        assert datatype_to_storage(1, DataType.BIT) == "1"
        assert datatype_to_storage(0, DataType.BIT) == "0"

    def test_int_positive(self):
        assert datatype_to_storage(0, DataType.INT) == "0"
        assert datatype_to_storage(100, DataType.INT) == "100"
        assert datatype_to_storage(32767, DataType.INT) == "32767"

    def test_int_negative(self):
        assert datatype_to_storage(-32768, DataType.INT) == "4294934528"
        assert datatype_to_storage(-1, DataType.INT) == "4294967295"

    def test_int2_positive(self):
        assert datatype_to_storage(0, DataType.INT2) == "0"
        assert datatype_to_storage(100, DataType.INT2) == "100"

    def test_int2_negative(self):
        assert datatype_to_storage(-2147483648, DataType.INT2) == "2147483648"
        assert datatype_to_storage(-2, DataType.INT2) == "4294967294"

    def test_hex_values(self):
        assert datatype_to_storage(65535, DataType.HEX) == "65535"
        assert datatype_to_storage(255, DataType.HEX) == "255"
        assert datatype_to_storage(0, DataType.HEX) == "0"

    def test_float_values(self):
        assert datatype_to_storage(0.0, DataType.FLOAT) == "0"
        assert datatype_to_storage(1.0, DataType.FLOAT) == "1065353216"
        assert datatype_to_storage(-1.0, DataType.FLOAT) == "3212836864"

    def test_txt_values(self):
        assert datatype_to_storage(48, DataType.TXT) == "48"
        assert datatype_to_storage(65, DataType.TXT) == "65"
        assert datatype_to_storage(90, DataType.TXT) == "90"

    def test_none_value(self):
        assert datatype_to_storage(None, DataType.INT) == ""
        assert datatype_to_storage(None, DataType.HEX) == ""


class TestDatatypeToDisplay:
    """Tests for datatype_to_display: native Python type -> UI string."""

    def test_bit_values(self):
        assert datatype_to_display(True, DataType.BIT) == "1"
        assert datatype_to_display(False, DataType.BIT) == "0"

    def test_int_values(self):
        assert datatype_to_display(0, DataType.INT) == "0"
        assert datatype_to_display(100, DataType.INT) == "100"
        assert datatype_to_display(-32768, DataType.INT) == "-32768"
        assert datatype_to_display(32767, DataType.INT) == "32767"

    def test_int2_values(self):
        assert datatype_to_display(0, DataType.INT2) == "0"
        assert datatype_to_display(-2147483648, DataType.INT2) == "-2147483648"
        assert datatype_to_display(2147483647, DataType.INT2) == "2147483647"

    def test_hex_values(self):
        assert datatype_to_display(65535, DataType.HEX) == "FFFF"
        assert datatype_to_display(255, DataType.HEX) == "00FF"
        assert datatype_to_display(0, DataType.HEX) == "0000"
        assert datatype_to_display(1, DataType.HEX) == "0001"

    def test_float_values(self):
        assert datatype_to_display(0.0, DataType.FLOAT) == "0"
        assert datatype_to_display(1.0, DataType.FLOAT) == "1"
        assert datatype_to_display(3.1400001049041748, DataType.FLOAT) == "3.14"
        assert datatype_to_display(3.4028234663852886e38, DataType.FLOAT) == "3.402823E+38"
        assert datatype_to_display(-3.4028234663852886e38, DataType.FLOAT) == "-3.402823E+38"

    def test_txt_printable(self):
        assert datatype_to_display(48, DataType.TXT) == "0"
        assert datatype_to_display(65, DataType.TXT) == "A"
        assert datatype_to_display(90, DataType.TXT) == "Z"
        assert datatype_to_display(32, DataType.TXT) == " "

    def test_txt_nonprintable(self):
        assert datatype_to_display(5, DataType.TXT) == "5"
        assert datatype_to_display(127, DataType.TXT) == "127"

    def test_none_value(self):
        assert datatype_to_display(None, DataType.INT) == ""
        assert datatype_to_display(None, DataType.HEX) == ""


class TestDisplayToDatatype:
    """Tests for display_to_datatype: UI string -> native Python type."""

    def test_bit_values(self):
        assert display_to_datatype("1", DataType.BIT) is True
        assert display_to_datatype("0", DataType.BIT) is False
        assert display_to_datatype("True", DataType.BIT) is True
        assert display_to_datatype("ON", DataType.BIT) is True

    def test_int_values(self):
        assert display_to_datatype("0", DataType.INT) == 0
        assert display_to_datatype("100", DataType.INT) == 100
        assert display_to_datatype("-32768", DataType.INT) == -32768
        assert display_to_datatype("32767", DataType.INT) == 32767

    def test_int2_values(self):
        assert display_to_datatype("0", DataType.INT2) == 0
        assert display_to_datatype("-2147483648", DataType.INT2) == -2147483648
        assert display_to_datatype("2147483647", DataType.INT2) == 2147483647

    def test_hex_values(self):
        assert display_to_datatype("FFFF", DataType.HEX) == 65535
        assert display_to_datatype("FF", DataType.HEX) == 255
        assert display_to_datatype("0xFF", DataType.HEX) == 255
        assert display_to_datatype("0", DataType.HEX) == 0

    def test_float_values(self):
        assert display_to_datatype("3.14", DataType.FLOAT) == pytest.approx(3.14)
        assert display_to_datatype("0.0", DataType.FLOAT) == 0.0
        assert display_to_datatype("-1.0", DataType.FLOAT) == -1.0

    def test_txt_char(self):
        assert display_to_datatype("A", DataType.TXT) == "A"
        assert display_to_datatype("Z", DataType.TXT) == "Z"
        assert display_to_datatype("0", DataType.TXT) == "0"
        assert display_to_datatype(" ", DataType.TXT) == " "

    def test_txt_numeric(self):
        assert display_to_datatype("65", DataType.TXT) == "A"

    def test_empty_value(self):
        assert display_to_datatype("", DataType.INT) is None
        assert display_to_datatype("", DataType.HEX) is None

    def test_invalid_value(self):
        assert display_to_datatype("abc", DataType.INT) is None


class TestRoundTripConversion:
    """Tests for round-trip conversions across layers."""

    def test_storage_datatype_roundtrip_int(self):
        for storage_val in ["0", "100", "32767", "4294934528", "4294967295"]:
            native = storage_to_datatype(storage_val, DataType.INT)
            storage = datatype_to_storage(native, DataType.INT)
            assert storage_to_datatype(storage, DataType.INT) == native

    def test_storage_datatype_roundtrip_int2(self):
        for storage_val in ["0", "100", "2147483647", "2147483648", "4294967294"]:
            native = storage_to_datatype(storage_val, DataType.INT2)
            storage = datatype_to_storage(native, DataType.INT2)
            assert storage_to_datatype(storage, DataType.INT2) == native

    def test_storage_datatype_roundtrip_hex(self):
        for storage_val in ["0", "255", "65535"]:
            native = storage_to_datatype(storage_val, DataType.HEX)
            storage = datatype_to_storage(native, DataType.HEX)
            assert storage == storage_val

    def test_storage_datatype_roundtrip_float(self):
        for storage_val in ["0", "1065353216", "3212836864"]:
            native = storage_to_datatype(storage_val, DataType.FLOAT)
            storage = datatype_to_storage(native, DataType.FLOAT)
            assert storage == storage_val

    def test_storage_datatype_roundtrip_txt(self):
        for storage_val in ["32", "48", "65", "90"]:
            native = storage_to_datatype(storage_val, DataType.TXT)
            storage = datatype_to_storage(native, DataType.TXT)
            assert storage == storage_val

    def test_display_datatype_roundtrip_hex(self):
        for display_val, expected in [("0", "0000"), ("FF", "00FF"), ("FFFF", "FFFF")]:
            native = display_to_datatype(display_val, DataType.HEX)
            display = datatype_to_display(native, DataType.HEX)
            assert display == expected

    def test_display_datatype_roundtrip_txt(self):
        for char in ["A", "Z", "0", " "]:
            native = display_to_datatype(char, DataType.TXT)
            display = datatype_to_display(native, DataType.TXT)
            assert display == char

    def test_full_pipeline_snapshot(self):
        """Full pipeline: CDV storage -> datatype -> display string."""
        cases = [
            ("4286578685", DataType.FLOAT, "-3.402823E+38"),
            ("2139095037", DataType.FLOAT, "3.402823E+38"),
            ("0", DataType.HEX, "0000"),
            ("65535", DataType.HEX, "FFFF"),
            ("1", DataType.HEX, "0001"),
            ("4294967295", DataType.INT, "-1"),
            ("4294967295", DataType.INT2, "-1"),
        ]
        for storage_val, data_type, expected_display in cases:
            native = storage_to_datatype(storage_val, data_type)
            display = datatype_to_display(native, data_type)
            assert display == expected_display, (
                f"Pipeline failed for {storage_val} (type {data_type}): "
                f"got {display!r}, expected {expected_display!r}"
            )

    def test_full_pipeline_float_pi(self):
        """Full pipeline for pi-ish float value."""
        native = storage_to_datatype("1078523331", DataType.FLOAT)
        display = datatype_to_display(native, DataType.FLOAT)
        assert display.startswith("3.14")


class TestValidateNewValue:
    def test_empty_is_valid(self):
        assert validate_new_value("", DataType.INT) == (True, "")

    def test_invalid_int(self):
        assert validate_new_value("abc", DataType.INT) == (False, "Must be integer")

    def test_valid_int(self):
        assert validate_new_value("100", DataType.INT) == (True, "")


class TestDataviewRowValidateNewValue:
    def test_read_only_address(self):
        row = DataviewRow(address="XD0", data_type=DataType.HEX)
        assert row.validate_new_value("0001") == (False, "Read-only address")

    def test_no_data_type(self):
        row = DataviewRow(address="DS1")
        assert row.validate_new_value("100") == (False, "No address set")

    def test_delegates_validation(self):
        row = DataviewRow(address="DS1", data_type=DataType.INT)
        assert row.validate_new_value("abc") == (False, "Must be integer")


class TestNewValueDisplay:
    def test_empty_when_no_new_value(self):
        row = DataviewRow(address="DS1", data_type=DataType.INT)
        assert row.new_value_display == ""

    def test_empty_when_no_data_type(self):
        row = DataviewRow(address="DS1", new_value="100")
        assert row.new_value_display == ""

    def test_int_round_trip_display(self):
        row = DataviewRow(address="DS1", data_type=DataType.INT, new_value="100")
        assert row.new_value_display == "100"


class TestSetNewValueFromDisplay:
    def test_clear_on_empty(self):
        row = DataviewRow(address="DS1", data_type=DataType.INT, new_value="100")
        assert row.set_new_value_from_display("") is True
        assert row.new_value == ""

    def test_fails_without_data_type(self):
        row = DataviewRow(address="DS1")
        assert row.set_new_value_from_display("100") is False

    def test_fails_on_invalid_input(self):
        row = DataviewRow(address="DS1", data_type=DataType.INT)
        assert row.set_new_value_from_display("abc") is False

    def test_sets_storage_value(self):
        row = DataviewRow(address="DS1", data_type=DataType.INT)
        assert row.set_new_value_from_display("100") is True
        assert row.new_value == "100"
        assert row.new_value_display == "100"


class TestLoadCdv:
    """Tests for load_cdv function."""

    def test_load_basic_cdv(self, tmp_path):
        cdv = tmp_path / "test.cdv"
        lines = ["0,0,0\n"]
        lines.append(f"X001,{_CdvStorageCode.BIT}\n")
        lines.append(f"DS1,{_CdvStorageCode.INT}\n")
        for _ in range(98):
            lines.append(",0\n")
        cdv.write_text("".join(lines), encoding="utf-16")

        rows, has_new_values, header = load_cdv(cdv)
        assert len(rows) == MAX_DATAVIEW_ROWS
        assert has_new_values is False
        assert rows[0].address == "X001"
        assert rows[0].data_type == DataType.BIT
        assert rows[1].address == "DS1"
        assert rows[1].data_type == DataType.INT
        assert rows[2].is_empty
        assert header == "0,0,0"

    def test_load_infers_data_type_when_missing(self, tmp_path):
        cdv = tmp_path / "test.cdv"
        lines = ["0,0,0\n", "DS1,\n"]
        for _ in range(99):
            lines.append(",0\n")
        cdv.write_text("".join(lines), encoding="utf-16")

        rows, _has_new_values, _header = load_cdv(cdv)
        assert rows[0].data_type == DataType.INT

    def test_load_with_new_values(self, tmp_path):
        cdv = tmp_path / "test.cdv"
        lines = ["-1,0,0\n"]
        lines.append(f"X001,{_CdvStorageCode.BIT},1\n")
        for _ in range(99):
            lines.append(",0\n")
        cdv.write_text("".join(lines), encoding="utf-16")

        rows, has_new_values, _header = load_cdv(cdv)
        assert has_new_values is True
        assert rows[0].new_value == "1"

    def test_load_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_cdv(tmp_path / "missing.cdv")


class TestSaveCdv:
    """Tests for save_cdv function."""

    def test_save_and_reload(self, tmp_path):
        cdv = tmp_path / "test.cdv"
        rows = create_empty_dataview()
        rows[0].address = "X001"
        rows[0].data_type = DataType.BIT
        rows[1].address = "DS1"
        rows[1].data_type = DataType.INT

        save_cdv(cdv, rows, has_new_values=False)

        loaded_rows, has_new_values, _header = load_cdv(cdv)
        assert has_new_values is False
        assert loaded_rows[0].address == "X001"
        assert loaded_rows[0].data_type == DataType.BIT
        assert loaded_rows[1].address == "DS1"
        assert loaded_rows[1].data_type == DataType.INT
        assert loaded_rows[2].is_empty

    def test_save_with_new_values(self, tmp_path):
        cdv = tmp_path / "test.cdv"
        rows = create_empty_dataview()
        rows[0].address = "X001"
        rows[0].data_type = DataType.BIT
        rows[0].new_value = "1"

        save_cdv(cdv, rows, has_new_values=True)

        loaded_rows, has_new_values, _header = load_cdv(cdv)
        assert has_new_values is True
        assert loaded_rows[0].new_value == "1"


class TestCheckCdv:
    def test_check_cdv_file_valid(self, tmp_path):
        cdv = tmp_path / "valid.cdv"
        rows = create_empty_dataview()
        rows[0].address = "X001"
        rows[0].data_type = DataType.BIT
        save_cdv(cdv, rows, has_new_values=False)

        assert check_cdv_file(cdv) == []

    def test_check_cdv_file_invalid_address(self, tmp_path):
        cdv = tmp_path / "invalid-address.cdv"
        rows = create_empty_dataview()
        rows[0].address = "INVALID"
        rows[0].data_type = DataType.BIT
        save_cdv(cdv, rows, has_new_values=False)

        issues = check_cdv_file(cdv)
        assert len(issues) == 1
        assert "Invalid address format" in issues[0]

    def test_check_cdv_file_type_mismatch(self, tmp_path):
        cdv = tmp_path / "mismatch.cdv"
        rows = create_empty_dataview()
        rows[0].address = "DS1"
        rows[0].data_type = DataType.BIT
        save_cdv(cdv, rows, has_new_values=False)

        issues = check_cdv_file(cdv)
        assert len(issues) == 1
        assert "Data type mismatch" in issues[0]

    def test_check_cdv_file_invalid_new_value_bit(self, tmp_path):
        cdv = tmp_path / "invalid-bit.cdv"
        rows = create_empty_dataview()
        rows[0].address = "X001"
        rows[0].data_type = DataType.BIT
        rows[0].new_value = "2"
        save_cdv(cdv, rows, has_new_values=True)

        issues = check_cdv_file(cdv)
        assert len(issues) == 1
        assert "invalid for BIT" in issues[0]

    def test_check_cdv_file_non_writable_with_new_value(self, tmp_path):
        cdv = tmp_path / "non-writable.cdv"
        rows = create_empty_dataview()
        rows[0].address = "XD0"
        rows[0].data_type = DataType.HEX
        rows[0].new_value = "1"
        save_cdv(cdv, rows, has_new_values=True)

        issues = check_cdv_file(cdv)
        assert len(issues) == 1
        assert "not writable" in issues[0]
