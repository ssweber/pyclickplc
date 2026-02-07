# pyclickplc Architecture Plan

High-level plan for the `pyclickplc` package — shared CLICK PLC knowledge consumed by ClickNick (GUI editor), pyrung (simulation), and standalone Modbus client/server tooling.

---

## What the Package Does

| Capability | Consumer(s) |
|------------|-------------|
| PLC bank definitions & data types | All |
| Address parsing & formatting | All |
| Nickname CSV read/write | ClickNick, pyrung |
| BlockTag parsing & computation | ClickNick, pyrung |
| DataView CDV file I/O | ClickNick |
| Nickname/field validation | ClickNick |
| Modbus client (ClickClient) | pyrung, standalone |
| Modbus server (ClickServer) | pyrung (testing), standalone |

---

## Module Layout

```
pyclickplc/
├── __init__.py          # Public API re-exports
├── banks.py             # Bank definitions, DataType enum, address ranges
├── addresses.py         # Address parsing, formatting, AddressRecord
├── validation.py        # CLICK field validation rules
├── blocks.py            # BlockTag parsing, BlockRange, MemoryBankMeta
├── nicknames.py         # Nickname CSV read/write
├── dataview.py          # DataView .cdv file I/O
├── modbus.py            # Modbus mapping, register packing, sparse logic
├── client.py            # ClickClient (Modbus TCP client)
└── server.py            # ClickServer (Modbus TCP server)
```

---

## Module Responsibilities

### `banks.py` — Foundation (zero dependencies)

The single source of truth for "what memory banks exist in a CLICK PLC."

From ClickNick extraction:
- `DataType` enum (`BIT`, `INT`, `INT2`, `FLOAT`, `HEX`, `TXT`)
- `ADDRESS_RANGES` — PLC address ranges per bank
- `MEMORY_TYPE_BASES` — unique key offsets per bank (for `addr_key`)
- `MEMORY_TYPE_TO_DATA_TYPE` — which DataType each bank uses
- `DATA_TYPE_DISPLAY` / `DATA_TYPE_HINTS` — display strings
- `DEFAULT_RETENTIVE` — retentive defaults per bank
- `INTERLEAVED_PAIRS` — T↔TD, CT↔CTD pairing
- `BIT_ONLY_TYPES` — banks that are coil-only

New:
- `BankConfig` frozen dataclass combining range + data type + properties into one object
- Dict of all `BankConfig` instances keyed by bank name
- **Sparse addressing as PLC knowledge** — which X/Y addresses are valid is a hardware fact, not a protocol detail. `BankConfig` expresses valid sub-ranges for sparse banks so that *both* ClickNick (display filtering) and the Modbus layer (coil mapping) use the same source of truth.

This module has **no** Modbus knowledge. It describes the PLC, not the protocol.

### `addresses.py` — Address Parsing & Formatting

Depends on: `banks.py`

The one parser that everyone uses. Handles all PLC address string operations.

From ClickNick extraction:
- `get_addr_key(memory_type, address)` → unique int key
- `parse_addr_key(addr_key)` → `(memory_type, address)`
- `format_address_display(memory_type, address)` → `"X001"`, `"DS100"`
- `parse_address(display_str)` → `(memory_type, mdb_address)` — strict, raises ValueError
- `normalize_address(address_str)` → canonical form
- XD/YD helpers (`is_xd_yd_upper_byte`, etc.)
- `AddressRecord` frozen dataclass (shared between ClickNick and pyrung)

One unified `parse_address` returns MDB indices for all banks (including XD/YD). Used everywhere: Modbus layer, client, server, nicknames, dataview.

### `validation.py` — CLICK Validation Rules

Depends on: `banks.py`

From ClickNick extraction:
- `NICKNAME_MAX_LENGTH`, `COMMENT_MAX_LENGTH`
- `FORBIDDEN_CHARS`, `RESERVED_NICKNAMES`
- Numeric range constants (`INT_MIN/MAX`, etc.)
- `validate_nickname(name)` → `(valid, error)`
- `validate_initial_value(value, data_type)` → `(valid, error)`
- `validate_comment(comment)` → `(valid, error)`

### `blocks.py` — BlockTag System

Depends on: `banks.py`, `addresses.py`

From ClickNick extraction (post Phase 0 simplification):
- `BlockTag` dataclass
- `BlockRange` dataclass
- `MemoryBankMeta` dataclass
- Parsing: `parse_block_tag`, `format_block_tag`, `extract_block_name`, etc.
- Computation: `compute_all_block_ranges`, `find_paired_tag_index`
- Validation: `validate_block_span`
- `extract_bank_metas(records)` → discovered bank metadata

