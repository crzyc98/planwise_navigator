# Contract: Default Year-Scoped State Purge

**Component**: `planalign_orchestrator.pipeline.state_manager.StateManager.maybe_clear_year_data(year)`
**Called from**: `PipelineOrchestrator._execute_year_workflow` (once per simulated year, before any stage builds)

## Behavior

Given the run's `SimulationConfig`:

| # | Precondition | Guaranteed behavior |
|---|---|---|
| 1 | `config.setup` absent, `None`, or not a dict | Delete all rows with `simulation_year = year` from every `main`-schema table whose name starts with `int_` or `fct_` and that has a `simulation_year` column, scoped to `scenario_id`/`plan_design_id` where those columns exist |
| 2 | `setup` dict present, `clear_tables` key absent | Same as #1 (unset ≠ false) |
| 3 | `setup.clear_tables` is explicitly falsy (`False`, `0`, `''`) | No rows deleted (documented opt-out) |
| 4 | `setup.clear_tables: true`, `clear_mode` in (`'year'`, unset) | Same purge, honoring `setup.clear_table_patterns` when provided (unchanged) |
| 5 | `setup.clear_tables: true`, `clear_mode: 'all'` | No year-level deletion (one-time full reset handled by `maybe_full_reset` before the year loop — unchanged) |
| 6 | Target table does not exist / database is fresh | No error; table skipped |
| 7 | Table lacks `scenario_id`/`plan_design_id` columns | Year-only delete; warning logged for critical fact tables (existing `_year_scope` behavior) |
| 8 | Rows exist for other scenarios/plans or other years | Never deleted (FR-010) |

Scenario identifiers fall back to `'default'` when unset, matching dbt's `var('scenario_id', 'default')`.

## Run-start stale-range warning

**Component**: `PipelineOrchestrator.execute_multi_year_simulation` (run start, after optional full reset)

| Precondition | Behavior |
|---|---|
| Rows exist in critical fact tables for this scenario with `simulation_year > end_year` | Log WARNING naming the years found and recommending `setup.clear_tables: true, clear_mode: 'all'`; do not delete |
| Rows exist with `simulation_year < start_year` | No action (legitimate prior-year state for mid-range runs) |

## Non-goals

- No change to `maybe_full_reset` gating (explicit opt-in only).
- No change to `clear_year_fact_rows` (remains the unconditional critical-table guard).
- No dbt model or schema changes for the purge itself.

## Observability

- INFO log per year: number of tables cleared (existing message retained).
- The opt-out path (#3) logs at DEBUG that clearing was explicitly disabled.
