# Changelog

## Unreleased

### Fixed

- `AUTOMATIONDIRECT_SYSTEM_NICKNAMES` and `canonical_system_nickname` give the names CLICK itself writes for system addresses (`_RTC_Month`, not `_RTC_Month (1-12)`). 22 names changed (SC19-SC29, SC64, SC332, SD19-SD26, SD214).

### Behaviour changes

- The system nickname catalog's strings changed, for example SD21 from `_RTC_Month (1-12)` to `_RTC_Month` and SC20 from `_I/O_BUS_Error` to `_I/O Module Error`. `is_canonical_system_nickname` is false for the old string, and `canonicalize_system_nickname` leaves it as it was.
  - Compare against `canonical_system_nickname`, not a saved string. A project that holds a help-page name is not offered a repair.
- `SystemNicknameGuidance.source`, and `AUTOMATIONDIRECT_SYSTEM_CONTROL_RELAY_SOURCE` and `AUTOMATIONDIRECT_SYSTEM_DATA_REGISTER_SOURCE`, are now the text `CLICK 4.00 PLCType.ini [SYSTEM0]`, not help-page URLs. SD71, SD72, SD75 and SD76 keep a help-page URL.
  - Do not fetch `source` as a URL.
- `validate_nickname` and `validate_comment` reject a value that starts or ends with a tab or other character up to 0x20, as they did a space, with the same message. CLICK strips them on import, even quoted; CLICK was seen to strip a space and a tab, and the rest is inferred. A tab inside a comment is still valid.
  - Strip the value before you validate and store it.
- `validate_initial_value` rejects a value of any type but Text that starts or ends with a space, tab or other character up to 0x20 (`" 5"`, `"1.5\t"`), with the message `Cannot start or end with a space`. CLICK was seen to refuse a quoted number with an edge space or tab and to strip an edge space from a bare one; the rest is inferred.
  - Strip the value before you validate and store it.
- `write_csv` and `format_csv` quote a Text initial value that starts or ends with a space, tab or other character up to 0x20, so ` a` is written `" a"` (only a lone space was quoted). CLICK was seen to strip a bare space, tab, VT or FF at a Text value's ends and keep it quoted; the rest is inferred.
  - Regenerate any saved output your tests compare against.
- `validate_initial_value` rejects an INT, INT2, FLOAT or HEX value holding a non-ASCII character, such as `٥`, fullwidth `５` or a no-break space at an edge (`Must be ASCII`); Python's `int()` and `float()` take them. CLICK was seen to refuse those values as INT and FLOAT from a file without a BOM, which is what `write_csv` writes; INT2, HEX and other non-ASCII characters are inferred.
  - Use ASCII digits, and remove a no-break space.
- `validate_initial_value` rejects an INT, INT2, FLOAT or HEX value holding an underscore, such as `1_000` (`Cannot contain _`). CLICK was seen to refuse `1_000` as INT and FLOAT; INT2 and HEX are inferred.
  - Leave out the underscores (`1000`).
- `validate_initial_value` rejects a HEX value with a `0x` prefix, such as `0x1F` (`Cannot start with 0x`). CLICK was seen to refuse `0x1F`; `0X` and a sign before the prefix are inferred.
  - Leave out the prefix (`1F`).

## 0.7.0 - 2026-11-15

### Added

- `iter_address_slots` yields `(memory_type, address)` for every slot CLICK shows, in bank order, so a caller can loop over all of them.
- `read_plc_name` reads the PLC name from a project's `Project.ini`, and `write_plc_name` sets it, changing or adding only the name line.
- `validate_click_name` checks a PLC or DataView name: 1 to 24 letters, digits, spaces, underscores and hyphens, ignoring surrounding whitespace.

### Fixed

