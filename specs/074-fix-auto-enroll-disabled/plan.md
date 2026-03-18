# Implementation Plan: Fix Auto Enrollment Runs Despite Being Disabled

**Branch**: `074-fix-auto-enroll-disabled` | **Date**: 2026-03-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/074-fix-auto-enroll-disabled/spec.md`

## Summary

Auto-enrollment events are generated during simulation even when the feature is explicitly disabled in DC plan configuration. The `auto_enrollment_enabled` dbt variable is correctly exported from Python config but two downstream dbt models (`int_enrollment_events.sql` and `int_proactive_voluntary_enrollment.sql`) do not gate on it. The fix adds the missing checks following the pattern already established in `int_auto_enrollment_window_determination.sql`.

## Technical Context

**Language/Version**: SQL (dbt-core 1.8.8, dbt-duckdb 1.8.1), Python 3.11
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, DuckDB 1.0.0, Pydantic 2.7.4
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: dbt tests, pytest (fast suite)
**Target Platform**: Linux server / work laptop
**Project Type**: CLI + web-service (simulation engine)
**Performance Goals**: N/A (bug fix, no performance changes)
**Constraints**: Single-threaded dbt execution, backward compatibility (default to enabled)
**Scale/Scope**: 2 dbt model modifications, 1-2 new dbt tests, 1-2 Python integration tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No changes to event schema; fix prevents incorrect event generation |
| II. Modular Architecture | PASS | Changes are localized to 2 dbt models; no new modules needed |
| III. Test-First Development | PASS | Plan includes dbt and Python tests for the fix |
| IV. Enterprise Transparency | PASS | Fix ensures config is correctly respected; no audit changes needed |
| V. Type-Safe Configuration | PASS | Uses existing Pydantic-validated config; no new config fields |
| VI. Performance & Scalability | PASS | Adding a boolean check has negligible performance impact |

**Post-Design Re-Check**: All gates still pass. The fix is minimal and follows established patterns.

## Project Structure

### Documentation (this feature)

```text
specs/074-fix-auto-enroll-disabled/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research findings
├── data-model.md        # Data model analysis
├── quickstart.md        # Developer quickstart
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
dbt/
├── models/intermediate/
│   ├── int_enrollment_events.sql                    # FIX: Add auto_enrollment_enabled gate
│   └── int_proactive_voluntary_enrollment.sql       # FIX: Add auto_enrollment_enabled gate
└── tests/
    └── test_auto_enrollment_disabled_no_events.sql  # NEW: dbt test

tests/
└── integration/
    └── test_auto_enrollment_disabled.py             # NEW: Python integration test
```

**Structure Decision**: No new modules or directories needed. Changes are localized to existing dbt models with new test files.

## Complexity Tracking

No violations to justify. The fix is minimal — adding a boolean check to 2 existing SQL models.
