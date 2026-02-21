# Changelog

## 2026-02-21

### Breaking Changes
- `ClickClient` now accepts `tags: Mapping[str, AddressRecord] | None` and no longer accepts `tag_filepath`.
- Renamed `DataviewRow` to `DataViewRecord` across API exports and dataview helpers.

### Notes
- `read_csv` now returns `AddressRecordMap`, which is `dict[int, AddressRecord]` compatible and adds
  `records.addr[...]` (normalized address lookup) and `records.tag[...]` (case-insensitive nickname lookup).
- CSV nickname loading now rejects case-insensitive collisions (`nickname.lower()` conflicts).

## 2026-02-13

### Breaking Changes
- Removed `read_mdb_csv` from `pyclickplc` public API (`pyclickplc` and `pyclickplc.nicknames`).
- Removed `export_cdv`, `get_dataview_folder`, and `list_cdv_files` from `pyclickplc` public API (`pyclickplc` and `pyclickplc.dataview`).

### Notes
- `load_cdv` and `save_cdv` remain in `pyclickplc.dataview`.
