# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`pyclickplc` is a shared utility library for AutomationDirect CLICK PLCs. It provides PLC bank definitions, address parsing, nickname CSV and DataView CDV file I/O, BlockTag parsing, Modbus protocol mapping, and async Modbus TCP client/server. Consumed by ClickNick (GUI editor), pyrung (simulation), and standalone tooling.

## Commands

- **Install**: `uv sync --all-extras --dev`
- **Run all (install + lint + test)**: `make` or `make default`
- **Test**: `make test` (runs `uv run pytest`)
- **Single test**: `uv run pytest tests/test_addresses.py::TestParseAddress::test_xd_basic -v`
- **Lint**: `make lint` (runs `uv run devtools/lint.py` — codespell, ruff check --fix, ruff format, ty check)
- **Build**: `make build` (runs `uv build`)

## Architecture

### Two-Layer Design

PLC knowledge and Modbus protocol are separated into two layers linked by bank name:

1. **`banks.py`** (foundation, zero deps) — `BankConfig`, `BANKS` dict, `DataType` enum, sparse `valid_ranges` for X/Y hardware slots, address validation
2. **`modbus.py`** (depends on banks) — `ModbusMapping`, `MODBUS_MAPPINGS` dict, forward/reverse address mapping, register pack/unpack

### Address System

All address parsing flows through `parse_address()` in `addresses.py`, which returns `(memory_type, mdb_address)` — MDB-style indices for all banks. XD/YD use contiguous MDB indices 0-16; display addresses 0-8 map via `xd_yd_display_to_mdb()`. The `format_address_display()` function handles the reverse. These two functions are the canonical formatting/parsing entry points used by client, server, nicknames, and dataview modules.

### Dependency Graph

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

### Key Modules

- **`client.py`** — `ClickClient` (async Modbus TCP client using pymodbus) with `AddressAccessor`, `AddressInterface`, `TagInterface`
- **`server.py`** — `ClickServer` (async Modbus TCP server) with `DataProvider` protocol and `MemoryDataProvider`
- **`nicknames.py`** — Read/write CLICK nickname CSV files
- **`dataview.py`** — Read/write DataView CDV files (UTF-16 LE CSV format)
- **`blocks.py`** — BlockTag parsing and computation

### Modbus Mapping

`plc_to_modbus(bank, index)` uses `base + index` for 0-based banks (XD/YD) and `base + width * (index - 1)` for 1-based banks. X/Y are sparse coil banks with slot-based offset formulas. `modbus_to_plc()` reverses the mapping.

## Conventions

- `DataType` enum is the single source of truth for PLC types; Modbus properties derive from it
- All dataclasses use `frozen=True`
- Tests in `tests/` mirror source modules (e.g., `test_addresses.py` tests `addresses.py`)
- pytest discovers tests from both `src/` and `tests/` directories (`python_files = ["*.py"]`)
- `asyncio_mode = "auto"` — async tests need no decorator
- Package uses src-layout: source is in `src/pyclickplc/`
- Python 3.11+ required; CI tests 3.11-3.14
- Ruff line-length is 100
