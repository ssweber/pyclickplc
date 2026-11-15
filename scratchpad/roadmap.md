# pyclickplc roadmap

What is still to do in this repo, in order. Work that crosses repos is in the ecosystem plan
(`ssweber.github.io/plan/README.md`, "Who owns what" and "Order by repo"); it is linked here, not repeated.
When an item lands, delete it.

Each item says what it needs: **nothing** (code only), **CLICK software**, **a real PLC**, or **Sam's
judgment**. Work that needs nothing is not queued behind work that needs Sam.

Branches: feature and refactor branches into an always-releasable `main`. Sam squash-merges. Push and open a
PR only once Sam has said so directly; otherwise stop at "CI green locally, ready to push".

## 1. Release the address and CSV reader changes (0.6.0)

Needs: Sam (he publishes the release). The changes are on `main` once their PR merges; the changelog's
Unreleased section lists them. laddercodec's parity test waits on this release, and ClickNick can then move
onto `read_csv`, `format_csv` and `read_mdb_csv`. pyrung's tag map reads through `read_csv`, so a pyrung CSV
with a bad address or an unknown Data Type now fails to load instead of losing the row.

pyrung follow-up (pyrung's, not ours): `read_csv` no longer fails on a repeated nickname, and pyrung's own
repeat check (`seen_names` in `tag_map/_nickname_io.py`) is case-sensitive, so `Pump` at X001 and `pump` at
X002 now load as two tags in pyrung, where pyclickplc's `.tag` treats them as one nickname.

## 2. Smaller items from ClickNick's inventory

Needs: nothing for the code; the API names are settled with the ClickNick session through Sam.

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
- Does CLICK import a nickname CSV whose non-Text initial value is quoted (`"1.5"`)? `write_csv` quotes one
  only when it holds a comma, double quote or line break. If not, `write_csv` refuses such a value instead.
- Does CLICK ever export a Data Type that isn't the bank's, or the name `TXT`? `read_csv` refuses both, and
  `read_mdb_csv` ignores Address.csv's DataType column. If it does, `read_csv` accepts what CLICK writes.
- Can an Address Comment hold a line break? If yes, `read_csv` must requote a bare-comma Text row whose
  quoted comment spans lines (it raises today).
- Does a "Read Data from PLC" dump give X/Y expansion rows more than 16 cells? `read_plc_data` skips cells
  past a bank's addresses. If it does, check what those cells hold before skipping them stays the rule.

## Unscheduled

- **pymodbus is capped below 3.13.** 3.13 routes the server through SimDevice, so `server.py` needs a
  rewrite to lift it. Revisit when something forces it (a security fix, or a Python version the capped
  pymodbus does not support). pyrung imports only public names (`DataProvider`, `MemoryDataProvider`,
  `PlcValue`, `ClickServer`), so the rewrite does not involve pyrung as long as those keep their shape.
- The docs site's old `/releases/v0.2.0/` page disappears at the next docs deploy; the changelog replaces it.
