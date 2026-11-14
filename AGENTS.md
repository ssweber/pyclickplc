# pyclickplc Agent Guidance

`pyclickplc` is a shared library for AutomationDirect CLICK PLCs: bank definitions, address parsing, Modbus mapping, an async Modbus TCP client and server, and readers/writers for CLICK's files (nickname CSV, DataView CDV, PLC data dumps, Project.ini). ClickNick, pyrung and standalone tools consume it, so a change to output bytes or exceptions is a change for them.

## Commands

- **Install**: `uv sync --all-extras --dev`
- **All (install + lint + test)**: `make`
- **Test**: `make test` (`uv run pytest`)
- **Single test**: `uv run pytest tests/test_addresses.py::TestParseAddress::test_xd_yd_returns_mdb -v`
- **Lint**: `make lint` (codespell, `ruff check --fix`, `ruff format`, `ty check`). It edits files.
- **Build**: `make build`

## Architecture

PLC knowledge and Modbus protocol are separate layers joined by bank name:

- `banks.py` (no internal deps): `BankConfig`, `BANKS`, `DataType`, sparse `valid_ranges` for X/Y.
- `modbus.py` (banks): `ModbusMapping`, `MODBUS_MAPPINGS`, `plc_to_modbus` / `modbus_to_plc`, register pack/unpack.

Other modules and their internal imports:

| Module | Purpose | Imports |
|---|---|---|
| `addresses.py` | `parse_address`, `format_address_display`, XD/YD helpers | banks |
| `validation.py` | nickname, comment, initial-value and runtime-value checks | banks |
| `blocks.py` | BlockTag parsing in comments | — |
| `nicknames.py` | nickname CSV (`read_csv`, `write_csv`) | addresses, banks |
| `dataview.py` | DataView `.cdv` (UTF-16 LE CSV) | addresses, banks, validation |
| `plcdata.py` | "Read Data from PLC" CSV dumps | addresses, banks |
| `project.py` | modules, channels and I/O layout from Project.ini | addresses, `_module_catalog` |
| `client.py` | `ClickClient` (async, pymodbus) | addresses, banks, modbus, nicknames, validation |
| `modbus_service.py` | `ModbusService`, a sync wrapper over `ClickClient` for UIs | addresses, banks, client, modbus, validation |
| `server.py` | `ClickServer`, `DataProvider`, `MemoryDataProvider` | addresses, banks, modbus, validation |
| `server_tui.py` | terminal UI for `ClickServer` | server |
| `system/` | CLICK system-address nicknames (SC/SD) | — |

### Addresses

`parse_address()` returns `(memory_type, mdb_address)` and `format_address_display()` reverses it. Use these two everywhere; don't parse or format addresses by hand. XD/YD are MDB indices 0-16; display XD0-XD8 maps through `xd_yd_display_to_mdb()` (`XD1` → 2, `XD0u` → 1).

### Modbus mapping

`plc_to_modbus(bank, index)` is `base + index` for 0-based banks (XD/YD), `base + (index - 1) // 2` for TXT (two characters per register), and `base + width * (index - 1)` for other 1-based banks. X/Y are sparse coil banks with slot-based offsets.

## Conventions

- File output must match CLICK byte for byte (encoding, BOM, line ends, quoting). Test against a CLICK-written fixture.
- `DataType` is the single source of truth for PLC types; Modbus properties derive from it.
- Dataclasses are `frozen=True`, except the editing models `BlockRange`, `BlockTag`, `DataViewRecord` and `DataViewFile`.
- `pymodbus` is capped `<3.13`: 3.13 routes the server through SimDevice, so `server.py`'s overrides go unused and real clients get exception 02 (unit tests still pass; `tests/test_integration.py` catches it). Don't lift the cap without rewriting `server.py`.
- Tests in `tests/` mirror source modules. pytest also collects from `src/` (`python_files = ["*.py"]`), and async tests need no decorator (`asyncio_mode = "auto"`).
- src layout; Python 3.11+ (CI runs 3.11-3.14); ruff line length 100.
- CHANGELOG: write for a user deciding whether to upgrade, one line per item, with a "Behaviour changes" block (what changed, then what to do) for anything a caller could trip on. Leave out internal names and fixes to unreleased work.
