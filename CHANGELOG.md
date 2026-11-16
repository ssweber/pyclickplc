# Changelog

## 0.8.0 - 2026-11-16

### Added

- `ClickServer.bound_port`: the port the server listens on, or `None` when it is not running. Start a server with `port=0` and read the port the system picked; it is the same for every address the host resolves to (`127.0.0.1` and `::1` for `localhost`).

### Fixed

- `ClickServer` answers every request, in order and with its own transaction id, when several arrive together; before, it answered only some of them, and could give a reply the wrong transaction id.
- `ClickServer` answers a request too short for its function code with exception 03; before, it got no answer and the connection stopped answering.
- On Windows, after a client connects and resets before the server has accepted it, `ClickServer` takes no more clients. `is_running()` now gives False then (it gave True before), and calling `start()` listens again.
- `write_plc_data` raises `ValueError` naming the address, with a short message, for a huge DF value; before, a DF `10**5000` raised Python's 4300-digit `ValueError` with no address.
- `write_plc_data` raises `ValueError` naming the address, with a short message, for a huge TXT value; before, the message was as long as the value.
- `write_plc_data` says `outside the float32 range` for a DF number too large for a Python float (2**1024 or more), as it does for a smaller one past the float32 range; before, it said `is not a float32`.

### Behaviour changes

Modbus server and pymodbus:

- pyclickplc now works with pymodbus 3.12 and any later 3.x; 0.7.0 pinned 3.12.x, so installing or upgrading brings the newest pymodbus 3 unless something else pins pymodbus.
  - If your own pymodbus code needs 3.12, pin `pymodbus<3.13`.
- `ClickServer` no longer uses pymodbus, so it answers the same whatever pymodbus is installed. Only `ClickClient` uses it.
- `ClickServer` answers exception 03 and stores nothing when a write of several coils or registers (function code 15 or 16) has a byte count that disagrees with the count or with the data sent; before, it stored the data it received.
  - Send a byte count of (count + 7) // 8 for coils and 2 × count for registers, followed by that many data bytes.
- `ClickServer` answers exception 01 to every function code but 1-6, 15 and 16; before, 7, 8, 11, 12, 17 and 24 got the answers of a generic Modbus device, 20 (read file record) got a made-up record, 21 (write file record) was answered as if written, and 43 got no answer.
  - Treat exception 01 as "not supported".
- `ClickServer` answers an unknown function code with exception 01 and the request's transaction id; before, the reply had transaction id 0, which a client could not match.
- `ClickServer` closes a connection whose frame header gives a length below 2 or above 262; before, a length below 2 stopped the connection answering, and a frame with a longer length was answered.
  - Send the length of the unit id and PDU in the header.
- `ClickServer` drops a frame whose protocol id is not 0 unanswered, then answers the requests after it; before, such a frame stopped the connection answering.
  - Send protocol id 0.
- On Windows, starting a server on a port another server holds raises `RuntimeError`; before, it did not raise.
  - Stop the other server, or start this one on another port.
- `ClickServer.start()` and `serve_forever()` raise `RuntimeError` when the server is already listening; before, a second `start()` did not raise, and the first listener kept answering after `stop()`.
  - Call `start()` once, or check `is_running()` first.
- `ClickServer.start()`, `serve_forever()` and `stop()` raise `RuntimeError` while the server runs on another event loop that is still open.
  - Stop the server on the loop that started it.
- The `RuntimeError` for a port `ClickServer` can't listen on gives the system's reason, with the `OSError` as its cause; before, the message gave no reason.
- Cancelling `ClickServer.serve_forever()` stops the server and raises `CancelledError`; before, it returned and the server kept listening.
  - Call `stop()`, or cancel the task, to stop the server.
- `ClickServer.list_clients()` gives client ids `"1"`, `"2"` and so on, counting up across restarts; before, they were pymodbus's connection ids.
  - Pass the ids `list_clients()` gives to `disconnect_client()`.

Nicknames, comments and initial values:

- `validate_nickname` rejects `max`, `min`, `mdn`, `avg`, `rand` and `abs` in any case (`Reserved keyword`), and a nickname holding a comma (`Invalid: ,`).
  - Rename such a nickname (`Max_Speed` and `MAXIMUM` are fine).
- `validate_nickname` and `validate_comment` reject a value that starts or ends with a tab or other character up to 0x20, as they did a space, with the same message. A tab inside a comment is still valid.
  - Strip the value before you validate and store it.
- `validate_initial_value` rejects a value of any type but Text that starts or ends with a space, tab or other character up to 0x20 (`" 5"`, `"1.5\t"`), with the message `Cannot start or end with a space`.
  - Strip the value before you validate and store it.
- `validate_initial_value` rejects an INT, INT2, FLOAT or HEX value holding a non-ASCII character, such as `٥`, fullwidth `５` or a no-break space at an edge (`Must be ASCII`); before, Python's `int()` and `float()` took them.
  - Use ASCII digits, and remove a no-break space.
