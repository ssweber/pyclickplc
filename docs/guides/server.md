# Modbus Server

`ClickServer` simulates a CLICK PLC over Modbus TCP.

```python
import asyncio
from pyclickplc import ClickServer, MemoryDataProvider

async def main():
    provider = MemoryDataProvider()
    provider.bulk_set(
        {
            "DS1": 42,
            "Y001": True,
        }
    )

    async with ClickServer(provider, host="localhost", port=5020):
        await asyncio.sleep(60)

asyncio.run(main())
```

`MemoryDataProvider` helper methods:

- `get(address)`
- `set(address, value)`
- `bulk_set({...})`

## Interactive TUI

Use `run_server_tui` for a basic interactive terminal interface:

```python
import asyncio
from pyclickplc import ClickServer, MemoryDataProvider, run_server_tui

async def main():
    provider = MemoryDataProvider()
    server = ClickServer(provider, host="127.0.0.1", port=5020)
    await run_server_tui(server)

asyncio.run(main())
```

Supported commands:

- `help`
- `status`
- `clients`
- `disconnect <client_id>`
- `disconnect all`
- `shutdown` (`exit` / `quit`)

