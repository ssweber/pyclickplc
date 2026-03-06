# Types & Values

Every value you read or write is a native Python type.

## Bank family to Python type

| Bank family | Python type | Example |
| --- | --- | --- |
| `X`, `Y`, `C`, `T`, `CT`, `SC` | `bool` | `True` |
| `DS`, `DD`, `DH`, `TD`, `CTD`, `SD`, `XD`, `YD` | `int` | `42`, `0x1234` |
| `DF` | `float` | `3.14` |
| `TXT` | `str` | `"A"` |

No raw Modbus registers — the client handles packing and unpacking automatically.

## Read return shapes

Single-index reads return a bare value:

```python
ds1 = await plc.ds[1]  # int
```

Range reads return a `ModbusResponse`, a dict keyed by canonical normalized addresses:

```python
values = await plc.ds.read(1, 3)
# {"DS1": 100, "DS2": 200, "DS3": 300}

values["ds1"]  # 100 — lookups are case-insensitive
```

## Write validation

Writes are validated before being sent to the PLC:

- **Type mismatch** — writing `str` to `DS` raises `ValueError`.
- **Out of range** — value exceeds the bank's data type limits raises `ValueError`.
- **Not writable** — some addresses (certain SC/SD) are read-only and raise `ValueError`.

## See also

- [Client guide](client.md) — how to read and write values
- [Addressing](addressing.md) — normalization and sparse ranges
