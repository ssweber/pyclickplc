"""Tests for pyclickplc.dataview — DataView model and CDV file I/O."""

from pyclickplc.dataview import (
    MAX_DATAVIEW_ROWS,
    WRITABLE_SC,
    WRITABLE_SD,
    DataviewRow,
    TypeCode,
    create_empty_dataview,
    display_to_storage,
    get_type_code_for_address,
    is_address_writable,
    load_cdv,
    save_cdv,
    storage_to_display,
)


class TestGetTypeCodeForAddress:
    """Tests for get_type_code_for_address function."""

    def test_bit_addresses(self):
        assert get_type_code_for_address("X001") == TypeCode.BIT
        assert get_type_code_for_address("Y001") == TypeCode.BIT
        assert get_type_code_for_address("C1") == TypeCode.BIT
        assert get_type_code_for_address("T1") == TypeCode.BIT
        assert get_type_code_for_address("CT1") == TypeCode.BIT
        assert get_type_code_for_address("SC1") == TypeCode.BIT

    def test_int_addresses(self):
        assert get_type_code_for_address("DS1") == TypeCode.INT
        assert get_type_code_for_address("TD1") == TypeCode.INT
        assert get_type_code_for_address("SD1") == TypeCode.INT

    def test_int2_addresses(self):
        assert get_type_code_for_address("DD1") == TypeCode.INT2
        assert get_type_code_for_address("CTD1") == TypeCode.INT2

    def test_hex_addresses(self):
        assert get_type_code_for_address("DH1") == TypeCode.HEX
        assert get_type_code_for_address("XD0") == TypeCode.HEX
        assert get_type_code_for_address("YD0") == TypeCode.HEX

    def test_float_addresses(self):
        assert get_type_code_for_address("DF1") == TypeCode.FLOAT

    def test_txt_addresses(self):
        assert get_type_code_for_address("TXT1") == TypeCode.TXT

    def test_invalid_address(self):
        assert get_type_code_for_address("INVALID") is None
        assert get_type_code_for_address("") is None


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
        assert row.type_code == 0
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

    def test_update_type_code(self):
        row = DataviewRow(address="DS100")
        assert row.update_type_code() is True
        assert row.type_code == TypeCode.INT

        row.address = "INVALID"
        assert row.update_type_code() is False

    def test_clear(self):
        row = DataviewRow(
            address="X001",
            type_code=TypeCode.BIT,
            new_value="1",
            nickname="Test",
            comment="Comment",
        )
        row.clear()
        assert row.address == ""
        assert row.type_code == 0
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


class TestStorageToDisplay:
    """Tests for storage_to_display conversion."""

    def test_bit_values(self):
        assert storage_to_display("1", TypeCode.BIT) == "1"
        assert storage_to_display("0", TypeCode.BIT) == "0"

    def test_int_positive(self):
        assert storage_to_display("0", TypeCode.INT) == "0"
        assert storage_to_display("100", TypeCode.INT) == "100"
        assert storage_to_display("32767", TypeCode.INT) == "32767"

    def test_int_negative(self):
        assert storage_to_display("4294934528", TypeCode.INT) == "-32768"
        assert storage_to_display("4294967295", TypeCode.INT) == "-1"
        assert storage_to_display("65535", TypeCode.INT) == "-1"

    def test_int2_positive(self):
        assert storage_to_display("0", TypeCode.INT2) == "0"
        assert storage_to_display("100", TypeCode.INT2) == "100"
        assert storage_to_display("2147483647", TypeCode.INT2) == "2147483647"

    def test_int2_negative(self):
        assert storage_to_display("2147483648", TypeCode.INT2) == "-2147483648"
        assert storage_to_display("4294967294", TypeCode.INT2) == "-2"
        assert storage_to_display("4294967295", TypeCode.INT2) == "-1"

    def test_float_values(self):
        assert storage_to_display("0", TypeCode.FLOAT) == "0"
        assert storage_to_display("1065353216", TypeCode.FLOAT) == "1"
        val = storage_to_display("1078523331", TypeCode.FLOAT)
        assert val.startswith("3.14")
        assert "-" in storage_to_display("4286578685", TypeCode.FLOAT)

    def test_hex_values(self):
        assert storage_to_display("65535", TypeCode.HEX) == "FFFF"
        assert storage_to_display("255", TypeCode.HEX) == "00FF"
        assert storage_to_display("0", TypeCode.HEX) == "0000"

    def test_txt_values(self):
        assert storage_to_display("48", TypeCode.TXT) == "0"
        assert storage_to_display("65", TypeCode.TXT) == "A"
        assert storage_to_display("90", TypeCode.TXT) == "Z"
        assert storage_to_display("49", TypeCode.TXT) == "1"

    def test_empty_value(self):
        assert storage_to_display("", TypeCode.INT) == ""
        assert storage_to_display("", TypeCode.HEX) == ""

    def test_txt_space(self):
        assert storage_to_display("32", TypeCode.TXT) == " "


