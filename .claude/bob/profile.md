# BOB profile: pyclickplc

This file holds the repo-specific settings that the bob plugin's skill and agents use.

## Paths and branches

- Main checkout `C:/Users/Sam/Documents/GitHub/pyclickplc`, base `main`. There is no merge queue.
  Each READY branch becomes its own pull request (the skill's section 3a).
- Worktrees `../pyclickplc-wt/<name>` on `bob/<name>` (`run.py worktree new <name>`).
- Job notes (`<jobs>`, `jobs_dir` in config.toml): `../pyclickplc-wt/.bob/jobs/<name>/`
  (`BRIEF.md`, `HANDOFF.md`, `REVIEW.md`, `PR.md`) and `../pyclickplc-wt/.bob/jobs/<arc>/LEDGER.md`.
- The plan of record is `scratchpad/roadmap.md`. Arc docs live under `<jobs>/<arc>/ARC.md`,
  outside the repo. When an arc closes, move its open items into the roadmap. When an item
  lands, delete it from the roadmap in the branch that lands it.

## Environment (put in every builder and reviewer brief)

- A new worktree needs `make install` once (`uv sync --locked --all-extras --dev`).
- `make lint` edits files (codespell, ruff fix and format, ty). `make test` runs the full suite
  and takes about 15 s. `make docs-check` runs the strict docs build. Targeted pytest is fine.
- Do not put multi-line content inline in a shell command (heredocs, `python -c`). Write a file
  with Write, then run it.

## Gate

The local gate is `make lint && make test && make docs-check`. Run it on the branch's last
commit. Afterwards the worktree must be clean, which means lint rewrote nothing. All three are
cheap, so builders run the whole gate. Read the gate's exit code directly, never through a pipe
without `pipefail`.

GitHub CI reruns lint and tests on Python 3.11-3.14 and builds the docs on every pull request.
Its `ci` job passes only when all of those pass. `main` requires the docs `build`. Until Sam
swaps the ruleset to `ci`, `main` also requires the four `build (ubuntu-latest, 3.x)` checks, so
do not change the test matrix before then.

## Correctness contract (put in every builder and reviewer brief)

- AGENTS.md is the contract. `parse_address` and `format_address_display` are the only way to
  parse or format an address. `DataType` is the single source of truth for PLC types.
  `ClickServer` runs on asyncio and imports no pymodbus. Only `ClickClient` uses pymodbus.
  Keep the suite passing on the pymodbus floor (3.12.0).
- What pyclickplc writes must match CLICK byte for byte (encoding, BOM, line ends, quoting).
  Test it against a CLICK-written fixture. A reader and its writer agree, so a write followed by
  a read gives back what was written. Where two paths do one job, they must agree. The client
  and the server are two such paths. So are `parse_address` and any code that parses addresses
  itself.
- If a change alters what pyclickplc writes for CLICK, or how it reads a CLICK file, Sam must
  check it in CLICK. The hand-back and the pull request both say what to check.
- ClickNick, pyrung and laddercodec (checkouts beside this repo) consume this library. A change
  to a public name, an output byte or an exception is a change for them. The hand-back lists
  each one, and each gets a line under the CHANGELOG's "Breaking changes" heading (AGENTS.md says
  how). Reviewers grep those repos' `src/` for the callers. Before a release, run their suites
  against the branch. For ClickNick, run
  `cd ../clicknick && uv run --no-sync --with-editable ../pyclickplc pytest -q`. For pyrung, the
  full suite takes over 25 minutes here, so run `tests/click` and its nickname, tag-map and
  data-dump tests with a timeout.
- A bug fix comes with a regression test that fails on the base and passes on the branch.
- Add a CHANGELOG (Unreleased) entry when a user sees the change. Add none for lockfile or CI
  changes. Never rewrite a published entry. Change user docs (`docs/`, CHANGELOG) only where
  what a user sees or does changes. A fine edge goes in a test, not a paragraph. Prose follows
  the Writing section of AGENTS.md. Do not tell the history of a change in docs or comments,
  and do not use marketing words.

## Ground truth

Ground truth is the files that CLICK Programming Software wrote (`tests/fixtures/*.csv`, `*.cdv`,
Project.ini samples) and the values that a real CLICK served over Modbus. Never edit one to fit
the code. A fixture stays byte for byte as CLICK wrote it (`.gitattributes` keeps its line
ends). Agents never touch Sam's real CLICK, his PLC programs or files on his Desktop. Ask Sam
the questions that only CLICK can answer, batched. They wait in `scratchpad/roadmap.md`
("Waiting on CLICK"). A pull request that depends on one stays open.

## Models

- Builders: Opus at `effort: high` for readers and writers of CLICK files, address parsing, the
  Modbus client and server; Sonnet for docs-only, tests-only, CI or a single small helper.
- Reviewers: Opus for file formats, addresses and Modbus; Sonnet for docs, tests and CI.
- Read-only code questions: `bob:bob-investigator`, Sonnet.

## Machine budget

Run up to ~4 builders in parallel, and up to `targeted_slots` (3) bounded runs at once.

## Releases

The release is Sam's. Never tag, publish or run a docs deploy. A release is a small PR that
dates the CHANGELOG's Unreleased section. After Sam publishes it, `publish.yml` uploads to PyPI
and starts the docs deploy.

## Gotcha

Agent `isolation: worktree` may fail here, because the cwd says `documents` and git says
`Documents`. Always use `run.py worktree new`, and give the builder the path in its brief.
