# Handoff: pyclickplc Implementation Order

See `ARCHITECTURE.md` for full module layout, dependency graph, and design decisions.

---

## Current State

- **Step 1 complete** (commit `7094c46` on `dev`)
- ClickNick: working app, Phase 0 (unique block names) done
- Specs written: `CLICKDEVICE_SPEC.md` (client), `CLICKSERVER_SPEC.md` (server)

### What exists in pyclickplc

| Module | Contents |
|---|---|
| `banks.py` | `DataType` enum, `BankConfig` frozen dataclass, `BANKS` (16 banks), `_SPARSE_RANGES`, `MEMORY_TYPE_BASES`, `_INDEX_TO_TYPE`, `DEFAULT_RETENTIVE`, interleaved/paired dicts, `NON_EDITABLE_TYPES`, `BIT_ONLY_TYPES`, `MEMORY_TYPE_TO_DATA_TYPE`, `is_valid_address()` |
| `addresses.py` | `get_addr_key`/`parse_addr_key`, XD/YD helpers, `format_address_display`, `parse_address_display` (lenient, MDB), `parse_address` (strict, display), `normalize_address`, `AddressRecord` frozen dataclass |
| `validation.py` | `FORBIDDEN_CHARS`/`RESERVED_NICKNAMES` (frozenset), numeric limits, `validate_nickname` (format-only), `validate_comment` (length-only), `validate_initial_value` |
| `__init__.py` | Re-exports public API (XD/YD helpers excluded) |

93 tests across `test_banks.py`, `test_addresses.py`, `test_validation.py`. Lint clean.

## ~~Step 1~~ Done

## Step 1.5 (optional): Plan Step 2 in detail

Read the ClickNick codebase to plan the exact import replacements before starting Step 2.

## ~~Step 2~~ Done

Wired ClickNick to import from pyclickplc:

- Deleted `models/constants.py` entirely (all constants now from pyclickplc)
- Slimmed `models/address_row.py`: removed 9 helper functions, kept `AddressRow` dataclass
- Updated imports in 15 source files + 5 test files
- Replaced `ADDRESS_RANGES` dict with `BANKS` (using `.min_addr`/`.max_addr`) in 4 files
- XD/YD helpers imported from `pyclickplc.addresses` (not re-exported from `__init__`)
- `validate_initial_value` re-exported from pyclickplc via `validation.py`
- `validate_nickname`/`validate_comment` stay in ClickNick (have uniqueness params)
- Added 11 pre-switch tests (`TestAddressRowDerivedProperties`) before migration
- 558 ClickNick tests + 93 pyclickplc tests pass, lint clean

## Step 3: `blocks.py` + `nicknames.py` + `dataview.py`

Extract remaining ClickNick shared code into pyclickplc:

- BlockTag system → `blocks.py`
- CSV read/write → `nicknames.py`
- CDV file I/O → `dataview.py`
- Update ClickNick imports, delete moved code

## Step 4: `modbus.py`

New code — Modbus protocol mapping layer:

- `ModbusMapping` definitions for all banks (XD/YD pending hardware testing)
- Forward/reverse address mapping
- Register packing/unpacking
- Sparse coil offset calculation (reads `valid_ranges` from `BankConfig`)

Can be developed in parallel with Step 3.

## Step 5: `client.py` + `server.py`

New code per the existing specs:

- `ClickDriver` (Modbus TCP client) per `CLICKDEVICE_SPEC.md`
- `ClickServer` (Modbus TCP server) per `CLICKSERVER_SPEC.md`
- Integration tests: driver ↔ server round-trips
