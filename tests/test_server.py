"""Tests for pyclickplc.server — Modbus TCP server for CLICK PLCs."""

from __future__ import annotations

import pytest

from pyclickplc.banks import DataType
from pyclickplc.modbus import modbus_to_plc_register, pack_value, plc_to_modbus
from pyclickplc.server import (
    ClickServer,
    MemoryDataProvider,
    _ClickDeviceContext,
)


def _as_float(value: object) -> float:
    assert isinstance(value, (int, float))
    return float(value)


# ==============================================================================
# MemoryDataProvider
# ==============================================================================


class TestMemoryDataProvider:
    """Tests for MemoryDataProvider defaults, set/get, and normalization."""

    def test_default_bool(self):
        p = MemoryDataProvider()
        assert p.get("C1") is False

    def test_default_int16(self):
        p = MemoryDataProvider()
        assert p.get("DS1") == 0

    def test_default_int32(self):
        p = MemoryDataProvider()
        assert p.get("DD1") == 0

    def test_default_float(self):
        p = MemoryDataProvider()
        assert p.get("DF1") == 0.0

    def test_default_hex(self):
        p = MemoryDataProvider()
        assert p.get("DH1") == 0

    def test_default_txt(self):
        p = MemoryDataProvider()
        assert p.get("TXT1") == "\x00"

    def test_set_get_round_trip(self):
        p = MemoryDataProvider()
        p.set("DF1", 3.14)
        assert p.get("DF1") == 3.14

    def test_write_read_round_trip(self):
        p = MemoryDataProvider()
        p.write("DS100", 42)
        assert p.read("DS100") == 42

    def test_set_then_read(self):
        p = MemoryDataProvider()
        p.set("C1", True)
        assert p.read("C1") is True

    def test_bulk_set(self):
        p = MemoryDataProvider()
        p.bulk_set({"DF1": 1.0, "DF2": 2.0, "DS1": 42})
        assert p.get("DF1") == 1.0
        assert p.get("DF2") == 2.0
        assert p.get("DS1") == 42

    def test_address_normalization(self):
        """Case-insensitive address normalization."""
        p = MemoryDataProvider()
        p.set("df1", 1.0)
        assert p.get("DF1") == 1.0

    def test_address_normalization_x(self):
        p = MemoryDataProvider()
        p.set("x1", True)
        assert p.get("X001") is True

    def test_overwrite(self):
        p = MemoryDataProvider()
        p.set("DS1", 10)
        p.set("DS1", 20)
        assert p.get("DS1") == 20

    def test_sc_default(self):
        p = MemoryDataProvider()
        assert p.get("SC1") is False

    def test_sd_default(self):
        p = MemoryDataProvider()
        assert p.get("SD1") == 0

    def test_td_default(self):
        p = MemoryDataProvider()
        assert p.get("TD1") == 0

    def test_ctd_default(self):
        p = MemoryDataProvider()
        assert p.get("CTD1") == 0

    def test_xd_default(self):
        p = MemoryDataProvider()
        assert p.get("XD0") == 0

    def test_yd_default(self):
        p = MemoryDataProvider()
        assert p.get("YD0") == 0

    def test_set_rejects_out_of_range_int(self):
        p = MemoryDataProvider()
        with pytest.raises(ValueError, match="DS1 value must be int"):
            p.set("DS1", 999999999999)

    def test_set_rejects_non_numeric_float(self):
        p = MemoryDataProvider()
        with pytest.raises(ValueError, match="DF1 value must be a finite float32"):
            p.set("DF1", "abc")

    def test_set_rejects_nan_float(self):
        p = MemoryDataProvider()
        with pytest.raises(ValueError, match="DF1 value must be a finite float32"):
            p.set("DF1", float("nan"))

    def test_set_rejects_inf_float(self):
        p = MemoryDataProvider()
        with pytest.raises(ValueError, match="DF1 value must be a finite float32"):
            p.set("DF1", float("inf"))

    def test_set_rejects_invalid_txt(self):
        p = MemoryDataProvider()
        with pytest.raises(
            ValueError, match="TXT1 TXT value must be blank or a single ASCII character"
        ):
            p.set("TXT1", "AB")

    def test_set_rejects_word_underflow(self):
        p = MemoryDataProvider()
        with pytest.raises(ValueError, match="DH1 must be WORD"):
            p.set("DH1", -1)

    def test_set_rejects_bool_for_numeric(self):
        p = MemoryDataProvider()
        with pytest.raises(ValueError, match="DS1 value must be int"):
            p.set("DS1", True)


