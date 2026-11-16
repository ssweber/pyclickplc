"""Integration tests: ClickClient <-> ClickServer round-trips.

Tests the full stack: driver -> pymodbus client -> TCP -> ClickServer
-> _ClickDeviceContext -> MemoryDataProvider, and the server's framing over raw sockets.
"""

from __future__ import annotations

import asyncio
import errno
import gc
import logging
import math
import os
import socket
import struct
import threading
import time
import warnings
from dataclasses import dataclass
from typing import Any, cast

import pytest

import pyclickplc.server as server_module
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
C2000 = plc_to_modbus("C", 2000)[0]
DS1 = plc_to_modbus("DS", 1)[0]
DS4500 = plc_to_modbus("DS", 4500)[0]


def _write_coils(
    count: int, *, start: int = C1, byte_count: int | None = None, data: bytes | None = None
) -> bytes:
    """An FC15 PDU setting every coil; byte_count and data default to what count needs."""
    if data is None:
        data = b"\xff" * ((count + 7) // 8)
    if byte_count is None:
        byte_count = (count + 7) // 8
    return struct.pack(">BHHB", 15, start, count, byte_count) + data


def _write_registers(
    count: int, *, start: int = DS1, byte_count: int | None = None, data: bytes | None = None
) -> bytes:
    """An FC16 PDU writing 7 to every register; byte_count and data default to what count needs."""
    if data is None:
        data = b"\x00\x07" * count
    if byte_count is None:
        byte_count = 2 * count
    return struct.pack(">BHHB", 16, start, count, byte_count) + data


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
            stored_after_bad = provider.get("C1")
            good = await self._raw(TEST_PORT + 4, struct.pack(">BHH", 5, C1, 0xFF00))
        assert bad == bytes([0x85, 3])
        assert stored_after_bad is False
        assert provider.get("C1") is True
        assert good[0] == 5

    @staticmethod
    async def _exchange(port: int, pdus: list[bytes]) -> list[bytes]:
        """Send each PDU on one connection and return each reply's PDU."""
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        replies = []
        try:
            for tid, pdu in enumerate(pdus, start=1):
                writer.write(struct.pack(">HHHB", tid, 0, len(pdu) + 1, 1) + pdu)
                await writer.drain()
                data = await asyncio.wait_for(reader.read(512), 2)
                assert struct.unpack(">H", data[:2])[0] == tid
                replies.append(data[7:])
        finally:
            writer.close()
        return replies

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "pdu",
        [
            pytest.param(_write_coils(0), id="fc15 count 0"),
            pytest.param(_write_coils(1969), id="fc15 count 1969"),
            pytest.param(_write_coils(2001), id="fc15 count 2001"),
            pytest.param(_write_coils(8, byte_count=2), id="fc15 byte count over count"),
            pytest.param(_write_coils(16, byte_count=1), id="fc15 byte count under count"),
            pytest.param(_write_coils(8, data=b"\xff\xff"), id="fc15 more data than byte count"),
            pytest.param(_write_coils(16, data=b"\xff"), id="fc15 less data than byte count"),
            pytest.param(_write_registers(0), id="fc16 count 0"),
            pytest.param(_write_registers(124), id="fc16 count 124"),
            pytest.param(_write_registers(2, byte_count=6), id="fc16 byte count over count"),
            pytest.param(_write_registers(2, byte_count=2), id="fc16 byte count under count"),
            pytest.param(
                _write_registers(2, data=b"\x00\x07" * 3), id="fc16 more data than byte count"
            ),
            pytest.param(
                _write_registers(2, data=b"\x00\x07"), id="fc16 less data than byte count"
            ),
        ],
    )
    async def test_bad_count_or_byte_count_gets_exception_03_and_stores_nothing(self, pdu):
        provider = MemoryDataProvider()
        async with ClickServer(provider, host="127.0.0.1", port=TEST_PORT + 3):
            await asyncio.sleep(0.1)
            reply = await self._raw(TEST_PORT + 3, pdu)
        assert reply == bytes([pdu[0] | 0x80, 3])
        assert provider._data == {}

    @pytest.mark.asyncio
    async def test_coil_and_register_write_edges_are_stored(self):
        provider = MemoryDataProvider()
        async with ClickServer(provider, host="127.0.0.1", port=TEST_PORT + 3):
            await asyncio.sleep(0.1)
            replies = await self._exchange(
                TEST_PORT + 3,
                [
                    _write_coils(1, start=C2000),
                    _write_coils(1968),
                    _write_registers(1, start=DS4500),
                    _write_registers(123),
                ],
            )
        assert replies == [
            struct.pack(">BHH", 15, C2000, 1),
            struct.pack(">BHH", 15, C1, 1968),
            struct.pack(">BHH", 16, DS4500, 1),
            struct.pack(">BHH", 16, DS1, 123),
        ]
        assert provider.get("C1968") is True
        assert provider.get("C1969") is False
        assert provider.get("C2000") is True
        assert provider.get("DS123") == 7
        assert provider.get("DS124") == 0
        assert provider.get("DS4500") == 7

    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", [1, 2, 3, 4, 5, 6, 15, 16])
    async def test_request_too_short_gets_exception_03_and_the_connection_still_answers(self, code):
        provider = MemoryDataProvider()
        async with ClickServer(provider, host="127.0.0.1", port=TEST_PORT + 3):
            await asyncio.sleep(0.1)
            short, read = await self._exchange(
                TEST_PORT + 3, [struct.pack(">BH", code, 0), struct.pack(">BHH", 3, DS1, 1)]
            )
        assert short == bytes([code | 0x80, 3])
        assert read == bytes([3, 2, 0, 0])
        assert provider._data == {}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "pdu",
        [
            pytest.param(struct.pack(">BBBHHH", 20, 7, 6, 1, 0, 1), id="fc20 odd record length"),
            pytest.param(struct.pack(">BBBHHH", 20, 7, 6, 1, 0, 2), id="fc20"),
            pytest.param(struct.pack(">BBBHHHH", 21, 9, 6, 1, 0, 1, 5), id="fc21"),
            pytest.param(struct.pack(">BHHH", 22, DS1, 0x0F, 0), id="fc22"),
            pytest.param(struct.pack(">BHHHHBH", 23, DS1, 1, DS1, 1, 2, 5), id="fc23"),
            pytest.param(struct.pack(">BHHHHB", 23, DS1, 1, DS1, 0, 0), id="fc23 write count 0"),
            pytest.param(struct.pack(">B", 7), id="fc7"),
            pytest.param(struct.pack(">BHH", 8, 0, 0x1234), id="fc8 echo"),
            pytest.param(struct.pack(">BHH", 8, 10, 0), id="fc8 clear counters"),
            pytest.param(struct.pack(">BH", 8, 10), id="fc8 short"),
            pytest.param(struct.pack(">B", 11), id="fc11"),
            pytest.param(struct.pack(">B", 12), id="fc12"),
            pytest.param(struct.pack(">B", 17), id="fc17"),
            pytest.param(struct.pack(">BH", 24, 0), id="fc24"),
            pytest.param(struct.pack(">B", 24), id="fc24 short"),
            pytest.param(struct.pack(">BBBB", 43, 14, 1, 0), id="fc43 device id"),
            pytest.param(struct.pack(">BB", 43, 14), id="fc43 short"),
            pytest.param(struct.pack(">BHH", 9, 0, 0), id="fc9 unknown"),
            pytest.param(struct.pack(">BHH", 65, 0, 0), id="fc65 unknown"),
        ],
    )
    async def test_refused_function_code_gets_exception_01_and_the_connection_still_answers(
        self, pdu
    ):
        provider = MemoryDataProvider()
        async with ClickServer(provider, host="127.0.0.1", port=TEST_PORT + 3):
            await asyncio.sleep(0.1)
            refused, read = await self._exchange(
                TEST_PORT + 3, [pdu, struct.pack(">BHH", 3, DS1, 1)]
            )
        assert refused == bytes([pdu[0] | 0x80, 1])
        assert read == bytes([3, 2, 0, 0])
        assert provider._data == {}


