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
from pyclickplc import ClickClient

async def main():
    async with ClickClient("192.168.1.10", 502) as plc:
        # Bank accessor
        await plc.ds.write(1, 100)
        value = await plc.ds[1]                   # bare value
        result = await plc.ds.read(1, 3)          # DS1..DS3 (inclusive range)

        # Address interface
        await plc.addr.write("df1", 3.14)
        by_addr = await plc.addr.read("df1")

    # Tag interface (requires tag_filepath on client construction)
    async with ClickClient("192.168.1.10", 502, tag_filepath="nicknames.csv") as tagged:
        await tagged.tag.write("MyTag", 42)
        tag_value = await tagged.tag.read("MyTag")
        all_tag_values = await tagged.tag.read()
        tag_defs = tagged.tag.read_all()  # synchronous tag metadata

asyncio.run(main())
```

All `read()` methods return `ModbusResponse`, a mapping keyed by canonical uppercase addresses (`"DS1"`, `"X001"`). Lookups are normalized (`resp["ds1"]` resolves `"DS1"`). Use `await plc.ds[1]` for a bare value.

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

## Nickname CSV Files

Read and write CLICK software nickname CSV files.

```python
from pyclickplc import read_csv, write_csv

# Read — returns dict[addr_key, AddressRecord]
records = read_csv("nicknames.csv")
for key, record in records.items():
    print(record.display_address, record.nickname, record.comment)

# Write — only records with content are written
count = write_csv("output.csv", records)
```

## DataView CDV Files

Read and write CLICK DataView `.cdv` files (UTF-16 LE format).

```python
from pyclickplc import load_cdv, save_cdv

# Load — returns (rows, has_new_values, header)
rows, has_new_values, header = load_cdv("dataview.cdv")
for row in rows:
    if not row.is_empty:
        print(row.address, row.type_code, row.new_value)

# Save
save_cdv("output.cdv", rows, has_new_values, header)
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

Full API reference is available via MkDocs (including advanced modules).

## Hardware Capability Profile

`ClickHardwareProfile` provides table-driven ladder portability rules:
- bank/address writability (`is_writable`)
- fixed instruction-role compatibility (`valid_for_role`)
- copy-family bank compatibility (`copy_compatible`)
- compare compatibility (`compare_compatible`, `compare_constant_compatible`)

```python
from pyclickplc import CLICK_HARDWARE_PROFILE

CLICK_HARDWARE_PROFILE.is_writable("SC", 50)  # True
CLICK_HARDWARE_PROFILE.valid_for_role("T", "timer_done_bit")  # True
CLICK_HARDWARE_PROFILE.copy_compatible("single", "X", "Y")  # True
```

## Development

```bash
uv sync --all-extras --dev    # Install dependencies
make test                     # Run tests (uv run pytest)
make lint                     # Lint (codespell, ruff, ty)
make docs-build               # Build docs with mkdocstrings
make docs-serve               # Serve docs locally
make                          # All of the above
```
