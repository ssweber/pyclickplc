"""Tests for pyclickplc.modbus — Modbus protocol mapping layer."""

from __future__ import annotations

import math
import struct
from typing import Any, cast

import pytest

from pyclickplc.banks import DataType
from pyclickplc.modbus import (
    MODBUS_MAPPINGS,
    MODBUS_SIGNED,
    MODBUS_WIDTH,
    STRUCT_FORMATS,
    modbus_to_plc,
    pack_value,
    plc_to_modbus,
    unpack_value,
)

# ==============================================================================
# ModbusMapping & MODBUS_MAPPINGS
# ==============================================================================


class TestModbusMappings:
    """Tests for MODBUS_MAPPINGS dict and ModbusMapping dataclass."""

    def test_all_16_banks_present(self):
        assert len(MODBUS_MAPPINGS) == 16
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
            "TD",
            "CTD",
            "SD",
            "TXT",
            "XD",
            "YD",
        }
        assert set(MODBUS_MAPPINGS) == expected

    def test_frozen_dataclass(self):
        m = MODBUS_MAPPINGS["DS"]
        with pytest.raises(AttributeError):
            cast(Any, m).base = 999

    def test_coil_banks(self):
        coil_banks = {k for k, v in MODBUS_MAPPINGS.items() if v.is_coil}
        assert coil_banks == {"X", "Y", "C", "T", "CT", "SC"}

    def test_register_banks(self):
        reg_banks = {k for k, v in MODBUS_MAPPINGS.items() if not v.is_coil}
        assert reg_banks == {"DS", "DD", "DH", "DF", "TD", "CTD", "SD", "TXT", "XD", "YD"}

    def test_x_read_only(self):
        m = MODBUS_MAPPINGS["X"]
        assert m.function_codes == frozenset({2})
        assert not m.is_writable

    def test_t_read_only(self):
        assert not MODBUS_MAPPINGS["T"].is_writable

    def test_ct_read_only(self):
        assert not MODBUS_MAPPINGS["CT"].is_writable

    def test_xd_read_only(self):
        assert not MODBUS_MAPPINGS["XD"].is_writable

    def test_y_writable(self):
        m = MODBUS_MAPPINGS["Y"]
        assert m.function_codes == frozenset({1, 5, 15})
        assert m.is_writable

    def test_c_writable(self):
        assert MODBUS_MAPPINGS["C"].is_writable

    def test_ds_writable(self):
        m = MODBUS_MAPPINGS["DS"]
        assert m.function_codes == frozenset({3, 6, 16})
        assert m.is_writable

    def test_sc_writable_subset(self):
        m = MODBUS_MAPPINGS["SC"]
        assert m.writable is not None
        assert 53 in m.writable
        assert 50 not in m.writable  # ladder-only, not Modbus-writable
        assert 51 not in m.writable
        assert 120 in m.writable

    def test_sd_writable_subset(self):
        m = MODBUS_MAPPINGS["SD"]
        assert m.writable is not None
        assert 29 in m.writable
        assert 214 in m.writable
        assert 1 not in m.writable

    def test_sd_read_only_fc(self):
        """SD has FC 4 (read input registers) — not writable via FCs."""
        assert not MODBUS_MAPPINGS["SD"].is_writable

    def test_width_2_banks(self):
        for bank in ("DD", "DF", "CTD"):
            assert MODBUS_MAPPINGS[bank].width == 2, f"{bank} should be width 2"

    def test_width_1_banks(self):
        for bank in ("DS", "DH", "TXT", "TD", "SD", "XD", "YD"):
            assert MODBUS_MAPPINGS[bank].width == 1, f"{bank} should be width 1"


# ==============================================================================
# DataType-derived constants
# ==============================================================================


