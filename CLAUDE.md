# Fidelity PlanAlign Engine

Event-sourced workforce and DC-plan simulation: DuckDB + dbt, driven by a Python orchestrator, with PlanAlign Studio (FastAPI + React/Vite + Tailwind v4) as the product UI. The team uses Studio, not the CLI; the CLI is the execution engine and dev tool. dbt-specific guidance lives in `dbt/CLAUDE.md`.

Versions are pinned in `pyproject.toml` (Python 3.12, DuckDB, dbt-core/dbt-duckdb) and `planalign_studio/package.json`. Current release: `_version.py`.

## Commands

Each tool shell is independent, so activating the venv in one call doesn't carry over. Run project commands through the runner:

```bash
python3 scripts/dev.py --check                          # Preflight: checkout + venv
python3 scripts/dev.py -- python -m pytest -m fast      # Fast suite (TDD loop)
python3 scripts/dev.py -- ruff check .
python3 scripts/dev.py -- planalign health              # Also detects DB locks
```

Fresh environment: `uv venv .venv --python python3.12 && uv pip install -e ".[dev]"`.

Main CLI commands (`planalign --help` for the full list): `simulate`, `batch`, `studio`, `validate`, `validate-change` (isolated-DB parity gate), `calibrate`, `fit`, `backtest`, `optimize`, `evidence-pack`, `provenance`, `report`, `gc`.

Run dbt only from `dbt/`, always with `--threads 1`.

## Architecture

- **Events are immutable.** Every workforce/plan change is a row in `fct_yearly_events`. Same seed + inputs ⇒ identical output. Python event models (Pydantic v2) live in `planalign_core/events`.
- **Per-year pipeline** (`planalign_orchestrator/pipeline/workflow.py` is authoritative): INITIALIZATION → FOUNDATION → EVENT_GENERATION (ends by publishing `fct_yearly_events`) → STATE_ACCUMULATION (accumulators → contributions/match → `fct_workforce_snapshot`) → VALIDATION → REPORTING.
- **Construction:** `build_orchestrator(ConstructionSpec(...))` from `planalign_orchestrator`; then `orchestrator.execute_multi_year_simulation(start_year, end_year)`.
- **New event types:** subclass `EventGenerator` in `planalign_orchestrator/generators/` and register with `@EventRegistry.register(...)`. `generators/sabbatical.py` is the template.
- **One DB per scenario.** Studio gives every run its own `runs/<run_id>/` database; batch writes one `.duckdb` per scenario. Prefer warnings over schema migrations for cross-scenario concerns.
- **DB paths:** in Python always use `get_database_path()` (`planalign_orchestrator.config`), which honors `DATABASE_PATH`. The orchestrator pins dbt to `dbt/profiles.yml`, which reads the same variable.

## Hard rules

**Validate behavioral changes in an isolated database, never the shared `dbt/simulation.duckdb`.** Reading it is fine. Running dbt into it overwrites shared state, and its contents aren't ground truth.

```bash
planalign batch --scenarios my_edge_case --clean
# or
DATABASE_PATH=/tmp/run/iso.duckdb planalign simulate 2025-2027 \
  --config /tmp/run/cfg.yaml --database /tmp/run/iso.duckdb
DATABASE_PATH=/tmp/run/iso.duckdb python -m pytest tests/test_x.py -v
```

Cover edge configs, not just defaults (e.g. `auto_enrollment_scope: all_eligible_employees`). Use a full multi-year `simulate` for cross-year invariants. A single-year dbt run can hide them.

**Event counts are config-dominated.** The same code and census can differ by 100k+ events under different configs, so only compare runs that share a config. `run_metadata` stamps each run's config fingerprint and seed. A drift warning means the DB was written under a different config.

**Code quality** (enforced in review):
- Cognitive complexity ≤ 15, nesting ≤ 3, functions ≤ ~40 lines, ≤ 13 parameters (group them into dataclasses or config objects).
- Full type hints; return types cover every path. Pydantic v2 for data/config models.
- No bare `except:`, no swallowed exceptions, no commented-out code, no unused imports.

## Testing & CI

- Markers: `fast`, `integration`, `multi_year_invariants`, `edge_config_matrix`, plus area markers (`orchestrator`, `events`, `config`, `dbt`, ...). They're registered in `pyproject.toml` with `--strict-markers`.
- Integration tests run against an isolated `DATABASE_PATH`.
- The fast suite has a CI time budget (`scripts/check_fast_suite_runtime.py`). Coverage is a 75% gate that only ratchets up. Local Mac timings are unreliable, so measure timing on CI.
- **Don't add the `full-ci` label by default.** `scripts/ci_policy.py` already runs the invariants and edge-config matrix for non-frontend, non-docs changes. `full-ci` only adds the integration shards and coverage, which run on every push to `main` and nightly anyway. If a PR does need it, apply the label at creation. Adding it later starts a second run, and the cancelled first run's `CI Gate` failure is spurious.

## Gotchas

- **"Conflicting lock is held":** an IDE or DBeaver has the DuckDB open. Close it (`planalign health` detects this).
- **sqlparse token limit:** fixed automatically by a `.pth` installed on first `import planalign_orchestrator`. Don't hand-patch sqlparse.
- **Disk filling up (`var/`, `workspaces/`):** `planalign gc` (dry run), then `planalign gc --yes`.
- **Frontend:** Tailwind is bundled via `@tailwindcss/vite`. Never add CDN scripts or external stylesheets to `planalign_studio/index.html`.
- **Security:** the API binds to loopback by default, and `PLANALIGN_API_TOKEN` gates non-local deployments (see `SECURITY.md`). Don't weaken these defaults. Report vulnerabilities privately, never in public issues.
- **PII:** `data/`, `var/`, and `*.duckdb` are git-ignored census/output artifacts. Never commit them or quote their contents unnecessarily.
- **Worktrees:** keep nested checkouts under `.worktrees/` (see `scripts/README.md`).

## References

- `docs/architecture.md`, `docs/data-model.md`, `docs/development.md`
- `docs/guides/`: fitting, backtesting, ensembles, optimizer, fan-out, net employer cost, and more
- `docs/perf/`: run-cost profiles, state-pipeline redesign
- `docs/VERSIONING_GUIDE.md`, `CHANGELOG.md`

## Active Technologies
- Authoritative versions live in `pyproject.toml` and `planalign_studio/package.json`. Per-feature entries below are appended by speckit.

## Recent Changes
