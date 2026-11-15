# BOB profile: pyclickplc

Repo-specific rules for the /bob skill. Another repo replaces this file.

## Paths

- Main checkout `C:/Users/Sam/Documents/GitHub/pyclickplc`, base branch `main`. Feature and
  refactor branches go into an always-releasable `main` through PRs; Sam squash-merges and
  publishes releases.
- Worktrees `../pyclickplc-wt/<name>` on `bob/<name>`; mergeq home `../pyclickplc-wt/buildbot`
  (logs, `jobs/<id>/{BRIEF,HANDOFF,REVIEW,LEDGER}.md`).
- The plan of record is `scratchpad/roadmap.md`. Arc docs live under the home, outside the repo
  (`jobs/<arc>/ARC.md`). When an arc closes, its open items move into the roadmap.

## Environment (put in every builder and reviewer brief)

- A new worktree needs `make install` once (`uv sync --locked --all-extras --dev`).
- `make lint` edits files (codespell, ruff fix and format, ty). `make test` is the full suite,
  about 15 s. `make docs-check` is the strict docs build. Targeted pytest is fine.
- No multi-line content inlined in shell commands (heredocs, `python -c`): write a file with
  Write, then run it.
- Reviewers run tests as `cd <worktree> && uv run pytest <tests> -q` (the hook wraps pytest in
  a timeout itself).

## Correctness contract (put in every builder and reviewer brief)

- AGENTS.md is the contract. File output matches CLICK byte for byte, tested against a
  CLICK-written fixture. `parse_address` and `format_address_display` are the only way to
  parse or format an address. `DataType` is the single source of truth for PLC types.
  `pymodbus` stays below 3.13.
- Ground truth is what CLICK Programming Software writes and reads (nickname CSV, DataView
  CDV, data dumps, Project.ini) and what a real CLICK serves over Modbus. Never edit a recorded
  expectation to fit the code.
- Agents never touch the user's real CLICK or files on Sam's Desktop. Questions only CLICK can
  answer go to the user, batched.
- ClickNick, pyrung and laddercodec (checkouts beside this repo) consume pyclickplc. Every
  change to a public name, output byte or exception gets a CHANGELOG "Behaviour changes" line.
  Before a release, run their suites against the branch:
  `cd ../pyrung && uv run --with-editable ../pyclickplc pytest -q` (the same for clicknick).
- A bug fix comes with a regression test that fails on the base and passes on the branch.
- CHANGELOG (Unreleased) moves with what a user sees; no entry for lockfile or CI changes, and
  published entries are never rewritten. Docs follow docs/AGENTS.md.

## Gate

`make lint`, `make test`, `make docs-check`, all three on every branch (they are cheap).
GitHub CI reruns lint and tests on Python 3.11-3.14 for the PR.

## Models

- Builders: Opus at `effort: high` for readers and writers of CLICK files, address parsing,
  the Modbus client and server; Sonnet for docs-only, tests-only or a single small helper.
- Reviewers: Opus for file formats, addresses and Modbus; Sonnet for docs and tests.
- Read-only code questions: `bob-investigator`, Sonnet.

## Machine budget

- Up to ~4 builders in parallel. Only `targeted_slots` (3) test runs go at once.
- Read a gate's exit code directly, never through a pipe without `pipefail`.

## Ground truth

Sam runs CLICK and can export a nickname CSV, save a DataView, or read data from a PLC. Collect
those questions and list them in milestone reports, batched.

## Gotcha

Agent `isolation: worktree` may fail here (cwd `documents` vs git `Documents` case mismatch):
always use `M worktree new` and brief the builder with the path.
