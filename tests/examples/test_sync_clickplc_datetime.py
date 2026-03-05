from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import pytest

from ._traffic_light_loader import load_sync_clickplc_datetime_example


class _FakeAccessor:
    def __init__(self, read_values: dict[int, bool] | None = None) -> None:
        self._read_values = read_values or {}
        self.write_calls: list[tuple[int, bool | int | list[bool] | list[int]]] = []

    async def write(self, start: int, data: bool | int | list[bool] | list[int]) -> None:
        self.write_calls.append((start, data))

    async def _read_single(self, index: int) -> bool:
        return self._read_values.get(index, False)

    def __getitem__(self, index: int):
        return self._read_single(index)


class _FakeClickClient:
    error_bits_by_host: ClassVar[dict[str, dict[int, bool]]] = {}
    fail_by_host: ClassVar[dict[str, Exception]] = {}
    instances: ClassVar[list[_FakeClickClient]] = []

    def __init__(self, host: str, port: int = 502, device_id: int = 1) -> None:
        self.host = host
        self.port = port
        self.device_id = device_id
        self.sd = _FakeAccessor()
        self.sc = _FakeAccessor(self.error_bits_by_host.get(host, {}))
        _FakeClickClient.instances.append(self)

    async def __aenter__(self) -> _FakeClickClient:
        maybe_error = self.fail_by_host.get(self.host)
        if maybe_error is not None:
            raise maybe_error
        return self

    async def __aexit__(self, *args: object) -> None:
        del args


@pytest.fixture(autouse=True)
def _reset_fakes() -> None:
    _FakeClickClient.error_bits_by_host = {}
    _FakeClickClient.fail_by_host = {}
    _FakeClickClient.instances = []


@pytest.mark.asyncio
async def test_sync_click_datetime_uses_individual_sd_writes(monkeypatch: pytest.MonkeyPatch):
    module = load_sync_clickplc_datetime_example()
    monkeypatch.setattr(module, "ClickClient", _FakeClickClient)

    async def _noop_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(module.asyncio, "sleep", _noop_sleep)

    dt = datetime(2026, 3, 5, 14, 30, 45)
    await module.sync_click_datetime("plc-1", dt, settle_seconds=0.0)

    fake = _FakeClickClient.instances[-1]
    assert fake.sd.write_calls == [
        (29, 2026),
        (31, 3),
        (32, 5),
        (34, 14),
        (35, 30),
        (36, 45),
    ]
    assert fake.sc.write_calls == [
        (53, True),
        (53, False),
        (55, True),
        (55, False),
    ]


@pytest.mark.asyncio
async def test_sync_click_datetime_returns_date_error(monkeypatch: pytest.MonkeyPatch):
    module = load_sync_clickplc_datetime_example()
    monkeypatch.setattr(module, "ClickClient", _FakeClickClient)

    async def _noop_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(module.asyncio, "sleep", _noop_sleep)
    _FakeClickClient.error_bits_by_host = {"plc-2": {54: True}}

    dt = datetime(2026, 3, 5, 14, 30, 45)
    await module.sync_click_datetime("plc-2", dt, settle_seconds=0.0)

    fake = _FakeClickClient.instances[-1]
    assert fake.sd.write_calls == [
        (29, 2026),
        (31, 3),
        (32, 5),
        (34, 14),
        (35, 30),
        (36, 45),
    ]
    assert fake.sc.write_calls == [
        (53, True),
        (53, False),
        (55, True),
        (55, False),
    ]


@pytest.mark.asyncio
async def test_sync_click_datetime_reports_unhandled_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    module = load_sync_clickplc_datetime_example()
    monkeypatch.setattr(module, "ClickClient", _FakeClickClient)
    _FakeClickClient.fail_by_host = {"bad-plc": OSError("connect failed")}

    dt = datetime(2026, 3, 5, 14, 30, 45)
    await module.sync_click_datetime("bad-plc", dt)

    captured = capsys.readouterr()
    assert "An error occurred with PLC at bad-plc: connect failed" in captured.out
