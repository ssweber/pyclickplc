# pyclickplc

Utilities for AutomationDirect CLICK PLCs — address parsing, Modbus TCP client/server, nickname CSV and DataView CDV file I/O, and BlockTag comment parsing.

## Installation

```bash
pip install pyclickplc
```

Requires Python 3.11+. The Modbus client and server depend on [pymodbus](https://github.com/pymodbus-dev/pymodbus).

## Modbus Client

`ClickClient` is an async Modbus TCP driver with three access patterns: bank accessors, address strings, and tag nicknames.

```python
import asyncio
from pyclickplc import ClickClient

async def main():
    async with ClickClient("192.168.1.10") as plc:
        # Bank accessors — read/write by bank and index
        value = await plc.ds.read(1)           # Read DS1
        await plc.ds.write(1, 100)             # Write 100 to DS1
        values = await plc.ds.read(1, 10)      # Read DS1-DS10 (returns dict)
        await plc.y.write(1, [True, False])    # Write Y001=True, Y002=False

        # Address interface — read/write by address string
        value = await plc.addr.read("df1")     # Read DF1
        await plc.addr.write("df1", 3.14)      # Write 3.14 to DF1
        values = await plc.addr.read("c1-c10") # Read C1-C10 range

        # Tag interface — read/write by nickname (requires CSV file)
        plc_with_tags = ClickClient("192.168.1.10", tag_filepath="nicknames.csv")
        # ... use as context manager, then:
        # value = await plc_with_tags.tag.read("MyTag")
        # await plc_with_tags.tag.write("MyTag", 42)
        # all_tags = await plc_with_tags.tag.read()  # Read all tags

asyncio.run(main())
```

Supported banks: `X`, `Y`, `C`, `T`, `CT`, `SC`, `DS`, `DD`, `DH`, `DF`, `XD`, `YD`, `TD`, `CTD`, `SD`, `TXT`.

## Modbus Server

`ClickServer` simulates a CLICK PLC over Modbus TCP. Supply a `DataProvider` to back the address space.

```python
import asyncio
from pyclickplc import ClickServer, MemoryDataProvider

async def main():
    provider = MemoryDataProvider()
    provider.set("DS1", 42)
    provider.set("Y001", True)

    async with ClickServer(provider, host="localhost", port=5020) as server:
        # Server is now accepting Modbus TCP connections
        await asyncio.sleep(60)

asyncio.run(main())
```

Implement the `DataProvider` protocol for custom backends:

```python
from pyclickplc.server import DataProvider, PlcValue

class MyProvider:
    def read(self, address: str) -> PlcValue: ...
    def write(self, address: str, value: PlcValue) -> None: ...
```

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

MDB-format CSV files (exported by CLICK software) are also supported via `read_mdb_csv()`.

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

## Modbus Mapping

Map between PLC addresses and raw Modbus coil/register addresses.

```python
from pyclickplc import plc_to_modbus, modbus_to_plc, pack_value, unpack_value
from pyclickplc import DataType

# PLC address → Modbus address
modbus_addr, reg_count = plc_to_modbus("DS", 1)    # (0, 1)
modbus_addr, reg_count = plc_to_modbus("DF", 1)    # (28672, 2)

# Modbus address → PLC address
result = modbus_to_plc(0, is_coil=False)     # ("DS", 1)
result = modbus_to_plc(0, is_coil=True)      # ("X", 1)

# Pack/unpack values for Modbus registers
regs = pack_value(3.14, DataType.FLOAT)      # [low_word, high_word]
value = unpack_value(regs, DataType.FLOAT)   # 3.14
```

## Bank Definitions

All 16 CLICK PLC memory banks are defined in `BANKS`:

```python
from pyclickplc import BANKS, DataType

ds = BANKS["DS"]
print(ds.min_addr, ds.max_addr, ds.data_type)  # 1, 4500, DataType.INT

# Sparse banks (X/Y) have valid_ranges for hardware slot validation
x = BANKS["X"]
print(x.valid_ranges)  # ((1, 16), (21, 36), (101, 116), ...)
```

## Development

```bash
uv sync --all-extras --dev    # Install dependencies
make test                     # Run tests (uv run pytest)
make lint                     # Lint (codespell, ruff, ty)
make                          # All of the above
```
