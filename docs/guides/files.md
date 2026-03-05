# File I/O

## Nickname CSV

```python
from pyclickplc import read_csv, write_csv

records = read_csv("nicknames.csv")
motor = records.addr["ds1"]
tag = records.tag["mytag"]
count = write_csv("output.csv", records)
```

## DataView CDV

```python
from pyclickplc import read_cdv, write_cdv

dataview = read_cdv("dataview.cdv")
write_cdv("output.cdv", dataview)
```

## Address Helpers

```python
from pyclickplc import format_address_display, normalize_address, parse_address

bank, index = parse_address("X001")  # ("X", 1)
display = format_address_display("X", 1)  # "X001"
normalized = normalize_address("x1")  # "X001"
```

## Friendly Record Constructors

```python
from pyclickplc import make_address_record, make_dataview_record

nick = make_address_record("ds1", nickname="TankTemp")
row = make_dataview_record("x1")
write_row = make_dataview_record("df1", new_value=3.14)
```

## Related Guides

- Address semantics and edge cases: [`guides/addressing.md`](addressing.md)
- Native value contract: [`guides/types.md`](types.md)
- Full API signatures: `API Reference -> Files API`

