# pyclickplc

**Talk to AutomationDirect CLICK PLCs from Python.** Async Modbus TCP client/server, address helpers, nickname CSV and DataView CDV file I/O.

- Documentation: https://ssweber.github.io/pyclickplc/
- LLM docs index: https://ssweber.github.io/pyclickplc/llms.txt
- LLM full context: https://ssweber.github.io/pyclickplc/llms-full.txt

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

No PLC on hand? The [quickstart](https://ssweber.github.io/pyclickplc/getting-started/quickstart/) uses `ClickServer` to simulate one locally.

## What's included

**[Modbus client](https://ssweber.github.io/pyclickplc/guides/client/)** — `ClickClient` reads and writes PLC values as native Python types (`bool`, `int`, `float`, `str`). Access by bank (`plc.ds`), by address string (`plc.addr`), or by tag name (`plc.tag`).

**[Modbus service](https://ssweber.github.io/pyclickplc/guides/modbus_service/)** — `ModbusService` wraps the async client for sync and UI applications with background polling and auto-reconnect.

**[Modbus server](https://ssweber.github.io/pyclickplc/guides/server/)** — `ClickServer` simulates a CLICK PLC over Modbus TCP. Use it for development and testing without hardware.

**[File I/O](https://ssweber.github.io/pyclickplc/guides/files/)** — Read and write CLICK nickname CSV and DataView CDV files. Compatible with CLICK programming software and [ClickNick](https://github.com/ssweber/clicknick).

## Learn more

| | |
|---|---|
| [Quickstart](https://ssweber.github.io/pyclickplc/getting-started/quickstart/) | Connect, read/write, simulate a traffic light |
| [Client guide](https://ssweber.github.io/pyclickplc/guides/client/) | Bank accessors, address strings, tags |
| [Types & values](https://ssweber.github.io/pyclickplc/guides/types/) | Native Python types per bank family |
| [Addressing](https://ssweber.github.io/pyclickplc/guides/addressing/) | Normalization, sparse X/Y, XD/YD display indexing |
| [File I/O](https://ssweber.github.io/pyclickplc/guides/files/) | Nickname CSV and DataView CDV |
| [Examples](https://ssweber.github.io/pyclickplc/guides/examples/) | Runnable scripts |

## Development

```bash
uv sync --all-extras --dev    # Install dependencies
make test                     # Run tests (uv run pytest)
make lint                     # Lint (codespell, ruff, ty)
make docs-build               # Build docs (mkdocs + mkdocstrings)
make docs-serve               # Serve docs locally
make                          # All of the above
```
