# BOB profile: pyclickplc

This repo's specifics for the bob plugin's skill and agents.

## Paths and branches

- Main checkout `C:/Users/Sam/Documents/GitHub/pyclickplc`, base `main`. No merge queue: each
  READY branch becomes its own pull request (the skill's section 3a).
- Worktrees `../pyclickplc-wt/<name>` on `bob/<name>` (`run.py worktree new <name>`).
- Job notes (`<jobs>`): `../pyclickplc-wt/.bob/jobs/<name>/` (`BRIEF.md`, `HANDOFF.md`,
  `REVIEW.md`, `PR.md`) and `../pyclickplc-wt/.bob/jobs/<arc>/LEDGER.md`.
- The plan of record is `scratchpad/roadmap.md`. Arc docs live under `<jobs>/<arc>/ARC.md`,
  outside the repo. When an arc closes, its open items move into the roadmap, and an item that
  lands is deleted from the roadmap in the branch that lands it.

## Environment (put in every builder and reviewer brief)

- A new worktree needs `make install` once (`uv sync --locked --all-extras --dev`).
- `make lint` edits files (codespell, ruff fix and format, ty). `make test` is the full suite,
  about 15 s. `make docs-check` is the strict docs build. Targeted pytest is fine.
- No multi-line content inlined in shell commands (heredocs, `python -c`): write a file with
  Write, then run it.

## Gate

The local gate is `make lint && make test && make docs-check` on the branch's last commit,
with a clean worktree afterwards (lint rewrites nothing). All three are cheap, so builders run
the whole gate. Read a gate's exit code directly, never through a pipe without `pipefail`.
GitHub CI reruns lint and tests on Python 3.11-3.14 (its `ci` job passes only when all of them
did) and builds the docs on every pull request. `main` requires the docs `build` and, until Sam
swaps the ruleset to `ci`, the four `build (ubuntu-latest, 3.x)` checks: don't change the test
matrix before that.

## Correctness contract (put in every builder and reviewer brief)

- AGENTS.md is the contract. `parse_address` and `format_address_display` are the only way to
  parse or format an address. `DataType` is the single source of truth for PLC types.
  The server decodes and answers through its own `custom_pdu` request classes, never
  pymodbus's datastore or request decoding. Raise the pymodbus cap only after these pass on
  the new version: the full suite, the request coverage test in `tests/test_server.py` and
  the raw limit tests in `tests/test_integration.py`. Keep the suite passing on the floor
  (3.12.0).
- What pyclickplc writes must match CLICK byte for byte (encoding, BOM, line ends, quoting),
  tested against a CLICK-written fixture. A reader and its writer agree: a write followed by a
  read gives back what was written. Where two paths do one job (the client and the server;
  `parse_address` and any code that parses addresses itself), they must agree.
- A change to what pyclickplc writes for CLICK, or to how it reads a CLICK file, needs a check
  in CLICK by Sam: the hand-back says what to check, and so does the pull request.
- ClickNick, pyrung and laddercodec (checkouts beside this repo) consume this library. A change
  to a public name, an output byte or an exception is a change for them: the hand-back lists
  each, and each gets a line in the CHANGELOG's "Behaviour changes" block (AGENTS.md says how).
  Reviewers grep their `src/` for the callers. Before a release, run their suites against the
  branch: `cd ../clicknick && uv run --no-sync --with-editable ../pyclickplc pytest -q`; for pyrung,
  whose full suite takes over 25 minutes here, run `tests/click` and its nickname, tag-map and
  data-dump tests with a timeout.
- A bug fix comes with a regression test that fails on the base and passes on the branch.
- CHANGELOG (Unreleased) moves with what a user sees; no entry for lockfile or CI changes, and
  published entries are never rewritten. User docs (`docs/`, CHANGELOG) change only where what
  a user sees or does changes; a fine edge goes in a test, not a paragraph. Writing follows
  docs/AGENTS.md: plain and direct, no history, no marketing words.

## Ground truth

Files CLICK Programming Software wrote (`tests/fixtures/*.csv`, `*.cdv`, Project.ini samples)
and values a real CLICK served over Modbus. Never edit one to fit the code; a fixture stays byte
for byte as CLICK wrote it (`.gitattributes` keeps its line ends). Agents never touch Sam's real
CLICK, his PLC programs or files on his Desktop. Questions only CLICK can answer go to Sam,
batched, and wait in `scratchpad/roadmap.md` ("Waiting on CLICK"); a pull request that depends
on one stays open.

## Models

- Builders: Opus at `effort: high` for readers and writers of CLICK files, address parsing, the
  Modbus client and server; Sonnet for docs-only, tests-only, CI or a single small helper.
- Reviewers: Opus for file formats, addresses and Modbus; Sonnet for docs, tests and CI.
- Read-only code questions: `bob:bob-investigator`, Sonnet.

## Machine budget

Up to ~4 builders in parallel; `targeted_slots` (3) bounded runs at once.

## Releases

The release is Sam's: never tag, publish or run a docs deploy. A release is a small PR that
dates the CHANGELOG's Unreleased section; after Sam publishes it, `publish.yml` uploads to PyPI
and starts the docs deploy.

## Gotcha

Agent `isolation: worktree` may fail here (cwd `documents` vs git `Documents` case mismatch):
always use `run.py worktree new` and brief the builder with the path.
