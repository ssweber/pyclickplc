"""Integration tests: ClickClient <-> ClickServer round-trips.

Tests the full stack: driver -> pymodbus client -> TCP -> pymodbus server
-> _ClickDeviceContext -> MemoryDataProvider.
"""

from __future__ import annotations

import asyncio
import logging
import math
import struct
import warnings

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
    async def test_start_and_stop_log_and_warn_nothing(self, caplog):
        caplog.set_level(logging.DEBUG, logger="pymodbus")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            async with ClickServer(MemoryDataProvider(), host="127.0.0.1", port=TEST_PORT + 7):
                await asyncio.sleep(0.05)
        pymodbus_warnings = [
            record.getMessage()
            for record in caplog.records
            if record.name.startswith("pymodbus") and record.levelno >= logging.WARNING
        ]
        assert pymodbus_warnings == []
        assert [str(warning.message) for warning in caught] == []

    async def test_bound_socket_is_reachable_through_the_server(self):
        # pyrung reads the port bound for port 0 through ClickServer._server.transport.
        server = ClickServer(MemoryDataProvider(), host="127.0.0.1", port=0)
        async with server:
            assert server._server is not None
            transport = server._server.transport
            assert isinstance(transport, asyncio.Server)
            port = transport.sockets[0].getsockname()[1]
            assert port != 0
            async with ClickClient("127.0.0.1", port) as plc:
                assert await plc.ds.read(1) == {"DS1": 0}