class TestDerivedConstants:
    def test_modbus_width_keys(self):
        assert set(MODBUS_WIDTH) == set(DataType)

    def test_modbus_width_values(self):
        assert MODBUS_WIDTH[DataType.BIT] == 1
        assert MODBUS_WIDTH[DataType.INT2] == 2
        assert MODBUS_WIDTH[DataType.FLOAT] == 2

    def test_modbus_signed(self):
        assert MODBUS_SIGNED[DataType.INT] is True
        assert MODBUS_SIGNED[DataType.HEX] is False

    def test_struct_formats(self):
        assert STRUCT_FORMATS[DataType.INT] == "h"
        assert STRUCT_FORMATS[DataType.INT2] == "i"
        assert STRUCT_FORMATS[DataType.FLOAT] == "f"
        assert STRUCT_FORMATS[DataType.HEX] == "H"


# ==============================================================================
# Forward mapping: plc_to_modbus
# ==============================================================================


class TestPlcToModbus:
    """Tests for plc_to_modbus forward mapping."""

    # --- Standard coils ---

    def test_c1(self):
        assert plc_to_modbus("C", 1) == (16384, 1)

    def test_c2000(self):
        assert plc_to_modbus("C", 2000) == (18383, 1)

    def test_t1(self):
        assert plc_to_modbus("T", 1) == (45056, 1)

    def test_ct1(self):
        assert plc_to_modbus("CT", 1) == (49152, 1)

    def test_sc1(self):
        assert plc_to_modbus("SC", 1) == (61440, 1)

    # --- Sparse coils (X) ---

    def test_x001(self):
        assert plc_to_modbus("X", 1) == (0, 1)

    def test_x016(self):
        assert plc_to_modbus("X", 16) == (15, 1)

    def test_x021(self):
        assert plc_to_modbus("X", 21) == (16, 1)

    def test_x036(self):
        assert plc_to_modbus("X", 36) == (31, 1)

    def test_x101(self):
        assert plc_to_modbus("X", 101) == (32, 1)

    def test_x116(self):
        assert plc_to_modbus("X", 116) == (47, 1)

    def test_x201(self):
        assert plc_to_modbus("X", 201) == (64, 1)

    def test_x816(self):
        assert plc_to_modbus("X", 816) == (271, 1)

    # --- Sparse coils (Y) ---

    def test_y001(self):
        assert plc_to_modbus("Y", 1) == (8192, 1)

    def test_y101(self):
        assert plc_to_modbus("Y", 101) == (8224, 1)

    # --- Standard registers ---

    def test_ds1(self):
        assert plc_to_modbus("DS", 1) == (0, 1)

    def test_ds4500(self):
        assert plc_to_modbus("DS", 4500) == (4499, 1)

    def test_dd1(self):
        assert plc_to_modbus("DD", 1) == (16384, 2)

    def test_dd2(self):
        assert plc_to_modbus("DD", 2) == (16386, 2)

    def test_df1(self):
        assert plc_to_modbus("DF", 1) == (28672, 2)

    def test_df2(self):
        assert plc_to_modbus("DF", 2) == (28674, 2)

    def test_dh1(self):
        assert plc_to_modbus("DH", 1) == (24576, 1)

    def test_txt1(self):
        assert plc_to_modbus("TXT", 1) == (36864, 1)

    def test_td1(self):
        assert plc_to_modbus("TD", 1) == (45056, 1)

    def test_ctd1(self):
        assert plc_to_modbus("CTD", 1) == (49152, 2)

    def test_ctd2(self):
        assert plc_to_modbus("CTD", 2) == (49154, 2)

    def test_sd1(self):
        assert plc_to_modbus("SD", 1) == (61440, 1)

    # --- XD/YD ---

    def test_xd0(self):
        assert plc_to_modbus("XD", 0) == (57344, 1)

    def test_xd1(self):
        # MDB index 2 = XD1 display
        assert plc_to_modbus("XD", 2) == (57346, 1)

    def test_xd8(self):
        # MDB index 16 = XD8 display
        assert plc_to_modbus("XD", 16) == (57360, 1)

    def test_yd0(self):
        assert plc_to_modbus("YD", 0) == (57856, 1)

    def test_yd1(self):
        # MDB index 2 = YD1 display
        assert plc_to_modbus("YD", 2) == (57858, 1)

    # --- Errors ---

    def test_invalid_bank(self):
        with pytest.raises(ValueError, match="Unknown bank"):
            plc_to_modbus("ZZ", 1)

    def test_invalid_index_ds0(self):
        with pytest.raises(ValueError, match="Invalid address"):
            plc_to_modbus("DS", 0)

    def test_invalid_index_x017(self):
        with pytest.raises(ValueError, match="Invalid address"):
            plc_to_modbus("X", 17)

    def test_invalid_index_ds4501(self):
        with pytest.raises(ValueError, match="Invalid address"):
            plc_to_modbus("DS", 4501)


