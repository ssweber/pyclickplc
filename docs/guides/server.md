# Server & Simulator

`ClickServer` simulates a CLICK PLC over Modbus TCP. Use it for development and testing without hardware.

```python
import asyncio
from pyclickplc import ClickServer, MemoryDataProvider

async def main():
    provider = MemoryDataProvider()
    provider.bulk_set({"DS1": 42, "Y001": True})

    async with ClickServer(provider, host="localhost", port=5020):
        print("Server running on localhost:5020")
        await asyncio.sleep(60)

asyncio.run(main())
```

Connect to it with `ClickClient` or any Modbus TCP tool — it behaves like a real CLICK PLC.

## MemoryDataProvider

`MemoryDataProvider` stores PLC values in memory with address validation:

```python
provider = MemoryDataProvider()
provider.set("DS1", 100)
provider.get("DS1")       # 100
provider.bulk_set({"DS1": 42, "C1": True, "TXT1": "HELLO"})
```

Addresses are normalized automatically — `provider.set("ds1", 100)` and `provider.set("DS1", 100)` are equivalent.

For the full server + client workflow, see the [quickstart](../getting-started/quickstart.md).

## Interactive TUI

`run_server_tui` adds a terminal interface for inspecting and controlling the server:

```python
import asyncio
from pyclickplc import ClickServer, MemoryDataProvider, run_server_tui

async def main():
    provider = MemoryDataProvider()
    server = ClickServer(provider, host="localhost", port=5020)
    await run_server_tui(server)

asyncio.run(main())
```

Commands: `help`, `status`, `clients`, `disconnect <id>`, `disconnect all`, `shutdown`.

## See also

- [Quickstart](../getting-started/quickstart.md) — server + client together
- [Client guide](client.md) — connect to the simulated PLC
