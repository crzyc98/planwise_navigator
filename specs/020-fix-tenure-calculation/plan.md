# Implementation Plan: Fix Current Tenure Calculation

**Branch**: `020-fix-tenure-calculation` | **Date**: 2026-01-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/020-fix-tenure-calculation/spec.md`

## Summary

Fix the `current_tenure` calculation to use day-based arithmetic: `floor((12/31/simulation_year - hire_date) / 365.25)`. Currently, the SQL pipeline uses year-only subtraction which produces incorrect results (e.g., hired 2021-01-01 → 4 years in 2025, not 5). The Polars pipeline already uses the correct formula. This fix aligns both pipelines and ensures accurate tenure for vesting, service-based contributions, and tenure band assignments.

## Technical Context

**Language/Version**: Python 3.11, SQL (DuckDB 1.0.0)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Polars 1.0+
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: pytest (Python), dbt tests (SQL)
**Target Platform**: macOS/Linux workstations, on-premises analytics servers
**Project Type**: Single monorepo with dbt + Python orchestrator
**Performance Goals**: No regression from current performance
**Constraints**: Single-threaded dbt execution for stability on work laptops
**Scale/Scope**: 100K+ employee census datasets

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No changes to event structure; tenure is derived state |
| II. Modular Architecture | PASS | Changes isolated to specific models |
| III. Test-First Development | PASS | Will add property-based tests for tenure calculation |
| IV. Enterprise Transparency | PASS | Calculation formula documented in models |
| V. Type-Safe Configuration | PASS | No config changes needed |
| VI. Performance & Scalability | PASS | Day-based calculation has same O(n) complexity |

**Gate Result**: PASS - No violations

## Project Structure

### Documentation (this feature)

```text
specs/020-fix-tenure-calculation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (files to modify)

```text
dbt/
├── models/
│   └── intermediate/
│       ├── int_baseline_workforce.sql        # FIX: Initial tenure calculation
│       ├── int_employee_compensation_by_year.sql  # VERIFY: Uses correct tenure
│       └── int_active_employees_prev_year_snapshot.sql  # OK: +1 increment correct
├── macros/
│   └── calculate_tenure.sql                  # NEW: Reusable tenure macro

planalign_orchestrator/
└── polars_state_pipeline.py                  # VERIFY: Already correct

tests/
├── test_tenure_calculation.py                # NEW: Property-based tests
└── fixtures/
    └── tenure_test_data.py                   # NEW: Test fixtures
```

**Structure Decision**: Minimal changes to existing models; add reusable macro for consistency.

## Complexity Tracking

> No violations to justify - all changes align with Constitution principles.
