# Changelog

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
