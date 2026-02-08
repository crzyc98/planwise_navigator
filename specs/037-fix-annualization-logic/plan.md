# Implementation Plan: Fix Census Compensation Annualization Logic

**Branch**: `037-fix-annualization-logic` | **Date**: 2026-02-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/037-fix-annualization-logic/spec.md`

## Summary

Fix the broken annualization formula in `stg_census_data.sql` (which is an algebraic no-op) by replacing it with a direct assignment (`employee_annualized_compensation = employee_gross_compensation`), then update `int_baseline_workforce.sql` to use the corrected field instead of the HOTFIX bypass. Add dbt data tests to prevent regression. Output values are numerically identical before and after — this is a code clarity and correctness fix.

## Technical Context

**Language/Version**: SQL (DuckDB 1.0.0) via dbt-core 1.8.8 + dbt-duckdb 1.8.1
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, dbt-utils
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: dbt test (schema tests in `schema.yml`, singular tests in `tests/`)
**Target Platform**: Linux server / work laptop (single-threaded dbt execution)
**Project Type**: Single project (dbt SQL models)
**Performance Goals**: N/A (no performance change — formula simplification only)
**Constraints**: Must not change output values for any employee. Zero regression tolerance.
**Scale/Scope**: 3 files modified, ~10 lines changed, 3 new dbt tests added

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Event Sourcing & Immutability | PASS | No events are modified. Staging model is a table materialization, not part of the immutable event store. |
| II. Modular Architecture | PASS | Changes are confined to 2 models in their correct layers (staging → intermediate). No circular dependencies introduced. |
| III. Test-First Development | PASS | New dbt data tests will be added to `schema.yml` to validate the corrected formulas before removing the HOTFIX. |
| IV. Enterprise Transparency | PASS | Removes confusing HOTFIX comments that obscure the compensation pipeline's intent. |
| V. Type-Safe Configuration | PASS | Schema contract for `stg_census_data` already defines both columns with proper types. No contract changes needed. |
| VI. Performance & Scalability | PASS | Simplified formula is computationally cheaper (direct assignment vs. round-trip arithmetic). |

**Post-Phase 1 Re-check**: All gates still pass. No new dependencies, no layer violations, tests included.

## Project Structure

### Documentation (this feature)

```text
specs/037-fix-annualization-logic/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Bug analysis and impact research
├── data-model.md        # Phase 1: Entity and field definitions
├── quickstart.md        # Phase 1: Verification steps
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
dbt/
├── models/
│   ├── staging/
│   │   ├── stg_census_data.sql       # FIX: Simplify annualization formula
│   │   └── schema.yml                # ADD: Annualization validation tests
│   └── intermediate/
│       └── int_baseline_workforce.sql # FIX: Remove HOTFIX, use annualized field
```

**Structure Decision**: This is a targeted fix within the existing dbt model hierarchy. No new files or directories are created. Changes are confined to the staging and intermediate layers following the existing `staging → intermediate → marts` dependency flow.

## Complexity Tracking

No constitution violations. No complexity tracking needed.

## Implementation Design

### Change 1: Simplify `stg_census_data.sql` (lines 109-122)

**Current** (broken/confusing):
```sql
comp_data AS (
  SELECT
    ad.*,
    CASE
      WHEN ad.days_active_in_year = 0 THEN 0.0
      ELSE ad.employee_gross_compensation * (ad.days_active_in_year / 365.0)
    END AS computed_plan_year_compensation,
    CASE
      WHEN ad.days_active_in_year = 0 THEN ad.employee_gross_compensation
      ELSE (ad.employee_gross_compensation * (ad.days_active_in_year / 365.0)) * 365.0 / GREATEST(1, ad.days_active_in_year)
    END AS employee_annualized_compensation
  FROM annualized_data ad
),
```

**After** (correct and clear):
```sql
comp_data AS (
  SELECT
    ad.*,
    CASE
      WHEN ad.days_active_in_year = 0 THEN 0.0
      ELSE ad.employee_gross_compensation * (ad.days_active_in_year / 365.0)
    END AS computed_plan_year_compensation,
    -- employee_gross_compensation is already an annual rate per the data contract.
    -- Annualized compensation equals gross compensation directly.
    ad.employee_gross_compensation AS employee_annualized_compensation
  FROM annualized_data ad
),
```

**Also update**: Remove the stale comment at lines 80-82 referencing the never-implemented `annualize_partial_year_compensation` var toggle.

### Change 2: Update `int_baseline_workforce.sql` (lines 25-27)

**Current** (HOTFIX):
```sql
-- **HOTFIX**: Use gross compensation to avoid annualization calculation bug
-- TODO: Fix the annualization logic in stg_census_data.sql later
stg.employee_gross_compensation AS current_compensation,
```

**After** (canonical path):
```sql
stg.employee_annualized_compensation AS current_compensation,
```

### Change 3: Add dbt tests in `dbt/models/staging/schema.yml`

Add under the `stg_census_data` model's `employee_annualized_compensation` column:

```yaml
- name: employee_annualized_compensation
  description: "Annualized compensation equals gross compensation (gross is already an annual rate per data contract)."
  data_type: double
  data_tests:
    - not_null
    - dbt_utils.expression_is_true:
        expression: "= employee_gross_compensation"
        name: "annualized_comp_equals_gross"
```

Add under `employee_plan_year_compensation`:

```yaml
  data_tests:
    - not_null
    - dbt_utils.accepted_range:
        min_value: 0
        name: "plan_year_comp_non_negative"
    - dbt_utils.expression_is_true:
        expression: "<= employee_gross_compensation"
        name: "plan_year_comp_not_exceeds_gross"
```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Downstream regression from compensation value change | None | High | Values are mathematically identical (gross = annualized by definition). Verified by `dbt build --fail-fast`. |
| Schema contract violation | None | Medium | Column types and names are unchanged. Only the computation behind `employee_annualized_compensation` changes. |
| Test failure from new tests | Low | Low | New tests validate the corrected formula. If they fail, the fix is wrong and should be investigated. |
