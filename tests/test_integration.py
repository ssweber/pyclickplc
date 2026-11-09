"""Integration tests: ClickClient <-> ClickServer round-trips.

Tests the full stack: driver -> pymodbus client -> TCP -> pymodbus server
-> _ClickDeviceContext -> MemoryDataProvider.
"""

from __future__ import annotations

import asyncio
import math
import struct

import pytest

from pyclickplc.client import ClickClient
from pyclickplc.modbus import plc_to_modbus
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
    async def test_non_finite_float_writes_arrive_as_registers(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.df.write(1, float("inf"))
        await plc.df.write(2, float("-inf"))
        await plc.df.write(3, float("nan"))
        await plc.df.write(4, struct.unpack("<f", struct.pack("<I", 0xFFA12345))[0])
        assert provider.get("DF1") == math.inf
        assert provider.get("DF2") == -math.inf
        assert math.isnan(provider.get("DF3"))
        assert math.isnan(provider.get("DF4"))
        raw = (await plc._client.read_holding_registers(28672, count=8)).registers
        assert raw == [0x0000, 0x7F80, 0x0000, 0xFF80, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF]

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


# ==============================================================================
# Connection lifecycle
# ==============================================================================


class TestConnectionLifecycle:
    @pytest.mark.asyncio
    async def test_disconnect_all_drops_clickclient_session(self):
        provider = MemoryDataProvider()
        server = ClickServer(provider, host="127.0.0.1", port=TEST_PORT + 1)
        await server.start()
        try:
            async with ClickClient("127.0.0.1", TEST_PORT + 1) as plc:
                await asyncio.sleep(0.05)
                assert len(server.list_clients()) == 1

                closed = server.disconnect_all_clients()
                assert closed == 1

                await asyncio.sleep(0.2)
                assert server.list_clients() == []

                with pytest.raises(ConnectionError, match="Not connected"):
                    await plc.ds.read(1)
        finally:
            await server.stop()


class _FailingReadProvider(MemoryDataProvider):
    def read(self, address: str):
        raise RuntimeError("provider down")


class TestFailedRead:
    @pytest.mark.asyncio
    async def test_failed_server_read_raises_oserror_on_client(self):
        async with ClickServer(_FailingReadProvider(), port=TEST_PORT + 2):
            await asyncio.sleep(0.1)
            async with ClickClient("localhost", TEST_PORT + 2) as plc:
                with pytest.raises(OSError):
                    await plc.df.read(1)
                with pytest.raises(OSError):
                    await plc.c.read(1)


class TestRangeSplitting:
    @pytest.mark.asyncio
    async def test_long_register_reads_split(self, plc_fixture):
        plc, provider = plc_fixture
        provider.set("DS1", 7)
        provider.set("DS200", 9)
        result = await plc.ds.read(1, 200)
        assert len(result) == 200
        assert result["DS1"] == 7
        assert result["DS200"] == 9

    @pytest.mark.asyncio
    async def test_width_two_read_never_splits_a_value(self, plc_fixture):
        plc, provider = plc_fixture
        for i in range(1, 101):
            provider.set(f"DD{i}", 100000 + i)
            provider.set(f"DF{i}", i + 0.5)
        dd = await plc.dd.read(1, 100)
        df = await plc.df.read(1, 100)
        assert [dd[f"DD{i}"] for i in range(1, 101)] == [100000 + i for i in range(1, 101)]
        assert [df[f"DF{i}"] for i in range(1, 101)] == [i + 0.5 for i in range(1, 101)]

    @pytest.mark.asyncio
    async def test_long_txt_read_splits(self, plc_fixture):
        plc, provider = plc_fixture
        provider.set("TXT300", "Z")
        result = await plc.txt.read(1, 300)
        assert len(result) == 300
        assert result["TXT300"] == "Z"

    @pytest.mark.asyncio
    async def test_long_register_write_splits(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.ds.write(1, list(range(1, 201)))
        assert provider.get("DS1") == 1
        assert provider.get("DS124") == 124
        assert provider.get("DS200") == 200

    @pytest.mark.asyncio
    async def test_width_two_write_never_splits_a_value(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.dd.write(1, [100000 + i for i in range(1, 101)])
        assert [provider.get(f"DD{i}") for i in range(1, 101)] == [
            100000 + i for i in range(1, 101)
        ]

    @pytest.mark.asyncio
    async def test_long_coil_read_and_write_split(self, plc_fixture):
        plc, provider = plc_fixture
        await plc.c.write(1, [True] * 2000)
        assert provider.get("C1") is True
        assert provider.get("C2000") is True
        result = await plc.c.read(1, 2000)
        assert len(result) == 2000


C1 = plc_to_modbus("C", 1)[0]


class TestRawRequestLimits:
    @staticmethod
    async def _raw(port: int, pdu: bytes) -> bytes:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        frame = struct.pack(">HHHB", 1, 0, len(pdu) + 1, 1) + pdu
        writer.write(frame)
        await writer.drain()
        data = await asyncio.wait_for(reader.read(512), 2)
        writer.close()
        return data[7:]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "pdu",
        [
            struct.pack(">BHH", 3, 28672, 200),
            struct.pack(">BHH", 3, 28672, 0),
            struct.pack(">BHH", 1, 0, 2001),
        ],
    )
    async def test_out_of_range_read_gets_exception_03(self, pdu):
        provider = MemoryDataProvider()
        async with ClickServer(provider, host="127.0.0.1", port=TEST_PORT + 3):
            await asyncio.sleep(0.1)
            reply = await self._raw(TEST_PORT + 3, pdu)
        assert reply == bytes([pdu[0] | 0x80, 3])

    @pytest.mark.asyncio
    async def test_fc05_value_other_than_00_or_ff00_gets_exception_03(self):
        provider = MemoryDataProvider()
        async with ClickServer(provider, host="127.0.0.1", port=TEST_PORT + 4):
            await asyncio.sleep(0.1)
            bad = await self._raw(TEST_PORT + 4, struct.pack(">BHH", 5, C1, 0x1234))
            good = await self._raw(TEST_PORT + 4, struct.pack(">BHH", 5, C1, 0xFF00))
        assert bad == bytes([0x85, 3])
        assert provider.get("C1") is True
        assert good[0] == 5