# ==============================================================================
# Reverse mapping: modbus_to_plc
# ==============================================================================


class TestModbusToPlc:
    """Tests for modbus_to_plc reverse mapping."""

    # --- Sparse coils (from CLICKSERVER_SPEC test scenarios) ---

    def test_coil_0_x001(self):
        assert modbus_to_plc(0, is_coil=True) == ("X", 1)

    def test_coil_15_x016(self):
        assert modbus_to_plc(15, is_coil=True) == ("X", 16)

    def test_coil_16_x021(self):
        assert modbus_to_plc(16, is_coil=True) == ("X", 21)

    def test_coil_31_x036(self):
        assert modbus_to_plc(31, is_coil=True) == ("X", 36)

    def test_coil_32_x101(self):
        assert modbus_to_plc(32, is_coil=True) == ("X", 101)

    def test_coil_47_x116(self):
        assert modbus_to_plc(47, is_coil=True) == ("X", 116)

    def test_coil_64_x201(self):
        assert modbus_to_plc(64, is_coil=True) == ("X", 201)

    def test_coil_8192_y001(self):
        assert modbus_to_plc(8192, is_coil=True) == ("Y", 1)

    def test_coil_8208_y021(self):
        assert modbus_to_plc(8208, is_coil=True) == ("Y", 21)

    def test_coil_8224_y101(self):
        assert modbus_to_plc(8224, is_coil=True) == ("Y", 101)

    # --- Standard coils ---

    def test_coil_16384_c1(self):
        assert modbus_to_plc(16384, is_coil=True) == ("C", 1)

    def test_coil_18383_c2000(self):
        assert modbus_to_plc(18383, is_coil=True) == ("C", 2000)

    def test_coil_45057_t1(self):
        assert modbus_to_plc(45056, is_coil=True) == ("T", 1)

    def test_coil_49152_ct1(self):
        assert modbus_to_plc(49152, is_coil=True) == ("CT", 1)

    def test_coil_61440_sc1(self):
        assert modbus_to_plc(61440, is_coil=True) == ("SC", 1)

    # --- Sparse gaps ---

    def test_coil_48_gap(self):
        """Coil 48 is X slot 1 offset 48: hundred=1, unit=17 -> gap."""
        assert modbus_to_plc(48, is_coil=True) is None

    def test_coil_8240_gap(self):
        """Coil 8240 = Y base + 48: hundred=1, unit=17 -> gap."""
        assert modbus_to_plc(8240, is_coil=True) is None

    # --- Unmapped coils ---

    def test_coil_10000_unmapped(self):
        assert modbus_to_plc(10000, is_coil=True) is None

    # --- Standard registers ---

    def test_reg_0_ds1(self):
        assert modbus_to_plc(0, is_coil=False) == ("DS", 1)

    def test_reg_4499_ds4500(self):
        assert modbus_to_plc(4499, is_coil=False) == ("DS", 4500)

    def test_reg_16384_dd1(self):
        assert modbus_to_plc(16384, is_coil=False) == ("DD", 1)

    def test_reg_16386_dd2(self):
        assert modbus_to_plc(16386, is_coil=False) == ("DD", 2)

    def test_reg_16385_dd1_mid(self):
        """Register 16385 is the second register of DD1 — mid-value."""
        assert modbus_to_plc(16385, is_coil=False) is None

    def test_reg_24576_dh1(self):
        assert modbus_to_plc(24576, is_coil=False) == ("DH", 1)

    def test_reg_28672_df1(self):
        assert modbus_to_plc(28672, is_coil=False) == ("DF", 1)

    def test_reg_28674_df2(self):
        assert modbus_to_plc(28674, is_coil=False) == ("DF", 2)

    def test_reg_36864_txt1(self):
        assert modbus_to_plc(36864, is_coil=False) == ("TXT", 1)

    def test_reg_45056_td1(self):
        assert modbus_to_plc(45056, is_coil=False) == ("TD", 1)

    def test_reg_49152_ctd1(self):
        assert modbus_to_plc(49152, is_coil=False) == ("CTD", 1)

    def test_reg_49154_ctd2(self):
        assert modbus_to_plc(49154, is_coil=False) == ("CTD", 2)

    def test_reg_61440_sd1(self):
        assert modbus_to_plc(61440, is_coil=False) == ("SD", 1)

    # --- XD/YD registers ---

    def test_reg_57344_xd0(self):
        assert modbus_to_plc(57344, is_coil=False) == ("XD", 0)

    def test_reg_57346_xd1(self):
        # MDB index 2 = XD1 display
        assert modbus_to_plc(57346, is_coil=False) == ("XD", 2)

    def test_reg_57345_xd0u(self):
        """Register 57345 is XD0u (MDB index 1) — now addressable."""
        assert modbus_to_plc(57345, is_coil=False) == ("XD", 1)

    def test_reg_57856_yd0(self):
        assert modbus_to_plc(57856, is_coil=False) == ("YD", 0)

    def test_reg_57858_yd1(self):
        # MDB index 2 = YD1 display
        assert modbus_to_plc(57858, is_coil=False) == ("YD", 2)

    # --- Unmapped registers ---

    def test_reg_5000_unmapped(self):
        assert modbus_to_plc(5000, is_coil=False) is None


