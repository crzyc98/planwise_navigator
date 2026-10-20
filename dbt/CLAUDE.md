# dbt project

The SQL engine for the simulation. The orchestrator runs these models one year at a time. Shared rules live in the root `CLAUDE.md`. This file covers only what's specific to dbt.

## Running dbt

- Run from this directory, always with `--threads 1`. DuckDB already parallelizes inside each query. Multi-threaded dbt was benchmarked and reverted.
- `profiles.yml` reads `DATABASE_PATH` (default `simulation.duckdb`). The orchestrator pins `DBT_PROFILES_DIR` to this directory. Running dbt manually from here does the same.
- **`simulation.duckdb` is the shared dev DB.** Read it freely, but validate changes in an isolated DB (see root `CLAUDE.md`). For production-shaped runs, use `planalign simulate`, not hand-rolled `dbt run` loops.
- Each dbt invocation costs ~4–5s of startup and parse. Batch selections, and don't delete `target/`, because partial parsing depends on it.

```bash
DATABASE_PATH=/tmp/run/iso.duckdb dbt run --select int_baseline_workforce --vars '{simulation_year: 2025}' --threads 1
dbt test --select fct_yearly_events --threads 1
dbt seed --threads 1        # after editing seeds/*.csv
```

## Layout

| Dir | Prefix | Purpose |
|-----|--------|---------|
| `models/staging/` | `stg_*` | Census and config cleanup |
| `models/intermediate/` | `int_*` | Business logic. `events/` holds per-type event models |
| `models/marts/` | `fct_*`, `dim_*` | Published outputs |
| `models/data_quality/`, `monitoring/`, `analysis/` | `dq_*`, `mon_*` | Checks and diagnostics |
| `models/debug/` | `debug_*` | Gated by `enable_debug_models` |
| `macros/` | | `bands/`, `events/`, `utils/`, plan-design (match/core) macros |
| `seeds/` | `config_*` | Hazards, bands, job levels, IRS limits |

Names follow `tier_entity_purpose`. Before trusting an `int_*` model, check that `planalign_orchestrator/pipeline/workflow.py` (or the DAG) actually builds it. Some models are orphaned.

## Data flow per year

1. **Foundation:** `int_baseline_workforce`, `int_employee_compensation_by_year`, `int_effective_parameters`, workforce needs.
2. **Event generation:** the per-type event models (termination, hire, new-hire termination, promotion, merit, eligibility, enrollment, deferral) feed `int_current_year_events`. That is published once as `fct_yearly_events`.
3. **State accumulation:** `int_workforce_state_accumulator`, then enrollment/deferral accumulators, then contributions, core, and match, then `fct_workforce_snapshot`. This runs as one dependency-closed invocation.

**Layering:** `int_*` must not read `fct_*` (that's a circular dependency). There are two sanctioned exceptions:
- `fct_yearly_events`, which state-stage models read after it's published.
- Prior-year workforce state. Read it via `workforce_state_projection`, an orchestrator-built source that holds only years before the current one.

## SQL conventions

- UPPERCASE keywords, 2-space indent, CTEs, `{{ ref() }}`, no `SELECT *`.
- Filter heavy models by `{{ var('simulation_year') }}`. Join on `(scenario_id, plan_design_id, employee_id, simulation_year)` where applicable.
- **Year-partitioned incrementals:** use `incremental_strategy='replace_simulation_year'` (`macros/utils/incremental_year_replace.sql`). It deletes the year (scoped to the scenario) and inserts in one transaction, and it handles empty years correctly. Older models still use `delete+insert`.
- **Accumulators** (`int_*_state_accumulator`) read their own prior year via `{{ this }}`. Never `--full-refresh` them mid-simulation, because that destroys prior-year state.
- **Randomness must be deterministic.** Use the frozen `PLANALIGN_HASH` macros (installed on run start by `macros/utils/stable_hash.sql`), seeded through `{{ subsystem_seed('<name>') }}`. Never use DuckDB's `HASH()` or `random()`: `HASH()` changes between DuckDB versions. Event IDs come from `generate_event_uuid()`.
- **Bands:** use `assign_age_band` / `assign_tenure_band` (seed-driven, `[min, max)` intervals). Don't hand-code CASE ranges.
- Don't use adapter-unsupported configs (`partition_by`, indexes).

## Tests

- Add or adjust `schema.yml` tests with every model change: uniqueness on the event/accumulator grain (`dbt_utils.unique_combination_of_columns`) and not-null on keys.
- Singular tests live in `tests/` (`assert_*.sql`).
- Band seeds have gap and overlap tests. Rerun them after editing `config_age_bands.csv` or `config_tenure_bands.csv`.

## Gotchas

- **Lock errors:** another process (IDE, DBeaver, Studio) holds the DB. Close it.
- **Missing `workforce_state_projection` / `enrollment_decision_projection`:** the orchestrator creates these, so a bare `dbt run` against a fresh DB won't have them. Run through `planalign simulate`, or point at a DB the orchestrator has populated.
- **Memory:** `profiles.yml` caps DuckDB at 4GB. Narrow the selection or raise the cap locally if needed.
- **Stray `.duckdb` files in this directory** are local scratch DBs (git-ignored). They're not fixtures.
