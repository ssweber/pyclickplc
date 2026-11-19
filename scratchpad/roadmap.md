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

## 2. Waiting on ClickNick's runner

Needs: CLICK software. The ClickNick session runs the check.

- **`validate_nickname` and `validate_comment` accept a character that cp1252 does not have, but `write_csv`
  raises `ValueError` for it.** `validate_initial_value` also rejects a Text value above 127 that `write_csv`
  writes and `read_csv` reads. ClickNick also writes nicknames into SC_.mdb directly, and Access keeps the
  Unicode there. The ClickNick session will check on its runner what CLICK shows for such a character. Once
  that is known, decide whether the validators call `first_non_cp1252_char`.

## Unscheduled

- **The Project.ini readers and `write_plc_name` rest on rules that no one has tested in CLICK.** The planner
  ruled on 2026-11-18 that they get no runs. Do not queue them again. The comments in `project.py` name each
  rule. The rules cover these cases:
  - a key only in the second of two sections whose names differ only in case;
  - a line indented under an option;
  - the case of the hardware section and key names, and which of two matches CLICK uses, in CLICK 4
    (`[Sec21]` to `[Sec23]`) and in CLICK 3 (`[SystemConfig]`, `[SystemConfigData]`, `[CPUBuild]`);
  - in CLICK 4, `[Sec22]` and `[Sec23]` beside their named sections, and a named section such as
    `[CPUBuild]` alone;
  - a CLICK 4 file that also has `[SystemConfig]`. The module reads it as a CLICK 3 file, including the PLC
    name;
  - in CLICK 3, the case of `[PLCName]` and `PLCName`, and repeated sections and keys.
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