# ==============================================================================
# Forward/Reverse round-trip
# ==============================================================================


class TestRoundTrip:
    """Verify that plc_to_modbus and modbus_to_plc are inverses."""

    @pytest.mark.parametrize(
        "bank,index",
        [
            ("X", 1),
            ("X", 16),
            ("X", 21),
            ("X", 36),
            ("X", 101),
            ("X", 116),
            ("X", 201),
            ("X", 816),
            ("Y", 1),
            ("Y", 16),
            ("Y", 101),
            ("Y", 816),
            ("C", 1),
            ("C", 1000),
            ("C", 2000),
            ("T", 1),
            ("T", 500),
            ("CT", 1),
            ("CT", 250),
            ("SC", 1),
            ("SC", 1000),
        ],
    )
    def test_coil_round_trip(self, bank: str, index: int):
        addr, _ = plc_to_modbus(bank, index)
        result = modbus_to_plc(addr, is_coil=True)
        assert result == (bank, index)

    @pytest.mark.parametrize(
        "bank,index",
        [
            ("DS", 1),
            ("DS", 4500),
            ("DD", 1),
            ("DD", 1000),
            ("DH", 1),
            ("DH", 500),
            ("DF", 1),
            ("DF", 500),
            ("TXT", 1),
            ("TXT", 1000),
            ("TD", 1),
            ("TD", 500),
            ("CTD", 1),
            ("CTD", 250),
            ("SD", 1),
            ("SD", 1000),
            ("XD", 0),
            ("XD", 2),
            ("XD", 16),
            ("YD", 0),
            ("YD", 2),
            ("YD", 16),
        ],
    )
    def test_register_round_trip(self, bank: str, index: int):
        addr, _ = plc_to_modbus(bank, index)
        result = modbus_to_plc(addr, is_coil=False)
        assert result == (bank, index)


