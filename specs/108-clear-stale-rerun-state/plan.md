# Implementation Plan: Clear Stale Prior-Run State on Scenario Re-Run

**Branch**: `108-clear-stale-rerun-state` | **Date**: 2026-07-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/108-clear-stale-rerun-state/spec.md`

## Summary

Issue #419: re-running a Studio scenario into its existing `simulation.duckdb` leaves stale prior-run rows in `int_deferral_rate_state_accumulator` (and any other yearly state store whose incremental rebuild does not regenerate every key), producing phantom "participating - census enrollment" employees at a 3% deferral from year 2 onward. Two code-level gaps remain after feature 107:

1. `StateManager.maybe_clear_year_data()` still no-ops unless `setup.clear_tables` is explicitly truthy (`state_manager.py:150`), and Studio configs carry no `setup` block — so only `clear_year_fact_rows()` runs, covering just 3 `fct_*` tables. The deferral accumulator's year-2+ `delete+insert` never emits rows for never-enrolled employees, so prior-run rows for those keys survive and propagate forward.
2. `fct_workforce_snapshot.sql:713` labels any participating employee with `esa.enrollment_method IS NULL` as `'participating - census enrollment'`, disguising unexplained participation as legitimate.

**Approach**: (a) Make year-scoped cleanup the *default* in `StateManager.maybe_clear_year_data` — purge all `int_*`/`fct_*` rows for the simulated year (scenario/plan-scoped) even when `setup`/`clear_tables` is omitted, with explicit `clear_tables: false` as the only opt-out and explicit `clear_mode: 'all'` full reset unchanged; (b) tighten the snapshot's participation-detail fallback to assert census enrollment only when `esa.enrollment_source = 'baseline'`, with a distinct "undetermined" label otherwise; (c) warn (not delete) when rows exist for the scenario beyond the run's end year; (d) regression coverage for the AE-on → AE-off re-run contamination scenario.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator), SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated `.sql`)
**Primary Dependencies**: `planalign_orchestrator` (StateManager, PipelineOrchestrator), DuckDB 1.0.0, dbt incremental models (`delete+insert`)
**Storage**: DuckDB — one `.duckdb` per scenario (Studio/batch); shared `dbt/simulation.duckdb` for dev only. Mutated stores: `int_deferral_rate_state_accumulator`, `int_enrollment_state_accumulator`, and all `int_*`/`fct_*` tables with a `simulation_year` column; `fct_workforce_snapshot` label logic
**Testing**: pytest (`-m fast` unit; integration against seeded in-memory/isolated DuckDB), dbt data tests in `dbt/tests/`
**Target Platform**: macOS/Linux analytics workstations (work-laptop constraints; single-threaded dbt)
**Project Type**: Simulation pipeline (Python orchestrator + dbt/SQL models)
**Performance Goals**: Per-year purge adds only information_schema scans + year-scoped DELETEs (~100 tables); negligible vs. per-year dbt build time. No new models
**Constraints**: Purge must be scoped to `(simulation_year, scenario_id, plan_design_id)` where columns exist (reuses `_year_scope`); must tolerate missing tables/fresh DBs; must never delete years *before* `start_year` (later runs legitimately read prior-year state); validation only in isolated DBs, never the shared dev DB
**Scale/Scope**: 100K+ employee rows per year per table; observed contamination: 1,582/776/786/862 stale rows across 2027–2030

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Event Sourcing & Immutability | ✅ Purge deletes rows only for years the current run is about to rebuild — the existing idempotent-re-run guard (`clear_year_fact_rows`) already does this for fact tables; this extends the same semantics. Reproducibility improves (SC-004): results no longer depend on what a prior run left behind. |
| II. Modular Architecture | ✅ Changes confined to `StateManager` (existing module, stays well under limits), one CASE expression in `fct_workforce_snapshot.sql`, and tests. No new modules or layers; no circular deps. |
| III. Test-First Development | ✅ Plan sequences failing unit tests (cleanup default-on semantics), integration test (stale-row purge), and a dbt data test (label lineage) before implementation. |
| IV. Enterprise Transparency | ✅ Purge logs table counts per year; new warning when out-of-range stale years are detected; "undetermined" label surfaces anomalies instead of masking them. |
| V. Type-Safe Configuration | ✅ No new config surface; existing `setup` dict semantics documented and tightened (unset ≠ false). dbt changes use `{{ ref() }}` only. |
| VI. Performance & Scalability | ✅ Year-scoped DELETEs on indexed-free DuckDB column-store are cheap; purge already ran for `clear_tables: true` users with no issue. Single-threaded default unchanged. |

**Gate result**: PASS (no violations; Complexity Tracking not needed).

**Post-design re-check (Phase 1)**: PASS — design adds no new modules, no schema migrations, no new config keys; the only behavior change is the default value of an existing switch plus one label fix.

## Project Structure

### Documentation (this feature)

```text
specs/108-clear-stale-rerun-state/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── default-year-purge.md
│   └── participation-label-lineage.md
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── pipeline/
│   └── state_manager.py            # MODIFY: maybe_clear_year_data default-on; docstrings
└── pipeline_orchestrator.py        # MODIFY: out-of-range stale-year warning at run start

