# Addressing

`pyclickplc` uses canonical normalized address strings across APIs.

## Canonical Normalized Addresses

- Address parsing is case-insensitive.
- Normalization returns canonical display format.

Examples:

```python
from pyclickplc import normalize_address, parse_address

assert normalize_address("x1") == "X001"
assert normalize_address("ds1") == "DS1"
assert normalize_address("xd0u") == "XD0u"

assert parse_address("X001") == ("X", 1)
assert parse_address("XD0u") == ("XD", 1)  # MDB index
```

## Sparse `X` and `Y` Ranges

`X` and `Y` are sparse banks. Not every numeric value is valid (for example `X017` is invalid).

Use parser/normalizer helpers to validate before building dynamic address lists.

## `XD` and `YD` Display-Indexed Access

- `plc.xd` and `plc.yd` are display-indexed (`0..8`).
- `plc.addr.read("XD0-XD4")` and `plc.addr.read("YD0-YD2")` use display-step ranges.
- Hidden odd MDB slots are not exposed in display-indexed range reads.

## `XD0u` and `YD0u` (Upper-Byte Aliases)

`XD0u` and `YD0u` are explicit upper-byte addresses and advanced edge cases:

- Use `plc.xd0u.read()` / `plc.yd0u.write(...)` for direct alias access.
- `XD`/`YD` ranges cannot include `u` addresses (for example `XD0-XD0u` is invalid).

## See Also

- Type and value contract: [`guides/types.md`](types.md)
- Full API contracts: `API Reference -> Addressing API`
