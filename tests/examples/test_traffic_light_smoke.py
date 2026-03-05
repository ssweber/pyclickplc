from __future__ import annotations

import asyncio

import pytest
from pyclickplc import ClickClient, ClickServer, MemoryDataProvider

from ._traffic_light_loader import load_traffic_light_example

TEST_PORT = 15031


@pytest.mark.asyncio
async def test_server_startup_shutdown_with_traffic_light_provider():
    module = load_traffic_light_example()
    provider = MemoryDataProvider()
    provider.bulk_set(module.RED_STATE.copy())

    async with ClickServer(provider, host="127.0.0.1", port=TEST_PORT):
        await asyncio.sleep(0.1)
        async with ClickClient("127.0.0.1", TEST_PORT) as plc:
            txt1 = await plc.addr.read("TXT1")
            c1 = await plc.addr.read("C1")
            c2 = await plc.addr.read("C2")
            c3 = await plc.addr.read("C3")

        assert txt1 == {"TXT1": "R"}
        assert c1 == {"C1": True}
        assert c2 == {"C2": False}
        assert c3 == {"C3": False}
