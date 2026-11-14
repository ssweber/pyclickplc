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
from pyclickplc import normalize_address, parse_address

normalize_address("X001")  # "X001"
normalize_address("X017")  # None — no such address
parse_address("X017")      # ValueError
```

Check an address you build at run time with `normalize_address` (returns `None`) or `parse_address` (raises).

## XD and YD words

`XD` and `YD` read one I/O position of `X` or `Y` as a 16-bit word:

| Address | Points |
|---|---|
| `XD0` | X001–X016 (CPU, or CLICK PLUS slot 0) |
| `XD0u` | X021–X036 (CLICK PLUS slot 1) |
| `XD1` | X101–X116 (expansion 1) |
| ... | ... |
| `XD8` | X801–X816 (expansion 8) |

`YD` follows the same layout over `Y`. Bank accessors take the number after `XD`; `XD0u` has its own accessor:

```python
xd0 = await plc.xd[0]             # XD0
values = await plc.xd.read(0, 2)  # XD0, XD1, XD2
upper = await plc.xd0u.read()     # {"XD0u": 0}
```

`XD0u` and `YD0u` are the only `u` addresses, and a range read cannot include them.

## See also

- [Types & values](types.md) — what Python type each bank returns
- [Client guide](client.md) — how to read and write using these addresses
