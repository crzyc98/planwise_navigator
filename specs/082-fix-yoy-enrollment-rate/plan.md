# Implementation Plan: Fix Year-over-Year Voluntary Enrollment Rate Override

**Branch**: `082-fix-yoy-enrollment-rate` | **Date**: 2026-03-20 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/082-fix-yoy-enrollment-rate/spec.md`

## Summary

The `voluntary_enrollment_rate` config (0.0–1.0 multiplier) is applied in two of three voluntary enrollment pathways but **not** in the year-over-year conversion CTE in `int_enrollment_events.sql`. The fix applies the same `voluntary_enrollment_rate` multiplier to the year-over-year conversion probability calculation, making it consistent with the other two pathways. This is a single-line SQL change with a corresponding dbt test.

## Technical Context

**Language/Version**: SQL (dbt-core 1.8.8, dbt-duckdb 1.8.1), Python 3.11
**Primary Dependencies**: dbt-core 1.8.8, DuckDB 1.0.0
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: dbt tests (SQL), pytest (Python)
**Target Platform**: Linux/macOS (on-premises analytics server)
**Project Type**: Data pipeline / workforce simulation
**Performance Goals**: No performance impact — adds one multiplication per row in a CTE
**Constraints**: Single-threaded dbt execution (`--threads 1`)
**Scale/Scope**: Single SQL model change + 1 dbt test

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No changes to event schema; enrollment events continue to be immutable records |
| II. Modular Architecture | PASS | Change is scoped to one CTE in one model; no new modules or circular dependencies |
| III. Test-First Development | PASS | Adding a dbt test to validate the fix before/alongside implementation |
| IV. Enterprise Transparency | PASS | Existing audit trail unchanged; the multiplier is already a logged dbt variable |
| V. Type-Safe Configuration | PASS | Uses existing `voluntary_enrollment_rate` dbt variable with COALESCE default |
| VI. Performance & Scalability | PASS | One additional multiplication per row; negligible impact |

**Gate Result**: ALL PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/082-fix-yoy-enrollment-rate/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (files to modify)

```text
dbt/
├── models/intermediate/
│   └── int_enrollment_events.sql          # BUG FIX: Add voluntary_enrollment_rate multiplier to year-over-year CTE
└── tests/
    └── test_yoy_respects_voluntary_rate.sql  # NEW: Validate year-over-year respects voluntary_enrollment_rate
```

**Structure Decision**: This is a targeted bug fix in the existing dbt model layer. No new modules, no config changes, no UI changes. The `voluntary_enrollment_rate` variable already flows through the config export pipeline to dbt; it just needs to be referenced in the year-over-year CTE.

## Complexity Tracking

> No constitution violations — this section is intentionally empty.
