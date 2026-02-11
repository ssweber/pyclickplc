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