- `validate_initial_value` rejects an INT, INT2, FLOAT or HEX value holding an underscore, such as `1_000` (`Cannot contain _`).
  - Leave out the underscores (`1000`).
- `validate_initial_value` rejects a HEX value with a `0x` prefix, such as `0x1F` (`Cannot start with 0x`).
  - Leave out the prefix (`1F`).
- `write_csv` and `format_csv` quote a Text initial value that starts or ends with a space, tab or other character up to 0x20, so ` a` is written `" a"`; before, only a lone space was quoted.
  - Regenerate any saved output your tests compare against.

System nicknames:

- `AUTOMATIONDIRECT_SYSTEM_NICKNAMES` and `canonical_system_nickname` give the names CLICK itself writes (`_RTC_Month`, not `_RTC_Month (1-12)`; SC20 is `_I/O Module Error`, not `_I/O_BUS_Error`). 22 names changed (SC19-SC29, SC64, SC332, SD19-SD26, SD214).
  - Compare against `canonical_system_nickname`, not a saved string. `is_canonical_system_nickname` is false for the old string, `canonicalize_system_nickname` leaves it as it was, and a project that holds a help-page name is not offered a repair.
- `SystemNicknameGuidance.source`, and `AUTOMATIONDIRECT_SYSTEM_CONTROL_RELAY_SOURCE` and `AUTOMATIONDIRECT_SYSTEM_DATA_REGISTER_SOURCE`, are now the text `CLICK 4.00 PLCType.ini [SYSTEM0]`, not help-page URLs. SD71, SD72, SD75 and SD76 keep a help-page URL.
  - Do not fetch `source` as a URL.

PLC data dumps:

- `write_plc_data` writes every TXT punctuation mark but a comma plain, so `"` is written `"` and `$` is written `$`; before, it raised `ValueError` for all but `+`, `-` and `.`.
  - Write the punctuation you left out.
- `write_plc_data` still raises `ValueError` for a TXT comma: CLICK writes it unquoted, so the row couldn't be read back.
  - Keep leaving out a comma.
- `read_plc_data` raises `ValueError` naming the row's first address for a row whose cells don't match its addresses, such as a row with a TXT comma, which CLICK writes unquoted; before, it read the row, with the comma's address and the next one blank and each address after them holding the value of the one before.
  - Replace the comma in the PLC's TXT data, then read the data from the PLC again.
- `write_plc_data` writes CLICK's digits for more large DF values, such as 1.5e30 and 1.8e30: `1.8e30` is `1800000027085439196000000000000.00000000` (it was `...1958...`). Some large values still differ in the last digits; `read_plc_data` reads either form as the same value.
  - Regenerate any saved output your tests compare against.

Project.ini:

- `read_plc_name` and `write_plc_name` match the section and key regardless of case, and use the first match when a file has several (`[sec20]` with `KEY1` gives the name); before, `read_plc_name` gave `None` for such a file, and `write_plc_name` added a `[PLCName]` section.
- `write_plc_name` writes into the first matching section and key, keeping their spelling; before, it raised `ValueError` for a header that differs only in case.
  - Remove any `except ValueError` that handled only a case-only header.
- `read_plc_name` takes the first of a repeated section or key; before, it raised `ValueError`.
  - Remove any `except ValueError` that handled only a repeat.
- `read_modules`, `read_channel_parameters` and `read_io_layout` find a section whose name differs in case, such as `[sec21]` or `[systemconfig]`; before, they read only CLICK's spelling, so a file with `[sec21]` gave no modules.
  - Check the hardware you read from a hand-edited `Project.ini`.
- `read_modules`, `read_channel_parameters` and `read_io_layout` take the first of a section or key repeated in any case; before, a repeat raised `ValueError`.
  - Remove a repeated section or key, and any `except ValueError` that handled only a repeat.
- `[SystemConfig]` in any case marks a CLICK 3 file for those readers; before, only `[SystemConfig]` did, so a file with `[systemconfig]` gave no modules.
- `write_plc_name` raises `ValueError` for a file with a continuation line, a line indented under an option such as `  more` or `  [Next]` after `Key2=x`; before, it set the name in some such files.
  - Remove the indent or the line, then set the name again.
- In a CLICK 4 `Project.ini`, `read_modules`, `read_channel_parameters` and `read_io_layout` ignore a named section that has its CLICK 4 section beside it, such as `[CPUBuild]` beside `[Sec23]`; before, they read the keys only the named section had, such as `[CPUBuild] AD2`.
  - Set a channel the stray section held in CLICK, which writes it to the CLICK 4 section.

### Documentation

- The `write_plc_data` docstring and the files guide warn that CLICK's Write Data into PLC writes every address of each memory type in the file, so an address the file leaves blank is cleared in the PLC.
  - To change some addresses and keep the rest, read the PLC's data first, then write it back with your changes.

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