class TestDisplayToStorage:
    """Tests for display_to_storage conversion."""

    def test_bit_values(self):
        assert display_to_storage("1", TypeCode.BIT) == "1"
        assert display_to_storage("0", TypeCode.BIT) == "0"

    def test_int_positive(self):
        assert display_to_storage("0", TypeCode.INT) == "0"
        assert display_to_storage("100", TypeCode.INT) == "100"
        assert display_to_storage("32767", TypeCode.INT) == "32767"

    def test_int_negative(self):
        assert display_to_storage("-32768", TypeCode.INT) == "4294934528"
        assert display_to_storage("-1", TypeCode.INT) == "4294967295"

    def test_int2_positive(self):
        assert display_to_storage("0", TypeCode.INT2) == "0"
        assert display_to_storage("100", TypeCode.INT2) == "100"

    def test_int2_negative(self):
        assert display_to_storage("-2147483648", TypeCode.INT2) == "2147483648"
        assert display_to_storage("-2", TypeCode.INT2) == "4294967294"

    def test_float_values(self):
        assert display_to_storage("0.0", TypeCode.FLOAT) == "0"
        assert display_to_storage("1.0", TypeCode.FLOAT) == "1065353216"
        assert display_to_storage("-1.0", TypeCode.FLOAT) == "3212836864"

    def test_hex_values(self):
        assert display_to_storage("FFFF", TypeCode.HEX) == "65535"
        assert display_to_storage("FF", TypeCode.HEX) == "255"
        assert display_to_storage("0xFF", TypeCode.HEX) == "255"
        assert display_to_storage("0", TypeCode.HEX) == "0"

    def test_txt_values(self):
        assert display_to_storage("0", TypeCode.TXT) == "48"
        assert display_to_storage("A", TypeCode.TXT) == "65"
        assert display_to_storage("Z", TypeCode.TXT) == "90"
        assert display_to_storage("1", TypeCode.TXT) == "49"

    def test_empty_value(self):
        assert display_to_storage("", TypeCode.INT) == ""
        assert display_to_storage("", TypeCode.HEX) == ""

    def test_txt_space(self):
        assert display_to_storage(" ", TypeCode.TXT) == "32"

    def test_snapshot_data_consistency(self):
        assert storage_to_display("4286578685", TypeCode.FLOAT) == "-3.402823E+38"
        assert storage_to_display("2139095037", TypeCode.FLOAT) == "3.402823E+38"
        assert storage_to_display("1078523331", TypeCode.FLOAT).startswith("3.14")
        assert storage_to_display("0", TypeCode.HEX) == "0000"
        assert storage_to_display("65535", TypeCode.HEX) == "FFFF"
        assert storage_to_display("1", TypeCode.HEX) == "0001"
        assert storage_to_display("4294967295", TypeCode.INT) == "-1"
        assert storage_to_display("4294967295", TypeCode.INT2) == "-1"


