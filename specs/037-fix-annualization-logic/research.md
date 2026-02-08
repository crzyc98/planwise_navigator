# Research: Fix Census Compensation Annualization Logic

**Branch**: `037-fix-annualization-logic` | **Date**: 2026-02-07

## Research Question 1: What is the actual annualization bug?

### Decision
The `employee_annualized_compensation` formula in `stg_census_data.sql` (lines 117-120) is an algebraic no-op. The formula `(gross * days/365) * 365/days` simplifies to `gross` for all non-zero cases. The HOTFIX in `int_baseline_workforce.sql` bypasses this column and uses `employee_gross_compensation` directly — which produces the same result but via a clearer path.

### Rationale
The data contract states that `employee_gross_compensation` is already an annual rate. Therefore:
- `employee_annualized_compensation` should simply equal `employee_gross_compensation` (it's already annualized)
- `employee_plan_year_compensation` (the pro-rated column) correctly computes `gross * days_active / 365`
- The current formula achieves the correct math accidentally but via a confusing round-trip

### Alternatives Considered
1. **Implement a true annualization toggle**: The comment at line 82 mentions `annualize_partial_year_compensation` as a var. However, since the census data contract defines gross compensation as an annual rate, there's no scenario where annualization (grossing up partial earnings) is needed. Rejected as unnecessary complexity.
2. **Remove both computed columns entirely**: Would break the schema contract and any potential external consumers. Rejected as too risky for the scope of this fix.

## Research Question 2: What is the downstream impact?

### Decision
The fix is surgically isolated. The two columns (`employee_annualized_compensation`, `employee_plan_year_compensation`) are produced by `stg_census_data` but **never consumed** by any downstream model.

### Evidence
- `int_baseline_workforce.sql` uses `employee_gross_compensation` directly (the HOTFIX)
- No other model references `employee_annualized_compensation` or `employee_plan_year_compensation` via `ref('stg_census_data')`
- The `debug_participation_pipeline.sql` analysis model references `stg_census_data` but does not use these columns

### Impact Chain
```
stg_census_data → employee_annualized_compensation (DEAD CODE, never read)
stg_census_data → employee_gross_compensation → int_baseline_workforce.current_compensation
  → int_employee_compensation_by_year → 30+ downstream models
```

After the fix:
```
stg_census_data → employee_annualized_compensation (= employee_gross_compensation)
  → int_baseline_workforce.current_compensation (via annualized field, not gross)
  → int_employee_compensation_by_year → 30+ downstream models (UNCHANGED VALUES)
```

### Conclusion
Since `employee_gross_compensation` equals `employee_annualized_compensation` (by definition — gross is already annual), switching the baseline model from `gross` to `annualized` produces **identical output values**. Zero regression risk.

## Research Question 3: What is the correct fix approach?

### Decision
Two-part fix:
1. **Simplify `stg_census_data.sql`**: Replace the confusing round-trip formula with a direct assignment: `employee_annualized_compensation = employee_gross_compensation`. Keep `computed_plan_year_compensation` as the pro-rated field.
2. **Update `int_baseline_workforce.sql`**: Replace `stg.employee_gross_compensation AS current_compensation` with `stg.employee_annualized_compensation AS current_compensation`. Remove HOTFIX/TODO comments.

### Rationale
- Makes the intent clear: annualized = gross (because gross is already annual)
- Removes confusing math that obscures the relationship
- Establishes `employee_annualized_compensation` as the canonical compensation field from staging
- The dead intermediate variable `annualize_partial_year_compensation` comment is cleaned up

### Alternatives Considered
1. **Keep the formula but fix the HOTFIX only**: Would leave confusing dead math in staging. Rejected — code clarity matters.
2. **Add the `annualize_partial_year_compensation` conditional toggle**: Over-engineering for a scenario that doesn't exist per the data contract. Rejected.

## Research Question 4: What tests are needed?

### Decision
Add dbt data tests in `schema.yml` for `stg_census_data`:
1. **Annualized = Gross test**: Assert `employee_annualized_compensation = employee_gross_compensation` for all rows
2. **Plan year compensation range test**: Assert `employee_plan_year_compensation <= employee_gross_compensation` (pro-rated can't exceed annual)
3. **Plan year compensation non-negative**: Assert `employee_plan_year_compensation >= 0`

### Rationale
These tests directly validate the corrected formulas and catch regressions. They are dbt singular or generic tests that run as part of `dbt test` and align with the existing test patterns in the project.
