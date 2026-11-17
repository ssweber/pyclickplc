# pyclickplc roadmap

What is still to do in this repo, in order. Work that crosses repos is in the ecosystem plan
(`ssweber.github.io/plan/README.md`, "Who owns what" and "Order by repo"); it is linked here, not repeated.
When an item lands, delete it.

Each item says what it needs: **nothing** (code only), **CLICK software**, **a real PLC**, or **Sam's
judgment**. Work that needs nothing is not queued behind work that needs Sam.

Branches: feature and refactor branches into an always-releasable `main`. Since 2026-11-15 the session pushes
its branch, opens the PR and squash-merges it once CI is green on the head commit, a fresh reviewer has passed
that commit, and nothing in it waits on Sam (his judgment, a CLICK check, a real PLC). The release (tag and
publish) stays Sam's.

## 1. Smaller items from ClickNick's inventory

Needs: nothing for the code; the API names are settled with the ClickNick session through Sam.

- **Leave the unassigned I/O slot titles in ClickNick** ("Option slot N - unassigned" and the like). They are
  ClickNick's wording, not a CLICK fact; pyclickplc's `ModuleIO` already gives the location and position.
  Revisit if CLICK itself shows these names.

## 2. Waiting on CLICK

Needs: CLICK software (Sam, or ClickNick's sandbox runner later). Keep today's behaviour until answered.

- What encoding does CLICK use when it exports a nickname CSV with a non-ASCII nickname or comment typed in
  CLICK? On import CLICK reads a file without a BOM as CP1252, so `write_csv`'s UTF-8 `café` is stored
  `cafÃ©`, and reads a UTF-8 file with a BOM as UTF-8, then brings it into CP1252 by best fit (`５` becomes
  `5`). An export from CLICK answers it; until then `write_csv` keeps its encoding.
- The PLC name in Project.ini. The fixtures show that CLICK 3 (`[PLCName] PLCName=`) and CLICK 4
  (`[Sec20] Key1=`) always write the name line, empty for a project with no name, so `write_plc_name` never
  adds a section to a file CLICK wrote. `read_plc_name` reads `[PLCName]` alone in a CLICK 4 file, where
  CLICK 4.00 shows no name (C2 p11). CLICK 4.00 was seen to match `[Sec20] Key1` regardless of case and
  take the first match. Two parts are inferred, not tested in CLICK: that CLICK 3 reads `[PLCName]` the same
  way, and that a key in a second section matching the first only in case is not searched (Windows' INI
  functions). Does CLICK 3 read `[PLCName]` so, and does CLICK 4 search a key in a second matching section?
- The hardware sections in Project.ini. `read_modules` and the channel readers match `[Sec21]` to `[Sec23]`
  and CLICK 3's sections regardless of case, take the first of a repeated section or key, and in a CLICK 4
  file ignore a named section beside its placeholder (`[CPUBuild]` beside `[Sec23]`). CLICK 4.00 was seen
  to do this only for `[Sec20]`: does it read the hardware sections the same way? And is a named section
  with no placeholder, such as `[CPUBuild]` alone, read in a CLICK 4 file? The readers read it, as
  `read_plc_name` reads `[PLCName]` alone. A line indented under an option (a continuation line) is read
  as configparser reads it, as part of that option's value, even `  [Sec20]`; Windows' INI functions
  likely trim the indent and read a line of its own (inferred), so `write_plc_name` refuses a file with a
  continuation line. The four Project.ini fixtures have no indented line.

## Unscheduled

- **`ClickServer` answers function code 17 (report server id) with exception 01, where a CLICK answers.**
  A real C2-03CPU in RUN (probed 2026-11-16) answered FC 7, 8 (sub-function 0), 11, 12, 20,
  24 and 43/14 with exception 01, as `ClickServer` does, and FC 17 with `11 09 00 ff 00 08 00 c6 03 c0 00`:
  run indicator FF, `00 c6` = 198, the catalog's id for C2-03CPU; the other bytes are unknown. Decided
  (Sam): keep 01.
- **CLICK's digits for a large DF value follow no rule found** (ClickNick's run D2), so `write_plc_data`
  matches CLICK's cell for some large values and not for others. Not pursued: both forms read back as the
  same float32.
- **On Windows, each client that resets before `ClickServer` accepts it logs an asyncio error and leaks a
  socket.** On the Proactor loop the accept fails (WinError 64); asyncio logs "Task exception was never
  retrieved" and, when the socket it made for the accept is collected, a ResourceWarning. The server keeps
  listening. The cause is in asyncio: `IocpProactor.accept` closes that socket only when the accept is
  cancelled, and the task that would close it is out of reach through public API. Needs: nothing here; a
  CPython report.
