# pyclickplc

Utilities for AutomationDirect CLICK PLCs: Modbus TCP client/server, address helpers, nickname CSV I/O, and DataView CDV I/O.

Documentation: https://ssweber.github.io/pyclickplc/
LLM docs index: https://ssweber.github.io/pyclickplc/llms.txt
LLM full context: https://ssweber.github.io/pyclickplc/llms-full.txt

## Installation

```bash
uv add pyclickplc
# or
pip install pyclickplc
```

Requires Python 3.11+. Modbus client/server functionality depends on [pymodbus](https://github.com/pymodbus-dev/pymodbus).

## Choose Your Interface

- `ClickClient`: async API for direct `asyncio` applications.
- `ModbusService`: sync + polling API for UI/event-driven applications that do not want to manage an async loop.

## Native Python Type Contract

All read/write APIs operate on native Python values.

| Bank family | Python type | Examples |
| --- | --- | --- |
| `X`, `Y`, `C`, `T`, `CT`, `SC` | `bool` | `True`, `False` |
| `DS`, `DD`, `DH`, `TD`, `CTD`, `SD`, `XD`, `YD` | `int` | `42`, `0x1234` |
| `DF` | `float` | `3.14` |
| `TXT` | `str` | `"A"` |

`read()` methods return `ModbusResponse`, keyed by canonical normalized addresses (`"DS1"`, `"X001"`):

- lookups are normalized (`resp["ds1"]` resolves `"DS1"`)
- single index reads like `await plc.ds[1]` return a bare native Python value

## Quickstart (`ClickClient`, async)

```python
import asyncio
from pyclickplc import ClickClient, read_csv

tags = read_csv("nicknames.csv")

async def main():
    async with ClickClient("192.168.1.10", 502, tags=tags) as plc:
        # Bank accessors
        await plc.ds.write(1, 100)
        ds1 = await plc.ds[1]
        df_values = await plc.df.read(1, 3)
        await plc.y.write(1, True)

        # String address interface
        await plc.addr.write("df1", 3.14)
        df1 = await plc.addr.read("DF1")

        # Tag interface (case-insensitive)
        await plc.tag.write("mytag", 42.0)
        tag_value = await plc.tag.read("MyTag")

        print(ds1, df_values, df1, tag_value)

asyncio.run(main())
```

## `ModbusService` (sync + polling)

```python
from pyclickplc import ModbusService, ReconnectConfig

def on_values(values):
    print(values)  # ModbusResponse keyed by canonical normalized addresses

svc = ModbusService(
    poll_interval_s=0.5,
    reconnect=ReconnectConfig(delay_s=0.5, max_delay_s=5.0),
    on_values=on_values,
)
svc.connect("192.168.1.10", 502, device_id=1, timeout=1)

svc.set_poll_addresses(["DS1", "DF1", "Y1"])
print(svc.read(["DS1", "DF1"]))
print(svc.write({"DS1": 100, "Y1": True, "X1": True}))  # X1 is not writable

svc.disconnect()
```

## Error Model

- Validation and address parsing failures raise `ValueError`.
- Transport/protocol failures raise `OSError` for reads.
- `ModbusService.write()` returns per-address outcomes (`ok` + `error`) instead of raising per-item validation failures.

## Addressing Nuances

- Address strings are canonical normalized (`x1` -> `X001`, `ds1` -> `DS1`).
- `X`/`Y` are sparse address families; not every numeric value is valid.
- `XD`/`YD` accessors are display-indexed (`0..8`) by default.
- `XD0u`/`YD0u` are explicit upper-byte aliases for advanced use cases.

See the addressing guide for details:
- https://ssweber.github.io/pyclickplc/guides/addressing/

## Other Features

- Modbus simulator: `ClickServer`, `MemoryDataProvider`, `run_server_tui`
- CLICK nickname CSV I/O: `read_csv`, `write_csv`, `AddressRecordMap`
- CLICK DataView CDV I/O: `read_cdv`, `write_cdv`, `verify_cdv`, `check_cdv_file`

Server docs:
- Guide: https://ssweber.github.io/pyclickplc/guides/server/
- API: https://ssweber.github.io/pyclickplc/reference/api/server/

## v0.1 API Stability

`pyclickplc` v0.1 follows a “stable core, evolving edges” policy.

- Stable core: client/service/server/file I/O/address/validation APIs surfaced in the docs site primary navigation.
- Advanced/evolving: low-level Modbus mapping helpers and bank metadata (`ModbusMapping`, `plc_to_modbus`, `BANKS`, etc.).

## Development

```bash
uv sync --all-extras --dev    # Install dependencies
make test                     # Run tests (uv run pytest)
make lint                     # Lint (codespell, ruff, ty)
make docs-build               # Build docs (mkdocs + mkdocstrings)
make docs-serve               # Serve docs locally
make                          # All of the above
```