# ==============================================================================
# Pack / Unpack
# ==============================================================================


class TestPackValue:
    """Tests for pack_value."""

    # --- INT (int16 signed) ---

    def test_int_zero(self):
        assert pack_value(0, DataType.INT) == [0]

    def test_int_positive(self):
        assert pack_value(1, DataType.INT) == [1]

    def test_int_negative(self):
        regs = pack_value(-1, DataType.INT)
        assert regs == [0xFFFF]

    def test_int_max(self):
        assert pack_value(32767, DataType.INT) == [32767]

    def test_int_min(self):
        regs = pack_value(-32768, DataType.INT)
        assert regs == [0x8000]

    # --- HEX (uint16) ---

    def test_hex_zero(self):
        assert pack_value(0, DataType.HEX) == [0]

    def test_hex_ffff(self):
        assert pack_value(0xFFFF, DataType.HEX) == [0xFFFF]

    def test_hex_abcd(self):
        assert pack_value(0xABCD, DataType.HEX) == [0xABCD]

    # --- INT2 (int32 signed) ---

    def test_int2_zero(self):
        assert pack_value(0, DataType.INT2) == [0, 0]

    def test_int2_positive(self):
        regs = pack_value(100000, DataType.INT2)
        raw = struct.pack("<i", 100000)
        lo, hi = struct.unpack("<HH", raw)
        assert regs == [lo, hi]

    def test_int2_negative(self):
        regs = pack_value(-100000, DataType.INT2)
        raw = struct.pack("<i", -100000)
        lo, hi = struct.unpack("<HH", raw)
        assert regs == [lo, hi]

    def test_int2_max(self):
        regs = pack_value(2147483647, DataType.INT2)
        assert len(regs) == 2

    def test_int2_min(self):
        regs = pack_value(-2147483648, DataType.INT2)
        assert len(regs) == 2

    # --- FLOAT ---

    def test_float_zero(self):
        assert pack_value(0.0, DataType.FLOAT) == [0, 0]

    def test_float_pi(self):
        regs = pack_value(3.14, DataType.FLOAT)
        assert len(regs) == 2

    def test_float_negative(self):
        regs = pack_value(-1.5, DataType.FLOAT)
        assert len(regs) == 2

    # --- TXT ---

    def test_txt_a(self):
        assert pack_value("A", DataType.TXT) == [65]

    def test_txt_z(self):
        assert pack_value("z", DataType.TXT) == [122]

    def test_txt_space(self):
        assert pack_value(" ", DataType.TXT) == [32]

    # --- BIT raises ---

    def test_bit_raises(self):
        with pytest.raises(ValueError, match="BIT"):
            pack_value(True, DataType.BIT)


class TestUnpackValue:
    """Tests for unpack_value."""

    def test_int_zero(self):
        assert unpack_value([0], DataType.INT) == 0

    def test_int_negative(self):
        assert unpack_value([0xFFFF], DataType.INT) == -1

    def test_hex_ffff(self):
        assert unpack_value([0xFFFF], DataType.HEX) == 0xFFFF

    def test_txt_a(self):
        assert unpack_value([65], DataType.TXT) == "A"

    def test_int2_zero(self):
        assert unpack_value([0, 0], DataType.INT2) == 0

    def test_float_zero(self):
        assert unpack_value([0, 0], DataType.FLOAT) == 0.0


