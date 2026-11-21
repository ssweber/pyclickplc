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

## 1. Decide whether the validators call `first_non_cp1252_char`

Needs: a decision by the pyclickplc session. ClickNick's runner has tried nicknames in CLICK but not comments.

- **`validate_nickname` and `validate_comment` accept a character that cp1252 does not have, but `write_csv`
  raises `ValueError` for it.** `validate_initial_value` also rejects a Text value above 127 that `write_csv`
  writes and `read_csv` reads. ClickNick also writes nicknames into SC_.mdb directly, and Access keeps the
  Unicode there.
- The ClickNick session's runner tried such characters in a nickname (job runner-batch2, J2, in
  `clicknick-wt/buildbot/jobs/runner-batch2/RESULTS.md`). CLICK 4.00's Address Picker changed ł to l and Ω to O
  without a message. It refused a nickname with Ж or an emoji. It stored U+0081. `first_non_cp1252_char`
  returns None for U+0081. ClickNick already refuses every character that `first_non_cp1252_char` returns.

## 2. Read the known modules when one module ID is unknown

Needs: nothing. It changes what the readers return and when they raise, so the session tells the ClickNick
session before it lands.

- If Project.ini has a module ID that the catalog does not have, `read_modules`, `read_io_layout` and
  `read_channel_parameters` raise `ValueError`. The caller then gets none of the modules that pyclickplc knows.
  On 2026-11-20 the ClickNick session asked for the readers to skip an unknown module and report it. ClickNick
  could then show the hardware that was read and name the module that was not.
- The catalog has every model and ID in the module tables of CLICK 2.60 to 4.00. An unknown ID should come only
  from a CLICK version after 4.00 or from a damaged file. The design is open: where the readers report the
  unknown ID, and whether `read_channel_parameters` still raises. The session that builds this item decides both
  and asks the ClickNick session before it lands.

## Unscheduled

- **The Project.ini readers and `write_plc_name` rest on rules that no one has tested in CLICK.** The planner
  ruled on 2026-11-18 that they get no runs. Do not queue them again. The comments in `project.py` name each
  rule.
- **On Windows, each client that resets before `ClickServer` accepts it logs an asyncio error and leaks a
  socket.** On the Proactor loop the accept fails (WinError 64). asyncio logs "Task exception was never
  retrieved". When the socket that asyncio made for the accept is collected, asyncio also logs a
  ResourceWarning. The server keeps listening. The cause is in asyncio. `IocpProactor.accept` closes that
  socket only when the accept is cancelled, and public API gives no way to reach the task that would close
  it. Needs: no change here. Someone should report it to CPython.
