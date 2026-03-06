from __future__ import annotations

import asyncio

import pytest

from pyclickplc import MemoryDataProvider

from ._traffic_light_loader import load_traffic_light_example


@pytest.mark.asyncio
async def test_run_traffic_light_cycles_red_green_yellow(monkeypatch):
    module = load_traffic_light_example()
    provider = MemoryDataProvider()
    states: list[dict[str, object]] = []

    def capture_bulk_set(values: dict[str, object]) -> None:
        states.append(dict(values))

    sleep_calls = 0

    async def bounded_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(provider, "bulk_set", capture_bulk_set)
    monkeypatch.setattr(module.asyncio, "sleep", bounded_sleep)

    with pytest.raises(asyncio.CancelledError):
        await module.run_traffic_light(provider)

    assert states[:3] == [module.RED_STATE, module.GREEN_STATE, module.YELLOW_STATE]
