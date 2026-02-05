"""Tests for pyclickplc.addresses module."""

from dataclasses import FrozenInstanceError, replace

import pytest

from pyclickplc.addresses import (
    AddressRecord,
    format_address_display,
    get_addr_key,
    is_xd_yd_hidden_slot,
    is_xd_yd_upper_byte,
    normalize_address,
    parse_addr_key,
    parse_address,
    parse_address_display,
    xd_yd_display_to_mdb,
    xd_yd_mdb_to_display,
)
from pyclickplc.banks import BANKS, DataType

# ==============================================================================
# addr_key functions
# ==============================================================================


class TestAddrKey:
    def test_get_parse_roundtrip_all_types(self):
        for mem_type in BANKS:
            addr = 1
            key = get_addr_key(mem_type, addr)
            parsed_type, parsed_addr = parse_addr_key(key)
            assert parsed_type == mem_type
            assert parsed_addr == addr

    def test_specific_values(self):
        assert get_addr_key("X", 1) == 0x0000001
        assert get_addr_key("DS", 100) == 0x6000064
        assert get_addr_key("TXT", 1) == 0xF000001

    def test_unknown_type_raises(self):
        with pytest.raises(KeyError):
            get_addr_key("FAKE", 1)


# ==============================================================================
# XD/YD helpers
# ==============================================================================


class TestXdYdHelpers:
    def test_upper_byte(self):
        assert is_xd_yd_upper_byte("XD", 1) is True
        assert is_xd_yd_upper_byte("YD", 1) is True
        assert is_xd_yd_upper_byte("XD", 0) is False
        assert is_xd_yd_upper_byte("XD", 2) is False
        assert is_xd_yd_upper_byte("DS", 1) is False

    def test_hidden_slot(self):
        assert is_xd_yd_hidden_slot("XD", 3) is True
        assert is_xd_yd_hidden_slot("XD", 5) is True
        assert is_xd_yd_hidden_slot("XD", 15) is True
        assert is_xd_yd_hidden_slot("XD", 0) is False
        assert is_xd_yd_hidden_slot("XD", 1) is False
        assert is_xd_yd_hidden_slot("XD", 2) is False
        assert is_xd_yd_hidden_slot("DS", 3) is False

    def test_mdb_to_display(self):
        assert xd_yd_mdb_to_display(0) == 0
        assert xd_yd_mdb_to_display(1) == 0  # XD0u -> display 0
        assert xd_yd_mdb_to_display(2) == 1
        assert xd_yd_mdb_to_display(4) == 2
        assert xd_yd_mdb_to_display(16) == 8

    def test_display_to_mdb(self):
        assert xd_yd_display_to_mdb(0) == 0
        assert xd_yd_display_to_mdb(0, upper_byte=True) == 1
        assert xd_yd_display_to_mdb(1) == 2
        assert xd_yd_display_to_mdb(8) == 16

    def test_mdb_display_roundtrip(self):
        # display -> mdb -> display for 0-8
        for d in range(9):
            mdb = xd_yd_display_to_mdb(d)
            assert xd_yd_mdb_to_display(mdb) == d


# ==============================================================================
# format_address_display
# ==============================================================================


class TestFormatAddressDisplay:
    def test_x_y_padded(self):
        assert format_address_display("X", 1) == "X001"
        assert format_address_display("Y", 816) == "Y816"
        assert format_address_display("X", 36) == "X036"

    def test_xd_yd_special(self):
        assert format_address_display("XD", 0) == "XD0"
        assert format_address_display("XD", 1) == "XD0u"
        assert format_address_display("XD", 2) == "XD1"
        assert format_address_display("XD", 16) == "XD8"

    def test_ds_no_padding(self):
        assert format_address_display("DS", 1) == "DS1"
        assert format_address_display("DS", 100) == "DS100"
        assert format_address_display("DS", 4500) == "DS4500"


# ==============================================================================
# parse_address_display
# ==============================================================================


class TestParseAddressDisplay:
    def test_basic_types(self):
        assert parse_address_display("X001") == ("X", 1)
        assert parse_address_display("DS100") == ("DS", 100)
        assert parse_address_display("C1") == ("C", 1)

    def test_case_insensitive(self):
        assert parse_address_display("x001") == ("X", 1)
        assert parse_address_display("ds100") == ("DS", 100)

    def test_xd_yd(self):
        assert parse_address_display("XD0") == ("XD", 0)
        assert parse_address_display("XD0U") == ("XD", 1)
        assert parse_address_display("XD0u") == ("XD", 1)
        assert parse_address_display("XD1") == ("XD", 2)
        assert parse_address_display("XD8") == ("XD", 16)

    def test_invalid_returns_none(self):
        assert parse_address_display("") is None
        assert parse_address_display("FAKE1") is None
        assert parse_address_display("XD1U") is None  # Only XD0 can have U
        assert parse_address_display("!!!") is None


