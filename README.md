# pyclickplc

Utilities for AutomationDirect CLICK PLCs: Modbus TCP client/server, address helpers, nickname CSV I/O, and DataView CDV I/O.

## Installation

```bash
uv install pyclickplc
pip install pyclickplc
```

Requires Python 3.11+. The Modbus client and server depend on [pymodbus](https://github.com/pymodbus-dev/pymodbus).

## Quickstart

`ClickClient` is an async Modbus TCP client for CLICK PLCs.

```python
import asyncio
from pyclickplc import AddressRecord, ClickClient

async def main():
    async with ClickClient("192.168.1.10", 502) as plc:
        # Bank accessor
        await plc.ds.write(1, 100)
        value = await plc.ds[1]                   # bare value
        result = await plc.ds.read(1, 3)          # DS1..DS3 (inclusive range)
        xd_word = await plc.xd[3]                 # XD3 (display-indexed, 0..8)
        await plc.ydu.write(0x1234)               # YD0u explicit upper-byte alias
        xdu_word = await plc.xdu.read()           # {"XD0u": ...}

        # Address interface
        await plc.addr.write("df1", 3.14)
        by_addr = await plc.addr.read("df1")
        yd_display = await plc.addr.read("YD0-YD8")  # display-step range for XD/YD

    # Tag interface (programmatic tags)
    tags = {
        "temp_source": AddressRecord(memory_type="DF", address=1, nickname="MyTag"),
    }
    async with ClickClient("192.168.1.10", 502, tags=tags) as tagged:
        await tagged.tag.write("MyTag", 42)
        tag_value = await tagged.tag.read("mytag")  # case-insensitive
        all_tag_values = await tagged.tag.read()
        tag_defs = tagged.tag.read_all()  # synchronous tag metadata

asyncio.run(main())
```

All `read()` methods return `ModbusResponse`, a mapping keyed by canonical uppercase addresses (`"DS1"`, `"X001"`). Lookups are normalized (`resp["ds1"]` resolves `"DS1"`). Use `await plc.ds[1]` for a bare value. `plc.xd`/`plc.yd` are display-indexed (`0..8`) with `plc.xdu`/`plc.ydu` aliases for `XD0u`/`YD0u`.

## ModbusService (Sync + Polling)

`ModbusService` is a synchronous wrapper intended for UI/event-driven callers. It owns a background asyncio loop and provides polling plus bulk writes.

```python
from pyclickplc import ModbusService, ReconnectConfig

def on_values(values):
    print(values)  # ModbusResponse keyed by canonical addresses

svc = ModbusService(
    poll_interval_s=0.5,
    reconnect=ReconnectConfig(delay_s=0.5, max_delay_s=5.0),  # optional
    on_values=on_values,
)
svc.connect("192.168.1.10", 502, device_id=1, timeout=1)

svc.set_poll_addresses(["ds1", "df1", "y1"])
print(svc.read(["ds1", "df1"]))

results = svc.write(
    {
        "ds1": 100,
        "y1": True,
        "x1": True,  # not writable -> per-item failure entry
    }
)
print(results)

svc.disconnect()
```

Error semantics:
- invalid read addresses raise `ValueError`
- transport/protocol read failures raise `OSError`
- writes return per-address outcomes (`ok` + `error`) for UI reporting

## Modbus Server

`ClickServer` simulates a CLICK PLC over Modbus TCP. `MemoryDataProvider` is the built-in in-memory backend.

```python
import asyncio
from pyclickplc import ClickServer, MemoryDataProvider

async def main():
    provider = MemoryDataProvider()
    provider.bulk_set({
        "DS1": 42,
        "Y001": True,
    })

    async with ClickServer(provider, host="localhost", port=5020):
        # Server is now accepting Modbus TCP connections
        await asyncio.sleep(60)

asyncio.run(main())
```

`MemoryDataProvider` convenience methods:
- `get(address)`
- `set(address, value)`
- `bulk_set({address: value, ...})`

Interactive server TUI helper:

```python
import asyncio
from pyclickplc import ClickServer, MemoryDataProvider, run_server_tui

async def main():
    provider = MemoryDataProvider()
    provider.set("DS1", 42)

    server = ClickServer(provider, host="127.0.0.1", port=5020)
    await run_server_tui(server)

asyncio.run(main())
```

TUI commands:
- `help`
- `status`
- `clients`
- `disconnect <client_id>`
- `disconnect all`
- `shutdown` (`exit` / `quit`)

## Nickname CSV Files

Read and write CLICK software nickname CSV files.

```python
from pyclickplc import read_csv, write_csv

# Read — returns AddressRecordMap (dict[int, AddressRecord] compatible)
records = read_csv("nicknames.csv")
for key, record in records.items():
    print(record.display_address, record.nickname, record.comment)

# Address/nickname lookup views
ds1 = records.addr["ds1"]
tag = records.tag["mytag"]  # case-insensitive nickname lookup

# Write — only records with content are written
count = write_csv("output.csv", records)
```

## DataView CDV Files

Read and write CLICK DataView `.cdv` files (UTF-16 LE format).

```python
from pyclickplc import read_cdv, write_cdv

# Read
dataview = read_cdv("dataview.cdv")
for row in dataview.rows:
    if not row.is_empty:
        print(row.address, row.data_type, row.new_value)

# Write
write_cdv("output.cdv", dataview)
```

## Address Parsing

Parse and format PLC address strings.

```python
from pyclickplc import parse_address, format_address_display, normalize_address

bank, index = parse_address("DS100")    # ("DS", 100)
bank, index = parse_address("X001")     # ("X", 1)
bank, index = parse_address("XD0u")     # ("XD", 1)  — MDB index

display = format_address_display("X", 1)    # "X001"
display = format_address_display("XD", 1)   # "XD0u"

normalized = normalize_address("x1")    # "X001"
```

Note: address helper functions remain MDB-oriented for XD/YD internals (`parse_address("XD3")` returns MDB index `6`).

Full API reference is available via MkDocs (including advanced modules).

## Development

```bash
uv sync --all-extras --dev    # Install dependencies
make test                     # Run tests (uv run pytest)
make lint                     # Lint (codespell, ruff, ty)
make docs-build               # Build docs with mkdocstrings
make docs-serve               # Serve docs locally
make                          # All of the above
```