# ==============================================================================
# modbus_to_plc_register
# ==============================================================================


class TestModbusToPlcRegister:
    """Tests for extended reverse register mapping."""

    def test_ds1(self):
        assert modbus_to_plc_register(0) == ("DS", 1, 0)

    def test_ds4500(self):
        assert modbus_to_plc_register(4499) == ("DS", 4500, 0)

    def test_dd1_first_reg(self):
        assert modbus_to_plc_register(16384) == ("DD", 1, 0)

    def test_dd1_second_reg(self):
        """Unlike modbus_to_plc, this returns the mid-value register."""
        assert modbus_to_plc_register(16385) == ("DD", 1, 1)

    def test_dd2(self):
        assert modbus_to_plc_register(16386) == ("DD", 2, 0)

    def test_df1_first_reg(self):
        assert modbus_to_plc_register(28672) == ("DF", 1, 0)

    def test_df1_second_reg(self):
        assert modbus_to_plc_register(28673) == ("DF", 1, 1)

    def test_df2(self):
        assert modbus_to_plc_register(28674) == ("DF", 2, 0)

    def test_dh1(self):
        assert modbus_to_plc_register(24576) == ("DH", 1, 0)

    def test_txt1(self):
        assert modbus_to_plc_register(36864) == ("TXT", 1, 0)

    def test_td1(self):
        assert modbus_to_plc_register(45056) == ("TD", 1, 0)

    def test_ctd1_first(self):
        assert modbus_to_plc_register(49152) == ("CTD", 1, 0)

    def test_ctd1_second(self):
        assert modbus_to_plc_register(49153) == ("CTD", 1, 1)

    def test_sd1(self):
        assert modbus_to_plc_register(61440) == ("SD", 1, 0)

    def test_xd0(self):
        assert modbus_to_plc_register(57344) == ("XD", 0, 0)

    def test_xd_mdb1(self):
        """XD MDB index 1 (XD0u) is now addressable."""
        assert modbus_to_plc_register(57345) == ("XD", 1, 0)

    def test_yd0(self):
        assert modbus_to_plc_register(57856) == ("YD", 0, 0)

    def test_unmapped(self):
        assert modbus_to_plc_register(5000) is None


# ==============================================================================
# _ClickDeviceContext — coil reads
# ==============================================================================