class TestRawAnswers:
    async def test_read_past_ds_answers_exception_02(self, plc_fixture):
        plc, _provider = plc_fixture
        response = await plc._client.read_holding_registers(4499, count=2)
        assert response.isError()
        assert response.exception_code == 2

    async def test_unnamed_yd_word_survives_a_server_restart(self):
        provider = MemoryDataProvider()
        server = ClickServer(provider, port=TEST_PORT)
        yd_base, _ = plc_to_modbus("YD", 0)
        for step in ("write", "read"):
            async with server:
                await asyncio.sleep(0.1)
                async with ClickClient("localhost", TEST_PORT) as plc:
                    if step == "write":
                        response = await plc._client.write_register(yd_base + 3, 0x8000)
                        assert not response.isError()
                    else:
                        response = await plc._client.read_holding_registers(yd_base + 2, count=2)
                        assert response.registers == [0, 0x8000]
        assert provider.get("YD1") == 0

    async def test_fc23_answers_exception_01_and_stores_nothing(self, plc_fixture):
        plc, provider = plc_fixture
        response = await plc._client.readwrite_registers(
            read_address=4499, read_count=2, write_address=0, values=[5]
        )
        assert response.isError()
        assert response.exception_code == 1
        assert provider.get("DS1") == 0

    async def test_fc22_answers_exception_01_and_stores_nothing(self, plc_fixture):
        plc, provider = plc_fixture
        provider.set("DS1", 0x00FF)
        response = await plc._client.mask_write_register(address=0, and_mask=0x0F, or_mask=0)
        assert response.isError()
        assert response.exception_code == 1
        assert provider.get("DS1") == 0x00FF


class TestTwoServers:
    async def test_each_server_answers_from_its_own_provider(self):
        first, second = MemoryDataProvider(), MemoryDataProvider()
        first.set("DS1", 1)
        second.set("DS1", 2)
        async with (
            ClickServer(first, port=TEST_PORT + 5),
            ClickServer(second, port=TEST_PORT + 6),
        ):
            await asyncio.sleep(0.1)
            async with (
                ClickClient("localhost", TEST_PORT + 5) as one,
                ClickClient("localhost", TEST_PORT + 6) as two,
            ):
                assert await one.ds.read(1) == {"DS1": 1}
                assert await two.ds.read(1) == {"DS1": 2}


