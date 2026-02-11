# File I/O

## Nickname CSV

```python
from pyclickplc import read_csv, write_csv

records = read_csv("nicknames.csv")
count = write_csv("output.csv", records)
```

## DataView CDV

```python
from pyclickplc import load_cdv, save_cdv

rows, has_new_values, header = load_cdv("dataview.cdv")
save_cdv("output.cdv", rows, has_new_values, header)
```

## Address Helpers

```python
from pyclickplc import format_address_display, normalize_address, parse_address

bank, index = parse_address("X001")  # ("X", 1)
display = format_address_display("X", 1)  # "X001"
normalized = normalize_address("x1")  # "X001"
```

