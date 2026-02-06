"""Tests for pyclickplc.client — ClickClient, AddressAccessor, etc.

Uses mocked transport (patching internal _read/_write methods).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pyclickplc.banks import DataType
from pyclickplc.client import (
    AddressAccessor,
    AddressInterface,
    ClickClient,
    TagInterface,
)
from pyclickplc.modbus import pack_value

# ==============================================================================
# Helpers
# ==============================================================================


def _make_plc(tag_filepath: str = "") -> ClickClient:
    """Create a ClickClient without connecting."""
    plc = ClickClient("localhost:5020", tag_filepath=tag_filepath)
    # Mock internal transport methods
    plc._read_coils = AsyncMock(return_value=[False])
    plc._write_coils = AsyncMock()
    plc._read_registers = AsyncMock(return_value=[0])
    plc._write_registers = AsyncMock()
    return plc


# ==============================================================================
# ClickClient construction and __getattr__
# ==============================================================================


class TestClickClient:
    @pytest.mark.asyncio
    async def test_construction(self):
        plc = ClickClient("192.168.1.100")
        assert plc.addr is not None
        assert plc.tag is not None
        assert plc.tags == {}

    @pytest.mark.asyncio
    async def test_construction_with_port(self):
        plc = ClickClient("192.168.1.100:5020")
        assert plc._client.comm_params.host == "192.168.1.100"
        assert plc._client.comm_params.port == 5020

    @pytest.mark.asyncio
    async def test_getattr_df(self):
        plc = _make_plc()
        accessor = plc.df
        assert isinstance(accessor, AddressAccessor)

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
            plc._private

    @pytest.mark.asyncio
    async def test_getattr_unknown_raises(self):
        plc = _make_plc()
        with pytest.raises(AttributeError, match="not a supported"):
            plc.invalid_bank

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


# ==============================================================================
# AddressAccessor — read single
# ==============================================================================


class TestAddressAccessorReadSingle:
    @pytest.mark.asyncio
    async def test_read_float(self):
        plc = _make_plc()
        regs = pack_value(3.14, DataType.FLOAT)
        plc._read_registers = AsyncMock(return_value=regs)
        value = await plc.df.read(1)
        import math

        assert math.isclose(value, 3.14, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_int16(self):
        plc = _make_plc()
        plc._read_registers = AsyncMock(return_value=[42])
        value = await plc.ds.read(1)
        assert value == 42

    @pytest.mark.asyncio
    async def test_read_int32(self):
        plc = _make_plc()
        regs = pack_value(100000, DataType.INT2)
        plc._read_registers = AsyncMock(return_value=regs)
        value = await plc.dd.read(1)
        assert value == 100000

    @pytest.mark.asyncio
    async def test_read_unsigned(self):
        plc = _make_plc()
        plc._read_registers = AsyncMock(return_value=[0xABCD])
        value = await plc.dh.read(1)
        assert value == 0xABCD

    @pytest.mark.asyncio
    async def test_read_bool(self):
        plc = _make_plc()
        plc._read_coils = AsyncMock(return_value=[True])
        value = await plc.c.read(1)
        assert value is True

    @pytest.mark.asyncio
    async def test_read_sparse_bool(self):
        plc = _make_plc()
        plc._read_coils = AsyncMock(return_value=[True])
        value = await plc.x.read(101)
        assert value is True

    @pytest.mark.asyncio
    async def test_read_txt(self):
        plc = _make_plc()
        # TXT1 is low byte of register
        plc._read_registers = AsyncMock(return_value=[ord("A") | (ord("B") << 8)])
        value = await plc.txt.read(1)
        assert value == "A"

    @pytest.mark.asyncio
    async def test_read_txt_even(self):
        plc = _make_plc()
        plc._read_registers = AsyncMock(return_value=[ord("A") | (ord("B") << 8)])
        value = await plc.txt.read(2)
        assert value == "B"


# ==============================================================================
# AddressAccessor — read range
# ==============================================================================


class TestAddressAccessorReadRange:
    @pytest.mark.asyncio
    async def test_read_df_range(self):
        plc = _make_plc()
        r1 = pack_value(1.0, DataType.FLOAT)
        r2 = pack_value(2.0, DataType.FLOAT)
        plc._read_registers = AsyncMock(return_value=r1 + r2)
        result = await plc.df.read(1, 2)
        assert isinstance(result, dict)
        assert len(result) == 2
        import math

        assert math.isclose(result["df1"], 1.0, rel_tol=1e-6)
        assert math.isclose(result["df2"], 2.0, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_c_range(self):
        plc = _make_plc()
        plc._read_coils = AsyncMock(return_value=[True, False, True])
        result = await plc.c.read(1, 3)
        assert result == {"c1": True, "c2": False, "c3": True}

    @pytest.mark.asyncio
    async def test_read_end_le_start_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="greater than start"):
            await plc.df.read(10, 5)


# ==============================================================================
# AddressAccessor — write
# ==============================================================================


class TestAddressAccessorWrite:
    @pytest.mark.asyncio
    async def test_write_float(self):
        plc = _make_plc()
        await plc.df.write(1, 3.14)
        plc._write_registers.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_int16(self):
        plc = _make_plc()
        await plc.ds.write(1, 42)
        plc._write_registers.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_bool(self):
        plc = _make_plc()
        await plc.c.write(1, True)
        plc._write_coils.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_list(self):
        plc = _make_plc()
        await plc.df.write(1, [1.0, 2.0, 3.0])
        plc._write_registers.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_wrong_type_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="Expected"):
            await plc.df.write(1, "string")

    @pytest.mark.asyncio
    async def test_write_float_to_int_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="Expected"):
            await plc.ds.write(1, 3.14)

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
        plc._write_coils.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_not_writable_sd(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="not writable"):
            await plc.sd.write(1, 42)

    @pytest.mark.asyncio
    async def test_write_writable_sd29(self):
        plc = _make_plc()
        await plc.sd.write(29, 100)
        plc._write_registers.assert_called_once()


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
        plc._read_registers = AsyncMock(return_value=regs)
        value = await plc.df.read(500)
        assert value == 0.0


# ==============================================================================
# AddressInterface
# ==============================================================================


class TestAddressInterface:
    @pytest.mark.asyncio
    async def test_read_single(self):
        plc = _make_plc()
        regs = pack_value(3.14, DataType.FLOAT)
        plc._read_registers = AsyncMock(return_value=regs)
        value = await plc.addr.read("df1")
        import math

        assert math.isclose(value, 3.14, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_range(self):
        plc = _make_plc()
        r1 = pack_value(1.0, DataType.FLOAT)
        r2 = pack_value(2.0, DataType.FLOAT)
        plc._read_registers = AsyncMock(return_value=r1 + r2)
        result = await plc.addr.read("df1-df2")
        assert isinstance(result, dict)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_read_case_insensitive(self):
        plc = _make_plc()
        regs = pack_value(0.0, DataType.FLOAT)
        plc._read_registers = AsyncMock(return_value=regs)
        value = await plc.addr.read("DF1")
        assert value == 0.0

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
    async def test_invalid_address_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError):
            await plc.addr.read("invalid1")

    @pytest.mark.asyncio
    async def test_write_single(self):
        plc = _make_plc()
        await plc.addr.write("df1", 3.14)
        plc._write_registers.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_list(self):
        plc = _make_plc()
        await plc.addr.write("df1", [1.0, 2.0])
        plc._write_registers.assert_called_once()


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
        plc._read_registers = AsyncMock(return_value=regs)
        value = await plc.tag.read("Temp")
        import math

        assert math.isclose(value, 25.0, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_missing_tag_raises(self):
        plc = self._plc_with_tags()
        with pytest.raises(KeyError, match="not found"):
            await plc.tag.read("NonExistent")

    @pytest.mark.asyncio
    async def test_read_all_tags(self):
        plc = self._plc_with_tags()
        regs = pack_value(25.0, DataType.FLOAT)
        plc._read_registers = AsyncMock(return_value=regs)
        plc._read_coils = AsyncMock(return_value=[True])
        result = await plc.tag.read()
        assert isinstance(result, dict)
        assert "Temp" in result
        assert "Valve" in result

    @pytest.mark.asyncio
    async def test_read_all_no_tags_raises(self):
        plc = _make_plc()
        with pytest.raises(ValueError, match="No tags loaded"):
            await plc.tag.read()

    @pytest.mark.asyncio
    async def test_write_tag(self):
        plc = self._plc_with_tags()
        await plc.tag.write("Temp", 30.0)
        plc._write_registers.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_missing_tag_raises(self):
        plc = self._plc_with_tags()
        with pytest.raises(KeyError, match="not found"):
            await plc.tag.write("NonExistent", 42)

    @pytest.mark.asyncio
    async def test_read_all_definitions(self):
        plc = self._plc_with_tags()
        result = plc.tag.read_all()
        assert "Temp" in result
        assert result["Temp"]["address"] == "DF1"
        # Should be a copy
        result["New"] = {"address": "DS1"}
        assert "New" not in plc.tags


# ==============================================================================
# TXT write tests (mocked)
# ==============================================================================


class TestAddressAccessorTxtWrite:
    @pytest.mark.asyncio
    async def test_write_single_txt(self):
        plc = _make_plc()
        # Mock read of current register value (for twin byte preservation)
        plc._read_registers = AsyncMock(return_value=[0])
        await plc.txt.write(1, "A")
        plc._write_registers.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_txt_list(self):
        plc = _make_plc()
        plc._read_registers = AsyncMock(return_value=[0])
        await plc.txt.write(1, ["H", "i"])
        assert plc._write_registers.call_count == 2
