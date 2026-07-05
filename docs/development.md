# Development Guide

## Setup

```bash
uv venv .venv --python python3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

planalign health          # verify system readiness
```

Python 3.11 is required. After recreating the venv, import the package once
(`planalign health` suffices) to auto-install the sqlparse token-limit fix.

## Everyday commands

```bash
planalign simulate 2025-2027                 # multi-year simulation
planalign simulate 2025 --dry-run            # preview execution plan
planalign batch --scenarios baseline high_growth --clean
planalign calibrate 2025-2029 --database iso.duckdb   # fast comp calibration
planalign studio                             # web UI (API :8000, frontend :5173)
planalign status --detailed
```

## Testing

```bash
pytest -m fast                       # ~1,500 unit tests, ~2 min
pytest -m "fast and orchestrator"    # component subsets: orchestrator/events/config
pytest -m integration                # integration suite
pytest --cov=planalign_orchestrator --cov=planalign_cli --cov-report=html
```

Fixtures live in `tests/fixtures/` (in-memory/populated/isolated databases, mock dbt
runners, sample workforce data). Pre-commit runs black + ruff; CI additionally runs
mypy. Run `./scripts/run_ci_tests.sh` before pushing.

## Validating behavioral changes — the isolated-DB rule

`dbt/simulation.duckdb` is the **shared dev database**: fine for quick reads, never
for validating a change. Running `dbt run`/`build` into it leaves half-built state
for the next person, and whatever config happens to be materialized there proves
nothing about edge configs.

Validate in an isolated, explicitly-configured database instead:

```bash
# Preferred: batch scenarios (one .duckdb per scenario)
planalign batch --scenarios my_edge_case --clean

# Or a one-off isolated run
DATABASE_PATH=/tmp/run/iso.duckdb \
  planalign simulate 2025-2027 --config /tmp/run/cfg.yaml --database /tmp/run/iso.duckdb

# Point tests at the isolated DB
DATABASE_PATH=/tmp/run/iso.duckdb pytest tests/test_my_feature.py -v
```

Cover the **edge configs** (e.g. `auto_enrollment_scope: all_eligible_employees`),
not just defaults, and run full multi-year simulations for cross-year invariants.
Before trusting a "fixed" `int_*` model, confirm it actually feeds
`fct_yearly_events`/`fct_workforce_snapshot` — some intermediate models are orphaned.

## dbt workflow

Always from the `dbt/` directory, always `--threads 1`:

```bash
cd dbt
dbt build --threads 1 --fail-fast
dbt run --select int_baseline_workforce+ --threads 1
dbt run --select tag:EVENT_GENERATION --vars "simulation_year: 2025" --threads 1
dbt test --select tag:data_quality
```

Incremental models use `incremental_strategy='delete+insert'` with a
`unique_key` of `['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year']`
and a pre-hook deleting the current `simulation_year`.

## Runtime outputs

Everything the app writes lands under `var/` (git-ignored):

| Path | Contents |
|------|----------|
| `var/artifacts/runs/` | Per-run JSON summaries — newest 50 retained automatically |
| `var/reports/` | Multi-year summary CSVs, memory/performance reports |
| `var/logs/` | `navigator.log` and rotated logs |
| `var/outputs/` | Batch scenario outputs and Excel exports |
| `var/backups/` | Database backups (safety config) |

Studio workspaces live in `workspaces/` (configurable via `planalign_api` settings).

## Common issues

- **`ModuleNotFoundError`** — activate the venv; after changing `pyproject.toml`
  packaging, re-run `uv pip install -e .`.
- **`Conflicting lock is held`** — close IDE/DBeaver connections to the DuckDB file;
  `planalign health` detects locks.
- **Multi-year run fails on Year 2+ with sqlparse token error** — the fix
  auto-installs on first import of `planalign_orchestrator`; just re-run.

## Code standards (enforced by SonarQube / CI)

- Cognitive complexity ≤ 15: guard clauses, extracted helpers, dictionary dispatch.
- ≤ 13 function parameters — group with dataclasses/config objects.
- No bare `except:`; catch specific exceptions and log or re-raise.
- No commented-out code, TODO comments, or empty blocks.
- Full type hints (Pydantic v2 for data models); SQL uses 2-space indent, uppercase
  keywords, `{{ ref() }}`, no `SELECT *`.
