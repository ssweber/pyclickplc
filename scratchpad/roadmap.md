# pyclickplc roadmap

What is still to do in this repo, in order. Work that crosses repos is in the ecosystem plan
(`ssweber.github.io/plan/README.md`, "Who owns what" and "Order by repo"). This file links to it and does not repeat it.
When an item lands, delete it.

Each item says what it needs: **nothing** (code only), **CLICK software**, **a real PLC**, or **Sam's
judgment**. Work that needs nothing is not queued behind work that needs Sam.

Branches: feature and refactor branches go into an always-releasable `main`. Since 2026-11-15 the session pushes
its branch and opens the PR. It squash-merges the PR when CI is green on the head commit, a fresh reviewer has
passed that commit, and nothing in the PR waits on Sam (his judgment, a CLICK check, a real PLC). The release
(tag and publish) stays Sam's.

## 1. Smaller items from ClickNick's inventory

Needs: nothing for the code. Sam settles the API names with the ClickNick session.

- **Leave the unassigned I/O slot titles in ClickNick** ("Option slot N - unassigned" and the like). They are
  ClickNick's wording, not a CLICK fact. pyclickplc's `ModuleIO` already gives the location and position.
  Revisit if CLICK itself shows these names.

## 2. Waiting on CLICK

Needs: CLICK software (Sam, or ClickNick's sandbox runner later). Keep today's behaviour until CLICK answers.

- What encoding does CLICK use when it exports a nickname CSV with a non-ASCII nickname or comment typed in
  CLICK? On import, CLICK reads a file without a BOM as CP1252. So `write_csv`'s UTF-8 `café` is stored as
  `cafÃ©`. CLICK reads a UTF-8 file with a BOM as UTF-8, then converts it to CP1252 by best fit (`５` becomes
  `5`). An export from CLICK would answer the question. Until then `write_csv` keeps its encoding.
- The PLC name in Project.ini. The fixtures show that CLICK 3 (`[PLCName] PLCName=`) and CLICK 4
  (`[Sec20] Key1=`) always write the name line, and leave it empty for a project with no name. So
  `write_plc_name` never adds a section to a file that CLICK wrote. `read_plc_name` reads `[PLCName]` alone in
  a CLICK 4 file. CLICK 4.00 shows no name for such a file (C2 p11). We saw CLICK 4.00 match `[Sec20] Key1`
  regardless of case and take the first match. Two parts are inferred and not tested in CLICK. One is that
  CLICK 3 reads `[PLCName]` the same way. The other is that CLICK does not search a key in a second section
  that matches the first only in case (Windows' INI functions). Two questions for CLICK: does CLICK 3 read
  `[PLCName]` that way, and does CLICK 4 search a key in a second matching section?
- The hardware sections in Project.ini. `read_modules` and the channel readers match `[Sec21]` to `[Sec23]`
  and CLICK 3's sections regardless of case. They take the first of a repeated section or key. In a CLICK 4
  file they ignore a named section that sits beside its placeholder (`[CPUBuild]` beside `[Sec23]`). We saw
  CLICK 4.00 do this only for `[Sec20]`. Does it read the hardware sections the same way? Does CLICK 4 read
  a named section with no placeholder, such as `[CPUBuild]` alone? The readers read it, as `read_plc_name`
  reads `[PLCName]` alone. The readers treat a line indented under an option (a continuation line) the way
  configparser does, as part of that option's value, even `  [Sec20]`. Windows' INI functions probably trim
  the indent and read the line as a line of its own (inferred). So `write_plc_name` refuses a file with a
  continuation line. The four Project.ini fixtures have no indented line.

## Unscheduled

- **`ClickServer` answers function code 17 (report server id) with exception 01, where a CLICK answers.**
  A real C2-03CPU in RUN (probed 2026-11-16) answered FC 7, 8 (sub-function 0), 11, 12, 20,
  24 and 43/14 with exception 01, as `ClickServer` does. It answered FC 17 with
  `11 09 00 ff 00 08 00 c6 03 c0 00`. The run indicator is FF, and `00 c6` = 198, the catalog's id for
  C2-03CPU. The other bytes are unknown. Sam decided to keep 01.
- **CLICK's digits for a large DF value follow no rule found** (ClickNick's run D2), so `write_plc_data`
  matches CLICK's cell for some large values and not for others. This is not pursued, because both forms
  read back as the same float32.
- **On Windows, each client that resets before `ClickServer` accepts it logs an asyncio error and leaks a
  socket.** On the Proactor loop the accept fails (WinError 64). asyncio logs "Task exception was never
  retrieved". When the socket that asyncio made for the accept is collected, asyncio also logs a
  ResourceWarning. The server keeps listening. The cause is in asyncio. `IocpProactor.accept` closes that
  socket only when the accept is cancelled, and public API gives no way to reach the task that would close
  it. Needs: nothing here, but a CPython report.
