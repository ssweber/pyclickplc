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

Needs: nothing for the code. This session and the ClickNick session settle the API names, and Sam passes the
messages between them.

- **Leave the unassigned I/O slot titles in ClickNick** ("Option slot N - unassigned" and the like). They are
  ClickNick's wording, not a CLICK fact. pyclickplc's `ModuleIO` already gives the location and position.
  Revisit if CLICK itself shows these names.

## 2. Waiting on CLICK

Needs: CLICK software (Sam, or ClickNick's sandbox runner later). Keep today's behaviour until CLICK answers.

- What encoding does CLICK use when it exports a nickname CSV with a non-ASCII nickname or comment typed in
  CLICK? On import, CLICK reads a file without a BOM as CP1252. `write_csv` writes UTF-8 without a BOM, so a
  `café` that it writes becomes `cafÃ©` in CLICK. CLICK reads a UTF-8 file with a BOM as UTF-8, then converts
  the text to CP1252 by best fit (`５` becomes `5`). An export from CLICK would answer the question. Until
  then, `write_csv` keeps writing UTF-8 without a BOM.
- The PLC name in Project.ini. In the fixtures, CLICK 3 always writes `PLCName=` under `[PLCName]`, and
  CLICK 4 always writes `Key1=` under `[Sec20]`. For a project with no name, the value is empty. So
  `write_plc_name` never adds a section to a file that CLICK wrote. In a CLICK 4 file that has
  `[PLCName] PLCName=` and no `[Sec20] Key1=`, `read_plc_name` returns the name under `[PLCName]`. CLICK
  4.00 shows no name for such a file. CLICK 4.00 matches `[Sec20]` and `Key1` regardless of case. If either appears twice,
  it uses the first. The code assumes two more rules that nobody has tested in CLICK. The first is that
  CLICK 3 reads `[PLCName]` the same way. The second is that if two sections have names that differ only in
  case, CLICK looks for the key only in the first of them. The code assumes this because Windows' INI
  functions behave that way. Two questions for CLICK: does CLICK 3 read `[PLCName]` that way, and does
  CLICK 4 look for a key in the second of two such sections?
- The hardware sections in Project.ini. CLICK 4 writes these sections under numbered placeholder names,
  such as `[Sec23]` for CLICK 3's `[CPUBuild]`. `read_modules` and the channel readers match `[Sec21]` to
  `[Sec23]` and CLICK 3's names regardless of case. If a section or key appears twice, they use the first.
  In a CLICK 4 file that has both a placeholder section and its named section, such as `[Sec23]` and
  `[CPUBuild]`, they ignore the named section. CLICK 4.00 is known to do this only for the PLC name. It
  shows the name under `[Sec20]` and ignores a `[PLCName]` beside it. Does CLICK 4 read the hardware
  sections the same way? Does CLICK 4 read a named section that has no placeholder beside it, such as
  `[CPUBuild]` alone? The readers read it, as `read_plc_name` reads `[PLCName]` alone. The readers follow
  configparser for a line that is indented under an option. They read the line as part of that option's
  value, even if it is `  [Sec20]`. Windows' INI functions probably trim the indent and read the line on
  its own. That is a guess, and nobody has tested it. Because the two readings can differ,
  `write_plc_name` refuses a file that has such a line. None of the four Project.ini fixtures has an
  indented line.

## Unscheduled

- **`ClickServer` answers function code 17 (report server id) with exception 01. A real CLICK answers it
  with data.** A real C2-03CPU in RUN (probed 2026-11-16) answered FC 7, 8 (sub-function 0), 11, 12, 20,
  24 and 43/14 with exception 01, as `ClickServer` does. It answered FC 17 with
  `11 09 00 ff 00 08 00 c6 03 c0 00`. The run indicator is FF. `00 c6` is 198, the module ID that
  `_module_catalog.py` gives the C2-03CPU. The other bytes are unknown. Sam decided to keep 01.
- **For a large DF value, CLICK's last digits follow no rule that anyone has found.** `write_plc_data`
  writes the same cell as CLICK for some large values and different last digits for others. This is left
  as it is, because both forms read back as the same float32.
- **On Windows, each client that resets before `ClickServer` accepts it logs an asyncio error and leaks a
  socket.** On the Proactor loop the accept fails (WinError 64). asyncio logs "Task exception was never
  retrieved". When the socket that asyncio made for the accept is collected, asyncio also logs a
  ResourceWarning. The server keeps listening. The cause is in asyncio. `IocpProactor.accept` closes that
  socket only when the accept is cancelled, and public API gives no way to reach the task that would close
  it. Needs: no change here. Someone should report it to CPython.