### `nicknames.py` — CSV Read/Write

Depends on: `banks.py`, `addresses.py`, `blocks.py`, `validation.py`

From ClickNick extraction:
- `CSV_COLUMNS`, `ADDRESS_PATTERN`
- `DATA_TYPE_STR_TO_CODE` / `DATA_TYPE_CODE_TO_STR`
- `read_csv(path)` → `dict[int, AddressRecord]`
- `read_mdb_csv(path)` → `dict[int, AddressRecord]`
- `write_csv(path, records)` → count

### `dataview.py` — DataView CDV File I/O

Depends on: `banks.py`, `addresses.py`

From ClickNick extraction (`cdv_file.py`):
- `read_cdv(path)` → list of DataView rows
- `write_cdv(path, rows)` → None
- CDV format details: UTF-16 LE CSV with specific column layout

### `modbus.py` — Modbus Protocol Mapping

Depends on: `banks.py`, `addresses.py`

New code (from CLICKDEVICE_SPEC / CLICKSERVER_SPEC):
- `ModbusMapping` frozen dataclass — Modbus-specific properties per bank:
  - `base: int` — Modbus base address
  - `is_coil: bool` — coil vs register
  - `width: int` — registers per value (2 for float/int32)
  - `signed: bool`
  - `writable: frozenset[int] | None`
- `MODBUS_MAPPINGS: dict[str, ModbusMapping]` — all bank mappings (including XD/YD once verified)
- Forward mapping: `plc_to_modbus(bank, index)` → Modbus address
- Reverse mapping: `modbus_to_plc(address, is_coil)` → `(bank, index)` or `None`
- Register packing: `pack_value(value, data_type)` → `list[int]`
- Register unpacking: `unpack_value(registers, data_type)` → value
- Sparse coil offset calculation (uses `valid_ranges` from `BankConfig` for the slot structure, adds the Modbus-specific offset math)
- Text register handling (packed ASCII with byte-swap)
- `STRUCT_FORMATS` constant

Note: Sparse addressing *validity* (which addresses exist) is in `banks.py`. Sparse *Modbus offset calculation* (mapping valid addresses to sequential coil numbers) is here.

### `client.py` — ClickClient

Depends on: `modbus.py`, `nicknames.py` (optional, for tag loading)

From CLICKDEVICE_SPEC:
- `ClickClient` class (async Modbus TCP client)
- `AddressAccessor` — `plc.df.read(1)`
- `AddressInterface` — `plc.addr.read('df1')`
- `TagInterface` — `plc.tag.read('MyTag')`
- Context manager, tag CSV loading

### `server.py` — ClickServer

Depends on: `modbus.py`

From CLICKSERVER_SPEC:
- `DataProvider` protocol
- `MemoryDataProvider` reference implementation
- `ClickServer` class (async Modbus TCP server)
- Request handling (FC 01-06, 15-16)

---

## Dependency Graph

```
banks.py                          ← no deps (foundation)
    ↑
    ├── validation.py
    ├── addresses.py
    │       ↑
    │       ├── blocks.py
    │       ├── dataview.py
    │       ├── modbus.py
    │       │       ↑
    │       │       ├── client.py ──→ nicknames.py
    │       │       └── server.py
    │       └── nicknames.py ──→ blocks.py, validation.py
```

No cycles. Clean layering.

---

## Key Design Decision: DataType Reconciliation

**Problem:** The extraction plan uses `DataType(IntEnum)` with values `BIT=0, INT=1, INT2=2, FLOAT=3, HEX=4, TXT=6`. The Modbus specs use string types `'bool', 'int16', 'int32', 'float', 'str'`.

