"""Integration tests: ClickClient <-> ClickServer round-trips.

Tests the full stack: driver -> pymodbus client -> TCP -> pymodbus server
-> _ClickDeviceContext -> MemoryDataProvider.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from pyclickplc.client import ClickClient
from pyclickplc.server import ClickServer, MemoryDataProvider

# Port for integration tests (avoid 502 which needs root)
TEST_PORT = 15020


@pytest.fixture
async def plc_fixture():
    """Provide a connected ClickClient and MemoryDataProvider."""
    provider = MemoryDataProvider()
    async with ClickServer(provider, port=TEST_PORT):
        # Small delay for server to be ready
        await asyncio.sleep(0.1)
        async with ClickClient("localhost", TEST_PORT) as plc:
            yield plc, provider


# ==============================================================================
# Basic round-trips by data type
# ==============================================================================


class TestRoundTrips:
    @pytest.mark.asyncio
    async def test_float_round_trip(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.df.write(1, 3.14)
        result = await plc.df.read(1)
        assert math.isclose(result["DF1"], 3.14, rel_tol=1e-6)
        assert math.isclose(provider.get("DF1"), 3.14, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_int32_round_trip(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.dd.write(1, 100000)
        result = await plc.dd.read(1)
        assert result == {"DD1": 100000}
        assert provider.get("DD1") == 100000

    @pytest.mark.asyncio
    async def test_int16_signed_positive(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.ds.write(1, 1234)
        result = await plc.ds.read(1)
        assert result == {"DS1": 1234}

    @pytest.mark.asyncio
    async def test_int16_signed_negative(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.ds.write(1, -1234)
        result = await plc.ds.read(1)
        assert result == {"DS1": -1234}

    @pytest.mark.asyncio
    async def test_int16_unsigned_dh(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.dh.write(1, 0xABCD)
        result = await plc.dh.read(1)
        assert result == {"DH1": 0xABCD}

    @pytest.mark.asyncio
    async def test_bool_round_trip(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.c.write(1, True)
        result = await plc.c.read(1)
        assert result == {"C1": True}
        assert provider.get("C1") is True

    @pytest.mark.asyncio
    async def test_bool_false(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.c.write(1, True)
        await plc.c.write(1, False)
        result = await plc.c.read(1)
        assert result == {"C1": False}

    @pytest.mark.asyncio
    async def test_text_round_trip(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.txt.write(1, "A")
        result = await plc.txt.read(1)
        assert result == {"TXT1": "A"}


# ==============================================================================
# Provider -> Driver reads
# ==============================================================================


class TestProviderToDriver:
    @pytest.mark.asyncio
    async def test_provider_set_driver_reads(self, plc_fixture):
        plc, provider = plc_fixture
        provider.set("DF1", 99.5)
        result = await plc.df.read(1)
        assert math.isclose(result["DF1"], 99.5, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_provider_set_bool(self, plc_fixture):
        plc, provider = plc_fixture
        provider.set("C1", True)
        result = await plc.c.read(1)
        assert result == {"C1": True}

    @pytest.mark.asyncio
    async def test_provider_set_ds(self, plc_fixture):
        plc, provider = plc_fixture
        provider.set("DS1", -42)
        result = await plc.ds.read(1)
        assert result == {"DS1": -42}


# ==============================================================================
# Range reads
# ==============================================================================


class TestRangeReads:
    @pytest.mark.asyncio
    async def test_read_df_range(self, plc_fixture):
        plc, provider = plc_fixture
        provider.set("DF1", 1.0)
        provider.set("DF2", 2.0)
        provider.set("DF3", 3.0)
        result = await plc.df.read(1, 3)
        assert len(result) == 3
        assert math.isclose(result["DF1"], 1.0, rel_tol=1e-6)
        assert math.isclose(result["DF2"], 2.0, rel_tol=1e-6)
        assert math.isclose(result["DF3"], 3.0, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_read_ds_range(self, plc_fixture):
        plc, provider = plc_fixture
        for i in range(1, 6):
            provider.set(f"DS{i}", i * 10)
        result = await plc.ds.read(1, 5)
        assert len(result) == 5
        assert result["DS1"] == 10
        assert result["DS5"] == 50


# ==============================================================================
# Range writes
# ==============================================================================


class TestRangeWrites:
    @pytest.mark.asyncio
    async def test_write_df_list(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.df.write(1, [1.0, 2.0, 3.0])
        assert math.isclose(provider.get("DF1"), 1.0, rel_tol=1e-6)
        assert math.isclose(provider.get("DF2"), 2.0, rel_tol=1e-6)
        assert math.isclose(provider.get("DF3"), 3.0, rel_tol=1e-6)

    @pytest.mark.asyncio
    async def test_write_ds_list(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.ds.write(1, [10, 20, 30])
        assert provider.get("DS1") == 10
        assert provider.get("DS2") == 20
        assert provider.get("DS3") == 30


# ==============================================================================
# Writability enforcement
# ==============================================================================


class TestWritability:
    @pytest.mark.asyncio
    async def test_sc_not_writable_through_stack(self, plc_fixture):
        plc, _ = plc_fixture
        with pytest.raises(ValueError, match="not writable"):
            await plc.sc.write(1, True)

    @pytest.mark.asyncio
    async def test_sd_not_writable_through_stack(self, plc_fixture):
        plc, _ = plc_fixture
        with pytest.raises(ValueError, match="not writable"):
            await plc.sd.write(1, 42)

    @pytest.mark.asyncio
    async def test_x_not_writable(self, plc_fixture):
        plc, _ = plc_fixture
        with pytest.raises(ValueError, match="not writable"):
            await plc.x.write(1, True)


# ==============================================================================
# Sparse coils
# ==============================================================================


class TestSparseCoils:
    @pytest.mark.asyncio
    async def test_y_write_read(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.y.write(1, True)
        result = await plc.y.read(1)
        assert result == {"Y001": True}

    @pytest.mark.asyncio
    async def test_x_read_from_provider(self, plc_fixture):
        plc, provider = plc_fixture
        provider.set("X001", True)
        result = await plc.x.read(1)
        assert result == {"X001": True}

    @pytest.mark.asyncio
    async def test_x_expansion_slot(self, plc_fixture):
        plc, provider = plc_fixture
        provider.set("X101", True)
        result = await plc.x.read(101)
        assert result == {"X101": True}
