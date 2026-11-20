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

## 1. After 0.11.0

Needs: nothing in this repo. The ClickNick and pyrung sessions do the steps below. 0.11.0 was published
on 2026-11-20. Delete this item when ClickNick requires 0.11.0 or later and pyrung's lock file has 0.11.0 or later.

- The ClickNick session moves ClickNick to the release. ClickNick encodes the `format_csv` text as UTF-8
  itself. It should encode the text as cp1252. `format_csv` raises `ValueError` for a character that cp1252
  does not have. ClickNick's save must report that error.
  ClickNick's test `test_an_encoding_failure_leaves_the_file_as_it_was` expects `UnicodeEncodeError` and
  must expect `ValueError`.
- pyrung writes nicknames with `write_csv`. It requires `pyclickplc>=0.9.1` with no upper bound. A user who
  installs pyrung now gets pyclickplc 0.11.0 or later, so their nickname CSV is written in cp1252 and `write_csv`
  can raise the new `ValueError`. pyrung's lock file stays at 0.9.1 until the pyrung session updates it.
- 0.11.1 no longer fills a blank nickname at SD132 to SD135. pyrung's `tests/click/test_tag_map.py` and
  ClickNick's `tests/test_live_system_nicknames.py` expect four repairs, including fills at SD134 and SD135.
  Each session updates its test when it moves to 0.11.1.

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
