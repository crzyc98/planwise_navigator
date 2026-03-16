# Implementation Plan: Fix Hardcoded Age/Tenure Band Label Mismatches

**Branch**: `073-fix-band-label-mismatch` | **Date**: 2026-03-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/073-fix-band-label-mismatch/spec.md`

## Summary

Replace hardcoded age/tenure band CASE statements across 19 dbt models with centralized `assign_age_band()` / `assign_tenure_band()` macro calls. Five models produce actively wrong labels causing zero-match JOINs with hazard rate tables (silently breaking salary growth and enrollment). Fourteen additional models hardcode correct-but-fragile labels that will break on band customization. Also fix `schema.yml` accepted_values tests and add a cross-model band consistency test.

## Technical Context

**Language/Version**: SQL (dbt-core 1.8.8, dbt-duckdb 1.8.1)
**Primary Dependencies**: dbt macros (`assign_age_band`, `assign_tenure_band`), seed CSVs
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`)
**Testing**: `dbt test` (schema tests, custom data quality tests)
**Target Platform**: Linux/macOS analytics workstation
**Project Type**: Data transformation pipeline (dbt)
**Performance Goals**: No regression; `dbt build --threads 1` completes successfully
**Constraints**: All changes are SQL-only within dbt layer; no Python changes
**Scale/Scope**: 19 model files + 1 schema file + 1 new test file

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No event schema changes; fixing label consistency only |
| II. Modular Architecture | PASS | Replacing hardcoded logic with centralized macros improves modularity |
| III. Test-First Development | PASS | Adding cross-model consistency test; fixing schema tests |
| IV. Enterprise Transparency | PASS | Correcting labels restores audit trail accuracy |
| V. Type-Safe Configuration | PASS | Moving from hardcoded strings to seed-driven macros improves type safety |
| VI. Performance & Scalability | PASS | Macro calls compile to equivalent CASE expressions; no performance impact |

**Post-Phase 1 Re-check**: All gates still pass. No new abstractions or dependencies introduced.

## Project Structure

### Documentation (this feature)

```text
specs/073-fix-band-label-mismatch/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research findings
├── data-model.md        # Band label contract
├── quickstart.md        # Verification guide
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (affected files)

```text
dbt/
├── macros/
│   ├── bands/
│   │   ├── assign_age_band.sql          # Existing macro (no changes)
│   │   └── assign_tenure_band.sql       # Existing macro (no changes)
│   └── events/
│       └── events_enrollment_sql.sql    # FIX: tenure band split (10-14/15-19 → 10-19)
├── models/
│   ├── intermediate/
│   │   ├── int_active_employees_by_year.sql        # FIX: critical mismatch
│   │   ├── int_active_employees_prev_year_snapshot.sql  # FIX: critical mismatch
│   │   ├── int_employee_compensation_by_year.sql   # FIX: fragile hardcoded
│   │   ├── int_workforce_previous_year.sql         # FIX: fragile hardcoded
│   │   ├── int_workforce_previous_year_v2.sql      # FIX: fragile hardcoded
│   │   ├── int_workforce_snapshot_optimized.sql     # FIX: fragile hardcoded
│   │   ├── int_new_hire_compensation_staging.sql    # FIX: fragile hardcoded
│   │   ├── events/
│   │   │   ├── int_enrollment_events.sql           # FIX: fragile hardcoded
│   │   │   ├── int_enrollment_events_v2.sql        # FIX: critical mismatch + fragile
│   │   │   ├── int_hiring_events.sql               # FIX: fragile hardcoded
│   │   │   ├── int_new_hire_termination_events.sql  # FIX: fragile hardcoded
│   │   │   ├── int_promotion_events_optimized.sql   # FIX: fragile hardcoded
│   │   │   ├── int_proactive_voluntary_enrollment.sql # FIX: fragile hardcoded
│   │   │   ├── int_deferral_rate_escalation_events.sql # FIX: fragile hardcoded
│   │   │   └── int_deferral_match_response_events.sql  # FIX: fragile hardcoded
│   │   └── schema.yml                              # FIX: accepted_values tests
│   ├── dimensions/
│   │   └── dim_enrollment_hazards.sql              # FIX: critical mismatch
│   └── marts/
│       └── fct_workforce_snapshot.sql              # FIX: fragile hardcoded
├── tests/
│   └── data_quality/
│       └── test_band_label_consistency.sql         # NEW: cross-model test
└── seeds/
    ├── config_age_bands.csv                        # Source of truth (no changes)
    └── config_tenure_bands.csv                     # Source of truth (no changes)
```

**Structure Decision**: All changes are within the existing `dbt/` directory. No new directories needed. One new test file added to the existing `dbt/tests/data_quality/` directory.

## Implementation Approach

### Phase 1: Fix 5 Critical Mismatches (P1)

These models produce wrong labels causing zero events:

| Model | Issue | Fix |
|-------|-------|-----|
| `int_active_employees_by_year.sql` | `Under 25` age, wrong tenure labels | Replace CASE with `{{ assign_age_band('current_age') }}` and `{{ assign_tenure_band('current_tenure') }}` |
| `int_active_employees_prev_year_snapshot.sql` | Same as above, uses `+1` expressions | Replace with `{{ assign_age_band('current_age + 1') }}` and `{{ assign_tenure_band('current_tenure + 1') }}` |
| `dim_enrollment_hazards.sql` | Tenure labels `0-1`, `1-3`, `3-5` | Replace with seed-defined labels `< 2`, `2-4`, `5-9`, `10-19`, `20+` |
| `int_enrollment_events_v2.sql` (lines 377-388) | Age `< 30, 30-39` etc; tenure in months | Replace with macro calls, convert tenure months to years |
| `events_enrollment_sql.sql` | Splits `10-19` into `10-14` / `15-19` | Replace tenure CASE with `{{ assign_tenure_band('se.current_tenure') }}` |

### Phase 2: Replace 14 Fragile Hardcoded CASE Blocks (P2)

Each file has a hardcoded CASE that currently produces correct labels. Replace each with the appropriate macro call. The column/expression to pass depends on the model:
- Models using `current_age` / `current_tenure` → `{{ assign_age_band('current_age') }}`
- Models using `current_age + 1` / `current_tenure + 1` → `{{ assign_age_band('current_age + 1') }}`
- Models referencing aliased columns (e.g., `he.employee_age`) → `{{ assign_age_band('he.employee_age') }}`

### Phase 3: Fix schema.yml (P3)

Update `accepted_values` tests at lines ~1564-1575 and ~1661-1672 to use seed-defined labels:
- Age: `['< 25', '25-34', '35-44', '45-54', '55-64', '65+']`
- Tenure: `['< 2', '2-4', '5-9', '10-19', '20+']`

### Phase 4: Add Cross-Model Consistency Test (P3)

New dbt test: `dbt/tests/data_quality/test_band_label_consistency.sql`

Logic: Anti-join `fct_workforce_snapshot` distinct age/tenure bands against seed tables. Test passes when zero unmatched labels exist.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Macro compile-time failure with expressions | Low | High | CLAUDE.md confirms expression support; test with `dbt compile` first |
| dim_enrollment_hazards boundary logic change affects enrollment rates | Medium | Medium | Verify enrollment event counts match expected hazard rates post-fix |
| Enrollment v2 tenure month-to-year conversion error | Medium | High | Validate converted values produce correct band assignments with test data |
| Downstream model breakage from label changes | Low | Medium | Run full `dbt build --threads 1 --fail-fast` after all changes |

## Complexity Tracking

No constitution violations. No complexity justifications needed.
