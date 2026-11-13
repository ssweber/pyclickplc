# Changelog

## Unreleased

### Fixed

- A saved DataView `.cdv` is now written as CLICK writes it: UTF-16 LE with a byte order mark and CRLF line ends, on any platform.
- `write_csv` now writes a nickname CSV as CLICK's export does: CRLF line ends and a quoted Text initial value, so a comma or quote in it round-trips.
- `read_csv` reads a UTF-8 CSV that starts with a byte order mark.
- `read_csv` keeps the leading and trailing spaces of a Text initial value.

### Behaviour changes

- `read_csv` raises `ValueError` when the Address or Nickname column is missing (it returned no rows).
  - Catch `ValueError` where you read a CSV that may not be a CLICK nickname export.
- The bytes of a saved `.cdv` and of `write_csv` output change: CRLF line ends, and a quoted Text initial value in the CSV.
  - Regenerate any saved files your tests compare this output against.

## 0.5.1 - 2026-11-10

### Fixed

- A DF write accepts +inf, -inf and NaN (it raised `ValueError`).
  - Every NaN goes out as 0xFFFF:0xFFFF, as a CLICK serves it.
  - A finite value outside the float32 range still raises.
  - DataView new values still refuse +inf, -inf and NaN.
- A DF nickname initial value or DataView new value of "nan" is refused (it was accepted).
- A Text value accepts any character with code 0..255 in a client write, a server write and a DataView (it refused 128..255 and turned a stored 200 into blank). A character above 255 still raises.
- A server read that fails answers Modbus exception 04 (it sent an empty reply).
- A client read whose reply is short raises `OSError` (it raised `IndexError` or `struct.error`).
- `ModbusService.write` keeps its per-item results when one batch fails with any error.
- A client range read or write splits at the Modbus limits (a long read raised `ValueError` and a long write got exception 03).
  - A read takes at most 125 registers or 2000 coils.
  - A write takes at most 123 registers or 1968 coils.
  - A DD or DF value never splits across two requests.
- A server Modbus write (FC05, FC06, FC15 or FC16) that is refused leaves memory unchanged (a write that ran past the last address stored the earlier values before it answered the exception).
- A server answers Modbus exception 03 for a request outside the Modbus limits (it timed out, served the read or took any value as ON).
  - A read count of 0, or over 125 registers or 2000 coils.
  - A write over 123 registers or 1968 coils.
  - An FC05 value other than 0x0000 or 0xFF00.
- A DF register pack of a finite value past the float32 range gives +inf or -inf by its sign (it raised `OverflowError` and failed a server read). A client write of such a value still raises `ValueError`.
- A server read past the end of a bank answers Modbus exception 02 (it served 0).
- A server FC15 write that runs past the end of a bank answers exception 02 and stores nothing (it stored the coils before the end).
- A server keeps each XD or YD register without an address name as a spare word of its own (a read served the named register before it and a write stored there).
  - These are the odd registers above XD0u and YD0u.
  - A YD spare word reads 0 until a client writes it, then keeps that value.
  - An XD spare word reads 0 and refuses a write.
  - The server holds the spare words itself, so a DataProvider never sees them.
- A server answers Modbus exception 01 to FC22 and FC23 (it served them).

## 0.5.0 - 2026-11-01

### Added

- `read_io_layout()` returns each installed module as a `ModuleIO` in physical order (CPU, CLICK PLUS slots, expansions) with its discrete X/Y addresses and per-channel analog DF assignments (`None` for unassigned channels). Slot 0 starts at X001/Y001 and slot 1 at X021/Y021. Analog parsing is shared with `read_channel_parameters()`.

### Fixed

- `read_modules()`, `read_channel_parameters()` and `read_io_layout()` read CLICK 4's Project.ini, which stores the same hardware under placeholder section and key names; before, they found no hardware in it.

## 0.4.1 - 2026-10-14

### Fixed

