"""Tests for pyclickplc.modbus_service."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

import pytest

from pyclickplc.addresses import format_address_display
from pyclickplc.banks import BANKS, DataType
from pyclickplc.client import ModbusResponse
from pyclickplc.modbus_service import ConnectionState, ModbusService, ReconnectConfig


def _default_for_data_type(data_type: DataType) -> bool | int | float | str:
    if data_type == DataType.BIT:
        return False
    if data_type == DataType.FLOAT:
        return 0.0
    if data_type == DataType.TXT:
        return "\x00"
    return 0


class _FakeAccessor:
    def __init__(self, client: _FakeClickClient, bank: str) -> None:
        self._client = client
        self._bank = bank

    async def read(self, start: int, end: int | None = None) -> ModbusResponse:
        self._client.read_calls.append((self._bank, start, end))
        if self._client.slow_read_s > 0:
            await asyncio.sleep(self._client.slow_read_s)
        if self._client.read_error_bank == self._bank:
            raise OSError(f"read failed for {self._bank}")

        stop = start if end is None else end
        payload: dict[str, bool | int | float | str] = {}
        for index in range(start, stop + 1):
            address = format_address_display(self._bank, index)
            payload[address] = self._client.data.get(
                address,
                _default_for_data_type(BANKS[self._bank].data_type),
            )
        return ModbusResponse(payload)

    async def write(
        self,
        start: int,
        data: bool | int | float | str | list[bool] | list[int] | list[float] | list[str],
    ) -> None:
        self._client.write_calls.append((self._bank, start, data))
        if self._client.write_error_bank == self._bank:
            raise OSError(f"write failed for {self._bank}")

        if isinstance(data, list):
            for offset, value in enumerate(data):
                address = format_address_display(self._bank, start + offset)
                self._client.data[address] = value
            return

        address = format_address_display(self._bank, start)
        self._client.data[address] = data


class _FakeClickClient:
    connect_error_hosts: set[str] = set()
    default_read_error_bank: str | None = None
    default_write_error_bank: str | None = None
    default_slow_read_s: float = 0.0
    instances: list[_FakeClickClient] = []

    def __init__(
        self,
        host: str,
        port: int = 502,
        tag_filepath: str = "",
        timeout: int = 1,
        device_id: int = 1,
        reconnect_delay: float = 0.0,
        reconnect_delay_max: float = 0.0,
    ) -> None:
        del tag_filepath
        del timeout
        del device_id
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay
        self.reconnect_delay_max = reconnect_delay_max
        self._client = _FakeConn()
        self.data: dict[str, bool | int | float | str] = {}
        self.read_calls: list[tuple[str, int, int | None]] = []
        self.write_calls: list[tuple[str, int, object]] = []
        self.read_error_bank = _FakeClickClient.default_read_error_bank
        self.write_error_bank = _FakeClickClient.default_write_error_bank
        self.slow_read_s = _FakeClickClient.default_slow_read_s
        self._accessors: dict[str, _FakeAccessor] = {}
        _FakeClickClient.instances.append(self)

    async def __aenter__(self) -> _FakeClickClient:
        if self.host in self.connect_error_hosts:
            raise OSError(f"connect failed for {self.host}:{self.port}")
        self._client.connected = True
        return self

    async def __aexit__(self, *args: object) -> None:
        del args
        self._client.connected = False

    def _get_accessor(self, bank: str) -> _FakeAccessor:
        if bank not in self._accessors:
            self._accessors[bank] = _FakeAccessor(self, bank)
        return self._accessors[bank]


@dataclass
class _FakeConn:
    connected: bool = False


@pytest.fixture(autouse=True)
def _reset_fake():
    _FakeClickClient.connect_error_hosts = set()
    _FakeClickClient.default_read_error_bank = None
    _FakeClickClient.default_write_error_bank = None
    _FakeClickClient.default_slow_read_s = 0.0
    _FakeClickClient.instances = []


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("pyclickplc.modbus_service.ClickClient", _FakeClickClient)
    svc = ModbusService(poll_interval_s=0.03)
    try:
        yield svc
    finally:
        svc.disconnect()


def _wait_for(predicate, *, timeout: float = 1.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Condition not met before timeout")


def _service_threads() -> list[threading.Thread]:
    return [
        t
        for t in threading.enumerate()
        if t.name == "pyclickplc-modbus-service" and t.is_alive()
    ]


class TestLifecycleState:
    def test_reconnect_config_validation(self):
        with pytest.raises(ValueError):
            ReconnectConfig(delay_s=-0.1)
        with pytest.raises(ValueError):
            ReconnectConfig(max_delay_s=-0.1)
        with pytest.raises(ValueError):
            ReconnectConfig(delay_s=2.0, max_delay_s=1.0)

    def test_connect_disconnect_state_transitions(self, service: ModbusService):
        states: list[ConnectionState] = []
        errors: list[Exception | None] = []

        state_service = ModbusService(
            poll_interval_s=0.03,
            on_state=lambda s, e: (states.append(s), errors.append(e)),
        )
        try:
            state_service.connect("localhost", 15020)
            state_service.disconnect()
        finally:
            state_service.disconnect()

        assert states == [
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
            ConnectionState.DISCONNECTED,
        ]
        assert errors[0] is None
        assert errors[1] is None
        assert errors[2] is None

    def test_connect_failure_emits_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("pyclickplc.modbus_service.ClickClient", _FakeClickClient)
        _FakeClickClient.connect_error_hosts = {"bad-host"}

        states: list[ConnectionState] = []
        errors: list[Exception | None] = []
        svc = ModbusService(
            poll_interval_s=0.03,
            on_state=lambda s, e: (states.append(s), errors.append(e)),
        )
        try:
            with pytest.raises(OSError):
                svc.connect("bad-host", 15020)
        finally:
            svc.disconnect()

        assert states[0] == ConnectionState.CONNECTING
        assert states[1] == ConnectionState.ERROR
        assert isinstance(errors[1], OSError)

    def test_connect_reconnect_config_passes_through(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("pyclickplc.modbus_service.ClickClient", _FakeClickClient)
        svc = ModbusService(
            poll_interval_s=0.03,
            reconnect=ReconnectConfig(delay_s=0.25, max_delay_s=2.0),
        )
        try:
            svc.connect("localhost", 15020)
            fake = _FakeClickClient.instances[-1]
            assert fake.reconnect_delay == 0.25
            assert fake.reconnect_delay_max == 2.0
        finally:
            svc.disconnect()

    def test_connect_without_reconnect_config_disables_reconnect(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("pyclickplc.modbus_service.ClickClient", _FakeClickClient)
        svc = ModbusService(poll_interval_s=0.03)
        try:
            svc.connect("localhost", 15020)
            fake = _FakeClickClient.instances[-1]
            assert fake.reconnect_delay == 0.0
            assert fake.reconnect_delay_max == 0.0
        finally:
            svc.disconnect()

    def test_poll_failure_emits_error_once_when_failure_starts(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("pyclickplc.modbus_service.ClickClient", _FakeClickClient)
        states: list[ConnectionState] = []
        errors: list[Exception | None] = []
        svc = ModbusService(
            poll_interval_s=0.03,
            on_state=lambda s, e: (states.append(s), errors.append(e)),
        )
        try:
            svc.connect("localhost", 15020)
            fake = _FakeClickClient.instances[-1]
            fake.read_error_bank = "DS"
            svc.set_poll_addresses(["DS1"])

            _wait_for(lambda: states.count(ConnectionState.ERROR) >= 1)
            time.sleep(0.1)

            error_indexes = [i for i, state in enumerate(states) if state == ConnectionState.ERROR]
            assert len(error_indexes) == 1
            assert isinstance(errors[error_indexes[0]], OSError)
        finally:
            svc.disconnect()

    def test_poll_failure_recovery_allows_future_failure_transition(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("pyclickplc.modbus_service.ClickClient", _FakeClickClient)
        states: list[ConnectionState] = []
        svc = ModbusService(
            poll_interval_s=0.03,
            on_state=lambda s, e: states.append(s),
        )
        try:
            svc.connect("localhost", 15020)
            fake = _FakeClickClient.instances[-1]
            svc.set_poll_addresses(["DS1"])

            fake.read_error_bank = "DS"
            _wait_for(lambda: states.count(ConnectionState.ERROR) >= 1)

            fake.read_error_bank = None
            _wait_for(lambda: states.count(ConnectionState.CONNECTED) >= 2)

            fake.read_error_bank = "DS"
            _wait_for(lambda: states.count(ConnectionState.ERROR) >= 2)
        finally:
            svc.disconnect()

    def test_disconnect_stops_background_thread(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("pyclickplc.modbus_service.ClickClient", _FakeClickClient)
        before = len(_service_threads())
        svc = ModbusService(poll_interval_s=0.03)
        try:
            svc.connect("localhost", 15020)
            _wait_for(lambda: len(_service_threads()) == before + 1)
            svc.disconnect()
            _wait_for(lambda: len(_service_threads()) == before)
        finally:
            svc.disconnect()

    def test_reconnect_after_disconnect_restarts_loop(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("pyclickplc.modbus_service.ClickClient", _FakeClickClient)
        svc = ModbusService(poll_interval_s=0.03)
        try:
            svc.connect("localhost", 15020)
            svc.disconnect()
            svc.connect("localhost", 15020)
        finally:
            svc.disconnect()

        assert len(_FakeClickClient.instances) == 2


class TestPollConfiguration:
    def test_set_poll_addresses_replaces_and_clear_stops(self, service: ModbusService):
        values_seen: list[ModbusResponse] = []
        callback_event = threading.Event()

        callback_service = ModbusService(
            poll_interval_s=0.03,
            on_values=lambda r: (values_seen.append(r), callback_event.set()),
        )
        try:
            callback_service.connect("localhost", 15020)
            fake = _FakeClickClient.instances[-1]
            fake.data["DS1"] = 11
            fake.data["DS2"] = 22
            fake.data["DS3"] = 33

            callback_service.set_poll_addresses(["ds1", "ds2"])
            _wait_for(lambda: len(values_seen) >= 1)
            assert set(values_seen[-1].keys()) == {"DS1", "DS2"}

            callback_service.set_poll_addresses(["ds3"])
            _wait_for(lambda: any(set(v.keys()) == {"DS3"} for v in values_seen))

            before = len(values_seen)
            callback_service.clear_poll_addresses()
            time.sleep(0.09)
            assert len(values_seen) == before
        finally:
            callback_service.disconnect()

    def test_stop_polling_pauses_until_reconfigured(self, service: ModbusService):
        values_seen: list[ModbusResponse] = []

        callback_service = ModbusService(
            poll_interval_s=0.03,
            on_values=lambda r: values_seen.append(r),
        )
        try:
            callback_service.connect("localhost", 15020)
            fake = _FakeClickClient.instances[-1]
            fake.data["DS1"] = 1
            fake.data["DS2"] = 2

            callback_service.set_poll_addresses(["DS1"])
            _wait_for(lambda: len(values_seen) >= 1)

            before = len(values_seen)
            callback_service.stop_polling()
            time.sleep(0.09)
            assert len(values_seen) == before

            callback_service.set_poll_addresses(["DS2"])
            _wait_for(lambda: any("DS2" in sample for sample in values_seen))
        finally:
            callback_service.disconnect()


class TestReadBehavior:
    def test_read_returns_modbus_response_with_canonical_keys(self, service: ModbusService):
        service.connect("localhost", 15020)
        fake = _FakeClickClient.instances[-1]
        fake.data["DS1"] = 42

        result = service.read(["ds1"])
        assert isinstance(result, ModbusResponse)
        assert result == {"DS1": 42}

    def test_read_invalid_address_raises_value_error(self, service: ModbusService):
        service.connect("localhost", 15020)
        with pytest.raises(ValueError):
            service.read(["not-an-address"])

    def test_read_transport_error_raises_oserror(self, service: ModbusService):
        service.connect("localhost", 15020)
        fake = _FakeClickClient.instances[-1]
        fake.read_error_bank = "DS"
        with pytest.raises(OSError):
            service.read(["DS1"])


class TestWriteBehavior:
    def test_write_accepts_mapping_and_iterable(self, service: ModbusService):
        service.connect("localhost", 15020)

        result_map = service.write({"ds1": 1, "ds2": 2})
        assert [r["ok"] for r in result_map] == [True, True]
        assert [r["address"] for r in result_map] == ["DS1", "DS2"]

        result_iter = service.write([("DS3", 3), ("DS4", 4)])
        assert [r["ok"] for r in result_iter] == [True, True]
        assert [r["address"] for r in result_iter] == ["DS3", "DS4"]

    def test_write_non_writable_address_fails_per_item(self, service: ModbusService):
        service.connect("localhost", 15020)
        result = service.write([("X1", True)])
        assert result == [{"address": "X001", "ok": False, "error": "X1 is not writable."}]

    def test_write_invalid_value_fails_and_service_continues(self, service: ModbusService):
        service.connect("localhost", 15020)
        result = service.write([("DS1", "bad"), ("DS2", 5)])
        assert result[0]["ok"] is False
        assert "DS1 value must be int" in cast(str, result[0]["error"])
        assert result[1] == {"address": "DS2", "ok": True, "error": None}

    def test_write_transport_failure_marks_batch_failed(self, service: ModbusService):
        service.connect("localhost", 15020)
        fake = _FakeClickClient.instances[-1]
        fake.write_error_bank = "DS"

        result = service.write([("DS1", 10), ("DS2", 20)])
        assert result[0]["ok"] is False
        assert result[1]["ok"] is False
        assert "write failed for DS" in cast(str, result[0]["error"])


class TestBatchingHeuristics:
    def test_contiguous_writes_are_batched_deterministically(self, service: ModbusService):
        service.connect("localhost", 15020)
        fake = _FakeClickClient.instances[-1]

        service.write([("DS1", 1), ("DS2", 2), ("DS3", 3), ("DF1", 1.0), ("DF2", 2.0)])

        assert fake.write_calls == [
            ("DS", 1, [1, 2, 3]),
            ("DF", 1, [1.0, 2.0]),
        ]

    def test_sparse_bank_reads_do_not_bridge_invalid_gaps(self, service: ModbusService):
        service.connect("localhost", 15020)
        fake = _FakeClickClient.instances[-1]

        service.read(["X001", "X016", "X021", "X022"])

        x_reads = [call for call in fake.read_calls if call[0] == "X"]
        assert x_reads == [
            ("X", 1, None),
            ("X", 16, None),
            ("X", 21, 22),
        ]

    def test_width_two_banks_honor_register_limits(self, service: ModbusService):
        service.connect("localhost", 15020)
        fake = _FakeClickClient.instances[-1]
        addresses = [f"DF{i}" for i in range(1, 64)]

        service.read(addresses)

        df_reads = [call for call in fake.read_calls if call[0] == "DF"]
        assert df_reads == [
            ("DF", 1, 62),
            ("DF", 63, None),
        ]


class TestThreadSafety:
    def test_concurrent_set_poll_addresses_during_poll_is_safe(self, service: ModbusService):
        service.connect("localhost", 15020)
        service.set_poll_addresses(["DS1", "DS2"])
        errors: list[Exception] = []

        def worker(values: Iterable[str]) -> None:
            try:
                for _ in range(20):
                    service.set_poll_addresses(values)
            except Exception as exc:  # pragma: no cover - safety capture
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=(["DS1"],))
        t2 = threading.Thread(target=worker, args=(["DS2"],))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == []

    def test_disconnect_during_active_poll_exits_cleanly(self, service: ModbusService):
        service.connect("localhost", 15020)
        fake = _FakeClickClient.instances[-1]
        fake.slow_read_s = 0.2
        service.set_poll_addresses(["DS1"])

        time.sleep(0.05)
        service.disconnect()
        # second disconnect should be a no-op
        service.disconnect()

    def test_sync_calls_inside_callbacks_fail_fast(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("pyclickplc.modbus_service.ClickClient", _FakeClickClient)
        callback_errors: list[Exception] = []
        callback_called = threading.Event()
        holder: dict[str, ModbusService] = {}

        def on_values(_values: ModbusResponse) -> None:
            try:
                holder["svc"].read(["DS1"])
            except Exception as exc:  # pragma: no cover - callback behavior
                callback_errors.append(exc)
            finally:
                callback_called.set()

        svc = ModbusService(poll_interval_s=0.03, on_values=on_values)
        holder["svc"] = svc
        try:
            svc.connect("localhost", 15020)
            svc.set_poll_addresses(["DS1"])
            _wait_for(callback_called.is_set)
        finally:
            svc.disconnect()

        assert len(callback_errors) == 1
        assert isinstance(callback_errors[0], RuntimeError)
