"""Tests for pyclickplc.client — ClickClient, AddressAccessor, etc.

Uses mocked transport (patching internal _read/_write methods).
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from pyclickplc.addresses import AddressRecord
from pyclickplc.banks import DataType
from pyclickplc.client import (
    AddressAccessor,
    AddressInterface,
    ClickClient,
    DisplayAddressAccessor,
    FixedAddressAccessor,
    ModbusResponse,
    TagInterface,
)
from pyclickplc.modbus import MODBUS_MAPPINGS, pack_value

# ==============================================================================
# Helpers
# ==============================================================================


def _make_plc() -> ClickClient:
    """Create a ClickClient without connecting."""
    plc = ClickClient("localhost", 5020)
    # Mock internal transport methods
    _set_read_coils(plc, [False])
    _set_write_coils(plc)
    _set_read_registers(plc, [0])
    _set_write_registers(plc)
    return plc


def _set_read_coils(plc: ClickClient, return_value: list[bool]) -> AsyncMock:
    mock = AsyncMock(return_value=return_value)
    object.__setattr__(plc, "_read_coils", mock)
    return mock


def _set_write_coils(plc: ClickClient) -> AsyncMock:
    mock = AsyncMock()
    object.__setattr__(plc, "_write_coils", mock)
    return mock


def _set_read_registers(plc: ClickClient, return_value: list[int]) -> AsyncMock:
    mock = AsyncMock(return_value=return_value)
    object.__setattr__(plc, "_read_registers", mock)
    return mock


def _set_write_registers(plc: ClickClient) -> AsyncMock:
    mock = AsyncMock()
    object.__setattr__(plc, "_write_registers", mock)
    return mock


def _get_write_coils_mock(plc: ClickClient) -> AsyncMock:
    return cast(AsyncMock, plc._write_coils)


def _get_write_registers_mock(plc: ClickClient) -> AsyncMock:
    return cast(AsyncMock, plc._write_registers)


def _as_float(value: object) -> float:
    assert isinstance(value, (int, float))
    return float(value)


# ==============================================================================
# ClickClient construction and __getattr__
# ==============================================================================


class TestClickClient:
    @pytest.mark.asyncio
    async def test_construction(self):
        plc = ClickClient("192.168.1.100")
        assert plc._client.comm_params.host == "192.168.1.100"
        assert plc._client.comm_params.port == 502
        assert plc._client.comm_params.reconnect_delay == 0.0
        assert plc._client.comm_params.reconnect_delay_max == 0.0
        assert plc.addr is not None
        assert plc.tag is not None
        assert plc.tags == {}

    @pytest.mark.asyncio
    async def test_construction_with_port(self):
        plc = ClickClient("192.168.1.100", 5020)
        assert plc._client.comm_params.host == "192.168.1.100"
        assert plc._client.comm_params.port == 5020

    @pytest.mark.asyncio
    async def test_construction_legacy_host_port_string(self):
        plc = ClickClient("192.168.1.100:5020")
        assert plc._client.comm_params.host == "192.168.1.100"
        assert plc._client.comm_params.port == 5020

    @pytest.mark.asyncio
    async def test_construction_with_device_id(self):
        plc = ClickClient("192.168.1.100", 5020, device_id=7)
        assert plc._device_id == 7

    @pytest.mark.asyncio
    async def test_construction_with_reconnect_settings(self):
        plc = ClickClient("192.168.1.100", reconnect_delay=0.5, reconnect_delay_max=2.0)
        assert plc._client.comm_params.reconnect_delay == 0.5
        assert plc._client.comm_params.reconnect_delay_max == 2.0

    @pytest.mark.asyncio
    async def test_construction_with_programmatic_tags(self):
        plc = ClickClient(
            "192.168.1.100",
            tags={
                "ignored": AddressRecord(memory_type="DF", address=1, nickname="Temp"),
                "other": AddressRecord(memory_type="C", address=1, nickname="Valve"),
            },
        )
        assert set(plc.tags.keys()) == {"Temp", "Valve"}
        assert plc.tags["Temp"]["address"] == "DF1"

    @pytest.mark.asyncio
    async def test_construction_with_programmatic_tags_skips_empty_nickname(self):
        plc = ClickClient(
            "192.168.1.100",
            tags={
                "first": AddressRecord(memory_type="DF", address=1, nickname=""),
                "second": AddressRecord(memory_type="C", address=1, nickname="Valve"),
            },
        )
        assert set(plc.tags.keys()) == {"Valve"}

    @pytest.mark.asyncio
    async def test_construction_with_programmatic_tags_rejects_case_collisions(self):
        with pytest.raises(ValueError, match="duplicate nickname"):
            ClickClient(
                "192.168.1.100",
                tags={
                    "a": AddressRecord(memory_type="DF", address=1, nickname="Pump"),
                    "b": AddressRecord(memory_type="DF", address=2, nickname="pump"),
                },
            )

    @pytest.mark.asyncio
    async def test_getattr_df(self):
        plc = _make_plc()
        accessor = plc.df
        assert isinstance(accessor, AddressAccessor)

    @pytest.mark.asyncio
    async def test_getattr_xd_is_display_indexed_accessor(self):
        plc = _make_plc()
        assert isinstance(plc.xd, DisplayAddressAccessor)

    @pytest.mark.asyncio
    async def test_getattr_yd_is_display_indexed_accessor(self):
        plc = _make_plc()
        assert isinstance(plc.yd, DisplayAddressAccessor)

    @pytest.mark.asyncio
    async def test_upper_byte_aliases_are_available(self):
        plc = _make_plc()
        assert isinstance(plc.xd0u, FixedAddressAccessor)
        assert isinstance(plc.yd0u, FixedAddressAccessor)
        assert plc.XD0U is plc.xd0u
        assert plc.YD0U is plc.yd0u

    @pytest.mark.asyncio
    async def test_getattr_case_insensitive(self):
        plc = _make_plc()
        accessor1 = plc.df
        accessor2 = plc.DF
        assert accessor1 is accessor2

    @pytest.mark.asyncio
    async def test_getattr_cached(self):
        plc = _make_plc()
        a1 = plc.ds
        a2 = plc.ds
        assert a1 is a2

    @pytest.mark.asyncio
    async def test_getattr_underscore_raises(self):
        plc = _make_plc()
        with pytest.raises(AttributeError):
            _ = cast(Any, plc)._private

    @pytest.mark.asyncio
    async def test_getattr_unknown_raises(self):
        plc = _make_plc()
        with pytest.raises(AttributeError, match="not a supported"):
            _ = cast(Any, plc).invalid_bank

    @pytest.mark.asyncio
    async def test_addr_is_address_interface(self):
        plc = _make_plc()
        assert isinstance(plc.addr, AddressInterface)

    @pytest.mark.asyncio
    async def test_tag_is_tag_interface(self):
        plc = _make_plc()
        assert isinstance(plc.tag, TagInterface)


# ==============================================================================
# AddressAccessor — repr
# ==============================================================================


class TestAddressAccessorRepr:
    @pytest.mark.asyncio
    async def test_repr_df(self):
        plc = _make_plc()
        assert repr(plc.df) == "<AddressAccessor(DF, max=500)>"

    @pytest.mark.asyncio
    async def test_repr_ds(self):
        plc = _make_plc()
        assert repr(plc.ds) == "<AddressAccessor(DS, max=4500)>"

    @pytest.mark.asyncio
    async def test_repr_x(self):
        plc = _make_plc()
        assert repr(plc.x) == "<AddressAccessor(X, max=816)>"

    @pytest.mark.asyncio
    async def test_repr_xd_display_accessor(self):
        plc = _make_plc()
        assert repr(plc.xd) == "<DisplayAddressAccessor(XD, max=8)>"

    @pytest.mark.asyncio
    async def test_repr_xd0u_fixed_accessor(self):
        plc = _make_plc()
        assert repr(plc.xd0u) == "<FixedAddressAccessor(XD0u)>"


# ==============================================================================
# AddressAccessor — read single
# ==============================================================================


class TestAddressAccessorReadSingle:
    @pytest.mark.asyncio
    async def test_read_float(self):
        plc = _make_plc()
        regs = pack_value(3.14, DataType.FLOAT)
        _set_read_registers(plc, regs)
        result = await plc.df.read(1)
        assert isinstance(result, ModbusResponse)
        import math

        assert math.isclose(result["DF1"], 3.14, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_int16(self):
        plc = _make_plc()
        _set_read_registers(plc, [42])
        result = await plc.ds.read(1)
        assert result == {"DS1": 42}

    @pytest.mark.asyncio
    async def test_read_int32(self):
        plc = _make_plc()
        regs = pack_value(100000, DataType.INT2)
        _set_read_registers(plc, regs)
        result = await plc.dd.read(1)
        assert result == {"DD1": 100000}

    @pytest.mark.asyncio
    async def test_read_unsigned(self):
        plc = _make_plc()
        _set_read_registers(plc, [0xABCD])
        result = await plc.dh.read(1)
        assert result == {"DH1": 0xABCD}

    @pytest.mark.asyncio
    async def test_read_bool(self):
        plc = _make_plc()
        _set_read_coils(plc, [True])
        result = await plc.c.read(1)
        assert result == {"C1": True}

    @pytest.mark.asyncio
    async def test_read_sparse_bool(self):
        plc = _make_plc()
        _set_read_coils(plc, [True])
        result = await plc.x.read(101)
        assert result == {"X101": True}

    @pytest.mark.asyncio
    async def test_read_txt(self):
        plc = _make_plc()
        # TXT1 is low byte of register
        _set_read_registers(plc, [ord("A") | (ord("B") << 8)])
        result = await plc.txt.read(1)
        assert result == {"TXT1": "A"}

    @pytest.mark.asyncio
    async def test_read_txt_even(self):
        plc = _make_plc()
        _set_read_registers(plc, [ord("A") | (ord("B") << 8)])
        result = await plc.txt.read(2)
        assert result == {"TXT2": "B"}


# ==============================================================================
# AddressAccessor — read range
# ==============================================================================


class TestAddressAccessorReadRange:
    @pytest.mark.asyncio
    async def test_read_df_range(self):
        plc = _make_plc()
        r1 = pack_value(1.0, DataType.FLOAT)
        r2 = pack_value(2.0, DataType.FLOAT)
        _set_read_registers(plc, r1 + r2)
        result = await plc.df.read(1, 2)
        assert isinstance(result, ModbusResponse)
        assert len(result) == 2
        import math

        assert math.isclose(result["DF1"], 1.0, rel_tol=1e-6)
        assert math.isclose(result["DF2"], 2.0, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_c_range(self):
        plc = _make_plc()
        _set_read_coils(plc, [True, False, True])
        result = await plc.c.read(1, 3)
        assert result == {"C1": True, "C2": False, "C3": True}

    @pytest.mark.asyncio
    async def test_read_end_le_start_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="greater than start"):
            await plc.df.read(10, 5)


# ==============================================================================
# DisplayAddressAccessor — XD/YD ergonomics
# ==============================================================================


class TestDisplayAddressAccessor:
    @pytest.mark.asyncio
    async def test_read_xd_display_single(self):
        plc = _make_plc()

        async def fake_read_registers(address: int, count: int, bank: str) -> list[int]:
            del bank
            return [address + i for i in range(count)]

        object.__setattr__(plc, "_read_registers", AsyncMock(side_effect=fake_read_registers))
        result = await plc.xd.read(3)
        assert result == {"XD3": 57350}

    @pytest.mark.asyncio
    async def test_read_xd_display_range_has_no_hidden_slots(self):
        plc = _make_plc()

        async def fake_read_registers(address: int, count: int, bank: str) -> list[int]:
            del bank
            return [address + i for i in range(count)]

        object.__setattr__(plc, "_read_registers", AsyncMock(side_effect=fake_read_registers))
        result = await plc.xd.read(0, 4)
        assert list(result.keys()) == ["XD0", "XD1", "XD2", "XD3", "XD4"]
        assert list(result.values()) == [57344, 57346, 57348, 57350, 57352]

    @pytest.mark.asyncio
    async def test_write_yd_display_single(self):
        plc = _make_plc()
        await plc.yd.write(3, 0xABCD)
        _get_write_registers_mock(plc).assert_called_once_with(57862, [0xABCD])

    @pytest.mark.asyncio
    async def test_write_yd_display_list(self):
        plc = _make_plc()
        await plc.yd.write(0, [1, 2, 3])
        assert _get_write_registers_mock(plc).call_count == 3
        assert _get_write_registers_mock(plc).call_args_list[0].args == (57856, [1])
        assert _get_write_registers_mock(plc).call_args_list[1].args == (57858, [2])
        assert _get_write_registers_mock(plc).call_args_list[2].args == (57860, [3])

    @pytest.mark.asyncio
    async def test_write_xd_display_not_writable(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="not writable"):
            await plc.xd.write(1, 0x1234)

    @pytest.mark.asyncio
    async def test_read_xd_out_of_range_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError):
            await plc.xd.read(9)


# ==============================================================================
# FixedAddressAccessor — XD0u/YD0u
# ==============================================================================


class TestFixedAddressAccessor:
    @pytest.mark.asyncio
    async def test_read_xd0u(self):
        plc = _make_plc()
        _set_read_registers(plc, [0x1234])
        result = await plc.xd0u.read()
        assert result == {"XD0u": 0x1234}

    @pytest.mark.asyncio
    async def test_write_xd0u_not_writable(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="not writable"):
            await plc.xd0u.write(0x1234)

    @pytest.mark.asyncio
    async def test_write_yd0u(self):
        plc = _make_plc()
        await plc.yd0u.write(0x1234)
        _get_write_registers_mock(plc).assert_called_once_with(57857, [0x1234])


# ==============================================================================
# AddressAccessor — write
# ==============================================================================


class TestAddressAccessorWrite:
    @pytest.mark.asyncio
    async def test_write_float(self):
        plc = _make_plc()
        await plc.df.write(1, 3.14)
        _get_write_registers_mock(plc).assert_called_once()

    @pytest.mark.asyncio
    async def test_write_int16(self):
        plc = _make_plc()
        await plc.ds.write(1, 42)
        _get_write_registers_mock(plc).assert_called_once()

    @pytest.mark.asyncio
    async def test_write_bool(self):
        plc = _make_plc()
        await plc.c.write(1, True)
        _get_write_coils_mock(plc).assert_called_once()

    @pytest.mark.asyncio
    async def test_write_list(self):
        plc = _make_plc()
        await plc.df.write(1, [1.0, 2.0, 3.0])
        _get_write_registers_mock(plc).assert_called_once()

    @pytest.mark.asyncio
    async def test_write_wrong_type_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="DF1 value must be a finite float32"):
            await plc.df.write(1, "string")

    @pytest.mark.asyncio
    async def test_write_float_to_int_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="DS1 value must be int"):
            await plc.ds.write(1, 3.14)

    @pytest.mark.asyncio
    async def test_write_int16_overflow_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="DS1 value must be int"):
            await plc.ds.write(1, 32768)

    @pytest.mark.asyncio
    async def test_write_int32_overflow_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="DD1 value must be int"):
            await plc.dd.write(1, 2147483648)

    @pytest.mark.asyncio
    async def test_write_word_underflow_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="DH1 must be WORD"):
            await plc.dh.write(1, -1)

    @pytest.mark.asyncio
    async def test_write_bool_for_numeric_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="DS1 value must be int"):
            await plc.ds.write(1, True)

    @pytest.mark.asyncio
    async def test_write_nan_float_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="DF1 value must be a finite float32"):
            await plc.df.write(1, float("nan"))

    @pytest.mark.asyncio
    async def test_write_inf_float_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="DF1 value must be a finite float32"):
            await plc.df.write(1, float("inf"))

    @pytest.mark.asyncio
    async def test_write_txt_too_long_raises(self):
        plc = _make_plc()
        with pytest.raises(
            ValueError, match="TXT1 TXT value must be blank or a single ASCII character"
        ):
            await plc.txt.write(1, "AB")

    @pytest.mark.asyncio
    async def test_write_txt_non_ascii_raises(self):
        plc = _make_plc()
        with pytest.raises(
            ValueError, match="TXT1 TXT value must be blank or a single ASCII character"
        ):
            await plc.txt.write(1, "\u00e9")

    @pytest.mark.asyncio
    async def test_write_not_writable_x(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="not writable"):
            await plc.x.write(1, True)

    @pytest.mark.asyncio
    async def test_write_not_writable_sc(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="not writable"):
            await plc.sc.write(1, True)

    @pytest.mark.asyncio
    async def test_write_writable_sc53(self):
        plc = _make_plc()
        await plc.sc.write(53, True)
        _get_write_coils_mock(plc).assert_called_once()

    @pytest.mark.asyncio
    async def test_write_not_writable_sd(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="not writable"):
            await plc.sd.write(1, 42)

    @pytest.mark.asyncio
    async def test_write_writable_sd29(self):
        plc = _make_plc()
        await plc.sd.write(29, 100)
        _get_write_registers_mock(plc).assert_called_once()


# ==============================================================================
# AddressAccessor — validation errors
# ==============================================================================


class TestAddressAccessorValidation:
    @pytest.mark.asyncio
    async def test_out_of_range_low(self):
        plc = _make_plc()
        with pytest.raises(ValueError):
            await plc.df.read(0)

    @pytest.mark.asyncio
    async def test_out_of_range_high(self):
        plc = _make_plc()
        with pytest.raises(ValueError):
            await plc.df.read(501)

    @pytest.mark.asyncio
    async def test_sparse_gap(self):
        plc = _make_plc()
        with pytest.raises(ValueError):
            await plc.x.read(17)

    @pytest.mark.asyncio
    async def test_sparse_gap_37(self):
        plc = _make_plc()
        with pytest.raises(ValueError):
            await plc.x.read(37)

    @pytest.mark.asyncio
    async def test_read_max_df(self):
        """Reading at max address should work."""
        plc = _make_plc()
        regs = pack_value(0.0, DataType.FLOAT)
        _set_read_registers(plc, regs)
        result = await plc.df.read(500)
        assert result == {"DF500": 0.0}


# ==============================================================================
# AddressInterface
# ==============================================================================


class TestAddressInterface:
    @pytest.mark.asyncio
    async def test_read_single(self):
        plc = _make_plc()
        regs = pack_value(3.14, DataType.FLOAT)
        _set_read_registers(plc, regs)
        result = await plc.addr.read("df1")
        assert isinstance(result, ModbusResponse)
        import math

        assert math.isclose(_as_float(result["DF1"]), 3.14, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_range(self):
        plc = _make_plc()
        r1 = pack_value(1.0, DataType.FLOAT)
        r2 = pack_value(2.0, DataType.FLOAT)
        _set_read_registers(plc, r1 + r2)
        result = await plc.addr.read("df1-df2")
        assert isinstance(result, ModbusResponse)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_read_case_insensitive(self):
        plc = _make_plc()
        regs = pack_value(0.0, DataType.FLOAT)
        _set_read_registers(plc, regs)
        result = await plc.addr.read("DF1")
        assert result == {"DF1": 0.0}

    @pytest.mark.asyncio
    async def test_inter_bank_range_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="Inter-bank"):
            await plc.addr.read("df1-dd10")

    @pytest.mark.asyncio
    async def test_end_le_start_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="greater than start"):
            await plc.addr.read("df10-df5")

    @pytest.mark.asyncio
    async def test_xd_range_is_display_step(self):
        plc = _make_plc()

        async def fake_read_registers(address: int, count: int, bank: str) -> list[int]:
            del bank
            return [address + i for i in range(count)]

        object.__setattr__(plc, "_read_registers", AsyncMock(side_effect=fake_read_registers))
        result = await plc.addr.read("XD0-XD4")
        assert list(result.keys()) == ["XD0", "XD1", "XD2", "XD3", "XD4"]
        assert list(result.values()) == [57344, 57346, 57348, 57350, 57352]

    @pytest.mark.asyncio
    async def test_yd_range_is_display_step(self):
        plc = _make_plc()

        async def fake_read_registers(address: int, count: int, bank: str) -> list[int]:
            del bank
            return [address + i for i in range(count)]

        object.__setattr__(plc, "_read_registers", AsyncMock(side_effect=fake_read_registers))
        result = await plc.addr.read("YD0-YD2")
        assert list(result.keys()) == ["YD0", "YD1", "YD2"]
        assert list(result.values()) == [57856, 57858, 57860]

    @pytest.mark.asyncio
    async def test_xd_range_rejects_upper_byte_start(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="upper-byte"):
            await plc.addr.read("XD0u-XD1")

    @pytest.mark.asyncio
    async def test_xd_range_rejects_upper_byte_end(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="upper-byte"):
            await plc.addr.read("XD0-XD0u")

    @pytest.mark.asyncio
    async def test_single_xd0u_read_still_works(self):
        plc = _make_plc()
        _set_read_registers(plc, [99])
        result = await plc.addr.read("XD0u")
        assert result == {"XD0u": 99}

    @pytest.mark.asyncio
    async def test_invalid_address_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError):
            await plc.addr.read("invalid1")

    @pytest.mark.asyncio
    async def test_write_single(self):
        plc = _make_plc()
        await plc.addr.write("df1", 3.14)
        _get_write_registers_mock(plc).assert_called_once()

    @pytest.mark.asyncio
    async def test_write_list(self):
        plc = _make_plc()
        await plc.addr.write("df1", [1.0, 2.0])
        _get_write_registers_mock(plc).assert_called_once()


# ==============================================================================
# TagInterface (without actual CSV file)
# ==============================================================================


class TestTagInterface:
    def _plc_with_tags(self) -> ClickClient:
        plc = _make_plc()
        plc.tags = {
            "Temp": {"address": "DF1", "type": "FLOAT", "comment": "Temperature"},
            "Valve": {"address": "C1", "type": "BIT", "comment": "Valve open"},
        }
        return plc

    @pytest.mark.asyncio
    async def test_read_single_tag(self):
        plc = self._plc_with_tags()
        regs = pack_value(25.0, DataType.FLOAT)
        _set_read_registers(plc, regs)
        value = await plc.tag.read("Temp")
        import math

        assert math.isclose(_as_float(value), 25.0, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_missing_tag_raises(self):
        plc = self._plc_with_tags()
        with pytest.raises(KeyError, match="not found"):
            await plc.tag.read("NonExistent")

    @pytest.mark.asyncio
    async def test_read_tag_case_insensitive(self):
        plc = self._plc_with_tags()
        regs = pack_value(25.0, DataType.FLOAT)
        _set_read_registers(plc, regs)
        value = await plc.tag.read("temp")
        import math

        assert math.isclose(_as_float(value), 25.0, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_all_tags(self):
        plc = self._plc_with_tags()
        regs = pack_value(25.0, DataType.FLOAT)
        _set_read_registers(plc, regs)
        _set_read_coils(plc, [True])
        result = await plc.tag.read_all()
        assert isinstance(result, dict)
        assert "Temp" in result
        assert "Valve" in result

    @pytest.mark.asyncio
    async def test_read_all_no_tags_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="No tags loaded"):
            await plc.tag.read_all()

    @pytest.mark.asyncio
    async def test_read_all_excludes_system_by_default(self):
        plc = self._plc_with_tags()
        plc.tags["SysFlag"] = {"address": "SC1", "type": "BIT", "comment": "System"}
        plc.tags["SysData"] = {"address": "SD1", "type": "INT", "comment": "System"}
        regs = pack_value(25.0, DataType.FLOAT)
        _set_read_registers(plc, regs)
        _set_read_coils(plc, [True])
        result = await plc.tag.read_all()
        assert "Temp" in result
        assert "Valve" in result
        assert "SysFlag" not in result
        assert "SysData" not in result

    @pytest.mark.asyncio
    async def test_read_all_includes_system_when_requested(self):
        plc = self._plc_with_tags()
        plc.tags["SysFlag"] = {"address": "SC1", "type": "BIT", "comment": "System"}
        regs = pack_value(25.0, DataType.FLOAT)
        _set_read_registers(plc, regs)
        _set_read_coils(plc, [True])
        result = await plc.tag.read_all(include_system=True)
        assert "Temp" in result
        assert "SysFlag" in result

    @pytest.mark.asyncio
    async def test_write_tag(self):
        plc = self._plc_with_tags()
        await plc.tag.write("Temp", 30.0)
        _get_write_registers_mock(plc).assert_called_once()

    @pytest.mark.asyncio
    async def test_write_missing_tag_raises(self):
        plc = self._plc_with_tags()
        with pytest.raises(KeyError, match="not found"):
            await plc.tag.write("NonExistent", 42)

    @pytest.mark.asyncio
    async def test_write_tag_case_insensitive(self):
        plc = self._plc_with_tags()
        await plc.tag.write("temp", 30.0)
        _get_write_registers_mock(plc).assert_called_once()


# ==============================================================================
# TXT write tests (mocked)
# ==============================================================================


class TestAddressAccessorTxtWrite:
    @pytest.mark.asyncio
    async def test_write_single_txt(self):
        plc = _make_plc()
        # Mock read of current register value (for twin byte preservation)
        _set_read_registers(plc, [0])
        await plc.txt.write(1, "A")
        _get_write_registers_mock(plc).assert_called_once()

    @pytest.mark.asyncio
    async def test_write_empty_string_clears_txt(self):
        plc = _make_plc()
        _set_read_registers(plc, [0x4142])  # "AB"
        await plc.txt.write(1, "")
        # Empty string → null byte in low position, high byte preserved
        _get_write_registers_mock(plc).assert_called_once_with(
            MODBUS_MAPPINGS["TXT"].base, [0x4100]
        )

    @pytest.mark.asyncio
    async def test_write_txt_list(self):
        plc = _make_plc()
        _set_read_registers(plc, [0])
        await plc.txt.write(1, ["H", "i"])
        assert _get_write_registers_mock(plc).call_count == 2


# ==============================================================================
# ModbusResponse
# ==============================================================================


class TestModbusResponse:
    def _sample(self) -> ModbusResponse:
        return ModbusResponse({"DS1": 10, "DS2": 20, "DS3": 30})

    # -- __getitem__ --------------------------------------------------------

    def test_getitem_exact_key(self):
        r = self._sample()
        assert r["DS1"] == 10

    def test_getitem_normalized_key(self):
        r = self._sample()
        assert r["ds1"] == 10

    def test_getitem_missing_raises(self):
        r = self._sample()
        with pytest.raises(KeyError):
            r["DS999"]

    def test_getitem_invalid_raises(self):
        r = self._sample()
        with pytest.raises(KeyError):
            r["invalid"]

    # -- __contains__ -------------------------------------------------------

    def test_contains_exact(self):
        r = self._sample()
        assert "DS1" in r

    def test_contains_normalized(self):
        r = self._sample()
        assert "ds2" in r

    def test_not_contains(self):
        r = self._sample()
        assert "DS999" not in r

    def test_contains_non_string(self):
        r = self._sample()
        assert 42 not in r

    # -- __len__ / __iter__ -------------------------------------------------

    def test_len(self):
        r = self._sample()
        assert len(r) == 3

    def test_iter(self):
        r = self._sample()
        assert list(r) == ["DS1", "DS2", "DS3"]

    # -- Mapping methods (inherited) ----------------------------------------

    def test_keys(self):
        r = self._sample()
        assert list(r.keys()) == ["DS1", "DS2", "DS3"]

    def test_values(self):
        r = self._sample()
        assert list(r.values()) == [10, 20, 30]

    def test_items(self):
        r = self._sample()
        assert list(r.items()) == [("DS1", 10), ("DS2", 20), ("DS3", 30)]

    def test_get_existing(self):
        r = self._sample()
        assert r.get("DS1") == 10

    def test_get_normalized(self):
        r = self._sample()
        assert r.get("ds3") == 30

    def test_get_missing_default(self):
        r = self._sample()
        assert r.get("DS999", -1) == -1

    def test_get_missing_none(self):
        r = self._sample()
        assert r.get("DS999") is None

    # -- __eq__ -------------------------------------------------------------

    def test_eq_modbus_response(self):
        a = ModbusResponse({"DS1": 10, "DS2": 20})
        b = ModbusResponse({"DS1": 10, "DS2": 20})
        assert a == b

    def test_eq_modbus_response_mismatch(self):
        a = ModbusResponse({"DS1": 10})
        b = ModbusResponse({"DS1": 99})
        assert a != b

    def test_eq_dict_uppercase(self):
        r = ModbusResponse({"DS1": 10, "DS2": 20})
        assert r == {"DS1": 10, "DS2": 20}

    def test_eq_dict_normalized(self):
        r = ModbusResponse({"DS1": 10, "DS2": 20})
        assert r == {"ds1": 10, "ds2": 20}

    def test_eq_dict_length_mismatch(self):
        r = ModbusResponse({"DS1": 10})
        assert r != {"DS1": 10, "DS2": 20}

    def test_eq_other_type(self):
        r = self._sample()
        assert r != 42

    # -- isinstance checks --------------------------------------------------

    def test_not_dict_instance(self):
        from collections.abc import Mapping

        r = self._sample()
        assert not isinstance(r, dict)
        assert isinstance(r, Mapping)

    # -- __repr__ -----------------------------------------------------------

    def test_repr(self):
        r = ModbusResponse({"DS1": 10})
        assert repr(r) == "ModbusResponse({'DS1': 10})"


# ==============================================================================
# AddressAccessor.__getitem__
# ==============================================================================


class TestAddressAccessorGetitem:
    @pytest.mark.asyncio
    async def test_getitem_int(self):
        plc = _make_plc()
        _set_read_registers(plc, [42])
        value = await plc.ds[1]
        assert value == 42

    @pytest.mark.asyncio
    async def test_getitem_float(self):
        plc = _make_plc()
        regs = pack_value(3.14, DataType.FLOAT)
        _set_read_registers(plc, regs)
        value = await plc.df[1]
        import math

        assert math.isclose(value, 3.14, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_getitem_bool(self):
        plc = _make_plc()
        _set_read_coils(plc, [True])
        value = await plc.c[1]
        assert value is True

    @pytest.mark.asyncio
    async def test_getitem_xd_is_display_indexed(self):
        plc = _make_plc()

        async def fake_read_registers(address: int, count: int, bank: str) -> list[int]:
            del bank
            return [address + i for i in range(count)]

        object.__setattr__(plc, "_read_registers", AsyncMock(side_effect=fake_read_registers))
        value = await plc.xd[3]
        assert value == 57350

    @pytest.mark.asyncio
    async def test_getitem_slice_raises(self):
        plc = _make_plc()
        with pytest.raises(TypeError, match="Slicing is not supported"):
            cast(Any, plc.ds)[1:5]

    @pytest.mark.asyncio
    async def test_getitem_out_of_range_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError):
            await plc.df[0]

    @pytest.mark.asyncio
    async def test_getitem_xd_out_of_range_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError):
            await plc.xd[9]