- `ClickClient` now translates pymodbus exceptions into stdlib `OSError` subclasses (`ConnectionException` → `ConnectionError`, other `ModbusException`s → `OSError`, with the original chained as `__cause__`). A connection dropped mid-write previously escaped `ModbusService.write()` as a raw pymodbus exception; it now marks the affected batches `ok=False` and the remaining batches are still attempted. Code that caught `pymodbus.exceptions.ModbusException` from `ClickClient` should catch `OSError` instead.
- Cancelling a task during a `ClickClient` request now raises `CancelledError` instead of pymodbus's `ModbusIOException("Request cancelled outside library.")`, so `ModbusService.disconnect()` can no longer hang when it cancels the poll loop mid-read.

## 0.4.0 - 2026-09-09

### Added

- `read_modules()` returns an immutable CPU, slot, and expansion inventory with model IDs and discrete/analog I/O counts, sharing hardware parsing with `read_channel_parameters()`.

- `read_channel_parameters()` reads analog input/output DF assignments from Project.ini for built-in CPU channels, both CLICK PLUS slots, and all eight expansion positions, using installed hardware to exclude outputs from inputs and ignore stale settings.

## 0.3.4 - 2026-09-02

### Added

- Maintained AutomationDirect guidance for 344 documented SC/SD system nicknames, including conservative canonicalization helpers and source metadata for downstream repair workflows.

## 0.3.3 - 2026-08-25

### Added

- `compose_structured_block_name()` for building structured block name strings from components (inverse of `parse_structured_block_name()`).
- `parse_structured_block_name()` now recognizes `Base.Field:udt` (with explicit `:udt` suffix) and `Base:block` (without start override) in addition to existing patterns.

## 0.3.2 - 2026-04-15

### Changed

- Pinned pymodbus to the compatible 3.12 release series and updated client/server integration for its current API.

## 0.3.1 - 2026-03-29

### Fixed

- `read_csv()` no longer rejects duplicate nicknames for system addresses (SC/SD). Click auto-populates these and may produce duplicates that users cannot control.

## 0.3.0 - 2026-03-26

### Added

- `read_plc_data()` and `write_plc_data()` for the CSV format used by Data > Read Data from PLC / Write Data into PLC.

## 0.2.0 - 2026-03-06

### Added

- `make_address_record()` and `make_dataview_record()` factory functions for building records from display addresses with inferred defaults.
- `AddressRecord.from_address()` and `DataViewRecord.from_address()` classmethods.
- Concise `__repr__` for `AddressRecord` and `DataViewRecord` (shows only populated fields).
- Examples section with traffic light simulator and PLC datetime sync script.

### Changed

- `write_csv()` accepts `Iterable[AddressRecord]` or `Mapping[int, AddressRecord]`.
- `write_cdv()` accepts `Iterable[DataViewRecord]` or `DataViewFile`.
- README and guides rewritten with code-first tone and progressive structure.

## 0.1.0 - 2026-02-26

### Added

- v0.1 documentation structure with capability-oriented API reference pages:
  - Client API
  - Service API
  - Server API
  - Files API
  - Addressing API
  - Validation API
  - Advanced API
- New usage guides:
  - `guides/types.md` for native Python value contracts
  - `guides/addressing.md` for canonical normalized addressing and XD/YD details
- API reference coverage guard in `docs/gen_reference.py` to ensure all exported symbols in `pyclickplc.__all__` are documented exactly once.

### Changed

- README restructured for v0.1 launch:
  - clearer async (`ClickClient`) vs sync (`ModbusService`) entry points
  - native Python type contract table
  - explicit error model (`ValueError` validation vs `OSError` transport)
  - `XD0u` / `YD0u` moved out of quickstart to addressing guidance
  - stability policy documented as "stable core, evolving edges"
- MkDocs navigation updated to capability-oriented API pages and new core guides.

### Notes

- Stable core APIs are documented in primary navigation.
- Lower-level Modbus mapping and bank metadata APIs are documented under Advanced API and may evolve more quickly.
