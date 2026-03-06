# Addressing

All pyclickplc APIs accept address strings and normalize them automatically.

## Canonical normalized addresses

Input is case-insensitive. Output is always canonical:

```python
from pyclickplc import normalize_address, parse_address

normalize_address("x1")    # "X001"
normalize_address("ds1")   # "DS1"
normalize_address("Df10")  # "DF10"

parse_address("X001")  # ("X", 1)
parse_address("DS1")   # ("DS", 1)
```

X/Y addresses are zero-padded to 3 digits (`X001`). All other banks use no padding (`DS1`, `DF10`).

## Sparse X and Y ranges

`X` and `Y` are hardware I/O banks tied to physical module slots. Not every numeric value is a valid address — for example, `X017` doesn't exist because slots have gaps.

```python
from pyclickplc import normalize_address

normalize_address("X001")  # "X001" — valid
normalize_address("X017")  # ValueError — no such address
```

Use `normalize_address` or `parse_address` to validate before building dynamic address lists.

## XD and YD display indexing

`XD` and `YD` are 16-bit word views of the X/Y I/O banks. They use display indices `0` through `8`:

| Display index | What it reads |
|---|---|
| `XD0` | X001–X008 as a 16-bit word (lower byte) |
| `XD1` | X101–X108 as a 16-bit word (lower byte) |
| ... | ... |
| `XD8` | X801–X808 as a 16-bit word (lower byte) |

Bank accessors use display indexing by default:

```python
xd0 = await plc.xd[0]  # display index 0
values = await plc.xd.read(0, 3)  # display indices 0, 1, 2
```

## XD0u and YD0u upper-byte aliases

Each XD/YD display index has a lower byte (default) and an upper byte. The upper byte covers inputs X009–X016 for slot 0, X109–X116 for slot 1, and so on.

Access the upper byte with the `u` suffix:

```python
normalize_address("XD0u")  # "XD0u"
parse_address("XD0u")      # ("XD", 1)  — MDB index 1

upper = await plc.xd0u.read()
```

Upper-byte addresses cannot be mixed with regular XD/YD in range reads.

## See also

- [Types & values](types.md) — what Python type each bank returns
- [Client guide](client.md) — how to read and write using these addresses
