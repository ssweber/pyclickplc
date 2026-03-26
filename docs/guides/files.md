# File I/O

Read and write CLICK nickname CSV and DataView CDV files. These are the same formats that CLICK programming software and [ClickNick](https://github.com/ssweber/clicknick) use.

## Nickname CSV

Nickname files map PLC addresses to human-readable names, comments, and initial values.

### Read

```python
from pyclickplc import read_csv

records = read_csv("nicknames.csv")

# Look up by address (case-insensitive)
motor = records.addr["ds1"]
print(motor.nickname, motor.comment)

# Look up by tag name (case-insensitive)
tag = records.tag["TankTemp"]
print(tag.address, tag.data_type)
```

`read_csv` returns an `AddressRecordMap` with `.addr` and `.tag` lookup dicts.

### Write

```python
from pyclickplc import make_address_record, write_csv

records = [
    make_address_record("DS1", nickname="TankTemp", comment="Degrees F"),
    make_address_record("C1", nickname="PumpRun"),
    make_address_record("DF1", nickname="FlowRate"),
]
count = write_csv("nicknames.csv", records)
print(f"Wrote {count} rows")
```

`write_csv` accepts any iterable of `AddressRecord` values (or a mapping keyed by address). Only records with content (nickname, comment, or non-default settings) are written.

### Build records

`make_address_record` creates an `AddressRecord` from a display address with sensible defaults:

```python
from pyclickplc import make_address_record

record = make_address_record("DS1", nickname="TankTemp")
# AddressRecord(address="DS1", nickname="TankTemp", data_type=DataType.INT16, ...)
```

Address normalization, data type inference, and default values are handled automatically.

## DataView CDV

DataView files define monitoring views for the CLICK programming software. They use UTF-16 LE encoding with a CSV-like structure.

### Read and write

```python
from pyclickplc import read_cdv, write_cdv

dataview = read_cdv("dataview.cdv")
write_cdv("output.cdv", dataview)
```

### Build a DataView

```python
from pyclickplc import make_dataview_record, write_cdv

write_cdv("monitoring.cdv", [
    make_dataview_record("DS1"),
    make_dataview_record("C1"),
    make_dataview_record("DF1", new_value=3.14),  # pre-fill a write value
])
```

`write_cdv` accepts a list of `DataViewRecord` values (or a `DataViewFile` for full control). `make_dataview_record` infers data type from the address. Use `new_value` to pre-populate a write value.

## PLC Data Dump

Read and write the CSV files produced by Data > Read Data from PLC > Save to File (and consumed by Data > Write Data into PLC > Load from File).

### Read

```python
from pyclickplc import read_plc_data

# Full dump — every address in the file
data = read_plc_data("data.csv")
# {"X001": True, "X002": True, "C1": True, "DS3": 1, "DH1": 895, ...}

# Only non-default values (skip False/0/0.0/"")
data = read_plc_data("data.csv", skip_default=True)
```

Returns a flat dict mapping normalised addresses to native Python values (`bool` for bits, `int` for INT/INT2/HEX, `float` for FLOAT, `str` for TXT).

### Write

```python
from pyclickplc import write_plc_data

write_plc_data("output.csv", data)                  # infers banks from data keys
write_plc_data("output.csv", data, banks=["DS"])     # only the DS bank
write_plc_data("output.csv", data, banks=["DS", "DF"])  # specific banks
```

Unspecified addresses within included banks get bank defaults. Banks not in `banks` (or not present in data keys when `banks` is omitted) are excluded from the file.

### Modify and write back

```python
data = read_plc_data("from_plc.csv")
data["DS3"] = 42
write_plc_data("to_plc.csv", data)
```

## Address helpers

Parse and normalize addresses without a client connection:

```python
from pyclickplc import format_address_display, normalize_address, parse_address

parse_address("X001")            # ("X", 1)
normalize_address("x1")          # "X001"
format_address_display("X", 1)   # "X001"
```

See [Addressing](addressing.md) for normalization rules and edge cases.

## See also

- [Quickstart](../getting-started/quickstart.md) — generate CSV and CDV files from scratch
- [Client guide](client.md) — use tag names from a nickname CSV
