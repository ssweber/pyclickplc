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

## Installed modules

```python
from pyclickplc.project import read_modules

modules = read_modules("Project.ini")
if modules.cpu is not None:
    print(modules.cpu.model)

for position, module in modules.expansions.items():
    print(position, module.model, module.discrete_inputs, module.discrete_outputs)

for slot, module in modules.slots.items():
    print(slot, module.model, module.analog_inputs, module.analog_outputs)
```

`Modules` contains the CPU (or `None` if unspecified), CPU slots keyed by
**0 and 1**, and expansions keyed by **1 through 8**. Empty positions are
omitted. The result, its mappings, and its `Module` records are immutable.
Power supplies are not included.

Each `Module` has `module_id`, `model`, `discrete_inputs`, `discrete_outputs`,
`analog_inputs`, and `analog_outputs`. These are hardware capacity counts;
`read_channel_parameters()` returns the assigned DF addresses. Both readers
share installed-module parsing and the same bundled hardware catalog.

Discrete counts are `None` for legacy IDs 41, 44, and 244 because the recorded
catalog identifies those models without supplying their discrete counts.
Zero means a known absence of that kind of I/O. Unknown module IDs raise
`ValueError`; the reader does not guess their capabilities.

`read_modules()` does not interpret channel settings, so it can read the
hardware inventory even if a channel record is malformed. It ignores stale
CPU slot entries that the installed CPU does not support. No CLICK
installation is required.

## Channel parameters

```python
from pyclickplc.project import read_channel_parameters

channels = read_channel_parameters("Project.ini")
print(channels.inputs)   # frozenset of DF addresses receiving analog input
print(channels.outputs)  # frozenset of DF addresses driving analog output
```

Reads the assigned addresses for built-in CPU channels, CLICK PLUS CPU slots
0 and 1, and expansion positions 1 through 8. The returned `ChannelParameters`
is immutable. Scaling, electrical ranges, and discrete X/Y assignments are not
included. CLICK does not need to be installed.

The reader uses installed module IDs to distinguish input and output channels
and ignores settings retained for removed or non-analog modules. It raises
`ValueError` for unknown hardware or malformed channel data, and `OSError`
for unreadable files. A project without assigned analog channels returns
empty sets.
