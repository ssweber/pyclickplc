"""Tests for pyclickplc.addresses module."""

from dataclasses import FrozenInstanceError, replace
from typing import Any, cast

import pytest

from pyclickplc.addresses import (
    AddressRecord,
    format_address_display,
    get_addr_key,
    is_xd_yd_hidden_slot,
    is_xd_yd_upper_byte,
    iter_address_slots,
    make_address_record,
    normalize_address,
    parse_addr_key,
    parse_address,
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
# parse_address
# ==============================================================================


class TestParseAddress:
    def test_basic_types(self):
        assert parse_address("X001") == ("X", 1)
        assert parse_address("DS100") == ("DS", 100)
        assert parse_address("C1") == ("C", 1)

    def test_case_insensitive(self):
        assert parse_address("x001") == ("X", 1)
        assert parse_address("ds100") == ("DS", 100)

    def test_xd_yd_returns_mdb(self):
        # parse_address returns MDB address
        assert parse_address("XD0") == ("XD", 0)
        assert parse_address("XD0U") == ("XD", 1)
        assert parse_address("XD0u") == ("XD", 1)
        assert parse_address("XD1") == ("XD", 2)
        assert parse_address("XD8") == ("XD", 16)

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
        with pytest.raises(ValueError):
            parse_address("XD1U")  # Only XD0 can have U

    def test_raises_on_sparse_gap(self):
        with pytest.raises(ValueError):
            parse_address("X017")  # In gap between slots

    @pytest.mark.parametrize(
        "address",
        [
            "DS1u",  # u suffix only on XD0u/YD0u
            "X001U",
            "TXT1u",
            "XD9",  # past XD8
            "DS١",  # Arabic-Indic digit one
            "DS１",  # fullwidth digit one
            "DS\U0001d7cf",  # mathematical bold digit one
            "ſC1",  # long s, which uppercases to S
            "ＤＳ1",  # fullwidth letters
            "DS 1",
            "DS+1",
        ],
    )
    def test_refuses_what_click_refuses(self, address):
        with pytest.raises(ValueError):
            parse_address(address)

    @pytest.mark.parametrize(
        ("address", "expected"),
        [
            # Kept until CLICK's own handling of these is checked
            ("DS0001", ("DS", 1)),
            ("X0001", ("X", 1)),
            ("XD01", ("XD", 2)),
            (" DS1 ", ("DS", 1)),
            ("\tx1\n", ("X", 1)),
        ],
    )
    def test_accepts_leading_zeros_and_surrounding_space(self, address, expected):
        assert parse_address(address) == expected


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
            cast(Any, rec).nickname = "test"

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

    def test_from_address_normalizes_and_infers(self):
        rec = AddressRecord.from_address("x1")
        assert rec.memory_type == "X"
        assert rec.address == 1
        assert rec.display_address == "X001"
        assert rec.data_type == DataType.BIT
        assert rec.retentive is False

    def test_from_address_uses_default_retentive(self):
        rec = AddressRecord.from_address("ds1")
        assert rec.memory_type == "DS"
        assert rec.address == 1
        assert rec.data_type == DataType.INT
        assert rec.retentive is True

    def test_from_address_overrides_retentive(self):
        rec = AddressRecord.from_address("ds1", retentive=False)
        assert rec.retentive is False

    def test_from_address_xd0u_maps_to_mdb_1(self):
        rec = AddressRecord.from_address("xd0u")
        assert rec.memory_type == "XD"
        assert rec.address == 1
        assert rec.display_address == "XD0u"

    @pytest.mark.parametrize("address", ["", "BAD1", "X017"])
    def test_from_address_invalid_raises(self, address: str):
        with pytest.raises(ValueError, match="Invalid address format"):
            AddressRecord.from_address(address)

    def test_make_address_record_uses_friendly_constructor(self):
        rec = make_address_record("ds1", nickname="Temp")
        assert rec == AddressRecord.from_address("ds1", nickname="Temp")

    def test_make_address_record_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid address format"):
            make_address_record("INVALID")

    def test_repr_concise_default(self):
        rec = AddressRecord(memory_type="DS", address=1, data_type=DataType.INT, retentive=True)
        assert repr(rec) == "AddressRecord(address='DS1', data_type='INT')"

    def test_repr_includes_meaningful_fields(self):
        rec = AddressRecord.from_address(
            "ds1",
            nickname="Temp",
            comment="Tank",
            initial_value="5",
            retentive=False,
            used=True,
        )
        assert repr(rec) == (
            "AddressRecord(address='DS1', data_type='INT', nickname='Temp', "
            "comment='Tank', initial_value='5', retentive=False, used=True)"
        )


# ==============================================================================
# iter_address_slots
# ==============================================================================


class TestIterAddressSlots:
    def test_round_trips_through_display_and_parse(self):
        for memory_type, address in iter_address_slots():
            assert parse_address(format_address_display(memory_type, address)) == (
                memory_type,
                address,
            )

    def test_banks_in_order_without_repeats(self):
        slots = list(iter_address_slots())
        assert len(slots) == len(set(slots))
        banks = [m for m, _ in slots]
        assert list(dict.fromkeys(banks)) == list(BANKS)
        assert banks == sorted(banks, key=list(BANKS).index)

    @pytest.mark.parametrize("bank", ["X", "Y"])
    def test_sparse_banks_yield_exactly_valid_ranges(self, bank):
        valid_ranges = BANKS[bank].valid_ranges
        assert valid_ranges is not None
        expected = [a for lo, hi in valid_ranges for a in range(lo, hi + 1)]
        assert [a for m, a in iter_address_slots() if m == bank] == expected

    @pytest.mark.parametrize("bank", ["XD", "YD"])
    def test_xd_yd_yield_the_slots_click_shows(self, bank):
        names = [format_address_display(m, a) for m, a in iter_address_slots() if m == bank]
        assert names == [f"{bank}0", f"{bank}0u", *(f"{bank}{n}" for n in range(1, 9))]
        assert not any(is_xd_yd_hidden_slot(m, a) for m, a in iter_address_slots() if m == bank)

    def test_counts_match_banks(self):
        counts: dict[str, int] = {}
        for memory_type, _ in iter_address_slots():
            counts[memory_type] = counts.get(memory_type, 0) + 1
        for name, bank in BANKS.items():
            if bank.valid_ranges is not None:
                expected = sum(hi - lo + 1 for lo, hi in bank.valid_ranges)
            elif name in ("XD", "YD"):
                expected = 10
            else:
                expected = bank.max_addr - bank.min_addr + 1
            assert counts[name] == expected, name
