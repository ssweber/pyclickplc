# Handoff: pyclickplc Implementation Order

See `ARCHITECTURE.md` for full module layout, dependency graph, and design decisions.

---

## Current State

- **Steps 1–4 complete** (latest commit `f672524` on `dev`)
- ClickNick: working app, Phase 0 (unique block names) done
- Specs written: `CLICKDEVICE_SPEC.md` (client), `CLICKSERVER_SPEC.md` (server)

### What exists in pyclickplc

| Module | Contents |
|---|---|
| `banks.py` | `DataType` enum, `BankConfig` frozen dataclass, `BANKS` (16 banks), `_SPARSE_RANGES`, `MEMORY_TYPE_BASES`, `_INDEX_TO_TYPE`, `DEFAULT_RETENTIVE`, interleaved/paired dicts, `NON_EDITABLE_TYPES`, `BIT_ONLY_TYPES`, `MEMORY_TYPE_TO_DATA_TYPE`, `is_valid_address()` |
| `addresses.py` | `get_addr_key`/`parse_addr_key`, XD/YD helpers, `format_address_display`, `parse_address_display` (lenient, MDB), `parse_address` (strict, display), `normalize_address`, `AddressRecord` frozen dataclass |
| `validation.py` | `FORBIDDEN_CHARS`/`RESERVED_NICKNAMES` (frozenset), numeric limits, `validate_nickname` (format-only), `validate_comment` (length-only), `validate_initial_value` |
| `blocks.py` | `BlockTag`, `BlockRange`, block parsing/formatting/validation |
| `dataview.py` | `DataviewRow`, CDV file I/O, type codes, writable sets, storage/display conversion |
| `nicknames.py` | CSV read/write, data type code mappings |
| `modbus.py` | `ModbusMapping` frozen dataclass, `MODBUS_MAPPINGS` (16 banks), `plc_to_modbus`/`modbus_to_plc` forward/reverse mapping, `pack_value`/`unpack_value` register encoding, sparse coil helpers, XD/YD stride-2 support |
| `__init__.py` | Re-exports public API (XD/YD helpers excluded) |

417 tests across `test_banks.py`, `test_addresses.py`, `test_validation.py`, `test_blocks.py`, `test_dataview.py`, `test_nicknames.py`, `test_modbus.py`. Lint clean.

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

## ~~Step 3~~ Done

Extracted remaining ClickNick shared code into pyclickplc:

- BlockTag system → `blocks.py`
- CSV read/write → `nicknames.py`
- CDV file I/O → `dataview.py`
- Updated ClickNick imports, deleted moved code

## ~~Step 4~~ Done

New code — Modbus protocol mapping layer (`modbus.py`):

- `ModbusMapping` frozen dataclass with `is_writable` property
- `MODBUS_MAPPINGS` for all 16 banks (6 coil, 10 register)
- Forward mapping `plc_to_modbus(bank, index)` with sparse coil and XD/YD stride-2 support
- Reverse mapping `modbus_to_plc(address, is_coil)` with gap detection
- `pack_value`/`unpack_value` — struct-based register encoding (little-endian word order)
- `_MODBUS_WRITABLE_SC` excludes 50/51 (ladder-only); `_MODBUS_WRITABLE_SD` matches spec
- 194 new tests (417 total), lint clean

## Step 5: `client.py` + `server.py`

New code per the existing specs:

- `ClickClient` (Modbus TCP client) per `CLICKDEVICE_SPEC.md`
- `ClickServer` (Modbus TCP server) per `CLICKSERVER_SPEC.md`
- Integration tests: driver ↔ server round-trips
