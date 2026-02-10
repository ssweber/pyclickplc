# ClickServer Specification

A Modbus TCP server that simulates an AutomationDirect CLICK PLC. Incoming Modbus requests are reverse-mapped to PLC addresses and routed to a user-supplied DataProvider.

---

## Table of Contents

1. [Overview](#overview)
2. [Dependencies](#dependencies)
3. [Shared Core Module](#shared-core-module)
4. [DataProvider Protocol](#dataprovider-protocol)
5. [MemoryDataProvider](#memorydataprovider)
6. [ClickServer Class](#clickserver-class)
7. [Internal Behavior](#internal-behavior)
8. [Validation Rules](#validation-rules)
9. [Error Handling](#error-handling)
10. [Test Scenarios](#test-scenarios)

---

## Overview

### Key Features

- Async server using pymodbus
- User-supplied DataProvider decouples storage from Modbus transport
- Full CLICK PLC Modbus address space (coils and registers)
- Context manager support (`async with`)
- Reference `MemoryDataProvider` included for testing and simple use cases

### Interface Summary

```python
from pyclickplc.server import ClickServer, MemoryDataProvider

# Simple in-memory simulator
provider = MemoryDataProvider()
provider.set('DF1', 3.14)
provider.set('X001', True)

async with ClickServer(provider, port=5020) as server:
    await server.serve_forever()
```

```python
# Integration test with ClickClient
provider = MemoryDataProvider()
provider.set('DF1', 3.14)

async with ClickServer(provider, port=5020) as server:
    async with ClickClient('localhost:5020') as plc:
        value = await plc.df.read(1)   # Returns 3.14
        await plc.ds.write(1, 42)

        stored = provider.get('DS1')   # Returns 42
```

### Request Flow

```
Modbus Client                    ClickServer                      DataProvider
     |                               |                                |
     |--- Read registers 28672-28675 -->                              |
     |                               |-- reverse map 28672 -> DF1 --> |
     |                               |-- reverse map 28674 -> DF2 --> |
     |                               |                    read('DF1') -->
     |                               |                 <-- 3.14 ------|
     |                               |                    read('DF2') -->
     |                               |                 <-- 0.0 -------|
     |                               |-- pack [3.14, 0.0] as 4 regs  |
     |<-- [reg, reg, reg, reg] ------|                                |
```

---

## Dependencies

### Runtime

- `pymodbus` — Modbus TCP server implementation
- `pyclickplc.core` — Shared address definitions, mapping, and packing logic

### Shared Core (`pyclickplc.core`)

The following components are shared between ClickClient and ClickServer. They are currently defined in the [ClickDevice Spec](CLICKDEVICE_SPEC.md) and must be extracted into a shared core module:

- `AddressType` dataclass (frozen)
- All address type configurations (x, y, c, t, ct, sc, ds, dd, dh, df, td, ctd, sd, txt)
- Address string parsing: `parse_address(address: str) -> tuple[str, int]`
- Forward mapping: PLC address → Modbus address
- Register packing/unpacking (struct-based conversion for int16, int32, float)
- Text handling (packed ASCII with byte-swapping)
- Sparse addressing logic (X/Y coil slot mapping)
- Validation rules (range checks, sparse gap checks)
- Constants: `STRUCT_FORMATS`, `TYPE_MAP`

The server adds one new core concern: **reverse mapping** (Modbus address → PLC address), which is the inverse of the forward mapping.

---

## DataProvider Protocol

The DataProvider is the user-supplied backend that stores and retrieves PLC values. The server translates Modbus requests into DataProvider calls.

```python
class DataProvider(Protocol):
    async def read(self, address: str) -> bool | int | float | str:
        """Read a single PLC address.

        Args:
            address: Uppercase PLC address string (e.g., 'DF1', 'X001', 'DS100')

        Returns:
            Current value. Type must match the address bank:
            - bool for X, Y, C, T, CT, SC
            - int for DS, DD, DH, TD, CTD, SD
            - float for DF
            - str for TXT (blank or single character)
        """
        ...

    async def write(self, address: str, value: bool | int | float | str) -> None:
        """Write a value to a single PLC address.

        Args:
            address: Uppercase PLC address string
            value: Value to write. Type and range must match the address bank.
        """
        ...
```

### Contract

- The server calls `read()`/`write()` once per PLC address per Modbus request. A Modbus read of 10 consecutive DF registers results in 5 `read()` calls (DF is width-2).
- Address strings are always uppercase with no spaces: `'DF1'`, `'X001'`, `'DS100'`.
- The server validates writability (SC/SD restrictions) **before** calling `write()`. The DataProvider does not need to enforce writability.
- The server handles all Modbus packing/unpacking. The DataProvider only deals in native Python types.
- `MemoryDataProvider` enforces strict runtime value validation for `write()` and `set()`.
- If `read()` returns a value of the wrong type, behavior is undefined.

---

## MemoryDataProvider

Reference implementation that stores values in an in-memory dictionary.

```python
class MemoryDataProvider:
    def __init__(self) -> None: ...

    async def read(self, address: str) -> bool | int | float | str: ...
    async def write(self, address: str, value: bool | int | float | str) -> None: ...

    # Synchronous convenience methods for setup and inspection
    def set(self, address: str, value: bool | int | float | str) -> None: ...
    def get(self, address: str) -> bool | int | float | str: ...
    def bulk_set(self, values: dict[str, bool | int | float | str]) -> None: ...
```

### Behavior

- Values stored in `dict[str, bool | int | float | str]`
- `read()` returns stored value, or a **type-appropriate default** if never written:

| Bank Data Type | Default |
|----------------|---------|
| `bool` (X, Y, C, T, CT, SC) | `False` |
| `int16` (DS, TD) | `0` |
| `int32` (DD, CTD) | `0` |
| `int16` unsigned (DH, SD) | `0` |
| `float` (DF) | `0.0` |
| `str` (TXT) | `'\x00'` |

- `write()` validates value type/range for the target bank, then stores it
- `set()` / `get()` are synchronous wrappers for test setup and inspection
- `bulk_set()` calls `set()` for each entry
- Address strings are normalized to uppercase internally
- Determines the bank's data type from the shared core address type configuration

---

## ClickServer Class

### Constructor

```python
def __init__(self, provider: DataProvider, host: str = 'localhost', port: int = 502)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | `DataProvider` | required | User-supplied value storage backend |
| `host` | `str` | `'localhost'` | Interface to bind (`'localhost'` for local-only, `'0.0.0.0'` for all) |
| `port` | `int` | `502` | TCP port (502 is Modbus default; use 5020+ for non-root testing) |

### Instance Attributes

- `provider: DataProvider` — The value storage backend
- `host: str` — Bound interface
- `port: int` — Bound port

### Lifecycle Methods

```python
async def start(self) -> None:
    """Start the Modbus TCP server. Returns immediately; server runs in background."""

async def stop(self) -> None:
    """Stop the server gracefully."""

async def serve_forever(self) -> None:
    """Start the server and block until stop() is called or task is cancelled."""
```

### Context Manager

```python
async with ClickServer(provider, port=5020) as server:
    # server.start() has been called
    ...
# server.stop() is called on exit
```

- `__aenter__` calls `start()`, returns `self`
- `__aexit__` calls `stop()`

---

## Internal Behavior

### Reverse Mapping: Modbus Address → PLC Address

The inverse of the driver's forward mapping. Given a raw Modbus coil or register number, determine the PLC bank and index.

#### Coil Reverse Mapping

Coil banks (from shared core):

| Bank | Base | Address Space Size |
|------|------|--------------------|
| x | 0 | 832 (26 slots * 32) |
| y | 8192 | 832 |
| c | 16384 | 2000 |
| t | 45057 | 500 |
| ct | 49152 | 250 |
| sc | 61440 | 1000 |

```
For each coil bank in [x, y, c, t, ct, sc]:
    end = base + address_space_size
    if base <= coil_address < end:
        offset = coil_address - base
        if bank.sparse:
            return reverse_sparse(bank, offset)
        else:
            index = offset + 1
            return f"{BANK}{index}"
return None  # Unmapped
```

#### Sparse Coil Reverse Mapping (X, Y)

```
offset = coil_address - base

if offset < 16:                         # CPU slot 1
    index = offset + 1                  # *001-*016

elif offset < 32:                       # CPU slot 2
    index = 21 + (offset - 16)         # *021-*036

else:                                   # Expansion slots
    hundred = offset // 32              # Slot number (1-8)
    unit = (offset % 32) + 1            # Position within slot
    if unit > 16:
        return None                     # Gap — unmapped
    index = hundred * 100 + unit        # *101-*116, *201-*216, ...

return f"{BANK}{index:03d}"
```

#### Register Reverse Mapping

Register banks (from shared core):

| Bank | Base | Max | Width | End Address |
|------|------|-----|-------|-------------|
| ds | 0 | 4500 | 1 | 4500 |
| dd | 16384 | 1000 | 2 | 18384 |
| dh | 24576 | 500 | 1 | 25076 |
| df | 28672 | 500 | 2 | 29672 |
| txt | 36864 | 1000 | 1 | 37864 |
| td | 45056 | 500 | 1 | 45556 |
| ctd | 49152 | 250 | 2 | 49652 |
| sd | 61440 | 1000 | 1 | 62440 |

```
For each register bank in [ds, dd, dh, df, txt, td, ctd, sd]:
    end = base + width * max_addr
    if base <= register_address < end:
        offset = register_address - base
        index = offset // width + 1
        reg_position = offset % width   # 0 = first register, 1 = second (width-2 only)
        return (bank, index, reg_position)
return None  # Unmapped
```

> **Note:** `reg_position` is needed for FC 06 (write single register) on width-2 types. See [Register Write Handling](#register-write-handling).

#### Unmapped Addresses

Modbus addresses that do not map to any PLC bank return default values without calling the DataProvider:
- Unmapped coils → `False`
- Unmapped registers → `0`

This matches real CLICK PLC behavior for undefined address space.

### Supported Function Codes

| FC | Name | Supported |
|----|------|-----------|
| 01 | Read Coils | Yes |
| 02 | Read Discrete Inputs | Yes (same as FC 01) |
| 03 | Read Holding Registers | Yes |
| 04 | Read Input Registers | Yes (same as FC 03) |
| 05 | Write Single Coil | Yes |
| 06 | Write Single Register | Yes |
| 15 | Write Multiple Coils | Yes |
| 16 | Write Multiple Registers | Yes |

> **Note:** The CLICK PLC does not distinguish between holding/input registers or coils/discrete inputs. FC 01 and FC 02 behave identically, as do FC 03 and FC 04.

### Coil Read Handling (FC 01/02)

1. For each coil in `[address, address + count)`:
   a. Reverse-map to PLC address
   b. If mapped: call `provider.read(plc_address)` → `bool`
   c. If unmapped (gap or undefined): return `False`
2. Return list of bool values

### Coil Write Handling

**FC 05 — Write Single Coil:**

1. Reverse-map coil address to PLC address
2. If unmapped: raise Modbus `IllegalAddress` exception
3. Validate writability (SC restrictions)
4. Call `provider.write(plc_address, bool_value)`

**FC 15 — Write Multiple Coils:**

1. For each coil in the write range:
   a. Reverse-map to PLC address
   b. If unmapped (sparse gap): skip silently
   c. If mapped but not writable: raise Modbus `IllegalAddress` exception
   d. Call `provider.write(plc_address, value)`

### Register Read Handling (FC 03/04)

1. For each register in `[address, address + count)`:
   a. Reverse-map to `(bank, index, reg_position)`
   b. If unmapped: yield `0`
   c. If mapped: collect into groups by `(bank, index)`
2. For each unique PLC address, call `provider.read(plc_address)` once
3. Pack each value into register(s) using shared core packing logic
4. Return concatenated register values in order

**Optimization:** When reading a range of consecutive addresses within one bank, the server can determine the full set of PLC addresses up front and batch the reads.

### Register Write Handling

**FC 16 — Write Multiple Registers:**

1. Determine which PLC addresses are covered by the write range
2. Group registers by PLC address
3. For each **complete** PLC address (all `width` registers present):
   a. Validate writability (SD restrictions)
   b. Unpack value from register(s) using shared core logic
   c. Call `provider.write(plc_address, unpacked_value)`
4. For **partial** PLC addresses at boundaries (width-2 type where only 1 register is in the write range):
   a. Read current value via `provider.read(plc_address)`
   b. Replace the affected register half
   c. Unpack the combined registers
   d. Call `provider.write(plc_address, new_value)`

**FC 06 — Write Single Register:**

FC 06 writes exactly one 16-bit register.

- **Width-1 types** (DS, DH, TXT, TD, SD): Unpack and write directly.
- **Width-2 types** (DD, DF, CTD): Read-modify-write:
  1. Call `provider.read(plc_address)` to get current value
  2. Pack current value into 2 registers
  3. Replace the register at `reg_position` with the new value
  4. Unpack the modified pair
  5. Call `provider.write(plc_address, new_value)`

### pymodbus Integration

The server uses pymodbus's `StartAsyncTcpServer` with a custom `ModbusSlaveContext`. The recommended implementation approach is a custom datastore (subclass of `ModbusBaseSlaveContext` or equivalent) that overrides value access to route through the reverse mapping and DataProvider.

---

## Validation Rules

### Writability

The server enforces writability restrictions **before** calling `provider.write()`:

- **SC coils:** Only addresses in `{53, 55, 60, 61, 65, 66, 67, 75, 76, 120, 121}` are writable
- **SD registers:** Only addresses in `{29, 31, 32, 34, 35, 36, 40, 41, 42, 50, 51, 60, 61, 106, 107, 108, 112, 113, 114, 140, 141, 142, 143, 144, 145, 146, 147, 214, 215}` are writable

Writing to a non-writable SC or SD address raises a Modbus `IllegalAddress` exception.

All other banks are fully writable within their address range.

### Address Range

The server accepts Modbus requests for any valid address in each bank's range. Requests beyond a bank's address space that don't fall in another bank return defaults (reads) or are rejected (writes).

### Runtime Value Validation (MemoryDataProvider)

`MemoryDataProvider` rejects invalid runtime values with `ValueError`.

| Data Type | Banks | Required Value |
|-----------|-------|----------------|
| `bool` | X, Y, C, T, CT, SC | `bool` |
| `int16` signed | DS, TD, SD | `int` in `[-32768, 32767]` |
| `int32` signed | DD, CTD | `int` in `[-2147483648, 2147483647]` |
| `WORD` unsigned | DH, XD, YD | `int` in `[0, 65535]` |
| `float32` | DF | finite `int`/`float` representable as float32 |
| `text` | TXT | blank (`""`) or single ASCII `str` character |

Additional rules:

- Bool values are rejected for numeric banks (`bool` is not accepted as `int`).
- `NaN`, `+Inf`, and `-Inf` are invalid for `DF`.
- TXT values may be blank (`""`) or exactly one character with ASCII code `0..127`.
- TXT space (`" "`) is valid.

---

## Error Handling

### Modbus Exceptions

The server returns standard Modbus exception responses:

| Condition | Modbus Exception |
|-----------|-----------------|
| Write to unmapped address | `IllegalAddress` (0x02) |
| Write to non-writable SC/SD | `IllegalAddress` (0x02) |
| DataProvider raises exception | `SlaveDeviceFailure` (0x04) |

### DataProvider Errors

If the DataProvider raises an exception during `read()` or `write()`, the server:
1. Catches the exception
2. Returns a Modbus `SlaveDeviceFailure` exception to the client
3. Logs the error (if logging is configured)

The server never crashes due to a DataProvider error.

This includes `MemoryDataProvider` validation failures (`ValueError`).

---

## Test Scenarios

### Construction

1. Create with MemoryDataProvider and default host/port
2. Create with custom host and port
3. Provider is stored as instance attribute

### Reverse Mapping — Coils

4. Coil `0` → `X001`
5. Coil `15` → `X016`
6. Coil `16` → `X021`
7. Coil `31` → `X036`
8. Coil `32` → `X101`
9. Coil `47` → `X116`
10. Coil `64` → `X201`
11. Coil `8192` → `Y001`
12. Coil `8208` → `Y021`
13. Coil `8224` → `Y101`
14. Coil `16384` → `C1`
15. Coil `16385` → `C2`
16. Coil `18383` → `C2000`
17. Coil `45057` → `T1`
18. Coil `49152` → `CT1`
19. Coil `61440` → `SC1`

### Reverse Mapping — Sparse Gaps

20. Coil `48` (X slot 1, unit 17) → unmapped
21. Coil `8240` (Y slot 1, unit 17) → unmapped
22. Verify all gap coils in CPU slot boundary (16-31 maps to *021-*036, not gaps)

### Reverse Mapping — Registers

23. Register `0` → `DS1`
24. Register `4499` → `DS4500`
25. Register `16384` → `DD1`
26. Register `16386` → `DD2` (width-2, second value)
27. Register `16385` → `DD1`, reg_position=1 (second register of DD1)
28. Register `24576` → `DH1`
29. Register `25075` → `DH500`
30. Register `28672` → `DF1`
31. Register `28674` → `DF2`
32. Register `36864` → `TXT1`
33. Register `45056` → `TD1`
34. Register `49152` → `CTD1`
35. Register `49154` → `CTD2`
36. Register `61440` → `SD1`

### Reverse Mapping — Unmapped

37. Coil `10000` (between Y and C) → unmapped, returns `False`
38. Register `5000` (between DS and DD) → unmapped, returns `0`

### Read via Modbus — Coils

39. Read single coil (C1) → `provider.read('C1')` called, bool returned
40. Read coil range (C1-C10) → `provider.read()` called 10 times
41. Read sparse coil (X001) → correct reverse mapping and read
42. Read sparse range spanning CPU slots (X010-X025) → correct gap handling
43. Read unmapped coil → `False` returned, provider not called

### Read via Modbus — Registers

44. Read single int16 register (DS1) → correct value
45. Read single unsigned int16 (DH1) → correct unsigned value
46. Read width-2 float (DF1) → 2 registers packed correctly
47. Read width-2 int32 (DD1) → 2 registers packed correctly
48. Read register range (DF1-DF5) → 10 registers, 5 provider calls
49. Read unmapped register → `0` returned, provider not called

### Write via Modbus — Coils

50. FC 05: Write single coil (C1=True) → `provider.write('C1', True)` called
51. FC 15: Write multiple coils (C1-C5) → 5 `provider.write()` calls
52. FC 05: Write unmapped coil → Modbus `IllegalAddress`
53. FC 05: Write non-writable SC (SC1) → Modbus `IllegalAddress`
54. FC 05: Write writable SC (SC53) → succeeds
55. FC 15: Write sparse coils spanning gap → gap addresses skipped

### Write via Modbus — Registers

56. FC 06: Write single int16 register (DS1=42) → `provider.write('DS1', 42)` called
57. FC 16: Write multiple registers for consecutive DS values
58. FC 16: Write float (DF1=3.14) → 2 registers unpacked to float, `provider.write('DF1', 3.14)` called
59. FC 16: Write int32 (DD1=100000) → 2 registers unpacked correctly
60. FC 06: Write single register of width-2 type (DF1, first half) → read-modify-write
61. FC 16: Partial write at boundary of width-2 type → read-modify-write for partial value
62. FC 06: Write unmapped register → Modbus `IllegalAddress`
63. FC 06: Write non-writable SD (SD1) → Modbus `IllegalAddress`
64. FC 06: Write writable SD (SD29) → succeeds

### MemoryDataProvider

65. Read unset bool address → `False`
66. Read unset int address → `0`
67. Read unset float address → `0.0`
68. Read unset text address → `'\x00'`
69. Write then read returns written value
70. `set()` then `get()` returns value (sync)
71. `set()` then `read()` returns value (async reads sync-set data)
72. `bulk_set()` sets multiple values
73. Address normalization: `set('df1', 1.0)` then `get('DF1')` returns `1.0`

MemoryDataProvider value validation:

- Reject out-of-range int16 (`set('DS1', 32768)`)
- Reject out-of-range int32 (`set('DD1', 2147483648)`)
- Reject out-of-range WORD (`set('DH1', -1)` or `set('DH1', 65536)`)
- Reject non-finite float (`set('DF1', float('nan'))`, `float('inf')`)
- Reject invalid TXT (`set('TXT1', 'AB')`, non-ASCII)
- Allow space TXT (`set('TXT1', ' ')`)
- Allow blank TXT (`set('TXT1', '')`)
- Reject bool for numeric banks (`set('DS1', True)`)

### Server Lifecycle

74. Context manager: server starts and stops cleanly
75. Explicit `start()` / `stop()` lifecycle
76. `serve_forever()` blocks until `stop()` called from another task
77. Multiple start/stop cycles work correctly
78. Stop while no clients connected
79. Stop while client connected — connection closed gracefully

### DataProvider Error Handling

80. Provider `read()` raises → Modbus `SlaveDeviceFailure` returned
81. Provider `write()` raises → Modbus `SlaveDeviceFailure` returned
82. Server continues operating after provider error

### Integration (ClickClient ↔ ClickServer)

83. Driver writes DF, provider sees value via `get()`
84. Provider `set()` value, driver reads it
85. Float round-trip preserves value (within float32 precision)
86. Int32 round-trip preserves value
87. Int16 signed round-trip (positive and negative)
88. Int16 unsigned (DH) round-trip
89. Bool round-trip
90. Text round-trip
91. Sparse coil (X/Y) round-trip
92. Read range via driver matches individual provider values

---

## Summary: Shared vs. Server-Specific

| Component | Location |
|-----------|----------|
| AddressType, bank configs, constants | `pyclickplc.core` (shared) |
| Address parsing, validation | `pyclickplc.core` (shared) |
| Forward mapping (PLC → Modbus) | `pyclickplc.core` (shared) |
| Register packing/unpacking | `pyclickplc.core` (shared) |
| Sparse addressing, text handling | `pyclickplc.core` (shared) |
| **Reverse mapping (Modbus → PLC)** | `pyclickplc.core` (shared, new) |
| DataProvider protocol | `pyclickplc.server` |
| MemoryDataProvider | `pyclickplc.server` |
| ClickServer class | `pyclickplc.server` |
| pymodbus server integration | `pyclickplc.server` |
