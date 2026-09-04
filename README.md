# pyclickplc

**Talk to AutomationDirect CLICK PLCs from Python.** Async Modbus TCP client and server, the CLICK address model, and nickname CSV and DataView CDV file I/O.

It's the wire under [pyrung](https://pyrung.com/pyrung/) and [ClickNick](https://pyrung.com/clicknick/), and it stands on its own as a Modbus client for any CLICK.

- Documentation: https://pyrung.com/pyclickplc/
- LLM docs index: https://pyrung.com/pyclickplc/llms.txt
- LLM full context: https://pyrung.com/pyclickplc/llms-full.txt

## Install

```bash
uv add pyclickplc
# or
pip install pyclickplc
```

Requires Python 3.11+.

## Quick example

```python
import asyncio
from pyclickplc import ClickClient

async def main():
    async with ClickClient("192.168.1.10", 502) as plc:
        # Read and write registers with native Python types
        await plc.ds.write(1, 100)
        ds1 = await plc.ds[1]          # int
        await plc.y.write(1, True)     # bool
        df1 = await plc.addr.read("DF1")  # float

asyncio.run(main())
```

The [quickstart](https://pyrung.com/pyclickplc/getting-started/quickstart/) uses `ClickServer` to simulate a PLC locally, so you don't need hardware to try it.

## What's included

**[Modbus client](https://pyrung.com/pyclickplc/guides/client/)** — `ClickClient` reads and writes PLC values as native Python types (`bool`, `int`, `float`, `str`). Access by bank (`plc.ds`), by address string (`plc.addr`), or by tag name (`plc.tag`).

**[Modbus service](https://pyrung.com/pyclickplc/guides/modbus_service/)** — `ModbusService` wraps the async client for sync and UI applications with background polling and auto-reconnect.

**[Modbus server](https://pyrung.com/pyclickplc/guides/server/)** — `ClickServer` simulates a CLICK PLC over Modbus TCP. Use it for development and testing without hardware.

**[File I/O](https://pyrung.com/pyclickplc/guides/files/)** — Read and write CLICK nickname CSV and DataView CDV files. Compatible with CLICK programming software and [ClickNick](https://pyrung.com/clicknick/).

## Learn more

| | |
|---|---|
| [Quickstart](https://pyrung.com/pyclickplc/getting-started/quickstart/) | Connect, read/write, simulate a traffic light |
| [Client guide](https://pyrung.com/pyclickplc/guides/client/) | Bank accessors, address strings, tags |
| [Types & values](https://pyrung.com/pyclickplc/guides/types/) | Native Python types per bank family |
| [Addressing](https://pyrung.com/pyclickplc/guides/addressing/) | Normalization, sparse X/Y, XD/YD display indexing |
| [File I/O](https://pyrung.com/pyclickplc/guides/files/) | Nickname CSV and DataView CDV |
| [Examples](https://pyrung.com/pyclickplc/guides/examples/) | Runnable scripts |

## Development

```bash
uv sync --all-extras --dev    # Install dependencies
make test                     # Run tests (uv run pytest)
make lint                     # Lint (codespell, ruff, ty)
make docs-build               # Build docs (mkdocs + mkdocstrings)
make docs-serve               # Serve docs locally
make                          # All of the above
```