dbt/
├── models/marts/
│   └── fct_workforce_snapshot.sql  # MODIFY: participation_status_detail lineage (esa.enrollment_source)
└── tests/
    └── test_participation_label_lineage.sql   # NEW: dbt invariant — census label ⇒ baseline source

tests/
├── unit/orchestrator/
│   └── test_cleanup_scoping.py     # MODIFY/EXTEND: default-on purge, explicit false opt-out,
│                                   #   accumulator stale-key purge, fresh-DB no-op
└── integration/
    └── test_stale_rerun_purge.py   # NEW: AE-on→AE-off contamination regression (seeded DuckDB)
```

**Structure Decision**: Single-project simulation pipeline. All Python changes live in the existing `planalign_orchestrator.pipeline.state_manager` module (plus a warning hook in `pipeline_orchestrator.py`); the reporting fix is one CASE expression in the existing snapshot mart. No new packages, models, or config schema.

## Design Decisions (summary — details in research.md)

1. **Default-on year purge** (FR-001/FR-002): In `maybe_clear_year_data`, treat *absent* `setup` or *unset* `clear_tables` as "purge this year" (default patterns `['int_', 'fct_']`, scenario/plan-scoped via existing `_year_scope`). Explicit `clear_tables: false` opts out; explicit `clear_mode: 'all'` continues to defer to the one-time `maybe_full_reset` (FR-003). Studio and CLI paths are covered with zero API/config changes.
2. **Keep `clear_year_fact_rows` as-is**: it remains the unconditional safety net for the three critical fact tables; the default-on purge supersets it but the redundancy is harmless and preserves behavior if a user opts out.
3. **Label lineage** (FR-007/FR-008): `'participating - census enrollment'` requires `esa.enrollment_source = 'baseline'` (the accumulator already records this; census enrollments deliberately have `enrollment_method IS NULL`). Unexplained participation (no `esa` row, or non-baseline source with NULL method) gets `'participating - unknown source'`.
4. **Out-of-range years: warn, don't delete** (edge case): at run start, if rows exist for this scenario with `simulation_year > end_year`, log a warning recommending an explicit full reset. Deleting years `< start_year` is forbidden (mid-range runs legitimately consume prior-year state); deleting years `> end_year` is destructive enough to require explicit opt-in via `clear_mode: 'all'`.
5. **Regression coverage** (FR-009): seeded-DuckDB integration test reproducing the contamination shape (stale accumulator rows with old `created_at`, keys not regenerated) + dbt data test for label lineage + quickstart manual validation for the full AE-on → AE-off isolated-DB run.

## Complexity Tracking

*No constitution violations — table not required.*
