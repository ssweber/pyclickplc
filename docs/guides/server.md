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
provider.bulk_set({"DS1": 42, "C1": True, "TXT1": "H", "TXT2": "I"})
```

When the server handles a write, it reads every target address before it stores anything. If the server refuses the request, the provider is unchanged. If the provider's `read` raises for an address in the request, the request fails.

Addresses are normalized automatically — `provider.set("ds1", 100)` and `provider.set("DS1", 100)` are equivalent.

For the full server + client workflow, see the [quickstart](../getting-started/quickstart.md).

## Requests outside the Modbus map

`ClickServer` answers some requests that CLICK's Modbus map does not list. It answers them the same way a CLICK does. Coil and register numbers here count from 0, as `plc_to_modbus` returns them.

- **X coils.** The server stores an FC05 or FC15 write to an X coil through your provider. The server does not scan inputs. A value that a client writes to an X coil stays until your provider writes that input again. If your provider raises in `write`, the client gets exception 04.
- **T and CT coils.** The server stores an FC05 or FC15 write to a T or CT bit through your provider.
- **Coils between slots.** Units 17 to 32 of slots 1 to 8 have no X or Y address. For X these are coils 48-63, 80-95 and so on, up to 272-287. For Y they are coils 8240-8255, 8272-8287 and so on, up to 8464-8479. The server stores writes to these coils itself, so your provider never sees them. FC01 and FC02 read them back. They keep their values when you call `stop()` and `start()`. To clear one, write 0 to it.
- **After XD8 and YD8.** A read of register 57361 (after XD8) or 57873 (after YD8) returns 0. A write to either register gets exception 02. A read of a later register that no address names, such as 57362 or 57874, also gets exception 02.
- **DF registers.** The server returns a DF as the two registers that the client wrote, including the payload of a NaN. It does this until your provider changes the value.
- **Write replies.** The reply to an FC05 or FC06 write echoes the request. To learn what your provider kept, read the address back.

`ClickClient` still refuses to write X coils and the coils between slots.

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
