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
- **The Text rules disagree about some characters.** An initial value is a cp1252 character, so the euro sign
  is valid and U+0080 is not. A runtime, DataView or PLC data value is a character with a code from 0 to 255, so
  U+0080 is valid and the euro sign (U+20AC) is not. A PLC was seen to store the Text byte 0xC8 unchanged. No one knows
  what a PLC holds after CLICK writes a project whose Text initial value is the euro sign. Needs: a real PLC.
