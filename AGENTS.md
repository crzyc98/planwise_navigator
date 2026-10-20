# Fidelity PlanAlign Engine – AGENTS.md

Guidance for Codex and other coding agents. `CLAUDE.md` (root) and `dbt/CLAUDE.md` hold the full project rules. When they disagree with this file, they win.

Event-sourced workforce and DC-plan simulation: DuckDB + dbt, driven by a Python orchestrator, with PlanAlign Studio (FastAPI + React/Vite + Tailwind v4) as the product UI. Versions are pinned in `pyproject.toml` and `planalign_studio/package.json`.

## How to work

- Make minimal, root-cause diffs that match the surrounding style. Mention unrelated issues in your final message; don't fix them.
- Don't install packages, fetch from the network, commit, or create branches unless asked.
- Avoid destructive actions (`rm -rf`, resets, writing to the shared dev DB) unless explicitly requested.
- Final message: what changed and why, the exact commands to verify it, and any assumptions.

## Commands

- **Environment:** each tool call is a fresh shell, so activating the venv in one call doesn't carry over. Start with `python3 scripts/dev.py --check`, then run commands as `python3 scripts/dev.py -- <command>` (for example `python3 scripts/dev.py -- python -m pytest -m fast`). In a worktree without the script, call the main checkout's `scripts/dev.py` by absolute path, with cwd still in the worktree. Never install into a borrowed environment. A missing module can also mean an undeclared dependency or a bad import, so read the error first.
- **Paths:** find uncertain filenames with `rg --files` before reading them. Use `--require <path>` to fail fast before expensive commands. Don't assume directories exist.
- **Search exit codes:** `rg`/`grep` exit 1 means no matches; exit 2 means an error. Handle an expected exit 1 explicitly rather than masking it with `|| true`. Keep searches separate from validation commands.
- **Tests:** `python -m pytest -m fast` for the TDD loop. Integration tests run against an isolated `DATABASE_PATH`.
- **Lint/type:** `ruff check .`, `mypy planalign_orchestrator/ planalign_cli/ planalign_core/ --ignore-missing-imports`.
- **dbt:** run only from `dbt/`, always with `--threads 1`, and narrow runs with `--select`.
- **CLI:** `planalign --help`. Key commands are `health`, `simulate`, `batch`, `validate`, and `validate-change` (the isolated-DB parity gate).

## Architecture

- **Events are immutable.** All changes land in `fct_yearly_events`. Same seed + inputs ⇒ identical output. Python event models (Pydantic v2) are in `planalign_core/events`.
- **Per-year pipeline** (`planalign_orchestrator/pipeline/workflow.py`): INITIALIZATION → FOUNDATION → EVENT_GENERATION (ends by publishing `fct_yearly_events`) → STATE_ACCUMULATION (accumulators → contributions/match → `fct_workforce_snapshot`) → VALIDATION → REPORTING.
- **Layering:** `int_*` models must not read `fct_*`. The two exceptions are `fct_yearly_events` and prior-year state read via `workforce_state_projection`.
- **New event types:** add an `EventGenerator` in `planalign_orchestrator/generators/` and register it with `@EventRegistry.register(...)`. Use `sabbatical.py` as the template.
- **Databases:** one DB per scenario or run. In Python, use `get_database_path()` from `planalign_orchestrator.config`, which honors `DATABASE_PATH`.

## Validate in an isolated database

`dbt/simulation.duckdb` is the shared dev DB. Read it freely, but never validate a behavioral change against it.

```bash
planalign batch --scenarios my_edge_case --clean
# or
DATABASE_PATH=/tmp/run/iso.duckdb planalign simulate 2025-2027 \
  --config /tmp/run/cfg.yaml --database /tmp/run/iso.duckdb
DATABASE_PATH=/tmp/run/iso.duckdb python -m pytest tests/test_x.py -v
```

Cover edge configs, not only the defaults. Run a full multi-year simulation to check cross-year invariants. Only compare event counts between runs that used the same config.

## Standards

- **Python:** full type hints, Pydantic v2 for models and config, cognitive complexity ≤ 15, functions ≤ ~40 lines, ≤ 13 parameters. No bare or swallowed exceptions, no dead or commented-out code, no mutable defaults.
- **dbt SQL:** UPPERCASE keywords, 2-space indent, CTEs, `{{ ref() }}`, no `SELECT *`. Filter heavy models by `{{ var('simulation_year') }}`.
  - Year-partitioned incrementals use `incremental_strategy='replace_simulation_year'`.
  - Never `--full-refresh` an accumulator mid-simulation.
  - Randomness goes through the `PLANALIGN_HASH` macros with `subsystem_seed()`, never DuckDB `HASH()` or `random()`.
  - Use the `assign_age_band` / `assign_tenure_band` macros for bands.
  - Add or adjust `schema.yml` tests with every model change.

## CI

Don't add the `full-ci` label by default. `scripts/ci_policy.py` already runs the invariants and edge-config matrix, and the integration shards run on every push to `main` and nightly. If a PR does need the label, apply it at creation. Labeling later starts a second run, and the cancelled first run's `CI Gate` failure is spurious.

## Gotchas

- **"Conflicting lock is held":** an IDE or DBeaver has the DB open (`planalign health` detects this).
- **sqlparse token limit:** fixed automatically on `import planalign_orchestrator`. Don't hand-patch sqlparse.
- **Frontend:** Tailwind is bundled via `@tailwindcss/vite`. No CDN scripts or external stylesheets in `planalign_studio/index.html`.
- **API security:** the API binds to loopback by default, and `PLANALIGN_API_TOKEN` gates non-local access (see `SECURITY.md`). Don't weaken these defaults.
- **PII:** `data/`, `var/`, and `*.duckdb` are git-ignored census/output artifacts. Never commit them or expose their contents.

## Active Technologies
- Authoritative versions live in `pyproject.toml` and `planalign_studio/package.json`. Per-feature entries below are appended by speckit.

## Recent Changes
