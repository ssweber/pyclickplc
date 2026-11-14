# File I/O

Read and write the files CLICK programming software uses: nickname CSV, DataView CDV and PLC data dumps. Read the installed hardware from a project's `Project.ini`. [ClickNick](https://pyrung.com/clicknick/) uses the same formats.

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
print(tag.display_address)  # DS1
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
# AddressRecord(address='DS1', data_type='INT', nickname='TankTemp')
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

Read and write the CSV files produced by PLC > Read Data from PLC... > All > Save (and consumed by Data > Write Data into PLC > Load from File).

### Read

```python
from pyclickplc import read_plc_data

# Full dump — every address in the file
data = read_plc_data("data.csv")
# {"X001": True, "X002": True, "C1": True, "DS3": 1, "DH1": 895, ...}

# Only non-default values (skip False/0/0.0/"")
data = read_plc_data("data.csv", skip_default=True)
```

Returns a flat dict mapping normalized addresses to native Python values (`bool` for bits, `int` for INT/INT2/HEX, `float` for FLOAT, `str` for TXT).

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

## Project.ini

A CLICK project folder keeps its hardware configuration in `Project.ini`. These readers don't need CLICK installed. Unknown hardware or a malformed record raises `ValueError`.

### Installed modules

```python
from pyclickplc import read_modules

modules = read_modules("Project.ini")
if modules.cpu is not None:
    print(modules.cpu.model)  # C2-01CPU-2

for slot, module in modules.slots.items():
    print(slot, module.model)  # 0 C2-14D1

for position, module in modules.expansions.items():
    print(position, module.model, module.discrete_inputs)  # 1 C0-08NE3 8
```

`slots` holds CLICK PLUS CPU slots 0 and 1; `expansions` holds positions 1 through 8. Empty positions are left out. Each `Module` gives its point counts: `discrete_inputs`, `discrete_outputs`, `analog_inputs` and `analog_outputs`.

### Channel parameters

```python
from pyclickplc import read_channel_parameters

channels = read_channel_parameters("Project.ini")
print(channels.inputs)   # frozenset({'DF41', 'DF42', 'DF43', 'DF44'})
print(channels.outputs)  # frozenset({'DF45'})
```

These are the DF addresses assigned to analog input and output channels. A project with no analog channels gives empty sets.

### I/O layout

```python
from pyclickplc import read_io_layout

for io in read_io_layout("Project.ini"):
    print(io.location, io.position, io.module.model, io.inputs, io.analog_inputs)
# cpu 0 C2-01CPU-2 () ()
# slot 0 C2-14D1 ('X001', ..., 'X008') ()
# slot 1 C2-08D2-6V ('X021', 'X022', 'X023', 'X024') ('DF41', 'DF42', 'DF43', 'DF44')
# expansion 1 C0-08NE3 ('X101', ..., 'X108') ()
```

You get one `ModuleIO` per installed module, in physical order. `inputs` and `outputs` are its X and Y addresses. `analog_inputs` and `analog_outputs` are its channels' DF addresses, with `None` for a channel that has none.

## See also

- [Quickstart](../getting-started/quickstart.md) — generate CSV and CDV files from scratch
- [Client guide](client.md) — use tag names from a nickname CSV
- [Addressing](addressing.md) — parse and normalize addresses without a connection
