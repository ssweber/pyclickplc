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

## 1. Next release

Needs: Sam's judgment (the version and the tag). The CHANGELOG's Unreleased section holds the nickname CSV
changes from #67. This session proposed 0.11.0, because the release breaks callers. `write_csv` writes
cp1252 instead of UTF-8. `write_csv` and `format_csv` raise `ValueError` for a character that cp1252 does
not have, and 0.10.0 accepted that character. When Sam picks the version, this session renames and dates
the section in a release PR, and Sam tags.

After the tag:

- The ClickNick session moves ClickNick to the release. ClickNick encodes the `format_csv` text as UTF-8
  itself. It should encode the text as cp1252. `format_csv` raises `ValueError` for a character that cp1252
  does not have, and ClickNick's save must report that error.
- pyrung writes nicknames with `write_csv`. It requires `pyclickplc>=0.9.1` with no upper bound. So a user
  who installs pyrung after the release gets cp1252 and the new `ValueError` at once. pyrung's lock file
  stays at 0.9.1 until the pyrung session updates it.

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
  rule.
- **On Windows, each client that resets before `ClickServer` accepts it logs an asyncio error and leaks a
  socket.** On the Proactor loop the accept fails (WinError 64). asyncio logs "Task exception was never
  retrieved". When the socket that asyncio made for the accept is collected, asyncio also logs a
  ResourceWarning. The server keeps listening. The cause is in asyncio. `IocpProactor.accept` closes that
  socket only when the accept is cancelled, and public API gives no way to reach the task that would close
  it. Needs: no change here. Someone should report it to CPython.
