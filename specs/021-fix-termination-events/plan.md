# Implementation Plan: Fix Termination Event Data Quality

**Branch**: `021-fix-termination-events` | **Date**: 2026-01-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/021-fix-termination-events/spec.md`

## Summary

Fix three data quality bugs in termination event generation and workforce snapshot processing:
1. **Uniform termination dates**: All terminations cluster on a single date (e.g., 2026-09-15) due to hash function not incorporating simulation year
2. **Incorrect new_hire_active status**: Employees without current-year hire events incorrectly classified as new hires
3. **Missing new hire termination data**: New hire terminations show employment_status='active' with null termination_date

Technical approach: Modify the hash-based date assignment formula to include simulation year for distribution, fix the is_new_hire flag propagation in fct_workforce_snapshot, and ensure new hire termination events flow through to the snapshot correctly.

## Technical Context

**Language/Version**: SQL (DuckDB 1.0.0) + dbt-core 1.8.8, Python 3.11 (Polars pipeline parity)
**Primary Dependencies**: dbt-duckdb 1.8.1, Polars 1.0+ (for state pipeline parity)
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: dbt tests (schema + custom data quality), pytest (property-based tests)
**Target Platform**: Linux/macOS workstations, on-premises analytics servers
**Project Type**: dbt transformation project with Python orchestration
**Performance Goals**: No regression from current performance; maintain <2s for single-year simulation events
**Constraints**: Must maintain determinism (identical results with same seed across runs)
**Scale/Scope**: 6,700+ employees, 100-300 terminations per simulation year

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Fix maintains immutable event generation; reproducibility preserved via year-aware hash |
| II. Modular Architecture | PASS | Changes confined to 3 models (int_termination_events, int_new_hire_termination_events, fct_workforce_snapshot) |
| III. Test-First Development | PASS | Will add dbt tests for date distribution and status code validation |
| IV. Enterprise Transparency | PASS | Termination dates will be visible in event_details; status codes auditable |
| V. Type-Safe Configuration | PASS | No configuration changes; SQL uses `{{ ref() }}` patterns |
| VI. Performance & Scalability | PASS | Hash calculation is O(1); no performance regression expected |

**Gate Status**: PASS - Proceed to Phase 0

## Project Structure

### Documentation (this feature)

```text
specs/021-fix-termination-events/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output - root cause analysis
├── data-model.md        # Phase 1 output - entity relationships
├── quickstart.md        # Phase 1 output - implementation guide
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
dbt/
├── models/
│   ├── intermediate/
│   │   └── events/
│   │       ├── int_termination_events.sql      # FIX: Date distribution hash
│   │       └── int_new_hire_termination_events.sql  # FIX: Date distribution hash
│   └── marts/
│       └── fct_workforce_snapshot.sql          # FIX: Status code + termination propagation
├── tests/
│   └── data_quality/
│       ├── test_termination_date_distribution.sql  # NEW: Monthly distribution validation
│       ├── test_new_hire_status_accuracy.sql       # NEW: Status code validation
│       └── test_new_hire_termination_data.sql      # NEW: Data completeness validation
└── macros/
    └── generate_termination_date.sql           # NEW: Reusable date generation macro

planalign_orchestrator/
└── polars_state_pipeline.py                    # UPDATE: Parity with SQL date generation

tests/
└── test_termination_events.py                  # NEW: Property-based distribution tests
```

**Structure Decision**: Changes are localized to existing dbt models and the Polars pipeline. A new macro encapsulates the date generation logic for reuse across experienced and new hire termination models.

## Complexity Tracking

> No violations - implementation uses existing patterns and maintains simplicity.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
