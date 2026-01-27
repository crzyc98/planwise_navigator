# Implementation Plan: Fix 401(a)(17) Compensation Limit for Employer Contributions

**Branch**: `026-fix-401a17-comp-limit` | **Date**: 2026-01-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/026-fix-401a17-comp-limit/spec.md`

## Summary

Fix IRS Section 401(a)(17) compliance by capping the compensation used for employer contribution calculations (match and core) at the annual compensation limit. Currently, high earners have contributions calculated on full compensation, resulting in overstated employer costs. The fix adds a `compensation_limit` column to `config_irs_limits.csv` and applies `LEAST(compensation, irs_401a17_limit)` in both `int_employee_match_calculations.sql` and `int_employer_core_contributions.sql`.

## Technical Context

**Language/Version**: SQL (DuckDB 1.0.0), Jinja2 (dbt macros)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: dbt tests (schema tests + custom data quality tests)
**Target Platform**: Linux server, work laptops (on-premises deployment)
**Project Type**: dbt transformation project (SQL models + seeds)
**Performance Goals**: 100K+ employees without memory errors, <2s dashboard queries (p95)
**Constraints**: Single-threaded execution default, `--threads 1` for stability
**Scale/Scope**: 3 files modified, 1 new test, 1 seed extended

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Event Sourcing & Immutability** | PASS | No event schema changes; contribution calculations are derived state |
| **II. Modular Architecture** | PASS | Changes isolated to 2 existing models + 1 seed; no new modules |
| **III. Test-First Development** | PASS | New dbt test `test_401a17_compliance.sql` validates the fix |
| **IV. Enterprise Transparency** | PASS | Adds `irs_401a17_limit_applied` audit field to track capping |
| **V. Type-Safe Configuration** | PASS | Uses existing CSV seed pattern; no raw SQL concatenation |
| **VI. Performance & Scalability** | PASS | Uses efficient `LEAST()` function; no additional JOINs |

**Gate Result**: PASS - All principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/026-fix-401a17-comp-limit/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (N/A - no API changes)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
dbt/
├── seeds/
│   └── config_irs_limits.csv          # MODIFY: Add compensation_limit column
├── models/
│   └── intermediate/
│       ├── events/
│       │   └── int_employee_match_calculations.sql  # MODIFY: Apply 401(a)(17) cap
│       └── int_employer_core_contributions.sql      # MODIFY: Apply 401(a)(17) cap
└── tests/
    └── data_quality/
        └── test_401a17_compliance.sql  # NEW: Validation test
```

**Structure Decision**: Uses existing dbt project structure. No new directories or modules required.

## Complexity Tracking

> No constitution violations to justify - all gates pass.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
