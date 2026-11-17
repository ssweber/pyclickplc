"""Tests for pyclickplc.server — Modbus TCP server for CLICK PLCs."""

from __future__ import annotations

import ast
import math
import struct
from pathlib import Path
from typing import cast

import pytest

import pyclickplc
from pyclickplc.banks import DataType
from pyclickplc.modbus import modbus_to_plc_register, pack_value, plc_to_modbus
from pyclickplc.server import (
    _CLICK_FUNCTION_CODES,
    _HANDLERS,
    ClickServer,
    MemoryDataProvider,
    _answer,
    _ClickDeviceContext,
)


def _as_float(value: object) -> float:
    assert isinstance(value, (int, float))
    return float(value)


# ==============================================================================
# MemoryDataProvider
# ==============================================================================


class _FailingProvider(MemoryDataProvider):
    def read(self, address: str):
        raise RuntimeError("provider down")


class TestGetValuesFailure:
    @pytest.mark.parametrize("func_code", [1, 2, 3, 4])
    def test_provider_failure_is_device_failure(self, func_code):

        ctx = _ClickDeviceContext(_FailingProvider())
        address = 0 if func_code in (1, 2) else 28672
        assert ctx.getValues(func_code, address, 1) == 4


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

    def test_address_normalization_y(self):
        p = MemoryDataProvider()
        p.set("y1", True)
        assert p.get("Y001") is True

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
        with pytest.raises(ValueError, match="DF1 value must be a float32"):
            p.set("DF1", "abc")

    def test_set_accepts_non_finite_float(self):
        p = MemoryDataProvider()
        p.set("DF1", float("inf"))
        p.set("DF2", float("-inf"))
        p.set("DF3", float("nan"))
        assert p.get("DF1") == float("inf")
        assert p.get("DF2") == float("-inf")
        assert math.isnan(cast(float, p.get("DF3")))

    def test_set_rejects_overflow_float(self):
        p = MemoryDataProvider()
        with pytest.raises(ValueError, match="DF1 value must fit in a float32"):
            p.set("DF1", 1e100)

    def test_set_rejects_invalid_txt(self):
        p = MemoryDataProvider()
        with pytest.raises(
            ValueError, match="TXT1 TXT value must be blank or a single character with code 0..255"
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

    def test_txt101(self):
        assert modbus_to_plc_register(36914) == ("TXT", 101, 0)

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
        assert result == 2

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
        assert result == 2

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

    def test_read_txt_register_high_index(self):
        p = MemoryDataProvider()
        p.set("TXT101", "Z")
        p.set("TXT102", "Y")
        ctx = _ClickDeviceContext(p)
        result = ctx.getValues(3, 36914, 1)
        assert result == [ord("Z") | (ord("Y") << 8)]


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

        assert result == 2

    def test_write_non_writable_sc(self):
        """SC1 is not Modbus-writable."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(5, 61440, [True])

        assert result == 2

    def test_write_writable_sc53(self):
        """SC53 is writable."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("SC", 53)
        result = ctx.setValues(5, addr, [True])
        assert result is None
        assert p.get("SC53") is True

    def test_write_x_is_stored(self):
        """A write to an X input is stored (b4 R3 and R6, 2026-11-17)."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        assert ctx.setValues(5, 0, [True]) is None
        assert p.get("X001") is True
        assert ctx.setValues(15, 0, [False, True]) is None
        assert p._data == {"X001": False, "X002": True}


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

        assert result == 2

    def test_fc06_write_non_writable_sd(self):
        """SD1 is not writable."""
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        result = ctx.setValues(6, 61440, [42])

        assert result == 2

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

    def test_fc06_write_txt_byte_above_127_in_either_half(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        assert ctx.setValues(6, 36864, [0xC841]) is None
        assert p.get("TXT1") == "A"
        assert p.get("TXT2") == chr(0xC8)
        assert ctx.setValues(6, 36864, [0x41C8]) is None
        assert p.get("TXT1") == chr(0xC8)
        assert p.get("TXT2") == "A"

    def test_fc16_write_txt_high_index(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        reg_val = ord("Z") | (ord("Y") << 8)
        result = ctx.setValues(16, 36914, [reg_val])
        assert result is None
        assert p.get("TXT101") == "Z"
        assert p.get("TXT102") == "Y"


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


# ==============================================================================
# Answers
# ==============================================================================

# The function codes a CLICK answers from its memory. Every other code gets exception 01.
CLICK_FUNCTION_CODES = {1, 2, 3, 4, 5, 6, 15, 16}
C1_COIL = plc_to_modbus("C", 1)[0]


class _BrokenContext(_ClickDeviceContext):
    def getValues(self, func_code, address, count=1):
        raise RuntimeError("context bug")

    def setValues(self, func_code, address, values):
        raise RuntimeError("context bug")


# A well-formed request for each function code a CLICK answers from its memory.
WELL_FORMED = {
    1: struct.pack(">BHH", 1, 0, 1),
    2: struct.pack(">BHH", 2, 0, 1),
    3: struct.pack(">BHH", 3, 0, 1),
    4: struct.pack(">BHH", 4, 0, 1),
    5: struct.pack(">BHH", 5, C1_COIL, 0xFF00),
    6: struct.pack(">BHH", 6, 0, 1),
    15: struct.pack(">BHHBB", 15, C1_COIL, 1, 1, 1),
    16: struct.pack(">BHHBH", 16, 0, 1, 2, 5),
}


class TestAnswer:
    def test_the_context_and_the_answers_serve_the_same_function_codes(self):
        assert set(_HANDLERS) == set(_CLICK_FUNCTION_CODES) == CLICK_FUNCTION_CODES

    def test_every_function_code_gets_an_answer_and_nothing_raises(self):
        context = _ClickDeviceContext(MemoryDataProvider())
        for code in range(256):
            for length in range(12):
                for fill in (0x00, 0x01, 0xFF):
                    response = _answer(context, bytes([code, *[fill] * length]))
                    assert response[0] in (code, code | 0x80)

    @pytest.mark.parametrize(
        "code", sorted(set(range(256)) - CLICK_FUNCTION_CODES), ids=lambda code: f"fc{code}"
    )
    def test_any_other_function_code_gets_exception_01_and_stores_nothing(self, code):
        provider = MemoryDataProvider()
        for data in (b"", struct.pack(">HHH", 0, 1, 5), struct.pack(">HHHHB", 0, 1, 0, 1, 2)):
            assert _answer(_ClickDeviceContext(provider), bytes([code]) + data) == bytes(
                [code | 0x80, 1]
            )
        assert provider._data == {}

    @pytest.mark.parametrize("code", sorted(CLICK_FUNCTION_CODES))
    def test_an_error_nothing_else_caught_gets_exception_04(self, code):
        response = _answer(_BrokenContext(MemoryDataProvider()), WELL_FORMED[code])
        assert response == bytes([code | 0x80, 4])

    @pytest.mark.parametrize("code", sorted(CLICK_FUNCTION_CODES))
    def test_well_formed_request_is_answered(self, code):
        response = _answer(_ClickDeviceContext(MemoryDataProvider()), WELL_FORMED[code])
        assert response[0] == code

    def test_reads_answer_byte_count_then_data(self):
        provider = MemoryDataProvider()
        provider.bulk_set({"C1": True, "C3": True, "C9": True, "DS1": -2, "DS2": 7})
        context = _ClickDeviceContext(provider)
        assert _answer(context, struct.pack(">BHH", 1, C1_COIL, 9)) == bytes([1, 2, 0x05, 0x01])
        ds1 = plc_to_modbus("DS", 1)[0]
        assert _answer(context, struct.pack(">BHH", 3, ds1, 2)) == bytes(
            [3, 4, 0xFF, 0xFE, 0x00, 0x07]
        )


class TestWriteCoilValue:
    @pytest.mark.parametrize("value", [0x0001, 0x00FF, 0x1234, 0xFF01, 0xFFFF])
    def test_value_other_than_0000_or_ff00_answers_03_and_stores_nothing(self, value):
        provider = MemoryDataProvider()
        response = _answer(_ClickDeviceContext(provider), struct.pack(">BHH", 5, C1_COIL, value))
        assert response == bytes([0x85, 3])
        assert provider.get("C1") is False

    @pytest.mark.parametrize(("value", "stored"), [(0xFF00, True), (0x0000, False)])
    def test_0000_and_ff00_are_stored(self, value, stored):
        provider = MemoryDataProvider()
        provider.set("C1", not stored)
        pdu = struct.pack(">BHH", 5, C1_COIL, value)
        assert _answer(_ClickDeviceContext(provider), pdu) == pdu
        assert provider.get("C1") is stored


# ==============================================================================
# ClickServer runtime controls (the rest, over sockets, in test_integration.py)
# ==============================================================================


class TestClickServerRuntimeControls:
    def test_is_running_false_before_start(self):
        server = ClickServer(MemoryDataProvider())
        assert server.is_running() is False

    def test_list_clients_empty_when_not_started(self):
        server = ClickServer(MemoryDataProvider())
        assert server.list_clients() == []
        assert server.disconnect_client("1") is False
        assert server.disconnect_all_clients() == 0

    def test_bound_port_is_none_when_not_started(self):
        assert ClickServer(MemoryDataProvider(), port=0).bound_port is None


@pytest.mark.parametrize("module", ["server.py", "server_tui.py"])
def test_server_does_not_import_pymodbus(module):
    tree = ast.parse((Path(pyclickplc.__file__).parent / module).read_text(encoding="utf-8"))
    imported = [
        name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
    ]
    assert [name for name in imported if name.split(".")[0] == "pymodbus"] == []


class TestAtomicWrites:
    def test_fc16_past_the_last_register_stores_nothing(self):

        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("DS", 4500)
        assert ctx.setValues(16, addr, [7, 8]) == 2
        assert p.get("DS4500") == 0

    def test_fc15_into_a_read_only_coil_stores_nothing(self):

        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("SC", 53)
        assert ctx.setValues(15, addr, [True, True]) == 2
        assert p.get("SC53") is False

    def test_provider_failure_midway_restores_earlier_stores(self):

        class Flaky(MemoryDataProvider):
            def write(self, address: str, value):
                if address == "DS2":
                    raise RuntimeError("down")
                super().write(address, value)

        p = Flaky()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("DS", 1)
        assert ctx.setValues(16, addr, [5, 6]) == 4
        assert p.get("DS1") == 0


class TestRequestLimits:
    @pytest.mark.parametrize(
        ("func_code", "count"), [(1, 0), (1, 2001), (2, 2001), (3, 0), (3, 126), (4, 200)]
    )
    def test_read_count_out_of_range_is_illegal_value(self, func_code, count):

        ctx = _ClickDeviceContext(MemoryDataProvider())
        assert ctx.getValues(func_code, 0, count) == 3

    def test_read_counts_at_the_limits_are_served(self):
        ctx = _ClickDeviceContext(MemoryDataProvider())
        assert len(cast(list, ctx.getValues(3, 0, 125))) == 125
        assert len(cast(list, ctx.getValues(1, 16384, 2000))) == 2000

    def test_fc15_over_1968_coils_is_illegal_value(self):

        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        assert ctx.setValues(15, 0, [True] * 1969) == 3
        assert p.get("C1") is False

    def test_fc16_over_123_registers_is_illegal_value(self):

        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("DS", 1)
        assert ctx.setValues(16, addr, [1] * 124) == 3
        assert p.get("DS1") == 0


class TestAnswersAsAClick:
    """A CLICK answered raw requests this way on 2026-11-10 (pyrung's modbus_raw part)."""

    @pytest.mark.parametrize(
        ("func_code", "address", "count"),
        [
            (3, 4500, 1),  # the register past DS4500
            (3, 4499, 2),  # DS4500 and the register past it
            (1, 18384, 1),  # C2001
            (3, 18384, 2),  # DD1001
        ],
    )
    def test_read_past_a_bank_is_illegal_address(self, func_code, address, count):

        ctx = _ClickDeviceContext(MemoryDataProvider())
        assert ctx.getValues(func_code, address, count) == 2

    def test_read_in_the_y_gap_is_off(self):
        ctx = _ClickDeviceContext(MemoryDataProvider())
        # Between Y116 and Y201.
        assert ctx.getValues(1, 8192 + 48, 1) == [False]

    def test_fc15_across_the_c_end_stores_nothing(self):

        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("C", 1999)
        assert ctx.setValues(15, addr, [True] * 4) == 2
        assert p.get("C1999") is False
        assert p.get("C2000") is False

    def test_fc15_over_the_y_gap_stores_the_gap_coils(self):
        # b4 R1 (2026-11-17) stored and read back the gap coils.
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("Y", 116)
        assert ctx.setValues(15, addr, [True] * 18) is None
        assert p.get("Y116") is True
        assert p.get("Y201") is True
        assert ctx.getValues(1, addr, 18) == [True] * 18

    def test_unnamed_yd_register_keeps_its_own_word(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        yd_base, _ = plc_to_modbus("YD", 0)
        assert ctx.setValues(6, yd_base + 3, [0x8000]) is None
        assert p.get("YD1") == 0
        assert ctx.getValues(3, yd_base + 2, 2) == [0, 0x8000]

    def test_unnamed_yd_registers_in_a_range_write(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        yd_base, _ = plc_to_modbus("YD", 0)
        assert ctx.setValues(16, yd_base + 2, [1, 2, 3]) is None
        assert p.get("YD1") == 1
        assert p.get("YD2") == 3
        assert ctx.getValues(3, yd_base + 2, 3) == [1, 2, 3]

    def test_unnamed_xd_register_reads_0_and_refuses_a_write(self):

        p = MemoryDataProvider()
        p.set("XD1", 0x1234)
        ctx = _ClickDeviceContext(p)
        xd_base, _ = plc_to_modbus("XD", 0)
        assert ctx.getValues(4, xd_base + 2, 2) == [0x1234, 0]
        assert ctx.setValues(6, xd_base + 3, [5]) == 2

    def test_provider_failure_midway_keeps_the_spare_words(self):

        class Flaky(MemoryDataProvider):
            def write(self, address: str, value):
                if address == "YD2":
                    raise RuntimeError("down")
                super().write(address, value)

        p = Flaky()
        ctx = _ClickDeviceContext(p)
        yd_base, _ = plc_to_modbus("YD", 0)
        assert ctx.setValues(16, yd_base + 2, [1, 2, 3]) == 4
        assert p.get("YD1") == 0
        assert ctx.memory.words == {}

    @pytest.mark.parametrize("func_code", [22, 23])
    def test_fc22_and_fc23_are_illegal_function(self, func_code):

        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        assert ctx.setValues(func_code, 0, [5]) == 1
        assert ctx.getValues(func_code, 0, 1) == 1
        assert p.get("DS1") == 0

    @pytest.mark.parametrize(("func_code", "base"), [(2, 0), (1, 8192)])
    def test_slot_8_reserved_coils_read_off(self, func_code, base):
        p = MemoryDataProvider()
        p.set("X816" if base == 0 else "Y816", True)
        ctx = _ClickDeviceContext(p)
        # X816 or Y816, then units 17..32 of slot 8 (offsets 272..287).
        assert ctx.getValues(func_code, base + 271, 17) == [True] + [False] * 16

    def test_coil_past_slot_8_is_illegal_address(self):

        ctx = _ClickDeviceContext(MemoryDataProvider())
        assert ctx.getValues(1, 8192 + 288, 1) == 2
        assert ctx.getValues(1, 8192 + 287, 2) == 2

    @pytest.mark.parametrize("offset", [48, 63, 80, 272, 287])
    @pytest.mark.parametrize("base", [0, 8192], ids=["X", "Y"])
    def test_fc05_to_a_reserved_coil_stores_it(self, base, offset):
        # b4 R1 and R6 (2026-11-17) wrote Y offsets 48, 80 and 272 (coils 8240, 8272 and 8464)
        # and X offset 48. The other gap coils are assumed to behave the same.
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        assert ctx.setValues(5, base + offset, [True]) is None
        assert ctx.getValues(1, base + offset, 1) == [True]
        assert ctx.getValues(2, base + offset, 1) == [True]
        assert p._data == {}

    def test_fc15_over_slot_8_reserved_coils_stores_them(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        addr, _ = plc_to_modbus("Y", 816)
        assert ctx.setValues(15, addr, [True] * 17) is None
        assert p.get("Y816") is True
        assert ctx.getValues(1, addr, 17) == [True] * 17

    def test_fc15_past_slot_8_stores_nothing(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        assert ctx.setValues(15, 8192 + 271, [True] * 18) == 2
        assert p._data == {}
        assert ctx.memory.coils == {}


class TestAnswersAsAClickB4:
    """What a C2-03CPU (firmware 4.00) answered on 2026-11-17: runs b3, b4 (R1 to R6) and t1ct1."""

    def test_r1_fc15_and_fc05_over_the_y_gap(self):
        ctx = _ClickDeviceContext(MemoryDataProvider())
        # Y115, Y116, the 16 gap coils 8240..8255, Y201 and Y202.
        fc01 = struct.pack(">BHH", 1, 8238, 20)
        assert _answer(ctx, fc01) == bytes([1, 3, 0x00, 0x00, 0x00])
        fc15 = struct.pack(">BHHB", 15, 8238, 20, 3) + bytes([0xFF, 0xFF, 0x0F])
        assert _answer(ctx, fc15) == struct.pack(">BHH", 15, 8238, 20)
        assert _answer(ctx, fc01) == bytes([1, 3, 0xFF, 0xFF, 0x0F])
        for value in (0xFF00, 0x0000):
            fc05 = struct.pack(">BHH", 5, 8240, value)
            assert _answer(ctx, fc05) == fc05
        fc15 = struct.pack(">BHHB", 15, 8238, 20, 3) + bytes(3)
        assert _answer(ctx, fc15) == struct.pack(">BHH", 15, 8238, 20)
        assert _answer(ctx, fc01) == bytes([1, 3, 0x00, 0x00, 0x00])

    def test_r1_the_gap_coils_live_in_the_server_not_the_provider(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        assert ctx.setValues(15, 8238, [True] * 20) is None
        assert set(p._data) == {"Y115", "Y116", "Y201", "Y202"}
        assert ctx.memory.coils == dict.fromkeys(range(8240, 8256), True)
        # A context on the same memory, as after a server restart, reads them back.
        assert _ClickDeviceContext(p, ctx.memory).getValues(1, 8240, 16) == [True] * 16

    def test_r1_provider_failure_midway_keeps_no_gap_coil(self):
        class Flaky(MemoryDataProvider):
            def write(self, address: str, value):
                if address == "Y201":
                    raise RuntimeError("down")
                super().write(address, value)

        p = Flaky()
        ctx = _ClickDeviceContext(p)
        assert ctx.setValues(15, 8238, [True] * 20) == 4
        assert p.get("Y115") is False
        assert ctx.memory.coils == {}

    @pytest.mark.parametrize(
        ("func_code", "address", "count", "answer"),
        [
            (4, 57344, 9, bytes([4, 18]) + bytes(18)),
            (4, 57353, 1, bytes([4, 2, 0, 0])),
            (4, 57352, 2, bytes([4, 4]) + bytes(4)),
            (3, 57865, 1, bytes([3, 2, 0, 0])),
            (3, 57864, 2, bytes([3, 4]) + bytes(4)),
            (2, 16, 16, bytes([2, 2, 0, 0])),
            (2, 48, 16, bytes([2, 2, 0, 0])),
            (2, 0, 64, bytes([2, 8]) + bytes(8)),
            # R2b: XD8 and YD8 are 57360 and 57872, and the register after each reads 0.
            (4, 57361, 1, bytes([4, 2, 0, 0])),
            (4, 57360, 2, bytes([4, 4]) + bytes(4)),
            (4, 57344, 18, bytes([4, 36]) + bytes(36)),
            (3, 57873, 1, bytes([3, 2, 0, 0])),
            (3, 57872, 2, bytes([3, 4]) + bytes(4)),
            (3, 57856, 18, bytes([3, 36]) + bytes(36)),
        ],
    )
    def test_r2_reads_answer_0(self, func_code, address, count, answer):
        # R2: 57353 and 57865 are the unnamed words after XD4 and YD4, inside the banks.
        ctx = _ClickDeviceContext(MemoryDataProvider())
        assert _answer(ctx, struct.pack(">BHH", func_code, address, count)) == answer

    @pytest.mark.parametrize("address", [57361, 57873])
    def test_r2b_the_register_after_xd8_or_yd8_refuses_a_write(self, address):
        # No run wrote it, nor read the register after it.
        ctx = _ClickDeviceContext(MemoryDataProvider())
        assert _answer(ctx, struct.pack(">BHH", 6, address, 1)) == bytes([0x86, 2])
        assert _answer(ctx, struct.pack(">BHH", 3, address, 2)) == bytes([0x83, 2])
        assert ctx.memory.words == {}

    def test_r3_a_write_to_x001_is_answered_and_stored(self):
        # The CLICK's input scan rewrote X001 to 0. The server has no input scan, so whatever
        # drives the provider's inputs does that.
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        fc05 = struct.pack(">BHH", 5, 0, 0xFF00)
        assert _answer(ctx, fc05) == fc05
        assert p.get("X001") is True
        p.set("X001", False)
        fc15 = struct.pack(">BHHBB", 15, 0, 1, 1, 1)
        assert _answer(ctx, fc15) == struct.pack(">BHH", 15, 0, 1)
        assert _answer(ctx, struct.pack(">BHH", 1, 0, 1)) == bytes([1, 1, 1])
        assert _answer(ctx, struct.pack(">BHH", 2, 0, 1)) == bytes([2, 1, 1])

    @pytest.mark.parametrize(("coil", "address"), [(16, "X021"), (48, None)])
    def test_r6_fc05_to_x021_or_an_x_gap_coil_reads_back_on_fc01_and_fc02(self, coil, address):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        fc05 = struct.pack(">BHH", 5, coil, 0xFF00)
        assert _answer(ctx, fc05) == fc05
        for func_code in (1, 2):
            assert _answer(ctx, struct.pack(">BHH", func_code, coil, 1)) == bytes([func_code, 1, 1])
        assert p._data == ({address: True} if address else {})

    def test_r6_fc15_over_x101_to_x132_reads_back_on_fc01_and_fc02(self):
        # X101..X116 through the provider, then slot 1's 16 gap coils in the server.
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        fc15 = struct.pack(">BHHB", 15, 32, 32, 4) + bytes([0xFF] * 4)
        assert _answer(ctx, fc15) == struct.pack(">BHH", 15, 32, 32)
        for func_code in (1, 2):
            read = struct.pack(">BHH", func_code, 32, 32)
            assert _answer(ctx, read) == bytes([func_code, 4]) + bytes([0xFF] * 4)
        assert p._data == {f"X{i}": True for i in range(101, 117)}
        assert ctx.memory.coils == dict.fromkeys(range(48, 64), True)
        # Written back to 0, as R6 ended.
        fc15 = struct.pack(">BHHB", 15, 32, 32, 4) + bytes(4)
        assert _answer(ctx, fc15) == struct.pack(">BHH", 15, 32, 32)
        assert _answer(ctx, struct.pack(">BHH", 2, 0, 64)) == bytes([2, 8]) + bytes(8)

    @pytest.mark.parametrize("coil", [8272, 8464])
    def test_r6_fc05_to_slot_2_and_slot_8_y_gap_coils(self, coil):
        ctx = _ClickDeviceContext(MemoryDataProvider())
        for value, bit in ((0xFF00, 1), (0x0000, 0)):
            fc05 = struct.pack(">BHH", 5, coil, value)
            assert _answer(ctx, fc05) == fc05
            assert _answer(ctx, struct.pack(">BHH", 1, coil, 1)) == bytes([1, 1, bit])

    @pytest.mark.parametrize(
        ("address", "coil"), [("T1", 45056), ("CT1", 49152), ("T2", 45057), ("CT2", 49153)]
    )
    def test_t1ct1_fc05_sets_and_clears_the_bit_fc01_and_fc02_read(self, address, coil):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        for value, bit in ((0xFF00, 1), (0x0000, 0)):
            fc05 = struct.pack(">BHH", 5, coil, value)
            assert _answer(ctx, fc05) == fc05
            assert p.get(address) is bool(bit)
            for func_code in (1, 2):
                read = struct.pack(">BHH", func_code, coil, 1)
                assert _answer(ctx, read) == bytes([func_code, 1, bit])

    @pytest.mark.parametrize(("address", "coil"), [("T1", 45056), ("CT1", 49152)])
    def test_r3_fc15_to_t1_and_ct1_stores_the_bit(self, address, coil):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        fc15 = struct.pack(">BHHBB", 15, coil, 1, 1, 1)
        assert _answer(ctx, fc15) == struct.pack(">BHH", 15, coil, 1)
        assert p.get(address) is True

    def test_r4_fc06_to_one_word_of_a_df_keeps_the_other(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        df1 = plc_to_modbus("DF", 1)[0]
        read = struct.pack(">BHH", 3, df1, 2)
        nan_words = bytes([3, 4, 0x00, 0x00, 0x7F, 0xC0])
        fc16_nan = struct.pack(">BHHBHH", 16, df1, 2, 4, 0x0000, 0x7FC0)
        assert _answer(ctx, fc16_nan) == struct.pack(">BHH", 16, df1, 2)
        assert _answer(ctx, read) == nan_words
        for reg_addr, value in ((df1, 0x0000), (df1 + 1, 0x7FC0)):
            fc06 = struct.pack(">BHH", 6, reg_addr, value)
            assert _answer(ctx, fc06) == fc06
            assert _answer(ctx, read) == nan_words
        # 2.5 (0x0000:0x4020) over the NaN, one word at a time.
        assert _answer(ctx, fc16_nan) == struct.pack(">BHH", 16, df1, 2)
        fc06 = struct.pack(">BHH", 6, df1, 0x0000)
        assert _answer(ctx, fc06) == fc06
        assert _answer(ctx, read) == nan_words
        fc06 = struct.pack(">BHH", 6, df1 + 1, 0x4020)
        assert _answer(ctx, fc06) == fc06
        assert _answer(ctx, read) == bytes([3, 4, 0x00, 0x00, 0x40, 0x20])
        assert p.get("DF1") == 2.5

    @pytest.mark.parametrize(
        "words",
        [(0x0000, 0x7FC0), (0x0001, 0x7F80), (0xFFFF, 0xFFFF), (0x0000, 0x3FC0)],
        ids=["quiet NaN", "signalling NaN", "FFFF FFFF", "1.5"],
    )
    def test_b3_a_df_reads_back_the_words_written(self, words):
        ctx = _ClickDeviceContext(MemoryDataProvider())
        df1 = plc_to_modbus("DF", 1)[0]
        assert ctx.setValues(16, df1, list(words)) is None
        assert ctx.getValues(3, df1, 2) == list(words)
        assert ctx.getValues(3, df1 + 1, 1) == [words[1]]
        # A write to the high word alone leaves the low word as it was written.
        assert ctx.setValues(6, df1 + 1, [words[1]]) is None
        assert ctx.getValues(3, df1, 2) == list(words)

    def test_a_df_the_provider_changes_reads_as_the_provider_holds_it(self):
        p = MemoryDataProvider()
        ctx = _ClickDeviceContext(p)
        df1 = plc_to_modbus("DF", 1)[0]
        assert ctx.setValues(16, df1, [0x0001, 0x7F80]) is None
        p.set("DF1", 1.5)
        assert ctx.getValues(3, df1, 2) == [0x0000, 0x3FC0]
        p.set("DF1", math.nan)
        assert ctx.getValues(3, df1, 2) == [0x0000, 0x7FC0]

    def test_a_number_written_over_a_nan_forgets_its_words(self):
        ctx = _ClickDeviceContext(MemoryDataProvider())
        df1 = plc_to_modbus("DF", 1)[0]
        assert ctx.setValues(16, df1, [0x0001, 0x7F80]) is None
        assert ctx.memory.nan_words == {"DF1": (0x0001, 0x7F80)}
        assert ctx.setValues(16, df1, [0x0000, 0x3FC0]) is None
        assert ctx.memory.nan_words == {}

    @pytest.mark.parametrize(
        ("value", "words"), [(math.nan, [0x0000, 0x7FC0]), (-math.nan, [0x0000, 0xFFC0])]
    )
    def test_a_nan_set_in_the_provider_reads_as_its_own_bits(self, value, words):
        p = MemoryDataProvider()
        p.set("DF1", value)
        ctx = _ClickDeviceContext(p)
        assert ctx.getValues(3, plc_to_modbus("DF", 1)[0], 2) == words

    def test_provider_failure_midway_keeps_no_nan_words(self):
        class Flaky(MemoryDataProvider):
            def write(self, address: str, value):
                if address == "DF2":
                    raise RuntimeError("down")
                super().write(address, value)

        ctx = _ClickDeviceContext(Flaky())
        df1 = plc_to_modbus("DF", 1)[0]
        assert ctx.setValues(16, df1, [0x0001, 0x7F80, 0x0000, 0x3FC0]) == 4
        assert ctx.memory.nan_words == {}