class TestServerLifecycle:
    async def test_start_serve_and_stop_log_and_warn_nothing(self, caplog):
        caplog.set_level(logging.DEBUG)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            async with ClickServer(MemoryDataProvider(), host="127.0.0.1", port=TEST_PORT + 7):
                await asyncio.sleep(0.05)
                async with ClickClient("127.0.0.1", TEST_PORT + 7) as plc:
                    assert await plc.ds.read(1) == {"DS1": 0}
        warnings_logged = [
            record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING
        ]
        assert warnings_logged == []
        assert [str(warning.message) for warning in caught] == []

    async def test_bound_port_gives_the_port_picked_for_port_0(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        assert server.bound_port is None
        async with server:
            port = server.bound_port
            assert port is not None and port != 0
            assert server.port == 0
            async with ClickClient("127.0.0.1", port) as plc:
                assert await plc.ds.read(1) == {"DS1": 0}
        assert server.bound_port is None

    async def test_bound_socket_is_reachable_through_the_server(self):
        # pyrung reads the port bound for port 0 through ClickServer._server.transport.
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        async with server:
            assert server._server is not None
            transport = server._server.transport
            assert isinstance(transport, asyncio.Server)
            port = transport.sockets[0].getsockname()[1]
            assert port == server.bound_port
            async with ClickClient("127.0.0.1", port) as plc:
                assert await plc.ds.read(1) == {"DS1": 0}


# ==============================================================================
# Framing (Modbus TCP over raw sockets)
# ==============================================================================

READ_DS1 = struct.pack(">BHH", 3, DS1, 1)
DS1_IS_0 = bytes([3, 2, 0, 0])


def _frame(
    tid: int, pdu: bytes, *, unit: int = 1, protocol: int = 0, length: int | None = None
) -> bytes:
    """A Modbus TCP frame; the length field defaults to the one the PDU needs."""
    if length is None:
        length = len(pdu) + 1
    return struct.pack(">HHHB", tid, protocol, length, unit) + pdu


async def _replies(reader: asyncio.StreamReader, count: int) -> list[tuple[int, int, bytes]]:
    """Read ``count`` replies as (transaction id, unit id, PDU), checking each header."""
    replies = []
    for _ in range(count):
        header = await asyncio.wait_for(reader.readexactly(7), 2)
        tid, protocol, length, unit = struct.unpack(">HHHB", header)
        assert protocol == 0
        pdu = await asyncio.wait_for(reader.readexactly(length - 1), 2)
        replies.append((tid, unit, pdu))
    return replies


async def _nothing_more(reader: asyncio.StreamReader) -> bool:
    """True when no byte arrives within a short wait."""
    try:
        data = await asyncio.wait_for(reader.read(1), 0.2)
    except TimeoutError:
        return True
    return data == b""


async def _closed(reader: asyncio.StreamReader) -> bool:
    """True when the server closes the connection without sending anything."""
    return await asyncio.wait_for(reader.read(), 2) == b""


async def _until(condition, timeout: float = 2.0) -> None:
    """Wait for a condition the server reaches on its own."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        assert asyncio.get_running_loop().time() < deadline
        await asyncio.sleep(0.01)


FRAMING_PORT = TEST_PORT + 8
# asyncio pauses a protocol once its transport holds more than 64 KiB to send, and reads at
# most 256 KiB at a time.
ANSWERS_HELD = 64 * 1024
REQUESTS_HELD = 256 * 1024


@dataclass(frozen=True)
class _SilentClient:
    """A client that sends requests and reads nothing until a test reads.

    A bare socket, because asyncio's StreamReader would go on reading into its own buffer.
    """

    sock: socket.socket
    sending: asyncio.Task[None]

    async def read(self, size: int) -> bytes:
        """Read size bytes, or fewer if the server closes first."""
        data = bytearray()
        while len(data) < size:
            chunk = await asyncio.get_running_loop().sock_recv(self.sock, size - len(data))
            if not chunk:
                break
            data += chunk
        return bytes(data)

    async def nothing_more(self) -> bool:
        """True when no byte arrives within a short wait."""
        receiving = asyncio.get_running_loop().sock_recv(self.sock, 1)
        try:
            data = await asyncio.wait_for(receiving, 0.2)
        except TimeoutError:
            return True
        return data == b""

    async def close(self) -> None:
        self.sending.cancel()
        await asyncio.gather(self.sending, return_exceptions=True)
        self.sock.close()


async def _client_that_does_not_read(
    server: ClickServer, count: int = 60_000
) -> tuple[server_module._Connection, _SilentClient]:
    """A client that sends count requests and reads no answer, once the server holds its
    answers.

    Before any request, the client's receive buffer is set to 4 KiB and the server side's send
    buffer to 64 KiB, as Windows has it, so the unread answers fill them well before the last.
    Linux otherwise grows loopback buffers to megabytes, enough to take every answer without
    the server holding any.
    """
    port = server.bound_port
    assert port is not None
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    sock.setblocking(False)
    await loop.sock_connect(sock, ("127.0.0.1", port))
    await _until(lambda: len(server.list_clients()) == 1)
    assert server._server is not None
    (connection,) = server._server.connections.values()
    assert connection.transport is not None
    server_side = connection.transport.get_extra_info("socket")
    server_side.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 64 * 1024)
    requests = b"".join(_frame(tid, READ_DS1) for tid in range(count))
    client = _SilentClient(sock, asyncio.create_task(loop.sock_sendall(sock, requests)))
    return await _held_connection(server), client


async def _held_connection(server: ClickServer):
    """The server's only connection, once it has paused for a client that does not read."""
    await _until(lambda: len(server.list_clients()) == 1)
    assert server._server is not None
    (connection,) = server._server.connections.values()
    await _until(lambda: connection._paused, timeout=10)
    # Still paused a little later: the client's answers stay unsent.
    await asyncio.sleep(0.2)
    await _until(lambda: connection._paused, timeout=10)
    return connection


@pytest.fixture
async def framing_server():
    provider = MemoryDataProvider()
    server = ClickServer(provider, host="127.0.0.1", port=FRAMING_PORT)
    async with server:
        yield server, provider


@pytest.fixture
async def connection(framing_server):
    reader, writer = await asyncio.open_connection("127.0.0.1", FRAMING_PORT)
    yield reader, writer
    writer.close()


class TestFraming:
    async def test_every_unit_id_is_answered_and_echoed(self, connection):
        reader, writer = connection
        for unit in range(256):
            writer.write(_frame(unit, READ_DS1, unit=unit))
            assert await _replies(reader, 1) == [(unit, unit, DS1_IS_0)]

    @pytest.mark.parametrize("tid", [0, 1, 0x1234, 0xFFFF])
    async def test_transaction_id_is_echoed(self, connection, tid):
        reader, writer = connection
        writer.write(_frame(tid, READ_DS1))
        assert await _replies(reader, 1) == [(tid, 1, DS1_IS_0)]

    @pytest.mark.parametrize("protocol", [1, 0xFFFF])
    async def test_protocol_id_other_than_0_is_dropped_unanswered(self, connection, protocol):
        reader, writer = connection
        writer.write(_frame(1, READ_DS1, protocol=protocol))
        assert await _nothing_more(reader)
        # The frame after it is answered, whether it comes in the same read or later.
        writer.write(_frame(2, READ_DS1, protocol=protocol) + _frame(3, READ_DS1))
        writer.write(_frame(4, READ_DS1))
        assert await _replies(reader, 2) == [(3, 1, DS1_IS_0), (4, 1, DS1_IS_0)]
        assert await _nothing_more(reader)

    async def test_frame_split_across_reads_is_reassembled(self, connection):
        reader, writer = connection
        for byte in _frame(1, READ_DS1):
            writer.write(bytes([byte]))
            await writer.drain()
            await asyncio.sleep(0.01)
        assert await _replies(reader, 1) == [(1, 1, DS1_IS_0)]

    async def test_several_frames_in_one_read_are_each_answered_in_order(self, connection):
        reader, writer = connection
        frames = b"".join(_frame(tid, READ_DS1) for tid in range(1, 41))
        # The last frame is cut, then finished in the next write.
        writer.write(frames + _frame(41, READ_DS1)[:9])
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.write(_frame(41, READ_DS1)[9:])
        assert await _replies(reader, 41) == [(tid, 1, DS1_IS_0) for tid in range(1, 42)]

    async def test_pipelined_requests_are_answered_in_order(self, framing_server, connection):
        _server, provider = framing_server
        reader, writer = connection
        for value in range(1, 11):
            writer.write(_frame(2 * value, struct.pack(">BHH", 6, DS1, value)))
            writer.write(_frame(2 * value + 1, READ_DS1))
        replies = await _replies(reader, 20)
        assert [tid for tid, _unit, _pdu in replies] == list(range(2, 22))
        assert [pdu for _tid, _unit, pdu in replies[1::2]] == [
            bytes([3, 2, 0, value]) for value in range(1, 11)
        ]
        assert provider.get("DS1") == 10

    @pytest.mark.parametrize(
        "frame",
        [
            pytest.param(_frame(1, READ_DS1, length=0), id="length 0"),
            pytest.param(_frame(1, b"", length=1), id="length 1"),
            pytest.param(_frame(1, READ_DS1, length=1), id="length 1 with a PDU"),
            pytest.param(_frame(1, b"\x03" + bytes(261)), id="length 263"),
            pytest.param(_frame(1, READ_DS1, length=1000), id="length 1000, frame cut"),
            pytest.param(_frame(1, READ_DS1, length=0xFFFF, protocol=1), id="protocol 1"),
        ],
    )
    async def test_length_outside_2_to_262_closes_the_connection(self, frame):
        provider = MemoryDataProvider()
        async with ClickServer(provider, host="127.0.0.1", port=FRAMING_PORT) as server:
            reader, writer = await asyncio.open_connection("127.0.0.1", FRAMING_PORT)
            writer.write(frame + _frame(2, READ_DS1))
            assert await _closed(reader)
            writer.close()
            await _until(lambda: server.list_clients() == [])
            # The server answers the next client.
            reader, writer = await asyncio.open_connection("127.0.0.1", FRAMING_PORT)
            writer.write(_frame(3, READ_DS1))
            assert await _replies(reader, 1) == [(3, 1, DS1_IS_0)]
            writer.close()

    @pytest.mark.parametrize(
        ("pdu", "reply"),
        [
            pytest.param(b"\x03", bytes([0x83, 3]), id="length 2"),
            pytest.param(b"\x03" + bytes(260), bytes([0x83, 3]), id="length 262"),
            pytest.param(b"\x07", bytes([0x87, 1]), id="length 2, fc7"),
            # The largest well-formed writes: the byte count is one byte, so 255 at most.
            pytest.param(
                struct.pack(">BHHB", 16, DS1, 127, 254) + bytes(254),
                bytes([0x90, 3]),
                id="fc16 count 127, length 261",
            ),
            pytest.param(
                struct.pack(">BHHB", 15, C1, 2040, 255) + bytes(255),
                bytes([0x8F, 3]),
                id="fc15 count 2040, length 262",
            ),
        ],
    )
    async def test_lengths_2_to_262_are_answered(self, connection, pdu, reply):
        reader, writer = connection
        writer.write(_frame(1, pdu) + _frame(2, READ_DS1))
        assert await _replies(reader, 2) == [(1, 1, reply), (2, 1, DS1_IS_0)]

    async def test_client_closing_mid_frame_leaves_nothing_behind(self, framing_server):
        server, provider = framing_server
        reader, writer = await asyncio.open_connection("127.0.0.1", FRAMING_PORT)
        writer.write(_frame(1, struct.pack(">BHH", 6, DS1, 5))[:10])
        await writer.drain()
        await _until(lambda: len(server.list_clients()) == 1)
        writer.close()
        await _until(lambda: server.list_clients() == [])
        assert server._server is not None
        assert server._server.connections == {}
        assert provider._data == {}
        reader, writer = await asyncio.open_connection("127.0.0.1", FRAMING_PORT)
        writer.write(_frame(2, READ_DS1))
        assert await _replies(reader, 1) == [(2, 1, DS1_IS_0)]
        writer.close()

    async def test_provider_failure_gets_04_and_the_connection_carries_on(self):
        class _FailsOnDs2(MemoryDataProvider):
            def read(self, address: str):
                if address == "DS2":
                    raise RuntimeError("provider down")
                return super().read(address)

        async with ClickServer(_FailsOnDs2(), host="127.0.0.1", port=FRAMING_PORT):
            reader, writer = await asyncio.open_connection("127.0.0.1", FRAMING_PORT)
            writer.write(_frame(1, struct.pack(">BHH", 3, DS1 + 1, 1)) + _frame(2, READ_DS1))
            assert await _replies(reader, 2) == [(1, 1, bytes([0x83, 4])), (2, 1, DS1_IS_0)]
            writer.close()

    async def test_every_function_code_is_answered_and_the_connection_still_answers(
        self, connection
    ):
        reader, writer = connection
        for code in range(256):
            for data in (b"", bytes(4), b"\xff" * 12):
                writer.write(_frame(1, bytes([code]) + data) + _frame(2, READ_DS1))
                (_tid, _unit, reply), read = await _replies(reader, 2)
                assert reply[0] in (code, code | 0x80)
                if code not in (1, 2, 3, 4, 5, 6, 15, 16):
                    assert reply == bytes([code | 0x80, 1])
                assert read == (2, 1, DS1_IS_0)

    async def test_a_client_that_does_not_read_gets_every_answer_in_order_once_it_reads(
        self, framing_server
    ):
        server, _provider = framing_server
        count = 60_000
        connection, client = await _client_that_does_not_read(server, count)
        # The server stops reading and answering, holding at most one read of requests and
        # the answers its transport takes before it asks the server to pause.
        assert connection.transport is not None
        assert connection.transport.get_write_buffer_size() <= ANSWERS_HELD + 11
        assert len(connection._buffer) <= REQUESTS_HELD
        data = await asyncio.wait_for(client.read(11 * count), 30)
        assert data == b"".join(
            struct.pack(">HHHB", tid, 0, 5, 1) + DS1_IS_0 for tid in range(count)
        )
        assert await client.nothing_more()
        await client.close()

    async def test_disconnecting_a_client_that_does_not_read_drops_it(self, framing_server):
        server, _provider = framing_server
        connection, client = await _client_that_does_not_read(server)
        assert server.disconnect_client(connection.client_id) is True
        assert server.list_clients() == []
        await _until(lambda: connection.lost.done(), timeout=3)
        assert server._server is not None
        assert server._server.connections == {}
        await client.close()


# ==============================================================================
# Client list, start and stop
# ==============================================================================


class TestServerControls:
    async def test_list_and_disconnect_clients(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        async with server:
            port = server.bound_port
            assert port is not None
            first = await asyncio.open_connection("127.0.0.1", port)
            second = await asyncio.open_connection("127.0.0.1", port)
            await _until(lambda: len(server.list_clients()) == 2)
            clients = server.list_clients()
            local_ports = {
                writer.get_extra_info("sockname")[1] for _reader, writer in (first, second)
            }
            assert {client.peer for client in clients} == {
                f"127.0.0.1:{local}" for local in local_ports
            }
            assert len({client.client_id for client in clients}) == 2
            assert all(isinstance(client.client_id, str) for client in clients)
            first_id = next(
                client.client_id
                for client in clients
                if client.peer == f"127.0.0.1:{first[1].get_extra_info('sockname')[1]}"
            )

            assert server.disconnect_client("missing") is False
            assert server.disconnect_client(first_id) is True
            assert await _closed(first[0])
            assert first_id not in {client.client_id for client in server.list_clients()}
            assert len(server.list_clients()) == 1
            assert server.disconnect_client(first_id) is False

            assert server.disconnect_all_clients() == 1
            assert await _closed(second[0])
            assert server.list_clients() == []
            assert server.disconnect_all_clients() == 0
            for _reader, writer in (first, second):
                writer.close()

    async def test_stop_closes_every_connection(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        await server.start()
        assert server.is_running() is True
        port = server.bound_port
        assert port is not None
        connections = [await asyncio.open_connection("127.0.0.1", port) for _ in range(3)]
        await _until(lambda: len(server.list_clients()) == 3)
        await server.stop()
        for reader, writer in connections:
            assert await _closed(reader)
            writer.close()
        assert server.is_running() is False
        assert server.list_clients() == []
        assert server.bound_port is None
        with pytest.raises(OSError):
            await asyncio.open_connection("127.0.0.1", port)
        await server.stop()  # A second stop does nothing.

    async def test_start_twice_raises_runtime_error(self):
        async with ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0) as server:
            with pytest.raises(RuntimeError, match="already running"):
                await server.start()

    async def test_concurrent_starts_give_one_listener(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        first, second = await asyncio.gather(server.start(), server.start(), return_exceptions=True)
        try:
            assert first is None
            assert isinstance(second, RuntimeError)
            assert "already running" in str(second)
            assert server.is_running() is True
        finally:
            await server.stop()

    async def test_client_ids_do_not_repeat_across_restarts(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        client_ids = []
        for _run in range(2):
            async with server:
                port = server.bound_port
                assert port is not None
                _reader, writer = await asyncio.open_connection("127.0.0.1", port)
                await _until(lambda: len(server.list_clients()) == 1)
                client_ids += [client.client_id for client in server.list_clients()]
                writer.close()
        assert len(set(client_ids)) == 2

    async def test_start_on_a_port_in_use_raises_runtime_error(self):
        async with ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0) as first:
            port = first.bound_port
            assert port is not None
            second = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=port)
            with pytest.raises(RuntimeError, match="Could not listen") as caught:
                await second.start()
            assert isinstance(caught.value.__cause__, OSError)
            assert second.is_running() is False

    async def test_serve_forever_returns_after_stop(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        task = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        port = server.bound_port
        assert port is not None
        async with ClickClient("127.0.0.1", port) as plc:
            assert await plc.ds.read(1) == {"DS1": 0}
        await server.stop()
        assert await asyncio.wait_for(task, 2) is None

    async def test_cancelling_serve_forever_stops_the_server(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        task = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        port = server.bound_port
        assert port is not None
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert server.is_running() is False
        assert await _closed(reader)
        writer.close()

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
    async def test_stop_during_a_start_leaves_the_server_stopped(self, host):
        server = ClickServer(MemoryDataProvider(), host=host, port=0)
        starting = asyncio.create_task(server.start())
        await asyncio.sleep(0)
        assert server._run is not None and server._server is None  # start() is still opening
        await server.stop()
        await starting
        assert server.is_running() is False
        assert server.bound_port is None
        assert server._server is None

    async def test_a_dead_listener_is_replaced_by_start(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        async with server:
            old = _listener_stopped_listening(server)
            old_port = old.port
            assert old_port is not None
            reader, writer = await asyncio.open_connection("127.0.0.1", old_port)
            await _until(lambda: len(old.connections) == 1)
            (old_id,) = old.connections
            assert server.is_running() is False
            # Two starts at once: one replaces the listener, the other finds it running.
            results = await asyncio.gather(server.start(), server.start(), return_exceptions=True)
            assert results[0] is None
            assert isinstance(results[1], RuntimeError)
            assert "already running" in str(results[1])
            # The old listener and its clients are closed.
            assert old.closed
            assert old.transport.is_serving() is False
            assert old.connections == {}
            assert await _closed(reader)
            writer.close()
            # The server listens again, and client ids go on counting.
            assert server._server is not old
            assert server.is_running() is True
            port = server.bound_port
            assert port is not None
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await _until(lambda: len(server.list_clients()) == 1)
            assert int(server.list_clients()[0].client_id) > int(old_id)
            writer.close()

    async def test_serve_forever_keeps_serving_after_a_replace_and_returns_after_stop(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        task = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        _listener_stopped_listening(server)
        await server.start()
        await asyncio.sleep(0.1)
        assert task.done() is False
        assert server.is_running() is True
        port = server.bound_port
        assert port is not None
        assert await _answers("127.0.0.1", port) is True
        await server.stop()
        assert await asyncio.wait_for(task, 2) is None
        assert server.is_running() is False

    async def test_cancelling_serve_forever_after_a_replace_stops_the_new_listener(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        task = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        _listener_stopped_listening(server)
        await server.start()
        new = server._server
        assert new is not None
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert server.is_running() is False
        assert new.closed
        assert new.transport.is_serving() is False

    # asyncio's Proactor loop leaks the socket of an accept that failed; it is collected below.
    @pytest.mark.filterwarnings("ignore::ResourceWarning")
    def test_is_running_says_whether_the_server_still_answers_after_resets(self):
        # On Windows, asyncio's Proactor loop closes the listening socket when a client resets
        # before its connection is accepted; is_running() then gives False, and start()
        # listens again.
        async def resets_then_start() -> None:
            server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
            async with server:
                port = server.bound_port
                assert port is not None
                for _ in range(30):
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.connect(("127.0.0.1", port))
                        linger = struct.pack("ii", 1, 0)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
                await asyncio.sleep(0.5)
                assert server.is_running() is await _answers("127.0.0.1", port)
                if not server.is_running():
                    await server.start()
                assert server.is_running() is True
                port = server.bound_port
                assert port is not None
                assert await _answers("127.0.0.1", port) is True

        # A loop of its own, closed before the collection, so nothing it leaks outlives the test.
        asyncio.run(resets_then_start())
        gc.collect()

    async def test_start_listens_again_after_a_listening_socket_dies(self):
        _skip_unless_proactor()
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        async with server:
            port = server.bound_port
            assert port is not None
            first_reader, first_writer = await asyncio.open_connection("127.0.0.1", port)
            await _until(lambda: len(server.list_clients()) == 1)
            (first_id,) = [client.client_id for client in server.list_clients()]
            _kill_listening_socket(server, 0)
            assert server.is_running() is False
            await server.start()
            assert server.is_running() is True
            port = server.bound_port
            assert port is not None
            assert await _answers("127.0.0.1", port) is True
            # The clients of the dead listener are closed, and ids go on counting.
            assert await _closed(first_reader)
            first_writer.close()
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await _until(lambda: len(server.list_clients()) == 1)
            assert int(server.list_clients()[0].client_id) > int(first_id)
            writer.close()
            with pytest.raises(RuntimeError, match="already running"):
                await server.start()

    async def test_start_listens_again_when_one_of_two_listening_sockets_dies(self, monkeypatch):
        _skip_unless_proactor()
        _resolve_to_two_addresses(monkeypatch)
        server = ClickServer(MemoryDataProvider(), port=0)
        async with server:
            assert server._server is not None
            if len(server._server.transport.sockets) < 2:
                pytest.skip("this host has no IPv6 loopback to listen on")
            _kill_listening_socket(server, 0)
            assert server.is_running() is False
            await server.start()
            assert server.is_running() is True
            port = server.bound_port
            assert port is not None
            assert len(server._server.transport.sockets) == 2
            assert await _answers("127.0.0.1", port) is True
            assert await _answers("::1", port) is True


# The event loops asyncio has here: Selector everywhere, and Proactor on Windows.
_LOOP_FACTORIES: list[Any] = [asyncio.SelectorEventLoop]
_LOOP_FACTORY_IDS = ["selector"]
if hasattr(asyncio, "ProactorEventLoop"):
    _LOOP_FACTORIES.append(asyncio.ProactorEventLoop)
    _LOOP_FACTORY_IDS.append("proactor")


class TestLifecycle:
    """start(), stop() and serve_forever() cancelled, or run together, at any await."""

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
    async def test_a_start_cancelled_at_any_step_leaves_nothing_listening(self, monkeypatch, host):
        servers = _record_servers(monkeypatch)
        _resolve_without_a_thread(monkeypatch)
        for steps in range(12):
            port = _free_tcp_port()
            server = ClickServer(MemoryDataProvider(), host=host, port=port)
            starting = asyncio.create_task(server.start())
            for _ in range(steps):
                await asyncio.sleep(0)
            starting.cancel()
            try:
                await starting
            except asyncio.CancelledError:
                assert server.is_running() is False
                assert server._server is None
                assert _open(servers) == []
                assert _bindable(port)
            else:
                assert server.is_running() is True
            await server.stop()
            # The port is free again: the server starts on it.
            await server.start()
            assert server.is_running() is True
            await server.stop()
            assert _open(servers) == []

    async def test_a_start_on_port_0_cancelled_at_any_step_leaves_no_socket_open(self, monkeypatch):
        servers = _record_servers(monkeypatch)
        _resolve_without_a_thread(monkeypatch)
        server = ClickServer(MemoryDataProvider(), port=0)
        for steps in range(12):
            starting = asyncio.create_task(server.start())
            for _ in range(steps):
                await asyncio.sleep(0)
            starting.cancel()
            try:
                await starting
            except asyncio.CancelledError:
                assert server.is_running() is False
                assert server._server is None
                assert _open(servers) == []
            else:
                assert server._server is not None
                assert _open(servers) == [server._server.transport]
            await server.stop()
            assert _open(servers) == []

    async def test_a_replace_cancelled_at_any_step_closes_the_old_clients(self, monkeypatch):
        servers = _record_servers(monkeypatch)
        _resolve_without_a_thread(monkeypatch)
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        # From 1: a start() cancelled before its first step leaves the old listener as it was.
        for steps in range(1, 12):
            await server.start()
            old = _listener_stopped_listening(server)
            reader, writer = await _client_of(old)
            starting = asyncio.create_task(server.start())
            for _ in range(steps):
                await asyncio.sleep(0)
            starting.cancel()
            try:
                await starting
            except asyncio.CancelledError:
                assert server.is_running() is False
                assert server._server is None
                assert _open(servers) == []
            else:
                assert server.is_running() is True
                assert server._server is not None
                assert _open(servers) == [server._server.transport]
            assert old.transport.is_serving() is False
            assert await _closed(reader)
            writer.close()
            await server.stop()
            assert _open(servers) == []

    async def test_concurrent_starts_leave_exactly_one_server_open(self, monkeypatch):
        servers = _record_servers(monkeypatch)
        server = ClickServer(MemoryDataProvider(), port=0)
        results = await asyncio.gather(*(server.start() for _ in range(5)), return_exceptions=True)
        try:
            assert results.count(None) == 1
            errors = [result for result in results if result is not None]
            assert all(isinstance(error, RuntimeError) for error in errors)
            assert all("already running" in str(error) for error in errors)
            assert server._server is not None
            assert _open(servers) == [server._server.transport]
        finally:
            await server.stop()
        assert _open(servers) == []

    async def test_serve_forever_returns_after_a_cancelled_stop(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        serving = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        connection, client = await _client_that_does_not_read(server)
        stopping = asyncio.create_task(server.stop())
        await asyncio.sleep(0)
        stopping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stopping
        assert server.is_running() is False
        assert await asyncio.wait_for(serving, 3) is None
        await _until(lambda: connection.lost.done(), timeout=3)
        await client.close()

    async def test_a_cancelled_stop_still_drops_a_client_that_does_not_read(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        await server.start()
        port = server.bound_port
        assert port is not None
        connection, client = await _client_that_does_not_read(server)
        stopping = asyncio.create_task(server.stop())
        await asyncio.sleep(0)
        stopping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stopping
        assert server.is_running() is False
        assert server._server is None
        assert _bindable(port)
        # Dropped after 1 s, though nothing waits for it any more.
        assert connection.lost.done() is False
        await _until(lambda: connection.lost.done(), timeout=3)
        await client.close()

    async def test_serve_forever_returns_after_stop_then_start(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        serving = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        await server.stop()
        await server.start()
        try:
            assert await asyncio.wait_for(serving, 2) is None
            assert server.is_running() is True
        finally:
            await server.stop()

    async def test_serve_forever_raises_when_a_replace_cannot_listen(self, monkeypatch):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        serving = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        _listener_stopped_listening(server)

        async def cannot_listen(protocol_factory):
            raise OSError(errno.EADDRINUSE, "address in use")

        monkeypatch.setattr(server, "_listen", cannot_listen)
        with pytest.raises(RuntimeError, match="Could not listen"):
            await server.start()
        with pytest.raises(RuntimeError, match="could not listen again"):
            await asyncio.wait_for(serving, 2)
        assert server.is_running() is False
        assert server._server is None

    async def test_serve_forever_raises_when_a_replace_is_cancelled(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        serving = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        old = _listener_stopped_listening(server)
        reader, writer = await _client_of(old)
        starting = asyncio.create_task(server.start())
        await asyncio.sleep(0)  # start() is closing the old listener's clients
        starting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await starting
        with pytest.raises(RuntimeError, match="could not listen again"):
            await asyncio.wait_for(serving, 3)
        assert server.is_running() is False
        assert server._server is None
        assert await _closed(reader)
        writer.close()

    async def test_cancelling_serve_forever_during_a_replace_stops_the_new_listener(
        self, monkeypatch
    ):
        servers = _record_servers(monkeypatch)
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        serving = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        old = _listener_stopped_listening(server)
        reader, writer = await _client_of(old)
        starting = asyncio.create_task(server.start())
        await asyncio.sleep(0)  # start() is closing the old listener's clients
        serving.cancel()
        with pytest.raises(asyncio.CancelledError):
            await serving
        await starting
        assert server.is_running() is False
        assert server._server is None
        assert _open(servers) == []
        assert await _closed(reader)
        writer.close()

    async def test_cancelling_serve_forever_leaves_a_later_run_alone(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        serving = asyncio.create_task(server.serve_forever())
        await _until(server.is_running)
        await server.stop()
        await server.start()
        serving.cancel()
        await asyncio.gather(serving, return_exceptions=True)
        try:
            assert server.is_running() is True
            port = server.bound_port
            assert port is not None
            assert await _answers("127.0.0.1", port) is True
        finally:
            await server.stop()

    async def test_bound_port_is_none_once_the_listener_stops_listening(self):
        async with ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0) as server:
            assert server.bound_port is not None
            _listener_stopped_listening(server)
            assert server.is_running() is False
            assert server.bound_port is None
            await server.start()
            assert server.bound_port is not None

    @pytest.mark.parametrize("waiter", ["start", "serve_forever"])
    async def test_a_stop_also_stops_a_start_waiting_on_another(self, waiter):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        opening = asyncio.create_task(server.start())
        await asyncio.sleep(0)  # The first start() is opening the listener.
        waiting = asyncio.create_task(getattr(server, waiter)())
        await asyncio.sleep(0)  # The second waits to see how that goes.
        await server.stop()
        await opening
        try:
            assert await asyncio.wait_for(waiting, 2) is None
            await asyncio.sleep(0.1)
            assert server.is_running() is False
            assert server._server is None
        finally:
            await server.stop()

    @pytest.mark.parametrize("waiter", ["start", "serve_forever"])
    async def test_a_stop_during_a_replace_also_stops_a_start_waiting_on_it(self, waiter):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        await server.start()
        old = _listener_stopped_listening(server)
        reader, writer = await _client_of(old)
        replacing = asyncio.create_task(server.start())
        await asyncio.sleep(0)  # The replace is closing the old listener's clients.
        waiting = asyncio.create_task(getattr(server, waiter)())
        await asyncio.sleep(0)  # The waiter waits to see how the replace goes.
        await server.stop()
        await replacing
        try:
            assert await asyncio.wait_for(waiting, 2) is None
            await asyncio.sleep(0.1)
            assert server.is_running() is False
            assert server._server is None
            assert await _closed(reader)
        finally:
            writer.close()
            await server.stop()

    async def test_starts_and_a_stop_together_leave_the_server_stopped(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        try:
            await asyncio.gather(server.start(), server.start(), server.stop())
            await asyncio.sleep(0.1)
            assert server.is_running() is False
        finally:
            await server.stop()

    def test_a_server_left_running_when_its_event_loop_closed_starts_on_the_next(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)

        async def start_only() -> int | None:
            await server.start()
            return server.bound_port

        async def start_then_stop() -> bool:
            await server.start()
            port = server.bound_port
            answers = port is not None and await _answers("127.0.0.1", port)
            await server.stop()
            return answers

        left_port = asyncio.run(start_only())
        assert left_port is not None
        assert server.is_running() is False
        assert server.bound_port is None
        assert asyncio.run(start_then_stop()) is True
        # The next start() closed the sockets the first loop left.
        assert _bindable(left_port)
        assert server.is_running() is False
        gc.collect()

    # The closed loop's transports can't be closed without it, and asyncio warns when they
    # are collected; the server closes their sockets. Collecting them must raise nothing.
    @pytest.mark.filterwarnings("ignore::ResourceWarning")
    @pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
    @pytest.mark.parametrize("loop_factory", _LOOP_FACTORIES, ids=_LOOP_FACTORY_IDS)
    def test_clients_of_a_server_left_running_when_its_loop_closed_are_closed(
        self, monkeypatch, loop_factory
    ):
        # Recorded servers stay alive, as a caller holding one keeps it, while the closed
        # loop's transports are collected.
        servers = _record_servers(monkeypatch)
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)

        def run(coroutine):
            with asyncio.Runner(loop_factory=loop_factory) as runner:
                return runner.run(coroutine)

        async def start_with_clients() -> tuple[int, list[socket.socket]]:
            await server.start()
            port = server.bound_port
            assert port is not None
            # Two: from Python 3.13, asyncio fails only on the second transport of a Server
            # collected.
            clients = [socket.create_connection(("127.0.0.1", port), timeout=2) for _ in "ab"]
            await _until(lambda: len(server.list_clients()) == 2)
            return port, clients

        async def start_then_stop() -> bool:
            await server.start()
            running = server.is_running()
            await server.stop()
            return running

        left_port, clients = run(start_with_clients())
        try:
            assert run(start_then_stop()) is True
            for client in clients:
                try:
                    assert client.recv(1) == b""
                except ConnectionResetError:
                    pass
        finally:
            for client in clients:
                client.close()
        assert _bindable(left_port)
        gc.collect()
        assert _open(servers) == []

    def test_start_and_stop_raise_while_the_server_runs_on_another_event_loop(self):
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        try:
            serving = asyncio.run_coroutine_threadsafe(server.serve_forever(), loop)
            deadline = time.monotonic() + 2
            while not server.is_running():
                assert time.monotonic() < deadline
                time.sleep(0.01)
            port = server.bound_port
            assert port is not None
            for operation in (server.start, server.stop):
                with pytest.raises(RuntimeError, match="another event loop"):
                    asyncio.run(operation())
                assert server.is_running() is True
                assert asyncio.run(_answers("127.0.0.1", port)) is True
            asyncio.run_coroutine_threadsafe(server.stop(), loop).result(5)
            assert serving.result(5) is None
            assert server.is_running() is False
            assert _bindable(port)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(5)
            loop.close()

    async def test_a_waiting_serve_forever_returns_when_a_stop_and_a_fresh_start_come_first(
        self,
    ):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        opening = asyncio.create_task(server.start())
        await asyncio.sleep(0)  # The first start() is opening the listener.
        waiting = asyncio.create_task(server.serve_forever())
        await asyncio.sleep(0)  # serve_forever() waits to see how that goes.
        stopping = asyncio.create_task(server.stop())
        await asyncio.sleep(0)
        await opening
        await server.start()  # A fresh run, before the waiter has woken.
        try:
            assert await asyncio.wait_for(waiting, 2) is None
            await stopping
            # The fresh run is not the one serve_forever() waited on, and runs on.
            assert server.is_running() is True
            port = server.bound_port
            assert port is not None
            assert await _answers("127.0.0.1", port) is True
        finally:
            await server.stop()
        assert server.is_running() is False

    async def test_the_server_agrees_with_itself_at_every_step(self, monkeypatch):
        servers = _record_servers(monkeypatch)
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        disagreements: set[str] = set()
        finished = asyncio.Event()

        async def watch() -> None:
            # Runs between every two steps of the code below.
            while not finished.is_set():
                disagreements.update(_disagreements(server, servers))
                await asyncio.sleep(0)

        watcher = asyncio.create_task(watch())
        try:
            await server.start()
            reader, writer = await _client_of(_listener_stopped_listening(server))
            await asyncio.gather(server.start(), server.start(), return_exceptions=True)
            assert await _closed(reader)
            writer.close()
            await server.stop()

            serving = asyncio.create_task(server.serve_forever())
            await _until(server.is_running)
            await server.stop()
            await serving

            starting = asyncio.create_task(server.start())
            await asyncio.sleep(0)
            await server.stop()
            await starting

            await asyncio.gather(server.start(), server.start(), server.stop())
            assert server.is_running() is False

            for steps in range(8):
                starting = asyncio.create_task(server.start())
                for _ in range(steps):
                    await asyncio.sleep(0)
                starting.cancel()
                await asyncio.gather(starting, return_exceptions=True)
                await server.stop()
        finally:
            finished.set()
            await watcher
        assert disagreements == set()

    def test_one_server_works_across_event_loops(self):
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)

        async def stop_during_a_start() -> bool:
            starting = asyncio.create_task(server.start())
            await asyncio.sleep(0)
            await server.stop()
            await starting
            return server.is_running()

        async def serve_forever_then_stop() -> None:
            serving = asyncio.create_task(server.serve_forever())
            await _until(server.is_running)
            await server.stop()
            await asyncio.wait_for(serving, 2)

        async def replace_then_stop() -> list[object]:
            await server.start()
            _listener_stopped_listening(server)
            results = await asyncio.gather(server.start(), server.start(), return_exceptions=True)
            assert server.is_running() is True
            await server.stop()
            return [type(result) for result in results]

        for _run in range(2):
            assert asyncio.run(stop_during_a_start()) is False
            asyncio.run(serve_forever_then_stop())
            assert asyncio.run(replace_then_stop()) == [type(None), RuntimeError]
            assert server.is_running() is False


def _record_servers(monkeypatch: pytest.MonkeyPatch) -> list[asyncio.Server]:
    """Record every asyncio.Server made from here on, even one a cancel leaves unreturned."""
    made: list[asyncio.Server] = []
    server_class = cast(Any, asyncio.base_events).Server

    class Recorded(server_class):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            made.append(cast(asyncio.Server, self))

    monkeypatch.setattr(asyncio.base_events, "Server", Recorded)
    return made


def _open(servers: list[asyncio.Server]) -> list[asyncio.Server]:
    """The servers that still hold sockets, serving or not."""
    return [server for server in servers if server.sockets]


def _disagreements(server: ClickServer, servers: list[asyncio.Server]) -> list[str]:
    """Where the server's state disagrees with itself or with the sockets it holds."""
    found = []
    running = server.is_running()
    if running != (server.bound_port is not None):
        found.append(f"is_running() gives {running}, bound_port {server.bound_port}")
    listener = server._server
    current = listener.transport if listener is not None else None
    for made in _open(servers):
        if made is not current:
            found.append(f"{made!r} holds sockets, but is not the server's listener")
    return found


def _free_tcp_port() -> int:
    """A port no socket listens on at 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _bindable(port: int) -> bool:
    """True when a server could listen on the port at 127.0.0.1 again.

    On POSIX the socket sets SO_REUSEADDR, as asyncio's create_server does, so the
    connections a server closed, which Linux keeps on the port in TIME_WAIT, don't count; a
    socket listening on the port still does. Windows needs no option for that, and there
    SO_REUSEADDR would let the socket share a port that another one listens on.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if os.name == "posix":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            sock.listen()
    except OSError:
        return False
    return True


async def _client_of(
    listener: server_module._Listener,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """A connection to a listener, once the listener has it."""
    reader, writer = await asyncio.open_connection("127.0.0.1", listener.port)
    await _until(lambda: len(listener.connections) == 1)
    return reader, writer


def _listener_stopped_listening(server: ClickServer) -> server_module._Listener:
    """Make the server's listener report that it stopped listening, as it does on Windows
    once asyncio has closed one of its sockets; return that listener."""
    listener = server._server
    assert listener is not None
    cast(Any, listener).is_listening = lambda: False
    return listener


def _skip_unless_proactor() -> None:
    """Skip a test that kills a listening socket, on a loop that can't stop a server with
    one killed. Called before the test opens anything, which a skip would leave open."""
    proactor = getattr(asyncio, "ProactorEventLoop", None)
    if proactor is None or not isinstance(asyncio.get_running_loop(), proactor):
        pytest.skip("only asyncio's Proactor loop (Windows) closes a listening socket itself")


def _kill_listening_socket(server: ClickServer, index: int) -> None:
    """Close one listening socket under a server, as asyncio's Proactor loop does when an
    accept fails. Other loops never close one, and can't stop a server that has one closed.
    """
    loop = asyncio.get_running_loop()
    _skip_unless_proactor()
    assert server._server is not None
    raw_socket = cast(Any, server._server.transport)._sockets[index]
    cast(Any, loop)._stop_serving(raw_socket)


def _resolve_to_two_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the running loop resolve every host to ::1 and 127.0.0.1, as localhost often is."""

    async def getaddrinfo(host, port, *, family=0, type=0, proto=0, flags=0):  # noqa: A002
        port = int(port or 0)
        addresses = [
            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("::1", port, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port)),
        ]
        return [address for address in addresses if family in (0, address[0])]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", getaddrinfo)


def _resolve_without_a_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the running loop resolve a host at once rather than in a thread, so each await
    in start() falls on the same loop iteration every run."""

    async def getaddrinfo(host, port, *, family=0, type=0, proto=0, flags=0):  # noqa: A002
        return socket.getaddrinfo(host, port, family, type, proto, flags)

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", getaddrinfo)


class _NoIPv6Socket(socket.socket):
    """A socket class that refuses IPv6, as on a host with IPv6 turned off."""

    def __init__(self, family=-1, type=-1, proto=-1, fileno=None):  # noqa: A002
        if family == socket.AF_INET6:
            raise OSError(errno.EAFNOSUPPORT, "Address family not supported by protocol")
        super().__init__(family, type, proto, fileno)


async def _answers(host: str, port: int) -> bool:
    """True when a server on host and port answers a read of DS1."""
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 5)
    except (OSError, TimeoutError):
        return False
    try:
        writer.write(_frame(9, READ_DS1))
        return await _replies(reader, 1) == [(9, 1, DS1_IS_0)]
    except (OSError, TimeoutError, asyncio.IncompleteReadError):
        return False
    finally:
        writer.close()


def _addresses(host: str) -> set[str]:
    """The addresses a host resolves to for a server."""
    infos = socket.getaddrinfo(host, 0, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE)
    return {str(info[4][0]) for info in infos}


class TestPort0:
    async def test_every_address_of_the_default_host_listens_on_bound_port(self):
        async with ClickServer(MemoryDataProvider(), port=0) as server:
            port = server.bound_port
            assert port is not None
            assert server._server is not None
            sockets = server._server.transport.sockets
            assert {sock.getsockname()[1] for sock in sockets} == {port}
            async with ClickClient("127.0.0.1", port) as plc:
                assert await plc.ds.read(1) == {"DS1": 0}
            if socket.has_ipv6 and "::1" in _addresses("localhost"):
                assert await _answers("::1", port) is True

    @pytest.fixture
    def held_port(self):
        """A port another socket listens on at 127.0.0.1."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            yield sock.getsockname()[1]

    async def test_a_port_held_on_one_address_is_passed_over(self, monkeypatch, held_port):
        _resolve_to_two_addresses(monkeypatch)
        offered = [held_port]
        free_port = server_module._free_port
        monkeypatch.setattr(
            server_module,
            "_free_port",
            lambda addresses: offered.pop() if offered else free_port(addresses),
        )
        async with ClickServer(MemoryDataProvider(), port=0) as server:
            assert offered == []
            port = server.bound_port
            assert port not in (None, held_port)
            assert server._server is not None
            assert {sock.getsockname()[1] for sock in server._server.transport.sockets} == {port}
            assert await _answers("127.0.0.1", port) is True

    async def test_start_gives_up_when_every_port_offered_is_held(self, monkeypatch, held_port):
        _resolve_to_two_addresses(monkeypatch)
        offered = []
        monkeypatch.setattr(
            server_module, "_free_port", lambda addresses: offered.append(held_port) or held_port
        )
        server = ClickServer(MemoryDataProvider(), port=0)
        with pytest.raises(RuntimeError, match="no port was free") as caught:
            await server.start()
        assert isinstance(caught.value.__cause__, OSError)
        assert len(offered) == 5
        assert server.is_running() is False
        assert server.bound_port is None

    async def test_port_0_listens_on_ipv4_when_ipv6_is_turned_off(self, monkeypatch):
        _resolve_to_two_addresses(monkeypatch)
        monkeypatch.setattr(socket, "socket", _NoIPv6Socket)
        async with ClickServer(MemoryDataProvider(), port=0) as server:
            port = server.bound_port
            assert port is not None
            assert server._server is not None
            assert [sock.family for sock in server._server.transport.sockets] == [socket.AF_INET]
            assert await _answers("127.0.0.1", port) is True

    async def test_port_0_falls_back_to_any_port_when_no_address_takes_a_socket(self, monkeypatch):
        _resolve_to_two_addresses(monkeypatch)
        monkeypatch.setattr(socket, "socket", _NoIPv6Socket)
        monkeypatch.setattr(server_module, "_free_port", lambda addresses: None)
        async with ClickServer(MemoryDataProvider(), port=0) as server:
            port = server.bound_port
            assert port is not None
            assert await _answers("127.0.0.1", port) is True


class TestFreePort:
    IPV6 = (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("::1", 0, 0, 0))
    IPV4 = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 0))

    def test_an_address_that_takes_no_socket_is_passed_over(self, monkeypatch):
        monkeypatch.setattr(socket, "socket", _NoIPv6Socket)
        port = server_module._free_port([self.IPV6, self.IPV4])
        assert port is not None and port > 0

    def test_none_when_no_address_takes_a_socket(self, monkeypatch):
        monkeypatch.setattr(socket, "socket", _NoIPv6Socket)
        assert server_module._free_port([self.IPV6]) is None
        assert server_module._free_port([]) is None
