# pyclickplc roadmap

What is still to do in this repo, in order. Work that crosses repos is in the ecosystem plan
(`ssweber.github.io/plan/README.md`, "Who owns what" and "Order by repo"); it is linked here, not repeated.
When an item lands, delete it.

Each item says what it needs: **nothing** (code only), **CLICK software**, **a real PLC**, or **Sam's
judgment**. Work that needs nothing is not queued behind work that needs Sam.

Branches: feature and refactor branches into an always-releasable `main`. Sam squash-merges. Push and open a
PR only once Sam has said so directly; otherwise stop at "CI green locally, ready to push".

## 1. Address parsing and the nickname CSV reader (one release)

Needs: nothing. Ships together, so a row that stops parsing is reported, not silently lost. laddercodec's
parity test waits on this release; pyrung's tag map and ClickNick's Address Editor read through `read_csv`, so
test against their checkouts before release. Every behaviour change below is a line in the changelog's
"Behaviour changes" block.

1. **Test first:** pin what `parse_address` accepts today. Accepted now and to be refused:
   - a stray `u` on any bank but XD/YD (`DS1u`, `X001u`, `TXT1u` parse as `DS1`, `X001`, `TXT1`)
   - non-ASCII digits (`DS١`, `DS１`, `DS𝟏`), because of `\d` and `int()`
   - non-ASCII letters that uppercase to ASCII (`ſC1` parses as `SC1`), because `.upper()` runs first

   Accepted now and kept until CLICK is checked (item 3): leading zeros (`DS0001`, `XD01`) and surrounding
   whitespace.
2. **`parse_address` changes in place.** ASCII letters and digits only; `u` only as `XD0u`/`YD0u`. Lowercase
   stays. No separate strict mode.
3. **XD/YD display-unit range:** a new `BankConfig` field beside `max_addr` (XD/YD display 0-8; `max_addr`
   stays the MDB index 0-16). `client.py`'s `DisplayAddressAccessor` reads it instead of its hard-coded 8.
4. **`read_csv` behaviour:**
   - raise `ValueError` on a row whose address does not parse, with the line number (today it skips silently)
   - keep Nickname and Address Comment as written (today both are stripped)
   - accept `true` and `1` for Retentive as well as `Yes`
   - a repeated nickname no longer fails the read; the map's `.tag` view still raises on lookup
   - report which columns the file had (ClickNick's Import from CSV needs only Address)
   - an unreadable encoding or malformed CSV raises `ValueError` naming the file and line
   - `data_type` is a `DataType`, as from `make_address_record`
5. **Nickname CSV text:** a function that returns the CSV text; `write_csv` writes it. ClickNick keeps its own
   file writing (it preserves a Hidden file and names Excel when the file is locked).
6. **`Address.csv` reader:** take in ClickNick's `read_mdb_csv` (CLICK's MDB-format export: AddrKey,
   MemoryType, Address, DataType, Nickname, Use, InitialValue, Retentive, Comment; UTF-8 with BOM; MDB
   addresses). Returns `AddressRecord`s, keeping `used` from the Use column.

Open, Sam's judgment: an unknown Data Type string silently becomes the bank's default. Proposal: raise with
the line number, as for a bad address, in the same release.

## 2. Smaller items from ClickNick's inventory

Needs: nothing for the code; the API names are settled with the ClickNick session through Sam. After item 1.

- **Take `validate_click_name`** (PLC and DataView names: 1-24 of letters, digits, space, `_`, `-`) into
  `pyclickplc.validation`.
- **Take `read_plc_name` and `write_plc_name`** into `pyclickplc.project`. Its knowledge of CLICK 4's
  placeholder sections (`[Sec20] Key1=` for `[PLCName] PLCName=`) joins `project.py`'s `_restore_names`
  instead of living twice. `write_plc_name` keeps the rest of Project.ini byte for byte.
- **Take `iter_address_slots`** (every editable slot in display order: X/Y valid ranges, XD/YD hidden slots
  skipped) into `addresses.py`. pyrung's tag map and ClickNick's view builder loop over banks the same way.
- **Leave the unassigned I/O slot titles in ClickNick** ("Option slot N - unassigned" and the like). They are
  ClickNick's wording, not a CLICK fact; pyclickplc's `ModuleIO` already gives the location and position.
  Revisit if CLICK itself shows these names.

## 3. Waiting on CLICK

Needs: CLICK software (Sam, or ClickNick's sandbox runner later). Keep today's behaviour until answered.

- Does CLICK accept leading zeros (`DS0001`) and surrounding spaces in an address? If not, `parse_address`
  refuses them.
- Does CLICK import a bare space as a Text initial value? It exports one bare and imports a quoted `" "`.
  If it refuses bare, `write_csv` quotes a space as it quotes a comma or double quote.
- Does CLICK strip spaces from nicknames and comments on import or export? Decides whether item 1's
  "keep as written" needs a rule on write.

## Unscheduled

- **pymodbus is capped below 3.13.** 3.13 routes the server through SimDevice, so `server.py` needs a
  rewrite to lift it. Revisit when something forces it (a security fix, or a Python version the capped
  pymodbus does not support). pyrung imports only public names (`DataProvider`, `MemoryDataProvider`,
  `PlcValue`, `ClickServer`), so the rewrite does not involve pyrung as long as those keep their shape.
- The docs site's old `/releases/v0.2.0/` page disappears at the next docs deploy; the changelog replaces it.
