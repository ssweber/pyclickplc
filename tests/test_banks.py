"""Tests for pyclickplc.banks module."""

from dataclasses import FrozenInstanceError

import pytest

from pyclickplc.banks import (
    _INDEX_TO_TYPE,
    _SPARSE_RANGES,
    BANKS,
    BIT_ONLY_TYPES,
    DEFAULT_RETENTIVE,
    INTERLEAVED_PAIRS,
    INTERLEAVED_TYPE_PAIRS,
    MEMORY_TYPE_BASES,
    MEMORY_TYPE_TO_DATA_TYPE,
    NON_EDITABLE_TYPES,
    DataType,
    is_valid_address,
)

# ==============================================================================
# DataType
# ==============================================================================


class TestDataType:
    def test_enum_values(self):
        assert DataType.BIT == 0
        assert DataType.INT == 1
        assert DataType.INT2 == 2
        assert DataType.FLOAT == 3
        assert DataType.HEX == 4
        assert DataType.TXT == 6

    def test_is_int_enum(self):
        assert isinstance(DataType.BIT, int)
        assert DataType.BIT + 1 == 1

    def test_all_members(self):
        assert len(DataType) == 6


# ==============================================================================
# BankConfig
# ==============================================================================


class TestBankConfig:
    def test_frozen(self):
        bank = BANKS["DS"]
        with pytest.raises(FrozenInstanceError):
            bank.name = "other"  # type: ignore[misc]

    def test_all_16_banks_defined(self):
        assert len(BANKS) == 16

    def test_bank_names(self):
        expected = {
            "X",
            "Y",
            "C",
            "T",
            "CT",
            "SC",
            "DS",
            "DD",
            "DH",
            "DF",
            "XD",
            "YD",
            "TD",
            "CTD",
            "SD",
            "TXT",
        }
        assert set(BANKS) == expected

    def test_sparse_ranges_on_x_y_only(self):
        for name, bank in BANKS.items():
            if name in ("X", "Y"):
                assert bank.valid_ranges is not None
                assert bank.valid_ranges == _SPARSE_RANGES
            else:
                assert bank.valid_ranges is None

    def test_sparse_ranges_structure(self):
        assert len(_SPARSE_RANGES) == 10
        assert _SPARSE_RANGES[0] == (1, 16)
        assert _SPARSE_RANGES[-1] == (821, 836)

    def test_interleaved_pairs(self):
        assert BANKS["T"].interleaved_with == "TD"
        assert BANKS["TD"].interleaved_with == "T"
        assert BANKS["CT"].interleaved_with == "CTD"
        assert BANKS["CTD"].interleaved_with == "CT"

    def test_non_interleaved_banks(self):
        for name in ("X", "Y", "C", "SC", "DS", "DD", "DH", "DF", "XD", "YD", "SD", "TXT"):
            assert BANKS[name].interleaved_with is None

    def test_xd_yd_start_at_zero(self):
        assert BANKS["XD"].min_addr == 0
        assert BANKS["YD"].min_addr == 0

    def test_specific_ranges(self):
        assert BANKS["DS"].max_addr == 4500
        assert BANKS["C"].max_addr == 2000
        assert BANKS["T"].max_addr == 500
        assert BANKS["CT"].max_addr == 250
        assert BANKS["DD"].max_addr == 1000
        assert BANKS["TXT"].max_addr == 1000

    def test_data_types(self):
        assert BANKS["X"].data_type == DataType.BIT
        assert BANKS["DS"].data_type == DataType.INT
        assert BANKS["DD"].data_type == DataType.INT2
        assert BANKS["DF"].data_type == DataType.FLOAT
        assert BANKS["DH"].data_type == DataType.HEX
        assert BANKS["TXT"].data_type == DataType.TXT


# ==============================================================================
# Legacy Dicts
# ==============================================================================


class TestLegacyDicts:
    def test_memory_type_bases_keys_match_banks(self):
        assert set(MEMORY_TYPE_BASES) == set(BANKS)

    def test_memory_type_bases_unique_values(self):
        values = list(MEMORY_TYPE_BASES.values())
        assert len(values) == len(set(values))

    def test_index_to_type_roundtrip(self):
        for name, base in MEMORY_TYPE_BASES.items():
            index = base >> 24
            assert _INDEX_TO_TYPE[index] == name

    def test_default_retentive_keys_match_banks(self):
        assert set(DEFAULT_RETENTIVE) == set(BANKS)

    def test_interleaved_type_pairs(self):
        assert frozenset({"T", "TD"}) in INTERLEAVED_TYPE_PAIRS
        assert frozenset({"CT", "CTD"}) in INTERLEAVED_TYPE_PAIRS
        assert len(INTERLEAVED_TYPE_PAIRS) == 2

    def test_interleaved_pairs_bidirectional(self):
        assert INTERLEAVED_PAIRS["T"] == "TD"
        assert INTERLEAVED_PAIRS["TD"] == "T"
        assert INTERLEAVED_PAIRS["CT"] == "CTD"
        assert INTERLEAVED_PAIRS["CTD"] == "CT"

    def test_non_editable_types(self):
        assert NON_EDITABLE_TYPES == frozenset({"SC", "SD", "XD", "YD"})

    def test_memory_type_to_data_type(self):
        for name, bank in BANKS.items():
            assert MEMORY_TYPE_TO_DATA_TYPE[name] == bank.data_type


# ==============================================================================
# Derived Constants
# ==============================================================================


class TestDerivedConstants:
    def test_bit_only_types(self):
        expected = {"X", "Y", "C", "T", "CT", "SC"}
        assert BIT_ONLY_TYPES == expected


# ==============================================================================
# is_valid_address
# ==============================================================================


class TestIsValidAddress:
    def test_contiguous_valid(self):
        assert is_valid_address("DS", 1) is True
        assert is_valid_address("DS", 4500) is True
        assert is_valid_address("DS", 2000) is True

    def test_contiguous_invalid(self):
        assert is_valid_address("DS", 0) is False
        assert is_valid_address("DS", 4501) is False

    def test_sparse_valid(self):
        assert is_valid_address("X", 1) is True
        assert is_valid_address("X", 16) is True
        assert is_valid_address("X", 101) is True
        assert is_valid_address("Y", 821) is True

    def test_sparse_invalid_gap(self):
        assert is_valid_address("X", 17) is False
        assert is_valid_address("X", 20) is False
        assert is_valid_address("X", 100) is False

    def test_sparse_boundary(self):
        # X036 is the end of slot 2
        assert is_valid_address("X", 36) is True
        # X037 is in the gap between slots
        assert is_valid_address("X", 37) is False

    def test_xd_range(self):
        assert is_valid_address("XD", 0) is True
        assert is_valid_address("XD", 16) is True
        assert is_valid_address("XD", 8) is True
        assert is_valid_address("XD", 17) is False

    def test_unknown_bank(self):
        assert is_valid_address("FAKE", 1) is False
