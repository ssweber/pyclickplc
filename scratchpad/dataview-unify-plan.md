# Dataview: Unify on DataType + Add New Value UI Support

## Context

ClickNick needs pyclickplc's dataview module to support live DataView editing with:
- **New Value** column: user-typed display strings, validated before acceptance
- **Live** column: values read via ClickClient, formatted for display
- Both columns use `datatype_to_display()` for rendering

Currently `DataviewRow.type_code` stores CDV file-format integers (`_CdvStorageCode`: 768, 0, 256...),
which leak a file-format detail into the data model. The `DataType` enum in `banks.py` is the canonical
type system. This refactor unifies on `DataType` and adds the convenience API clicknick needs.

---

## Part 1: Replace `type_code` with `DataType`

### 1a. Add private CDV code ↔ DataType bridge dicts

In `dataview.py`, keep `_CdvStorageCode` but add two private mappings used only by `load_cdv`/`save_cdv`:

```python
_CDV_CODE_TO_DATA_TYPE: dict[int, DataType] = {
    _CdvStorageCode.BIT: DataType.BIT,
    _CdvStorageCode.INT: DataType.INT,
    _CdvStorageCode.INT2: DataType.INT2,
    _CdvStorageCode.HEX: DataType.HEX,
    _CdvStorageCode.FLOAT: DataType.FLOAT,
    _CdvStorageCode.TXT: DataType.TXT,
}
_DATA_TYPE_TO_CDV_CODE: dict[DataType, int] = {v: k for k, v in _CDV_CODE_TO_DATA_TYPE.items()}
```

### 1b. `DataviewRow.type_code: int` → `DataviewRow.data_type: DataType | None`

- Field becomes `data_type: DataType | None = None` (None for empty rows)
- Remove `update_type_code()` method → replace with `update_data_type()` that uses `get_data_type_for_address()`
- `clear()` sets `data_type = None`

### 1c. Rename `get_type_code_for_address()` → `get_data_type_for_address()`

Returns `DataType | None`. Implementation: `parse_address()` → memory_type → `MEMORY_TYPE_TO_DATA_TYPE[memory_type]` (from `banks.py`, already exists).

Remove `MEMORY_TYPE_TO_CODE` dict (replaced by `banks.MEMORY_TYPE_TO_DATA_TYPE`).
Remove `CODE_TO_MEMORY_TYPES` dict (unused outside of this mapping).

### 1d. Conversion functions dispatch on `DataType`

All four functions change signature from `type_code: int` to `data_type: DataType`:
- `storage_to_datatype(value, data_type)` — dispatch on `DataType.BIT`, `DataType.INT`, etc.
- `datatype_to_storage(value, data_type)`
- `datatype_to_display(value, data_type)`
- `display_to_datatype(value, data_type)`

The switch statements change from `_CdvStorageCode.BIT` → `DataType.BIT` etc.

### 1e. `_validate_cdv_new_value` dispatches on `DataType`

Signature: `_validate_cdv_new_value(new_value, data_type, address, filename, row_num)`.

### 1f. `load_cdv` / `save_cdv` handle CDV code conversion at the boundary

- `load_cdv`: reads CDV integer → `_CDV_CODE_TO_DATA_TYPE[code]` → stores `DataType` on row
- `save_cdv`: reads `row.data_type` → `_DATA_TYPE_TO_CDV_CODE[data_type]` → writes CDV integer

### 1g. `check_cdv_file` uses `DataType`

Calls `get_data_type_for_address()` instead of `get_type_code_for_address()`.

---

## Part 2: Add New Value Convenience API

### 2a. `DataviewRow.new_value_display` property

```python
@property
def new_value_display(self) -> str:
    if not self.new_value or self.data_type is None:
        return ""
    native = storage_to_datatype(self.new_value, self.data_type)
    return datatype_to_display(native, self.data_type)
```

### 2b. `DataviewRow.set_new_value_from_display(display_str)` method

```python
def set_new_value_from_display(self, display_str: str) -> bool:
    if not display_str:
        self.new_value = ""
        return True
    if self.data_type is None:
        return False
    native = display_to_datatype(display_str, self.data_type)
    if native is None:
        return False
    self.new_value = datatype_to_storage(native, self.data_type)
    return True
```

### 2c. Standalone `validate_new_value()` function

```python
def validate_new_value(display_str: str, data_type: DataType) -> tuple[bool, str]:
    """Validate a user-entered display string for the New Value column."""
    if not display_str:
        return True, ""
    return validate_initial_value(display_str, data_type)
```

### 2d. `DataviewRow.validate_new_value()` method

```python
def validate_new_value(self, display_str: str) -> tuple[bool, str]:
    if not self.is_writable:
        return False, "Read-only address"
    if self.data_type is None:
        return False, "No address set"
    return validate_new_value(display_str, self.data_type)
```

---

## Part 3: Exports & Tests

### 3a. `__init__.py` — add exports

New public API:
- `get_data_type_for_address`
- `validate_new_value`
- `storage_to_datatype`, `datatype_to_storage`, `datatype_to_display`, `display_to_datatype`

### 3b. `test_dataview.py` — update all tests

- `TypeCode.BIT` → `DataType.BIT` etc. throughout
- `.type_code` → `.data_type` on all DataviewRow assertions
- Add new test classes:
  - `TestValidateNewValue` — standalone function
  - `TestDataviewRowValidateNewValue` — method on row
  - `TestNewValueDisplay` — property
  - `TestSetNewValueFromDisplay` — method

---

## Files Modified

| File | Summary |
|------|---------|
| `src/pyclickplc/dataview.py` | Core refactor + new API |
| `src/pyclickplc/__init__.py` | New exports |
| `tests/test_dataview.py` | Update all tests + new test classes |

---

## Verification

1. `make lint` — ruff + ty pass
2. `make test` — all tests pass (except 2 pre-existing T-bank failures in test_modbus.py)
3. Spot-check: `DataviewRow(address="DS1")` → `.update_data_type()` → `.data_type == DataType.INT`
4. Round-trip: `set_new_value_from_display("100")` → `.new_value_display == "100"`
5. Validation: `row.validate_new_value("abc")` → `(False, "Must be integer")`
