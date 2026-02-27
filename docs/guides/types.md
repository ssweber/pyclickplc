# Native Value Types

`pyclickplc` reads and writes native Python values.

## Bank Family to Python Type

| Bank family | Python type | Example |
| --- | --- | --- |
| `X`, `Y`, `C`, `T`, `CT`, `SC` | `bool` | `True` |
| `DS`, `DD`, `DH`, `TD`, `CTD`, `SD`, `XD`, `YD` | `int` | `42`, `0x1234` |
| `DF` | `float` | `3.14` |
| `TXT` | `str` | `"A"` |

## Read Return Shapes

- `read()` returns `ModbusResponse` keyed by canonical normalized addresses.
- Mapping lookups are normalized (`resp["ds1"]` resolves `DS1`).
- Single index access like `await plc.ds[1]` returns a bare native Python value.

## Write Validation Rules

- Type mismatches raise `ValueError` (for example writing `str` to `DS`).
- Out-of-range values raise `ValueError`.
- Non-writable addresses raise `ValueError`.
- Transport/protocol failures raise `OSError`.

## `ModbusService` Write Semantics

- `read(...)` invalid addresses raise `ValueError`.
- `read(...)` transport failures raise `OSError`.
- `write(...)` returns per-address `WriteResult` entries with `ok` and `error`.

## See Also

- Address semantics and normalization: [`guides/addressing.md`](addressing.md)
- Full API contracts: `API Reference -> Client API` and `Service API`
