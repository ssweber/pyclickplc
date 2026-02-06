# clickclient Driver Specification

A Python driver for AutomationDirect CLICK Plcs using Modbus TCP/IP.

---

## Table of Contents

1. [Overview](#overview)
2. [Dependencies](#dependencies)
3. [Data Structures](#data-structures)
4. [Address Types & Configuration](#address-types--configuration)
5. [ClickClient Class](#clickclient-class)
6. [AddressAccessor Class](#addressaccessor-class)
7. [AddressInterface Class](#addressinterface-class)
8. [TagInterface Class](#taginterface-class)
9. [Tag System](#tag-system)
10. [Validation Rules](#validation-rules)
11. [Test Scenarios](#test-scenarios)

---

## Overview

The driver provides asynchronous communication with AutomationDirect CLICK Plcs over Ethernet. It abstracts Modbus protocol details and PLC-specific quirks, offering a clean Pythonic interface with clear separation between raw address access and named tag access.

### Key Features

- Async/await pattern using asyncio
- Context manager support (`async with`)
- Clear separation: `plc.addr` for raw addresses, `plc.tag` for named tags
- Pythonic memory bank accessors: `plc.df.read(1, 10)` for ranges
- Optional tag file loading for named access

### Interface Summary

```python
async with ClickClient('192.168.1.100') as plc:
    # Category accessors (recommended for raw addresses)
    value = await plc.df.read(1)           # Single value
    values = await plc.df.read(1, 10)      # Range (inclusive)
    await plc.df.write(1, 3.14)             # Write single
    await plc.df.write(1, [1.0, 2.0])       # Write consecutive
    
    # Address interface (string-based)
    value = await plc.addr.read('df1')
    values = await plc.addr.read('df1-df10')
    await plc.addr.write('df1', 3.14)
    
    # Tag interface (requires tag file)
    value = await plc.tag.read('MyTagName')
    values = await plc.tag.read()          # All tags
    await plc.tag.write('MyTagName', 3.14)
```

---

## Dependencies

- Requires an `AsyncioModbusClient` base class from `clickclient.util` that provides:
  - `read_coils(address: int, count: int) -> CoilResult` (CoilResult has `.bits: list[bool]`)
  - `write_coils(address: int, data: list[bool]) -> None`
  - `read_registers(address: int, count: int) -> list[int]`
  - `write_registers(address: int, data: list[int]) -> None`
  - Context manager support (`__aenter__`, `__aexit__`)
  - Constructor: `__init__(self, address: str, timeout: int)`

---

## Data Structures

### AddressType (dataclass, frozen=True)

Defines configuration for a PLC address type.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `base` | `int` | required | Modbus base address |
| `max_addr` | `int` | required | Maximum valid PLC address number |
| `data_type` | `str` | required | One of: `'bool'`, `'int16'`, `'int32'`, `'float'`, `'str'` |
| `width` | `int` | `1` | Registers per value (2 for 32-bit types) |
| `signed` | `bool` | `True` | Whether numeric type is signed |
| `sparse` | `bool` | `False` | True for X/Y addresses with gaps in addressing |
| `writable` | `frozenset[int] \| None` | `None` | If set, only these specific addresses are writable |

---

## Address Types & Configuration

The following address types must be supported:

### Boolean Types (Coils)

| Category | Base | Max | Notes |
|----------|------|-----|-------|
| `x` | 0 | 836 | Inputs, sparse (CPU: `X001-X016`, `X021-X036`; Expansion: `*01-*16`) |
| `y` | 8192 | 836 | Outputs, sparse (CPU: `Y001-Y016`, `Y021-Y036`; Expansion: `*01-*16`) |
| `c` | 16384 | 2000 | Control relays |
| `t` | 45057 | 500 | Timer status bits |
| `ct` | 49152 | 250 | Counter status bits |
| `sc` | 61440 | 1000 | System control relays, **limited writable**: {53, 55, 60, 61, 65, 66, 67, 75, 76, 120, 121} |

### Numeric Types (Registers)

| Category | Base | Max | Type | Width | Signed |
|----------|------|-----|------|-------|--------|
| `ds` | 0 | 4500 | int16 | 1 | Yes |
| `dd` | 16384 | 1000 | int32 | 2 | Yes |
| `dh` | 24576 | 500 | int16 | 1 | No (unsigned) |
| `df` | 28672 | 500 | float | 2 | N/A |
| `td` | 45056 | 500 | int16 | 1 | Yes |
| `ctd` | 49152 | 250 | int32 | 2 | Yes |
| `sd` | 61440 | 1000 | int16 | 1 | No, **limited writable**: {29, 31, 32, 34, 35, 36, 40, 41, 42, 50, 51, 60, 61, 106, 107, 108, 112, 113, 114, 140, 141, 142, 143, 144, 145, 146, 147, 214, 215} |

### Text Type

| Category | Base | Max | Notes |
|----------|------|-----|-------|
| `txt` | 36864 | 1000 | Packed ASCII, 2 chars per register |

---

## ClickClient Class

Inherits from `AsyncioModbusClient`.

### Class Attribute

```python
data_types: ClassVar[dict[str, str]]  # Maps bank -> data_type string
```

### Constructor

```python
def __init__(self, address: str, tag_filepath: str = '', timeout: int = 1)
```

- `address`: PLC IP address or DNS name
- `tag_filepath`: Optional path to tags CSV file
- `timeout`: Communication timeout in seconds

### Instance Attributes

- `tags: dict` - Loaded tag definitions (empty dict if no file provided)
- `addr: AddressInterface` - Interface for raw address operations
- `tag: TagInterface` - Interface for tag-based operations

### Pythonic Memory Bank Accessors

#### `__getattr__(name: str) -> AddressAccessor`

Returns an `AddressAccessor` for the given bank.

```python
plc.df  # Returns AddressAccessor for DF registers
plc.x   # Returns AddressAccessor for X inputs
```

- Raises `AttributeError` for names starting with `_`
- Raises `AttributeError` for unknown banks
- Accessors are cached and reused

---

## AddressAccessor Class

Provides method-based access to a specific address banks.

### Constructor

```python
def __init__(self, plc: ClickClient, bank: str)
```

### Methods

#### `async read(start: int, end: int | None = None) -> dict | bool | int | float | str`

Read single value or range.

```python
value = await plc.df.read(1)       # Single value at DF1
values = await plc.df.read(1, 10)  # Range DF1 through DF10 (inclusive)
```

**Returns:**
- Single address (`end` is `None`): Returns the value directly
- Range: Returns `{address: value}` dict (e.g., `{'df1': 0.0, 'df2': 1.0, ...}`)

#### `async write(start: int, data) -> None`

Write single value or list of values.

```python
await plc.df.write(1, 3.14)           # Single value to DF1
await plc.df.write(1, [1.0, 2.0])     # Writes DF1=1.0, DF2=2.0
```

- Validates data types
- Validates writability for restricted addresses

#### `__repr__() -> str`

Returns `<AddressAccessor(BANK, max=N)>`

---

## AddressInterface Class

Provides string-based access to raw PLC addresses.

### Constructor

```python
def __init__(self, plc: ClickClient)
```

### Methods

#### `async read(address: str) -> dict | bool | int | float | str`

Read values by address string.

```python
value = await plc.addr.read('df1')        # Single value
values = await plc.addr.read('df1-df10')  # Range as dict
```

**Returns:**
- Single address: Returns the value directly
- Range: Returns `{address: value}` dict (e.g., `{'df1': 0.0, 'df2': 1.0, ...}`)

#### `async write(address: str, data) -> None`

Write values by address string.

```python
await plc.addr.write('df1', 3.14)           # Single value
await plc.addr.write('df1', [1.0, 2.0])     # Writes DF1, DF2
```

- `data` can be a single value or a list
- List writes consecutively starting at address
- Validates data type matches address type
- Validates writability for restricted addresses

---

## TagInterface Class

Provides access via tag nicknames. Requires tags to be loaded.

### Constructor

```python
def __init__(self, plc: ClickClient)
```

### Methods

#### `async read(tag_name: str | None = None) -> dict | bool | int | float | str`

Read values by tag name.

```python
value = await plc.tag.read('MyTag')   # Single tag value
values = await plc.tag.read()         # All tags as dict
```

**Behavior:**
- If `tag_name` provided: returns the value for that tag
- If `tag_name` is `None`: returns all tagged values as `{tag_name: value}`
- Raises `KeyError` if tag not found
- Raises `ValueError` if called with `None` when no tags loaded

#### `async write(tag_name: str, data) -> None`

Write value by tag name.

```python
await plc.tag.write('MyTag', 3.14)
await plc.tag.write('MyTag', [1.0, 2.0])  # Writes consecutive addresses
```

- Resolves tag to underlying address, then writes
- Validates data type and writability

#### `read_all() -> dict`

Returns a copy of all tag definitions (synchronous).

```python
tags = plc.tag.read_all()
# {'MyTag': {'address': 'DF1', 'type': 'float'}, ...}
```

---

## Tag System

### CSV File Format

Tags are loaded from a CSV file exported from Click programming software.

**Expected columns:**
- `Nickname` - Tag name (skip if empty or starts with `_`)
- `Address` - PLC address (e.g., `DF1`, `X101`)
- `Modbus Address` - Numeric Modbus address
- `Address Comment` - Optional comment

**Note:** First line may have `## ` prefix that must be stripped.

### Tag Data Structure

```python
{
    'TagName': {
        'address': str,             # PLC address (e.g., 'DF1', 'X101')
        'type': str,                # Data type string
        'comment': str,             # Optional, only if present in CSV
    }
}
```

Tags are sorted PLC address.

---

## Validation Rules

### Address Parsing

Format: `BANK + NUMBER` or `BANK + NUMBER - BANK + NUMBER`

- Bank is case-insensitive
- Inter-bank ranges not supported (e.g., `DF1-DD5` is invalid)
- End must be greater than start

### Sparse Addressing (X, Y)

X and Y addresses map to physical hardware slots with gaps in the Modbus address space.

**X (inputs) addressing:**
- CPU slot 1: `X001-X016` → coils 0-15
- CPU slot 2: `X021-X036` → coils 16-31
- Expansion slots: `X101-X116`, `X201-X216`, ..., `X801-X816` → standard 16 addresses per hundred

**Y (outputs) addressing:**
- CPU slot 1: `Y001-Y016` → coils 0-15
- CPU slot 2: `Y021-Y036` → coils 16-31
- Expansion slots: `Y101-Y116`, `Y201-Y216`, ..., `Y801-Y816` → standard 16 addresses per hundred

**Valid addresses:**
- X: 001-016, 021-036, 101-116, 201-216, ..., 801-816
- Y: 001-016, 021-036, 101-116, 201-216, ..., 801-816

**Invalid addresses:** Anything not listed above (e.g., X017-X020, X037-X100, Y017-Y020, Y037-Y100)

> **Note:** While current CLICK CPU slots only have 8 inputs (X) and 6 outputs (Y), the full 16 addresses per slot are reserved in the Modbus space.
> 
> **TODO:** Should we have a default toggle to only read X001-X008/X021-X028 and Y001-Y006/Y021-Y026?

### Range Validation

For non-sparse types:
- Start must be in `[1, max_addr]`
- End (if provided) must be `> start` and `<= max_addr`

For sparse types (X, Y):
- Address must be in a valid range (see Sparse Addressing above)
- Validation must check CPU slots (000) differently from expansion slots (100+)

### Data Type Validation

| Type | Accepted Python Types |
|------|----------------------|
| `bool` | `bool` |
| `int16` | `int` |
| `int32` | `int` |
| `float` | `int` or `float` |
| `str` | `str` |

### Writability Validation

For `sc` and `sd` categories, only specific addresses are writable. Writing to non-writable addresses raises `ValueError`.

---

## Internal Behavior Specifications

### Modbus Address Calculation

#### Coils (Boolean Types)

**Standard coils:**
```
coil_address = base + index - 1
```

**Sparse coils (X):**
```
if index <= 16:                    # CPU slot 1: X001-X016
    coil_address = base + index - 1
elif index <= 36:                  # CPU slot 2: X021-X036
    coil_address = base + 16 + (index - 21)
else:                              # Expansion: X101+
    hundred = index // 100
    unit = index % 100
    coil_address = base + 32 * hundred + (unit - 1)
```

**Sparse coils (Y):**
```
if index <= 16:                    # CPU slot 1: Y001-Y016
    coil_address = base + index - 1
elif index <= 36:                  # CPU slot 2: Y021-Y036
    coil_address = base + 16 + (index - 21)
else:                              # Expansion: Y101+
    hundred = index // 100
    unit = index % 100
    coil_address = base + 32 * hundred + (unit - 1)
```

#### Registers (Numeric Types)

```
register_address = base + width * (index - 1)
count = width * number_of_values
```

### Register Packing/Unpacking

**int16:** Direct 16-bit value (signed or unsigned based on config)

**int32 and float:** Little-endian, split across 2 registers
- Pack: Use struct to convert to 4 bytes, then unpack as two 16-bit values
- Unpack: Pack as 16-bit values, then unpack as 32-bit type

### Text Handling

TXT registers pack 2 ASCII characters per register with byte-swapping quirk:
- Each register stores low byte first, high byte second
- Reading requires byte swapping within each register

**Odd/even alignment:** Must handle cases where start or end address falls in the middle of a register.

**Writing:** Must write complete registers; fetch adjacent byte if writing single character.

### Sparse Coil Handling

When reading X/Y ranges that span gaps or slot boundaries:
- Read the required coil range from Modbus
- Map coils back to PLC addresses, skipping invalid address ranges
- Gaps: 017-020, 037-100 (same for both X and Y)

When writing X/Y ranges that span gaps:
- Insert `False` padding values for the gaps between valid ranges

---

## Test Scenarios

### Construction

1. Create with IP address only
2. Create with IP and tag file
3. Create with custom timeout
4. Invalid tag file path raises appropriate error
5. `plc.addr` is an `AddressInterface` instance
6. `plc.tag` is a `TagInterface` instance

### AddressAccessor - Reading

#### Single Values
7. `plc.df.read(1)` reads single float
8. `plc.ds.read(1)` reads single int16
9. `plc.dd.read(1)` reads single int32
10. `plc.dh.read(1)` reads single unsigned int16
11. `plc.x.read(101)` reads single bool (sparse)
12. `plc.c.read(1)` reads single bool
13. `plc.txt.read(1)` reads single char

#### Ranges (Inclusive)
14. `plc.df.read(1, 10)` reads DF1 through DF10 (10 values)
15. `plc.c.read(1, 100)` reads C1 through C100
16. `plc.x.read(101, 116)` reads within single sparse hundred
17. `plc.x.read(101, 216)` reads across sparse boundary

#### Edge Cases
18. Read at max address for each type
19. `plc.df.read(500)` (max DF address)
20. `plc.df.read(500, 500)` single value via range syntax

### AddressAccessor - Writing

21. `plc.df.write(1, 3.14)` writes single float
22. `plc.ds.write(1, 42)` writes single int16
23. `plc.c.write(1, True)` writes single bool
24. `plc.df.write(1, [1.0, 2.0, 3.0])` writes consecutive
25. `plc.x.write(101, [True, False, True])` writes sparse

#### Restricted Addresses
26. `plc.sc.write(53, True)` succeeds (writable)
27. `plc.sc.write(1, True)` raises ValueError (not writable)
28. `plc.sd.write(29, 100)` succeeds (writable)
29. `plc.sd.write(1, 100)` raises ValueError (not writable)

### AddressInterface

30. `plc.addr.read('df1')` returns single value
31. `plc.addr.read('df1-df10')` returns dict with 10 entries
32. `plc.addr.read('DF1')` works (case-insensitive)
33. `plc.addr.write('df1', 3.14)` writes single
34. `plc.addr.write('df1', [1.0, 2.0])` writes consecutive
35. `plc.addr.read('invalid1')` raises ValueError

### TagInterface

36. `plc.tag.read('ExistingTag')` returns value
37. `plc.tag.read('NonexistentTag')` raises KeyError
38. `plc.tag.read()` returns all tagged values
39. `plc.tag.read()` with no tags loaded raises ValueError
40. `plc.tag.write('ExistingTag', value)` writes
41. `plc.tag.read_all()` returns copy of tag definitions

### Memory Bank Accessor Attributes

42. `plc.df` returns AddressAccessor
43. `plc.DF` returns same AddressAccessor (case-insensitive)
44. `plc._private` raises AttributeError
45. `plc.invalid_bank` raises AttributeError
46. `repr(plc.df)` returns `<AddressAccessor(DF, max=500)>`

### Validation Errors

47. `plc.addr.read('df0')` raises ValueError (below min)
48. `plc.addr.read('df501')` raises ValueError (above max)
49. `plc.addr.read('df10-df5')` raises ValueError (end <= start)
50. `plc.addr.read('df1-dd10')` raises ValueError (inter-bank)
51. `plc.x.read(17)` raises ValueError (invalid sparse: in gap 017-020)
52. `plc.x.read(37)` raises ValueError (invalid sparse: in gap 037-100)
53. `plc.df.write(1, 'string')` raises ValueError (wrong type)
54. `plc.ds.write(1, 3.14)` raises ValueError (float for int16)

### Text Special Cases

55. Read single char at odd position (`txt1`)
56. Read single char at even position (`txt2`)
57. Read range with odd start, odd end
58. Read range with even start, even end
59. Write string of odd length
60. Write string of even length

### Sparse Coil Special Cases

61. Read X in CPU slot 1 (`x001`, `x016`)
62. Read X in CPU slot 2 (`x021`, `x036`)
63. Read X in expansion slot (`x101`, `x116`)
64. Read X range within CPU slot 1 (`x001-x010`)
65. Read X range spanning CPU slots (`x010-x025`)
66. Read X range spanning to expansion (`x030-x105`)
67. Read Y in CPU slot 1 (`y001`, `y016`)
68. Read Y in CPU slot 2 (`y021`, `y036`)
69. Read Y in expansion slot (`y101`, `y116`)
70. Read Y range spanning CPU slots (`y010-y025`)
71. Write X values spanning CPU slot gap (`x014-x023`)
72. Write Y values spanning CPU slot gap (`y014-y023`)
73. Validate X rejects `x017`, `x020`, `x037`, `x100`
74. Validate Y rejects `y017`, `y020`, `y037`, `y100`

---

## Error Messages

Provide clear, actionable error messages:

- `"'{bank}' is not a supported address type."`
- `"{BANK} address must be *01-*16."` (for sparse)
- `"{BANK} must be in [1, {max}]"`
- `"{BANK} end must be > start and <= {max}"`
- `"Inter-bank ranges are unsupported."`
- `"End address must be greater than start address."`
- `"Expected {address} as {expected_type}, got {actual_type}."`
- `"{BANK}{index} is not writable."`
- `"Tag '{name}' not found. Available: [...]"`
- `"No tags loaded. Provide a tag file or specify a tag name."`

---

## Constants

### STRUCT_FORMATS

```python
{'int16': 'h', 'int32': 'i', 'float': 'f'}
```

### TYPE_MAP

```python
{'bool': bool, 'int16': int, 'int32': int, 'float': (int, float), 'str': str}
```