class TestContextCoilReads:
    """Test _ClickDeviceContext.getValues for coils."""

    def test_read_single_coil_c1(self):
        p = MemoryDataProvider()
        p.set("C1", True)
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(1, 16384, 1)
        assert result == [True]

    def test_read_coil_range_c1_c5(self):
        p = MemoryDataProvider()
        for i in range(1, 6):
            p.set(f"C{i}", i % 2 == 1)
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(1, 16384, 5)
        assert result == [True, False, True, False, True]

    def test_read_sparse_x001(self):
        p = MemoryDataProvider()
        p.set("X001", True)
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(2, 0, 1)
        assert result == [True]

    def test_read_unmapped_coil(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(1, 10000, 1)
        assert result == [False]

    def test_read_sparse_gap(self):
        """Coil 48 is a sparse gap -> False."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(2, 48, 1)
        assert result == [False]


# ==============================================================================
# _ClickDeviceContext — register reads
# ==============================================================================


class TestContextRegisterReads:
    """Test _ClickDeviceContext.getValues for registers."""

    def test_read_ds1(self):
        p = MemoryDataProvider()
        p.set("DS1", 42)
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(3, 0, 1)
        # DS1=42 -> pack_value(42, INT) = [42]
        assert result == [42]

    def test_read_df1(self):
        p = MemoryDataProvider()
        p.set("DF1", 3.14)
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(3, 28672, 2)
        # Verify round-trip
        import struct

        raw = struct.pack("<f", 3.14)
        lo, hi = struct.unpack("<HH", raw)
        assert result == [lo, hi]

    def test_read_dd1(self):
        p = MemoryDataProvider()
        p.set("DD1", 100000)
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(3, 16384, 2)
        expected = pack_value(100000, DataType.INT2)
        assert result == expected

    def test_read_dh1_unsigned(self):
        p = MemoryDataProvider()
        p.set("DH1", 0xABCD)
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(3, 24576, 1)
        assert result == [0xABCD]

    def test_read_unmapped_register(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(3, 5000, 1)
        assert result == [0]

    def test_read_ds_negative(self):
        p = MemoryDataProvider()
        p.set("DS1", -1)
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(3, 0, 1)
        assert result == [0xFFFF]

    def test_read_txt_register(self):
        """TXT packs 2 chars per register."""
        p = MemoryDataProvider()
        p.set("TXT1", "A")  # low byte
        p.set("TXT2", "B")  # high byte
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(3, 36864, 1)
        assert result == [ord("A") | (ord("B") << 8)]


# ==============================================================================
# _ClickDeviceContext — coil writes
# ==============================================================================


class TestContextCoilWrites:
    """Test _ClickDeviceContext.setValues for coils."""

    def test_write_single_coil_c1(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(5, 16384, [True])
        assert result is None
        assert p.get("C1") is True

    def test_write_multiple_coils(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(15, 16384, [True, False, True])
        assert result is None
        assert p.get("C1") is True
        assert p.get("C2") is False
        assert p.get("C3") is True

    def test_write_unmapped_coil_fc5(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(5, 10000, [True])
        from pymodbus.constants import ExcCodes

        assert result == ExcCodes.ILLEGAL_ADDRESS

    def test_write_non_writable_sc(self):
        """SC1 is not Modbus-writable."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(5, 61440, [True])
        from pymodbus.constants import ExcCodes

        assert result == ExcCodes.ILLEGAL_ADDRESS

    def test_write_writable_sc53(self):
        """SC53 is writable."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("SC", 53)
        result = ctx.setValues(5, addr, [True])
        assert result is None
        assert p.get("SC53") is True

    def test_write_x_not_writable(self):
        """X inputs are read-only."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(5, 0, [True])
        from pymodbus.constants import ExcCodes

        assert result == ExcCodes.ILLEGAL_ADDRESS


# ==============================================================================
# _ClickDeviceContext — register writes
# ==============================================================================


class TestContextRegisterWrites:
    """Test _ClickDeviceContext.setValues for registers."""

    def test_fc06_write_ds1(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(6, 0, [42])
        assert result is None
        assert p.get("DS1") == 42

    def test_fc16_write_ds_multiple(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(16, 0, [10, 20, 30])
        assert result is None
        assert p.get("DS1") == 10
        assert p.get("DS2") == 20
        assert p.get("DS3") == 30

    def test_fc16_write_df1_float(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        regs = pack_value(3.14, DataType.FLOAT)
        result = ctx.setValues(16, 28672, regs)
        assert result is None
        import math

        assert math.isclose(_as_float(p.get("DF1")), 3.14, rel_tol=1e-6)

    def test_fc06_write_df1_read_modify_write(self):
        """FC 06 on width-2: writes one register, read-modify-write."""
        p = MemoryDataProvider()
        p.set("DF1", 0.0)
        ctx = _ClickDeviceContext(p)
        # Write low register only
        regs = pack_value(3.14, DataType.FLOAT)
        result = ctx.setValues(6, 28672, [regs[0]])
        assert result is None
        # Now write high register
        result = ctx.setValues(6, 28673, [regs[1]])
        assert result is None
        import math

        assert math.isclose(_as_float(p.get("DF1")), 3.14, rel_tol=1e-6)

    def test_fc06_write_unmapped(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(6, 5000, [42])
        from pymodbus.constants import ExcCodes

        assert result == ExcCodes.ILLEGAL_ADDRESS

    def test_fc06_write_non_writable_sd(self):
        """SD1 is not writable."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(6, 61440, [42])
        from pymodbus.constants import ExcCodes

        assert result == ExcCodes.ILLEGAL_ADDRESS

    def test_fc06_write_writable_sd29(self):
        """SD29 is writable."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("SD", 29)
        result = ctx.setValues(6, addr, [100])
        assert result is None
        assert p.get("SD29") == 100

    def test_fc16_write_txt(self):
        """TXT register write stores 2 chars."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        reg_val = ord("H") | (ord("i") << 8)
        result = ctx.setValues(16, 36864, [reg_val])
        assert result is None
        assert p.get("TXT1") == "H"
        assert p.get("TXT2") == "i"


# ==============================================================================
# ClickServer construction
# ==============================================================================


class TestClickServerConstruction:
    def test_default_host_port(self):
        p = MemoryDataProvider()
        s = ClickServer(p)
        assert s.host == "localhost"
        assert s.port == 502
        assert s.provider is p

    def test_custom_host_port(self):
        p = MemoryDataProvider()
        s = ClickServer(p, host="0.0.0.0", port=5020)
        assert s.host == "0.0.0.0"
        assert s.port == 5020