- `read_modules`, `read_channel_parameters` and `read_io_layout` read a CLICK 4 `Project.ini` that also has a `[SystemConfigData]` or `[CPUBuild]` section, and take CLICK 4's values (they raised `ValueError`).
- `read_plc_data` reads a dump with a DF cell CLICK shows as `Err-Format` (it raised `ValueError`). The value is `float("nan")`.
- `read_plc_data` reads a TXT cell CLICK writes as `$` and a hex code as that character: `$20` is a space, `$D` a carriage return and `$C8` is `"\xc8"` (it returned the cell's text).
- `write_plc_data` writes a DF value in CLICK's form: the float32 value in fixed point (`66.7` is `66.69999695`, `3e38` is `300000000549775575800000000000000000000.0`). How many digits CLICK keeps above about 1e19 is inferred from one dump.
- `write_plc_data` writes a TXT space, control character or character above `~` as CLICK does, as `$` and its hex code, and `"\x00"` as an empty cell.
- `write_plc_data` writes CRLF line ends and a blank line after the last section on any platform, as CLICK does. A dump CLICK wrote reads and writes back byte for byte, unless it has an `Err-Format` cell or TXT punctuation other than `+`, `-` and `.`.

### Behaviour changes

- `validate_nickname` and `validate_comment` reject a value with a leading or trailing space (`Cannot start or end with a space`). CLICK strips them, so `Pump ` and `Pump` would be one nickname.
  - Strip the value before you validate and store it, or have the user remove the space. `read_csv` still reads such a file as written.
- `write_csv` and `format_csv` write a Text initial value that is a single space as `" "`, quoted (it was bare, and CLICK imports a bare space as empty).
  - Regenerate any saved output your tests compare against.
- `write_plc_data` writes CLICK's forms: a DF value as its float32 (`66.7` is `66.69999695`), a TXT space as `$20`, CRLF line ends and a blank line at the end.
  - Regenerate any saved output your tests compare against.
- `write_plc_data` raises `ValueError` naming the address for a DF value that is NaN, infinite or outside the float32 range (it wrote `nan`, `inf` or the full number). CLICK's editor can't enter a NaN or an infinity. A dump with an `Err-Format` cell reads as NaN, so writing it back raises.
  - Set such an address to a number before writing.
- `write_plc_data` raises `ValueError` naming the address for a TXT value that isn't a string, is more than one character, has a code above 255, or is punctuation other than `+`, `-` and `.` (it wrote the value as is, so an int such as `5` was written `5`). CLICK's form for that punctuation hasn't been checked.
  - Write one character per TXT address, and leave out that punctuation.
- `read_plc_data` returns `float("nan")` for a DF cell CLICK shows as `Err-Format`, and the character itself for a TXT cell CLICK writes as `$` and a hex code (`$20` is now `" "`, not `"$20"`).
  - Treat a NaN as a value CLICK can't show, and match TXT characters rather than their `$` form.

## 0.6.0 - 2026-11-15

### Added

- `read_mdb_csv` reads CLICK's `Address.csv`, the nickname table CLICK keeps beside an open project's database.
- `format_csv` returns the nickname CSV text `write_csv` writes, for a caller that writes the file itself.
- `read_csv(path, required=...)` sets which columns the file must have, and the result's `columns` lists the ones it had.
- `BankConfig.display_max_addr` is the highest address CLICK shows: 8 for XD and YD, whose `max_addr` is the MDB address 16; `max_addr` for every other bank.

### Fixed

- `write_csv` quotes a non-Text initial value that holds a comma, double quote or line break, so it reads back as one value (`1,5` was written bare and split the row). CLICK never writes such a value, so output for CLICK's own files is unchanged.
- `read_plc_data` skips a row whose first address isn't a CLICK address and a cell past the end of its bank (it returned keys such as `DS0` and `X817`). `write_plc_data` leaves out a bank only named by a key that isn't a CLICK address.

### Behaviour changes

- `parse_address` and `normalize_address` refuse what CLICK refuses: a `u` suffix on anything but `XD0u`/`YD0u` (`DS1u` was read as `DS1`), and non-ASCII digits and letters (`DS١` was `DS1`, `ſC1` was `SC1`). This applies wherever pyclickplc takes an address string: `ClickClient.addr`, `ClickServer`, `ModbusService`, `.addr` lookups, `make_address_record` and the DataView checks.
  - Fix any stored address with a stray `u`. Leading zeros and surrounding spaces are still accepted.
- `read_csv` raises `ValueError` with the file name and line for a row whose Address isn't a CLICK address (it skipped the row).
  - Fix the row, or catch `ValueError`. A row with every cell blank is still skipped.
- `read_csv` raises `ValueError` with the file name and line for a Data Type that isn't one CLICK writes, or isn't the type of the row's bank (it used the bank's type). CLICK's names are accepted in any letter case; `TXT` is refused. A blank Data Type still takes the bank's type.
  - Fix the cell to the bank's type (BIT, INT, INT2, FLOAT, HEX or TEXT), or leave it blank.
- `read_csv` raises `ValueError` with the file name and line for a row with a non-blank cell past the header's columns (it dropped the cell).
  - Quote a value that holds a comma.
- `read_csv` no longer raises on a nickname used twice (ignoring case). The file loads and `.addr` works, but every `.tag` lookup then raises `ValueError` naming the repeats, and `ClickClient(tags=...)` still raises.
  - If you relied on the read failing, look up any nickname through `.tag` after reading.
- `read_csv` keeps Nickname and Address Comment as written, spaces included (it stripped them).
  - Strip them yourself if you compare against trimmed names.
- `read_csv` reads Retentive `True` and `1` as on, as well as `Yes` (anything else was off, and still is).
  - Check files that say `True` or `1` for an address you meant to be non-retentive.
- `read_csv`'s message for a missing column names the file (`Nicknames.csv is missing required column(s): Nickname`; it began `CSV is missing`).
  - Update any check that matches the message text.
- `read_csv` raises `ValueError` naming the file for a file that isn't UTF-8 or isn't CSV (it raised `UnicodeDecodeError` or `csv.Error`).
- `read_csv` gives `data_type` as a `DataType`, as `make_address_record` does (it was a plain int of equal value).

## 0.5.2 - 2026-11-14

### Fixed

- A saved DataView `.cdv` is now written as CLICK writes it: UTF-16 LE with a byte order mark and CRLF line ends, on any platform.
- `write_csv` now writes a nickname CSV with CRLF line ends, as CLICK's export does.
- `write_csv` quotes a Text initial value that is a comma or a double quote. CLICK's own export of such a value can't be imported back into CLICK, so pyclickplc writes it in the form CLICK accepts.
- `read_csv` reads CLICK's own export when a Text initial value is a comma or a double quote (it lost the value or shifted the row, and a double quote swallowed the next row).
- `read_csv` reads a UTF-8 CSV that starts with a byte order mark.
- `read_csv` keeps the leading and trailing spaces of a Text initial value.

### Behaviour changes

- `read_csv` raises `ValueError` when the Address or Nickname column is missing (it returned no rows).
  - Catch `ValueError` where you read a CSV that may not be a CLICK nickname export.
- The bytes of a saved `.cdv` and of `write_csv` output change: CRLF line ends, and a Text initial value that is a comma or a double quote is quoted in the CSV.
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
