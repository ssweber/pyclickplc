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

- Does CLICK import these number initial values, which Python's `int()` and `float()` accept and
  `validate_initial_value` accepts today? `1_000`, `+5`, `1e3`, `.5`, HEX `0x1F`; a value with `\xa0` or another
  Unicode space at an edge; non-ASCII digits such as `٥` and fullwidth `５`. The next import test answers them.
  A likely fix is to refuse non-ASCII for every type but TXT.
- Data dumps ("Read Data from PLC", `tests/fixtures/PlcDataDump.csv`). Owed:
  - How does CLICK write a TXT `,`, `$`, `"` and the other punctuation besides `+`, `-` and `.`?
    `write_plc_data` raises for them until a dump shows each form.
  - The dump shows `$20`, `$D` and `$C8`; the other TXT escapes follow from them. Read back a TXT holding
    0x01, 0x7F and 0xFF to confirm `write_plc_data`'s `$1`, `$7F` and `$FF`.
  - The DF form is inferred from 1e30, 3e37 and 3e38: CLICK keeps as many leading digits as fit in an
    unsigned 64-bit integer, writes zeros after them, and cuts decimals to keep 40 digits. Read back DF values
    of 1.8e30, 1.9e30, 2e30, 1.5e30, 1e35, -3e38, -0.0 and 0.001953125 to confirm; `write_plc_data` writes
    `1800000027085439195800000000000.00000000`, `1899999953032322092000000000000.00000000`,
    `2000000030094932440000000000000.00000000`, `1499999947013335603900000000000.00000000`,
    `100000004091847875960000000000000000.0000`, `-300000000549775575800000000000000000000.0`,
    `-0.00000000` and `0.00195312`. 1.8e30 and 1.9e30 tell a cut-off at 2**64 from one at 2e19.
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
