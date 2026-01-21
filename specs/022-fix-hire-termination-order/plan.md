# Implementation Plan: Fix Hire Date Before Termination Date Ordering

**Branch**: `022-fix-hire-termination-order` | **Date**: 2026-01-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/022-fix-hire-termination-order/spec.md`

## Summary

This feature fixes two related bugs in termination event generation:
1. **Bug 1**: Termination dates can occur before employee hire dates (impossible scenario)
2. **Bug 2**: Terminated employees show year-end tenure instead of tenure at termination date

**Root Cause**: The `generate_termination_date` macro uses January 1 as the base date, but employees hired mid-year can get termination dates before their hire date. Additionally, `fct_workforce_snapshot` passes through tenure from base workforce without recalculating for terminated employees.

**Technical Approach**:
1. Modify `generate_termination_date` macro to accept `hire_date_column` parameter and use it as the lower bound
2. Update models using the macro to pass employee hire date
3. Update `fct_workforce_snapshot` to recalculate tenure for terminated employees using termination_date
4. Mirror changes in Polars pipeline for parity
5. Add data quality tests to prevent regressions

## Technical Context

**Language/Version**: SQL (DuckDB 1.0.0), Python 3.11
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Polars 1.0+
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: dbt tests (data quality), pytest (Polars pipeline)
**Target Platform**: Linux server, local development
**Project Type**: Data transformation (dbt) + Python orchestration
**Performance Goals**: Maintain existing performance (<2s for dbt model builds)
**Constraints**: Must maintain deterministic date generation, must work in both SQL and Polars modes
**Scale/Scope**: 100K+ employee records per simulation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Fix maintains immutable event records, adds constraints for data integrity |
| II. Modular Architecture | PASS | Changes are in existing macros/models, no new modules needed |
| III. Test-First Development | PASS | Plan includes dbt data quality tests written before implementation |
| IV. Enterprise Transparency | PASS | Changes improve data accuracy for audit purposes |
| V. Type-Safe Configuration | PASS | No configuration changes needed, macro signature extended |
| VI. Performance & Scalability | PASS | No performance impact expected, same hash-based computation |

**All gates passed** - no violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/022-fix-hire-termination-order/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (affected files)

```text
dbt/
├── macros/
│   └── generate_termination_date.sql  # MODIFY: Add hire_date_column parameter
├── models/
│   ├── intermediate/events/
│   │   ├── int_termination_events.sql        # MODIFY: Pass hire_date to macro
│   │   └── int_new_hire_termination_events.sql  # VERIFY: Already constrains dates
│   └── marts/
│       └── fct_workforce_snapshot.sql         # MODIFY: Recalculate tenure for terminated
├── tests/data_quality/
│   ├── test_termination_after_hire.sql       # CREATE: FR-005
│   └── test_tenure_at_termination.sql        # CREATE: FR-008

planalign_orchestrator/
└── polars_event_factory.py  # MODIFY: Add hire_date constraint to date generation

tests/
└── test_termination_events.py  # MODIFY: Add regression test for tenure calculation
```

**Structure Decision**: No structural changes - modifications to existing files only.

## Complexity Tracking

> No violations - complexity tracking not required.