class TestRoundTripConversion:
    """Tests for round-trip storage <-> display conversion."""

    def test_int_roundtrip(self):
        for val in ["-32768", "-1", "0", "100", "32767"]:
            storage = display_to_storage(val, TypeCode.INT)
            display = storage_to_display(storage, TypeCode.INT)
            assert display == val, f"Round-trip failed for {val}"

    def test_int2_roundtrip(self):
        for val in ["-2147483648", "-2", "-1", "0", "100", "2147483647"]:
            storage = display_to_storage(val, TypeCode.INT2)
            display = storage_to_display(storage, TypeCode.INT2)
            assert display == val, f"Round-trip failed for {val}"

    def test_hex_roundtrip(self):
        test_cases = [
            ("0", "0000"),
            ("FF", "00FF"),
            ("FFFF", "FFFF"),
        ]
        for input_val, expected_display in test_cases:
            storage = display_to_storage(input_val, TypeCode.HEX)
            display = storage_to_display(storage, TypeCode.HEX)
            assert display == expected_display, f"Round-trip failed for {input_val}"

    def test_txt_roundtrip(self):
        for val in ["0", "A", "Z", "1"]:
            storage = display_to_storage(val, TypeCode.TXT)
            display = storage_to_display(storage, TypeCode.TXT)
            assert display == val, f"Round-trip failed for {val}"


class TestLoadCdv:
    """Tests for load_cdv function."""

    def test_load_basic_cdv(self, tmp_path):
        cdv = tmp_path / "test.cdv"
        lines = ["0,0,0\n"]
        lines.append("X001,768\n")
        lines.append("DS1,0\n")
        for _ in range(98):
            lines.append(",0\n")
        cdv.write_text("".join(lines), encoding="utf-16")

        rows, has_new_values, header = load_cdv(cdv)
        assert len(rows) == MAX_DATAVIEW_ROWS
        assert has_new_values is False
        assert rows[0].address == "X001"
        assert rows[0].type_code == 768
        assert rows[1].address == "DS1"
        assert rows[1].type_code == 0
        assert rows[2].is_empty

    def test_load_with_new_values(self, tmp_path):
        cdv = tmp_path / "test.cdv"
        lines = ["-1,0,0\n"]
        lines.append("X001,768,1\n")
        for _ in range(99):
            lines.append(",0\n")
        cdv.write_text("".join(lines), encoding="utf-16")

        rows, has_new_values, _header = load_cdv(cdv)
        assert has_new_values is True
        assert rows[0].new_value == "1"

    def test_load_nonexistent(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            load_cdv(tmp_path / "missing.cdv")


class TestSaveCdv:
    """Tests for save_cdv function."""

    def test_save_and_reload(self, tmp_path):
        cdv = tmp_path / "test.cdv"
        rows = create_empty_dataview()
        rows[0].address = "X001"
        rows[0].type_code = TypeCode.BIT
        rows[1].address = "DS1"
        rows[1].type_code = TypeCode.INT

        save_cdv(cdv, rows, has_new_values=False)

        loaded_rows, has_new_values, header = load_cdv(cdv)
        assert has_new_values is False
        assert loaded_rows[0].address == "X001"
        assert loaded_rows[0].type_code == TypeCode.BIT
        assert loaded_rows[1].address == "DS1"
        assert loaded_rows[1].type_code == TypeCode.INT
        assert loaded_rows[2].is_empty

    def test_save_with_new_values(self, tmp_path):
        cdv = tmp_path / "test.cdv"
        rows = create_empty_dataview()
        rows[0].address = "X001"
        rows[0].type_code = TypeCode.BIT
        rows[0].new_value = "1"

        save_cdv(cdv, rows, has_new_values=True)

        loaded_rows, has_new_values, _header = load_cdv(cdv)
        assert has_new_values is True
        assert loaded_rows[0].new_value == "1"
