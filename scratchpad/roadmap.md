# pyclickplc roadmap

What is still to do in this repo, in order. Work that crosses repos is in the ecosystem plan
(`ssweber.github.io/plan/README.md`, "Who owns what" and "Order by repo"); it is linked here, not repeated.
When an item lands, delete it.

Each item says what it needs: **nothing** (code only), **CLICK software**, **a real PLC**, or **Sam's
judgment**. Work that needs nothing is not queued behind work that needs Sam.

Branches: feature and refactor branches into an always-releasable `main`. Sam squash-merges. Push and open a
PR only once Sam has said so directly; otherwise stop at "CI green locally, ready to push".

## 1. Smaller items from ClickNick's inventory

Needs: nothing for the code; the API names are settled with the ClickNick session through Sam.

- **Leave the unassigned I/O slot titles in ClickNick** ("Option slot N - unassigned" and the like). They are
  ClickNick's wording, not a CLICK fact; pyclickplc's `ModuleIO` already gives the location and position.
  Revisit if CLICK itself shows these names.

## 2. Waiting on CLICK

Needs: CLICK software (Sam, or ClickNick's sandbox runner later). Keep today's behaviour until answered.

- Does CLICK accept spaces around an address? `parse_address` accepts them. If not, it refuses them.
- Does CLICK strip a tab (or other whitespace) at the edge of a nickname or comment, and does it import a bare
  tab as a Text initial value? Today only spaces are rejected (nickname, comment) or quoted (Text value).
- Does a "Read Data from PLC" dump give X/Y expansion rows more than 16 cells? `read_plc_data` skips cells
  past a bank's addresses. If it does, check what those cells hold before skipping them stays the rule.
- The PLC name in Project.ini. The fixtures show that CLICK 3 (`[PLCName] PLCName=`) and CLICK 4
  (`[Sec20] Key1=`) always write the name line, empty for a project with no name, so `write_plc_name` never
  adds a section to a file CLICK wrote. Still owed: does CLICK match section names regardless of case?
  `write_plc_name` refuses a header that differs from the name's section only in case.

## Unscheduled

- **pymodbus is capped below 3.13.** 3.13 routes the server through SimDevice, so `server.py` needs a
  rewrite to lift it. Revisit when something forces it (a security fix, or a Python version the capped
  pymodbus does not support). pyrung imports only public names (`DataProvider`, `MemoryDataProvider`,
  `PlcValue`, `ClickServer`), so the rewrite does not involve pyrung as long as those keep their shape.
- The docs site's old `/releases/v0.2.0/` page disappears at the next docs deploy; the changelog replaces it.