**Decision:** `DataType` enum is the single source of truth (it matches CLICK software's own type system). The Modbus layer derives protocol properties from it:

```python
# banks.py
class DataType(IntEnum):
    BIT = 0       # bool coil
    INT = 1       # signed 16-bit register
    INT2 = 2      # signed 32-bit (2 registers)
    FLOAT = 3     # 32-bit float (2 registers)
    HEX = 4       # unsigned 16-bit register
    TXT = 6       # packed ASCII text

# modbus.py derives from DataType:
MODBUS_WIDTH = {
    DataType.BIT: 1, DataType.INT: 1, DataType.INT2: 2,
    DataType.FLOAT: 2, DataType.HEX: 1, DataType.TXT: 1,
}
MODBUS_SIGNED = {
    DataType.INT: True, DataType.INT2: True,
    DataType.HEX: False, DataType.FLOAT: False,
}
STRUCT_FORMATS = {
    DataType.INT: 'h', DataType.INT2: 'i',
    DataType.FLOAT: 'f', DataType.HEX: 'H',
}
```

The Modbus spec's `data_types` class attribute and `TYPE_MAP` constant become derived from `DataType` rather than independent string-based maps.

---

## Key Design Decision: Bank Configuration

**Problem:** ClickNick has `ADDRESS_RANGES` (flat tuples). The Modbus spec has `AddressType` (dataclass with Modbus fields). Both describe the same banks differently. Sparse banks (X, Y) need richer representation than a flat min/max — both ClickNick (to display only valid addresses) and the Modbus layer (for coil mapping) need to know the valid sub-ranges.

**Decision:** Two-layer config. `BankConfig` in `banks.py` for PLC-level properties. `ModbusMapping` in `modbus.py` for protocol-level properties. Linked by bank name.

```python
# banks.py — PLC knowledge
@dataclass(frozen=True)
class BankConfig:
    name: str                   # "DS", "DF", "X", etc.
    min_addr: int               # Usually 1 (0 for XD/YD)
    max_addr: int               # e.g., 4500 for DS
    data_type: DataType
    valid_ranges: tuple[tuple[int, int], ...] | None = None  # Sparse banks only
    interleaved_with: str | None = None  # T↔TD, CT↔CTD

BANKS: dict[str, BankConfig] = { ... }
```

For non-sparse banks, `valid_ranges` is `None` (all addresses in `[min_addr, max_addr]` are valid).
For sparse banks (X, Y), `valid_ranges` enumerates the hardware slots:

```python
# X and Y share the same slot structure
_SPARSE_RANGES = (
    (1, 16),      # CPU slot 1
    (21, 36),     # CPU slot 2
    (101, 116),   # Expansion slot 1
    (201, 216),   # Expansion slot 2
    (301, 316),   # ...
    (401, 416),
    (501, 516),
    (601, 616),
    (701, 716),
    (801, 816),
)
```

This is the **one definition** that:
- ClickNick uses to show only valid X/Y rows (replacing the current full 1-816 range)
- `addresses.py` uses to validate sparse addresses
- `modbus.py` uses to compute coil offsets

```python
# modbus.py — protocol mapping
@dataclass(frozen=True)
class ModbusMapping:
    bank: str                   # References BankConfig.name
    base: int                   # Modbus base address
    is_coil: bool
    width: int = 1
    signed: bool = True
    writable: frozenset[int] | None = None

MODBUS_MAPPINGS: dict[str, ModbusMapping] = { ... }
```

Note: `sparse` and `valid_ranges` live on `BankConfig`, not `ModbusMapping`. The Modbus layer reads them from the bank config. This avoids duplicating sparse knowledge across layers.

---

## Key Design Decision: One Address Parser

**Problem:** Address parsing previously had two functions with different return conventions.

**Decision:** Single strict `parse_address()` in `addresses.py`, returning MDB indices for all banks:

```python
def parse_address(address_str: str) -> tuple[str, int]:
    """Parse 'DF1' → ('DF', 1), 'XD1' → ('XD', 2), 'XD0u' → ('XD', 1)
    Raises ValueError on invalid input."""
```

The Modbus layer calls `parse_address()` then looks up `ModbusMapping` by bank name. ClickNick calls `parse_address()` then looks up `BankConfig`. Same function, different downstream lookups. XD/YD use contiguous MDB indices (0-16), eliminating stride-2 special cases in the Modbus layer.

---

## Key Design Decision: Optional Modbus

**Problem:** ClickNick only needs nickname/blocktag functionality. It should not require pymodbus.

**Decision:** pymodbus is an optional dependency.

```toml
# pyproject.toml
[project.optional-dependencies]
modbus = ["pymodbus>=3.7"]
```

- `banks.py`, `addresses.py`, `blocks.py`, `nicknames.py`, `validation.py`, `dataview.py` — zero external dependencies (stdlib only)
- `client.py`, `server.py` — require pymodbus, import guarded
- Users: `pip install pyclickplc` for core, `pip install pyclickplc[modbus]` for everything

---

## Key Design Decision: XD/YD Banks

XD and YD are byte-grouped views of X/Y inputs/outputs exposed by the CLICK programming software. They have Modbus register addresses (not coils — they read/write 16-bit words that pack groups of I/O bits).

**Decision:** Include XD/YD in both `BANKS` and `MODBUS_MAPPINGS`. XD is read-only; YD is read/write. The `addresses.py` XD/YD helpers move over as-is.

> **TODO:** XD/YD Modbus details need to be confirmed by testing against real hardware. The `ModbusMapping` entries for XD/YD will be added once base addresses and behavior are verified.

---

## Implementation Phases

### Phase 1: Foundation

**Modules:** `banks.py`, `addresses.py`, `validation.py`

- Extract from ClickNick `constants.py` and `address_row.py`
- Create `BankConfig` dataclass
- Unify `DataType` enum as the canonical type system
- Port all address parsing/formatting functions
- Port all validation rules and functions
- Comprehensive tests

**Unblocks:** Everything else. ClickNick can start importing immediately.

### Phase 2: BlockTags

**Module:** `blocks.py`

- Requires ClickNick Phase 0 (unique block names) to be done first ✓
- Extract from ClickNick `blocktag.py` (post-simplification)
- `BlockTag`, `BlockRange`, `MemoryBankMeta`
- All parsing and computation functions
- Tests

### Phase 3: File I/O

**Modules:** `nicknames.py`, `dataview.py`

- Extract CSV read/write from ClickNick `data_source.py`
- Extract CDV read/write from ClickNick `cdv_file.py`
- Tests using existing test fixtures from ClickNick

### Phase 4: Modbus Core

**Module:** `modbus.py`

- New code — `ModbusMapping` definitions for all 14 Modbus banks
- Forward mapping (PLC → Modbus address)
- Reverse mapping (Modbus → PLC address)
- Register packing/unpacking (struct-based)
- Sparse coil logic (X/Y forward and reverse)
- Text register handling
- Tests — extensive, since this is new code

**Can run in parallel with Phases 2 & 3** (independent dependency chains).

### Phase 5: Modbus Client

**Module:** `client.py`

- New code — `ClickClient` per CLICKDEVICE_SPEC
- `AddressAccessor`, `AddressInterface`, `TagInterface`
- Uses `modbus.py` for mapping/packing, `nicknames.py` for tag loading
- Tests with mocked Modbus client

### Phase 6: Modbus Server

**Module:** `server.py`

- New code — `ClickServer` per CLICKSERVER_SPEC
- `DataProvider` protocol, `MemoryDataProvider`
- Request handling for all supported function codes
- Tests with mocked/real pymodbus server

### Phase 7: Integration

- Update ClickNick imports (mechanical find-and-replace)
- Integration tests: ClickClient ↔ ClickServer round-trips
- Wire into pyrung
- Delete moved code from ClickNick

---

## Changes from Original Extraction Plan

| Original Plan | Revised |
|---------------|---------|
| 5 modules (`banks`, `addresses`, `blocks`, `nicknames`, `validation`) | 9 modules (+ `dataview`, `modbus`, `client`, `server`) |
| `DataType` extracted as-is | `DataType` becomes canonical; Modbus types derived from it |
| `ADDRESS_RANGES` as flat tuples | `BankConfig` dataclass with `valid_ranges` for sparse banks |
| X/Y shown as full 1-816 range | Sparse `valid_ranges` defines exactly which addresses exist; ClickNick filters display accordingly |
| XD/YD excluded from Modbus | XD/YD included in `MODBUS_MAPPINGS` (XD read-only, YD read/write; details TBD pending hardware testing) |
| No Modbus knowledge | `modbus.py` adds protocol mapping layer |
| No mention of CDV files | `dataview.py` added |
| `AddressRecord` in `addresses.py` | Unchanged — still the shared data transfer object |
| pymodbus not mentioned | Optional dependency for client/server |

The original extraction plan's module boundaries and phase ordering are preserved. The Modbus layer slots in alongside without disturbing the ClickNick extraction path.

---

## Public API (`__init__.py`)

```python
# Core
from pyclickplc.banks import BankConfig, BANKS, DataType
from pyclickplc.addresses import AddressRecord, parse_address, format_address_display
from pyclickplc.validation import validate_nickname, validate_initial_value

# BlockTags
from pyclickplc.blocks import BlockTag, BlockRange, MemoryBankMeta

# File I/O
from pyclickplc.nicknames import read_csv, write_csv
from pyclickplc.dataview import read_cdv, write_cdv

# Modbus (import-guarded, requires pyclickplc[modbus])
from pyclickplc.client import ClickClient
from pyclickplc.server import ClickServer, MemoryDataProvider, DataProvider

- `load_nickname_file(path)` → `ClickProject`
- `ClickProject` dataclass (records + banks + standalone tags) ?
```
