# File I/O

Read and write the files CLICK programming software uses: nickname CSV, DataView CDV and PLC data dumps. Read the installed hardware and the PLC name from a project's `Project.ini`, and set the name. [ClickNick](https://pyrung.com/clicknick/) uses the same formats.

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

`read_csv` raises `ValueError` naming the file and line if a row's Address isn't a CLICK address or its Data Type doesn't match its bank.

If two rows use the same nickname (ignoring case), the file still loads and `.addr` works. Every `.tag` lookup then raises `ValueError` naming the repeats, until you rename one.

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

`make_address_record` normalizes the address (`ds1` becomes `DS1`) and sets the data type from the bank. If you leave out `retentive`, it uses the bank's default.

### CLICK's Address.csv

CLICK keeps an `Address.csv` beside its open project's database. It holds the same nicknames in database form. `read_mdb_csv` reads it into the same `AddressRecordMap` and sets `used` from the file's Use column:

```python
from pyclickplc import read_mdb_csv

records = read_mdb_csv("Address.csv")
print(records.addr["DS1"].used)  # True
```

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

Read and write the CSV files produced by PLC > Read Data from PLC... > All > Save (and loaded back by PLC > Write Data into PLC > File Select).

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

CLICK writes the cases below in a way that `read_plc_data` has to handle:

- CLICK shows `Err-Format` for a DF value it can't display. `read_plc_data` returns `float("nan")` for it.
- CLICK writes a TXT space, control character or byte above 0x7E as `$` and its hex code. `read_plc_data` returns the character (`$20` is `" "`, `$C8` is `"\xc8"`).
- CLICK writes a TXT comma without quotes, which gives its row a cell too many. `read_plc_data` rejoins the cells and returns `","` for the comma.

If a TXT comma is next to an empty TXT address, the row can be read in more than one way:

```python
from pyclickplc import PlcDataReadError, read_plc_data

try:
    data = read_plc_data("data.csv")
except PlcDataReadError as e:
    print("Check these in CLICK:", e.addresses)  # ('TXT976', 'TXT977', ...)
    data = e.values  # every other address in the file
```

`read_plc_data` reads the whole file, then raises `PlcDataReadError`. `addresses` names each TXT address that may hold a comma or nothing. `values` holds every other address, as `read_plc_data` would have returned it. `PlcDataReadError` is a `ValueError`.

### Write

```python
from pyclickplc import write_plc_data

write_plc_data("output.csv", data)                  # infers banks from data keys
write_plc_data("output.csv", data, banks=["DS"])     # only the DS bank
write_plc_data("output.csv", data, banks=["DS", "DF"])  # specific banks
```

Unspecified addresses within included banks get bank defaults. Banks not in `banks` (or not present in data keys when `banks` is omitted) are excluded from the file.

**CLICK's Write Data into PLC writes every address of each memory type in the file.** An address that the file leaves blank is cleared in the PLC. CLICK asks before it overwrites the PLC's data. To change some addresses and keep the rest, read the PLC's data first, then write it back with your changes, as in [Modify and write back](#modify-and-write-back).

`write_plc_data` writes a DF value as the float32 that the PLC holds, in CLICK's fixed-point form (`66.7` is written `66.69999695`). For some values above about 1e19, CLICK's last digits differ from pyclickplc's. Both read back as the same value.

CLICK's editor can't enter a NaN or an infinity, so `write_plc_data` raises `ValueError` naming the address for such a DF value. A program or a Modbus write can still put one in the PLC. `write_plc_data` also raises `ValueError` for a TXT comma. Nobody has tested whether CLICK's Write Data into PLC reads one.

### Modify and write back

```python
data = read_plc_data("from_plc.csv")
data["DS3"] = 42
write_plc_data("to_plc.csv", data)
```

If the dump has an `Err-Format` cell, set that address to a number before writing. If it has a TXT comma, change that address before writing.

## Project.ini

A CLICK project folder keeps its hardware configuration and PLC name in `Project.ini`. These functions don't need CLICK installed. They raise `ValueError` for unknown hardware or a malformed record.

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

`slots` is keyed by CLICK PLUS CPU slot, 0 and 1. `expansions` is keyed by position, 1 through 8. Empty positions are left out. Each `Module` has the point counts `discrete_inputs`, `discrete_outputs`, `analog_inputs` and `analog_outputs`.

### Channel parameters

```python
from pyclickplc import read_channel_parameters

channels = read_channel_parameters("Project.ini")
print(channels.inputs)   # frozenset({'DF41', 'DF42', 'DF43', 'DF44'})
print(channels.outputs)  # frozenset({'DF45'})
```

These are the DF addresses assigned to analog input and output channels. A project with no analog channels returns empty sets.

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

### PLC name

```python
from pyclickplc import read_plc_name, validate_click_name, write_plc_name

print(read_plc_name("Project.ini"))  # Line 1, or None if the project has no name

ok, error = validate_click_name("Line 2")
if ok:
    write_plc_name("Project.ini", "Line 2")
```

A PLC name is 1 to 24 letters, digits, spaces, underscores and hyphens. `write_plc_name` raises `ValueError` for a name `validate_click_name` refuses. It changes only the line that holds the name. If the file has no name line, it adds that line, and the section header too if the section is missing. It leaves the rest of the file as it was.

## See also

- [Quickstart](../getting-started/quickstart.md) — generate CSV and CDV files from scratch
- [Client guide](client.md) — use tag names from a nickname CSV
- [Addressing](addressing.md) — parse and normalize addresses without a connection
