# Implementation Plan: Remove Duplicate/Versioned dbt Models

**Branch**: `081-remove-duplicate-dbt-models` | **Date**: 2026-03-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/081-remove-duplicate-dbt-models/spec.md`

## Summary

Remove 5 unused/superseded dbt model files (`_v2` and `_optimized` variants with zero or debug-only downstream references) and rename 2 active `_v2` models to their canonical names. This is a pure cleanup — no business logic changes. All downstream `ref()` calls in SQL and string references in Python must be updated to match.

## Technical Context

**Language/Version**: SQL (dbt-core 1.8.8), Python 3.11
**Primary Dependencies**: dbt-duckdb 1.8.1, DuckDB 1.0.0
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: `dbt build --threads 1 --fail-fast` (primary), `pytest` (Python changes)
**Target Platform**: Linux (analytics server)
**Project Type**: Data pipeline (dbt project + Python orchestrator)
**Performance Goals**: N/A — no performance-affecting changes
**Constraints**: `dbt build` must pass with zero errors/failures after each phase
**Scale/Scope**: 144 total dbt models; 5 removals, 2 renames, ~20 reference updates

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No event schema changes; `fct_yearly_events` unaffected |
| II. Modular Architecture | PASS | Reduces model count, removes dead code — improves modularity |
| III. Test-First Development | PASS | Verification via `dbt build` after each phase; output comparison for final validation |
| IV. Enterprise Transparency | PASS | No audit trail changes |
| V. Type-Safe Configuration | PASS | `ref()` updates maintain type-safe references |
| VI. Performance & Scalability | PASS | No performance-affecting changes |

**Pre-Phase 0 Gate**: PASSED — all principles satisfied.

## Project Structure

### Documentation (this feature)

```text
specs/081-remove-duplicate-dbt-models/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Reference analysis and rename strategy
├── data-model.md        # Phase 1: Complete reference update matrix
└── quickstart.md        # Phase 1: Implementation quick reference
```

### Source Code (affected files)

```text
dbt/models/
├── intermediate/
│   ├── int_enrollment_events_v2.sql              # DELETE
│   ├── int_enrollment_events_optimized.sql       # DELETE
│   ├── int_deferral_rate_state_accumulator.sql   # DELETE (base, superseded)
│   ├── int_deferral_rate_state_accumulator_v2.sql # RENAME → int_deferral_rate_state_accumulator.sql
│   ├── int_workforce_previous_year.sql           # DELETE (base, superseded)
│   ├── int_workforce_previous_year_v2.sql        # RENAME → int_workforce_previous_year.sql
│   ├── int_deferral_escalation_state_accumulator.sql  # UPDATE ref()
│   ├── int_year_snapshot_preparation.sql              # UPDATE ref()
│   ├── events/
│   │   ├── int_promotion_events_optimized.sql    # DELETE
│   │   └── int_employee_contributions.sql        # UPDATE ref()
│   └── schema.yml                                # UPDATE entries
├── marts/
│   ├── fct_workforce_snapshot.sql                # UPDATE ref()
│   ├── reporting/rpt_deferral_rate_regulatory_audit_summary.sql  # UPDATE ref()
│   └── data_quality/
│       ├── dq_deferral_rate_state_audit_validation_v2.sql  # UPDATE ref()
│       └── dq_deferral_rate_state_audit_validation.sql     # UPDATE ref()
└── analysis/
    ├── debug_enrollment_event_counts.sql         # UPDATE (remove optimized CTE)
    └── debug_participation_pipeline.sql          # UPDATE ref()

planalign_orchestrator/
├── state_accumulator/__init__.py                 # UPDATE string refs
├── model_execution_types.py                      # UPDATE string refs
├── pipeline/
│   ├── workflow.py                               # UPDATE string refs
│   └── event_generation_executor.py              # REMOVE exclusion entry
└── init_database.py                              # UPDATE string refs

planalign_api/
└── services/simulation/db_cleanup.py             # UPDATE string refs
```

**Structure Decision**: No new files or directories. This is a deletion + rename + reference update operation within the existing project structure.

## Complexity Tracking

No constitution violations. This feature is a straightforward cleanup with well-defined, mechanical changes.

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Confirmed: no event schema or audit trail changes |
| II. Modular Architecture | PASS | Net reduction of 5 model files; naming consistency improved |
| III. Test-First Development | PASS | `dbt build` verification after each phase; output checksum comparison |
| IV. Enterprise Transparency | PASS | No changes to logging or audit infrastructure |
| V. Type-Safe Configuration | PASS | All `ref()` and string references updated atomically per phase |
| VI. Performance & Scalability | PASS | No performance-affecting changes |

**Post-Design Gate**: PASSED.