# ==============================================================================
# parse_address
# ==============================================================================


class TestParseAddress:
    def test_basic(self):
        assert parse_address("DS100") == ("DS", 100)
        assert parse_address("C1") == ("C", 1)

    def test_case_insensitive(self):
        assert parse_address("ds100") == ("DS", 100)
        assert parse_address("x001") == ("X", 1)

    def test_xd_returns_display_addr(self):
        # parse_address returns display address, NOT MDB
        assert parse_address("XD1") == ("XD", 1)
        assert parse_address("XD8") == ("XD", 8)
        assert parse_address("XD0") == ("XD", 0)

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError):
            parse_address("")
        with pytest.raises(ValueError):
            parse_address("FAKE1")
        with pytest.raises(ValueError):
            parse_address("DS0")  # Out of range
        with pytest.raises(ValueError):
            parse_address("DS4501")  # Out of range
        with pytest.raises(ValueError):
            parse_address("!!!")

    def test_raises_on_sparse_gap(self):
        with pytest.raises(ValueError):
            parse_address("X017")  # In gap between slots


# ==============================================================================
# normalize_address
# ==============================================================================


class TestNormalizeAddress:
    def test_roundtrip(self):
        assert normalize_address("x1") == "X001"
        assert normalize_address("X001") == "X001"
        assert normalize_address("ds100") == "DS100"
        assert normalize_address("xd0u") == "XD0u"
        assert normalize_address("XD0U") == "XD0u"

    def test_invalid_returns_none(self):
        assert normalize_address("") is None
        assert normalize_address("FAKE1") is None


# ==============================================================================
# AddressRecord
# ==============================================================================


class TestAddressRecord:
    def test_frozen(self):
        rec = AddressRecord(memory_type="DS", address=1, data_type=DataType.INT)
        with pytest.raises(FrozenInstanceError):
            rec.nickname = "test"  # type: ignore[misc]

    def test_replace(self):
        rec = AddressRecord(memory_type="DS", address=1, data_type=DataType.INT)
        new_rec = replace(rec, nickname="Updated")
        assert new_rec.nickname == "Updated"
        assert rec.nickname == ""

    def test_addr_key_matches_standalone(self):
        rec = AddressRecord(memory_type="DS", address=100, data_type=DataType.INT)
        assert rec.addr_key == get_addr_key("DS", 100)

    def test_display_address_matches_standalone(self):
        rec = AddressRecord(memory_type="X", address=1, data_type=DataType.BIT)
        assert rec.display_address == format_address_display("X", 1)
        assert rec.display_address == "X001"

    def test_data_type_display(self):
        rec = AddressRecord(memory_type="DS", address=1, data_type=DataType.INT)
        assert rec.data_type_display == "INT"

    def test_has_content_empty(self):
        rec = AddressRecord(memory_type="DS", address=1, data_type=DataType.INT, retentive=True)
        assert rec.has_content is False  # Default retentive for DS is True

    def test_has_content_with_nickname(self):
        rec = AddressRecord(
            memory_type="DS",
            address=1,
            data_type=DataType.INT,
            nickname="Test",
            retentive=True,
        )
        assert rec.has_content is True

    def test_has_content_non_default_retentive(self):
        rec = AddressRecord(
            memory_type="DS",
            address=1,
            data_type=DataType.INT,
            retentive=False,  # DS default is True
        )
        assert rec.has_content is True

    def test_can_edit_initial_value(self):
        editable = AddressRecord(memory_type="DS", address=1, data_type=DataType.INT)
        assert editable.can_edit_initial_value is True

        non_editable = AddressRecord(memory_type="SC", address=1, data_type=DataType.BIT)
        assert non_editable.can_edit_initial_value is False

    def test_can_edit_retentive(self):
        editable = AddressRecord(memory_type="DS", address=1, data_type=DataType.INT)
        assert editable.can_edit_retentive is True

        non_editable = AddressRecord(memory_type="XD", address=0, data_type=DataType.HEX)
        assert non_editable.can_edit_retentive is False

    def test_used_default_none(self):
        rec = AddressRecord(memory_type="DS", address=1, data_type=DataType.INT)
        assert rec.used is None

    def test_is_default_initial_value(self):
        rec = AddressRecord(memory_type="DS", address=1, data_type=DataType.INT)
        assert rec.is_default_initial_value is True

        rec_zero = replace(rec, initial_value="0")
        assert rec_zero.is_default_initial_value is True

        rec_nonzero = replace(rec, initial_value="42")
        assert rec_nonzero.is_default_initial_value is False

    def test_is_default_retentive(self):
        # DS default is True
        rec = AddressRecord(
            memory_type="DS",
            address=1,
            data_type=DataType.INT,
            retentive=True,
        )
        assert rec.is_default_retentive is True

        rec2 = replace(rec, retentive=False)
        assert rec2.is_default_retentive is False
