# Rich PLC Value Types — Design Handoff

## Problem

Client reads return bare Python types (`int`, `float`, `bool`, `str`). For HEX and FLOAT especially, the raw value isn't what users want to see:

- `plc.dh.read(1)` → `255` (user expects to see `"00FF"`)
- `plc.df.read(1)` → `3.140000104904175` (user expects `"3.14"`)

The dataview layer has formatting functions (`datatype_to_display`, etc.) but they require manual type code lookups. There's no unified way to get display-friendly values.

## Proposal

Introduce rich value types that subclass Python builtins. They behave exactly like their base types for math/comparisons but override `__str__` to show PLC display format.

```python
val = await plc.dh.read(1)
val + 1           # 256 — math works, it IS an int
print(val)        # 00FF — display-friendly by default
val.raw()         # 255 — explicit access to underlying value
f"{val:plc}"      # 00FF — optional __format__ protocol support
```

### Types needed

| Type | Base | `str()` example | `.raw()` |
|------|------|----------------|----------|
| PlcBit | bool-like* | `"1"` / `"0"` | `True` / `False` |
| PlcInt | int | `"42"` | `42` |
| PlcInt2 | int | `"42"` | `42` |
| PlcHex | int | `"00FF"` | `255` |
| PlcFloat | float | `"3.14"` | `3.140000104904175` |
| PlcStr | str | `"A"` | `"A"` (same) |

*PlcBit can't subclass `bool` (it's final in Python). Could subclass `int` with truthy semantics, or just be a small wrapper.

### Where they get created

1. **Client** — `AddressAccessor._read_single` and range reads wrap return values
2. **Dataview** — `storage_to_datatype` and `display_to_datatype` return rich types
3. **Server** — `MemoryDataProvider` could accept/return them (or just unwrap on write)

### Display formatting rules (from existing `datatype_to_display`)

- BIT: `"1"` / `"0"`
- INT/INT2: `str(int(value))`
- HEX: `format(int(value), "04X")`
- FLOAT: `f"{float(value):.7G}"`
- TXT: the character itself (already `str`)

### What moves where

The formatting logic currently in `dataview.py` (`datatype_to_display`, `display_to_datatype`) could either:
- Stay in `dataview.py` and be called by the rich types
- Move into a new `values.py` module alongside the type definitions

The conversion functions (`storage_to_datatype`, `datatype_to_storage`) stay in `dataview.py` since they're CDV-specific, but return rich types instead of bare values.

### Dict results

Range reads return `dict[str, PlcValue]`. Could use a `PlcResult(dict)` subclass with a `.display()` that formats all values, or just let users call `str()` on individual values.

## Open questions

- Module placement: new `values.py` or add to existing `banks.py`/`dataview.py`?
- Should `PlcBit` subclass `int` (like Python's `bool` does) or be a custom class?
- Should `.raw()` return the base type (`int(val)`) or just be an alias for clarity?
- How much `__format__` protocol support? Just `:plc` or more (`:hex`, `:dec`)?
- Should `MemoryDataProvider.read()` return rich types or bare values?

## Status

- TXT `str` unification is done (all four conversion functions handle `str` for TXT)
- README updated with API docs
- CLAUDE.md created
- 2 pre-existing test failures in `test_modbus.py` (T bank base address mismatch)