class TestPackUnpackRoundTrip:
    """Verify pack/unpack are inverses."""

    @pytest.mark.parametrize("value", [0, 1, -1, 32767, -32768])
    def test_int_round_trip(self, value: int):
        regs = pack_value(value, DataType.INT)
        assert unpack_value(regs, DataType.INT) == value

    @pytest.mark.parametrize("value", [0, 0xFFFF, 0xABCD, 1])
    def test_hex_round_trip(self, value: int):
        regs = pack_value(value, DataType.HEX)
        assert unpack_value(regs, DataType.HEX) == value

    @pytest.mark.parametrize("value", [0, 100000, -100000, 2147483647, -2147483648])
    def test_int2_round_trip(self, value: int):
        regs = pack_value(value, DataType.INT2)
        assert unpack_value(regs, DataType.INT2) == value

    @pytest.mark.parametrize("value", [0.0, 3.14, -1.5, 1e30, -1e30])
    def test_float_round_trip(self, value: float):
        regs = pack_value(value, DataType.FLOAT)
        result = unpack_value(regs, DataType.FLOAT)
        assert isinstance(result, float)
        if value == 0.0:
            assert result == 0.0
        else:
            assert math.isclose(result, value, rel_tol=1e-6)

    @pytest.mark.parametrize("value", ["A", "z", " ", "0", "~"])
    def test_txt_round_trip(self, value: str):
        regs = pack_value(value, DataType.TXT)
        assert unpack_value(regs, DataType.TXT) == value


# ==============================================================================
# Edge cases
# ==============================================================================


class TestEdgeCases:
    """Edge case tests for sparse coils and XD/YD boundaries."""

    def test_sparse_slot_boundaries(self):
        """Each sparse slot boundary maps correctly."""
        # First address of each slot
        for lo, _hi in [
            (1, 16),
            (21, 36),
            (101, 116),
            (201, 216),
            (301, 316),
            (401, 416),
            (501, 516),
            (601, 616),
            (701, 716),
            (801, 816),
        ]:
            addr, count = plc_to_modbus("X", lo)
            assert count == 1
            result = modbus_to_plc(addr, is_coil=True)
            assert result == ("X", lo)

    def test_sparse_slot_last_addresses(self):
        """Last address of each slot maps correctly."""
        for _lo, hi in [
            (1, 16),
            (21, 36),
            (101, 116),
            (201, 216),
            (301, 316),
            (401, 416),
            (501, 516),
            (601, 616),
            (701, 716),
            (801, 816),
        ]:
            addr, count = plc_to_modbus("X", hi)
            assert count == 1
            result = modbus_to_plc(addr, is_coil=True)
            assert result == ("X", hi)

    def test_xd_yd_all_mdb_indices_addressable(self):
        """All MDB indices 0-16 within XD/YD range are addressable."""
        # XD base=57344
        for mdb in range(17):
            result = modbus_to_plc(57344 + mdb, is_coil=False)
            assert result == ("XD", mdb)

        # YD base=57856
        for mdb in range(17):
            result = modbus_to_plc(57856 + mdb, is_coil=False)
            assert result == ("YD", mdb)

    def test_xd_all_valid_mdb_addresses(self):
        """XD MDB 0 through 16 all map correctly (contiguous)."""
        for mdb in range(17):
            addr, count = plc_to_modbus("XD", mdb)
            assert count == 1
            assert addr == 57344 + mdb
            result = modbus_to_plc(addr, is_coil=False)
            assert result == ("XD", mdb)

    def test_yd_all_valid_mdb_addresses(self):
        """YD MDB 0 through 16 all map correctly (contiguous)."""
        for mdb in range(17):
            addr, count = plc_to_modbus("YD", mdb)
            assert count == 1
            assert addr == 57856 + mdb
            result = modbus_to_plc(addr, is_coil=False)
            assert result == ("YD", mdb)

    def test_df_mid_register_returns_none(self):
        """Odd offsets in DF (width-2) return None."""
        # DF1 is at 28672-28673, DF2 at 28674-28675
        assert modbus_to_plc(28673, is_coil=False) is None

    def test_dd_mid_register_returns_none(self):
        """Odd offsets in DD (width-2) return None."""
        assert modbus_to_plc(16385, is_coil=False) is None

    def test_ctd_mid_register_returns_none(self):
        """Odd offsets in CTD (width-2) return None."""
        assert modbus_to_plc(49153, is_coil=False) is None
