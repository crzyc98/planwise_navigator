# Implementation Plan: Fix Census Compensation Annualization Logic

**Branch**: `043-fix-annualization-logic` | **Date**: 2026-02-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/043-fix-annualization-logic/spec.md`

## Summary

Fix the annualization logic in `stg_census_data.sql` by clarifying the computation and comments for `employee_annualized_compensation` and `employee_plan_year_compensation`. Remove HOTFIX/bypass patterns from `int_baseline_workforce.sql`. Add comprehensive annualization-specific dbt tests covering proration math, boundary conditions, and cross-model consistency.

**Key finding from research**: `employee_gross_compensation` is already an annual rate per the data contract, so `employee_annualized_compensation = employee_gross_compensation` is functionally correct. The fix is primarily about code clarity, removing misleading comments, and closing test coverage gaps. No downstream value changes are expected.

## Technical Context

**Language/Version**: SQL (DuckDB 1.0.0) via dbt-core 1.8.8, dbt-duckdb 1.8.1
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, dbt-utils
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: dbt singular SQL tests in `dbt/tests/data_quality/` with severity classification
**Target Platform**: Local analytics (work laptop)
**Project Type**: dbt data transformation project
**Performance Goals**: Tests complete in <15 seconds; models rebuild in <30 seconds
**Constraints**: Single-threaded execution (`--threads 1`) for stability
**Scale/Scope**: 3 files modified, 1 file created, 52 downstream models validated via regression

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Event Sourcing & Immutability | PASS | No changes to `fct_yearly_events`. Staging and intermediate models are not part of the immutable event store. |
| II. Modular Architecture | PASS | Changes are scoped to 2 existing models + 1 new test file. No circular dependencies introduced. Staging → intermediate direction preserved. |
| III. Test-First Development | PASS | New test file (`test_annualization_logic.sql`) validates the fix. Existing schema tests remain. |
| IV. Enterprise Transparency | PASS | Removing misleading comments improves transparency. Test output includes severity classification and validation messages for audit. |
| V. Type-Safe Configuration | PASS | No configuration changes. Existing `{{ ref() }}` and `{{ var() }}` patterns maintained. |
| VI. Performance & Scalability | PASS | No performance impact. New test uses year-aware filtering. |

**Post-Phase 1 re-check**: All gates still pass. No new patterns or abstractions introduced.

## Project Structure

### Documentation (this feature)

```text
specs/043-fix-annualization-logic/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: research findings
├── data-model.md        # Phase 1: entity relationships
├── quickstart.md        # Phase 1: verification guide
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
dbt/
├── models/
│   ├── staging/
│   │   ├── stg_census_data.sql          # MODIFY: clarify annualization logic
│   │   └── schema.yml                   # VERIFY: existing schema tests
│   └── intermediate/
│       └── int_baseline_workforce.sql   # MODIFY: remove HOTFIX patterns
└── tests/
    └── data_quality/
        └── test_annualization_logic.sql # CREATE: new annualization test
```

**Structure Decision**: This is a dbt-only change within the existing project structure. No new directories or architectural changes needed. The test follows the established `dbt/tests/data_quality/` convention.

## Implementation Phases

### Phase 1: Clarify Staging Model Annualization (stg_census_data.sql)

**Scope**: Lines 79-118 of `stg_census_data.sql`

**Changes**:
1. Replace the misleading comment on line 115 ("Gross compensation is already an annual rate; no annualization needed") with a clear explanation of the data contract and the relationship between the three compensation fields.
2. Ensure `computed_plan_year_compensation` calculation (line 113) is clearly documented as the prorated plan-year amount.
3. Ensure `employee_annualized_compensation` (line 116) is clearly documented as the full-year equivalent rate (equals gross per data contract).
4. Verify edge case handling: `days_active_in_year = 0` produces `plan_year_compensation = 0` (line 112).

**No value changes**: The SQL logic remains the same. Only comments and documentation clarity change.

### Phase 2: Remove HOTFIX from Baseline Model (int_baseline_workforce.sql)

**Scope**: `int_baseline_workforce.sql`

**Changes**:
1. Verify line 25 uses `stg.employee_annualized_compensation AS current_compensation` — this is already correct.
2. Remove any HOTFIX, bypass, or TODO comments related to annualization.
3. Add a brief comment documenting that `current_compensation` equals the annual salary rate from staging.

**No value changes**: The field reference remains the same.

### Phase 3: Add Annualization Tests (test_annualization_logic.sql)

**Scope**: New file `dbt/tests/data_quality/test_annualization_logic.sql`

**Test cases** (following project severity-classification pattern):

| Rule | Severity | Validation |
| ---- | -------- | ---------- |
| ANN_001 | CRITICAL | `employee_annualized_compensation = employee_gross_compensation` for all employees |
| ANN_002 | CRITICAL | `employee_plan_year_compensation >= 0` for all employees |
| ANN_003 | ERROR | `employee_plan_year_compensation <= employee_gross_compensation * (366.0 / 365.0)` |
| ANN_004 | ERROR | `days_active_in_year` between 0 and 366 inclusive |
| ANN_005 | WARNING | Full-year employees have `plan_year_comp ≈ gross_comp` (within 0.3% for leap year) |
| ANN_006 | ERROR | Zero-day employees have `plan_year_compensation = 0` |
| ANN_007 | WARNING | Cross-model: `int_baseline_workforce.current_compensation = stg_census_data.employee_annualized_compensation` |

**Pattern**: Returns 0 rows on PASS. Violations stored in `test_failures` schema.

### Phase 4: Regression Validation

**Scope**: Full dbt build to confirm zero downstream impact.

**Steps**:
1. `dbt run --select stg_census_data int_baseline_workforce --threads 1`
2. `dbt test --select test_annualization_logic --vars "simulation_year: 2025" --threads 1`
3. `dbt test --select stg_census_data --threads 1` (schema tests)
4. `dbt test --select test_compensation_bounds test_negative_compensation --vars "simulation_year: 2025" --threads 1`
5. `dbt build --threads 1 --fail-fast` (full regression)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Accidental value change during refactoring | Low | High | Schema test enforces `annualized = gross`; new test ANN_001 double-validates |
| Downstream regression | Very Low | High | Full `dbt build` regression in Phase 4; 52 models validated |
| Data contract assumption wrong | Low | Medium | Research R1 confirmed via code comments and existing tests |

## Complexity Tracking

No constitution violations. No complexity justifications needed.
