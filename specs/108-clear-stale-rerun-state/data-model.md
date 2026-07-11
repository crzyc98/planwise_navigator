# Data Model: Clear Stale Prior-Run State on Scenario Re-Run

**Feature**: 108-clear-stale-rerun-state | **Date**: 2026-07-10

No new tables, columns, or schema migrations. The feature changes *lifecycle rules* for existing yearly state and one derived label. Entities below map the spec's key entities onto concrete stores.

## Entities

### Scenario Run (behavioral entity — not persisted as a table)

One execution of `PipelineOrchestrator.execute_multi_year_simulation(start_year, end_year)` into the scenario's database.

| Attribute | Source | Notes |
|---|---|---|
| scenario_id / plan_design_id | `SimulationConfig.scenario_id` / `.plan_design_id`, defaulting to `'default'` | Must match dbt's `var('scenario_id', 'default')` fallback (existing `_year_scope` behavior) |
| year range | `simulation.start_year` .. `end_year` | Purge applies only to years within this range |
| state-clearing directive | `config.setup` dict: `clear_tables`, `clear_mode`, `clear_table_patterns` | **New semantics**: absent ⇒ year-scoped purge (see state transitions) |

### Yearly Simulation State (existing tables)

All `main`-schema tables matching patterns `['int_', 'fct_']` that have a `simulation_year` column. Scoping columns `scenario_id`/`plan_design_id` are used when present (warning logged for critical tables lacking them — existing behavior).

**Lifecycle rule (new default)**: before year N of a run builds, every row with `simulation_year = N` (scenario/plan-scoped) is deleted from every matching table — regardless of whether the run will regenerate the same keys.

**Invariant (FR-004)**: after a completed run, every row in yearly simulation state for the simulated years is attributable to that run (operationally: no `created_at` earlier than the run start, for tables that carry one).

### Deferral-Rate State — `int_deferral_rate_state_accumulator` (existing)

The store where contamination was observed. Relevant columns: `employee_id`, `simulation_year`, `current_deferral_rate`, `rate_source`, `is_enrolled_flag`, `created_at`, scenario keys. Sparse in year 2+ (rows only for enrolled employees) — precisely why `delete+insert` cannot self-clean and the orchestrator purge is required. No model change in this feature.

### Enrollment State History — `int_enrollment_state_accumulator` (existing)

Authoritative per-year enrollment record. Relevant columns for this feature:

| Column | Values | Role |
|---|---|---|
| `enrollment_source` | `'baseline'`, `'event_<year>'`, `'none'`, carried-forward prior value | `'baseline'` is the only value that may justify a census-enrollment label |
| `enrollment_method` | `'auto'`, `'voluntary'`, NULL | NULL for census enrollments by design — no longer sufficient to claim census lineage |

No model change; the snapshot starts *reading* `enrollment_source` at the label site.

### Participation Detail Label — `fct_workforce_snapshot.participation_status_detail` (existing column, revised derivation)

| Condition (participating: `current_deferral_rate > 0`) | Label |
|---|---|
| `esa.enrollment_method = 'auto'` | `participating - auto enrollment` (unchanged) |
| `esa.enrollment_method = 'voluntary'` | `participating - voluntary enrollment` (unchanged) |
| `esa.enrollment_method IS NULL AND esa.enrollment_source = 'baseline'` | `participating - census enrollment` (**tightened**) |
| `esa.enrollment_method IS NULL AND esa.enrollment_source LIKE 'event_%'` | `participating - voluntary enrollment` (event enrollment, method unrecorded — previously mislabeled census) |
| `esa.enrollment_method IS NULL` otherwise (no esa row, `'none'`, or NULL source) | `participating - unknown source` (**new**, no enrollment lineage at all) |
| other method values | `participating - voluntary enrollment` (unchanged fallback) |

Not-participating branch unchanged.

## State Transitions: state-clearing directive resolution

```
config.setup
├─ absent / not a dict ──────────────────────────► YEAR PURGE (new default)
├─ clear_tables key absent ──────────────────────► YEAR PURGE (new default)
├─ clear_tables: false (explicit) ───────────────► no purge (opt-out)
└─ clear_tables: true
   ├─ clear_mode: 'year' (or unset) ─────────────► YEAR PURGE (unchanged)
   └─ clear_mode: 'all' ─────────────────────────► one-time FULL RESET before year loop
                                                    (maybe_full_reset — unchanged, never default)
```

Additional run-start check (new): if rows exist for this scenario with `simulation_year > end_year` in critical fact tables → log warning (no deletion). Years `< start_year` are never inspected or deleted (legitimate prior-year state).

## Validation Rules

1. Year purge is scoped to `(simulation_year, scenario_id, plan_design_id)` where columns exist (FR-010); tables without `simulation_year` are never touched.
2. Purge tolerates missing tables and empty databases without error (FR-006).
3. Census label requires baseline enrollment source (FR-007); unexplained participation must surface as `unknown source` (FR-008) — enforced by dbt data test `test_participation_label_lineage.sql`.
4. Regression: after AE-on → AE-off re-run of the same DB, no deferral-state rows predate the second run and never-enrolled employees are `not_participating` in every year (FR-009 / SC-001 / SC-002).
