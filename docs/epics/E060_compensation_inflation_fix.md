# Epic E060: Critical Compensation Inflation Fix

## Executive Summary

A critical data integrity issue has been discovered where employee compensation values in `fct_workforce_snapshot` are inflated by approximately 91x compared to their actual census values. For example, employee EMP_2024_000783 with a census gross compensation of $100,800 shows as $9,198,000 in the workforce snapshot. This affects all compensation-related calculations including contributions, employer matches, and financial projections.

## Scope & Constraints

- Fix must occur within the transformation logic (marts) and not mutate events or baseline inputs, preserving event-sourced lineage and auditability.
- Changes must be minimal, targeted, and consistent with dbt model structure and contracts (no breaking dependencies or model names).
- Use existing debug/monitoring patterns in the repo (e.g., `int_compensation_periods_debug`, analysis/monitoring models) before adding new utilities.

## Problem Statement

### Current State
- **Symptom**: Employee compensation values in `fct_workforce_snapshot` are massively inflated
- **Example**: EMP_2024_000783 shows:
  - Census (expected): $100,800
  - Workforce snapshot (actual): $9,198,000
  - Inflation factor: ~91.25x
- **Impact**: All three compensation columns affected:
  - `current_compensation`: $9,198,000
  - `prorated_annual_compensation`: $9,198,000
  - `full_year_equivalent_compensation`: $9,198,000
- **Scope**: Unknown number of employees affected (requires full audit)

### Business Impact
- **Financial Projections**: Wildly incorrect compensation budgets and forecasts
- **Contribution Calculations**: Employee and employer contributions incorrectly calculated
- **Compliance Risk**: IRS contribution limits may be incorrectly applied
- **Decision Making**: Management decisions based on incorrect compensation data
- **Audit Risk**: Financial statements and regulatory reports contain material errors

### Technical Impact
- **Data Integrity**: Core fact table contains incorrect data
- **Downstream Models**: All models depending on `fct_workforce_snapshot` affected
- **Testing Gap**: No validation caught this 91x inflation
- **Trust**: Stakeholder confidence in simulation accuracy compromised

## Root Cause Analysis

### Suspected Causes
1. **Percentage Multiplication Error**
   - A percentage value (like 91.25%) being multiplied as 91.25 instead of 0.9125
   - Common in compensation adjustment calculations

2. **Contribution Calculation Error**
   - Employer contributions being incorrectly multiplied with base compensation
   - Possible confusion between contribution rates and amounts

3. **CTE Data Flow Issue**
   - Value gets inflated in one of the many CTEs in `fct_workforce_snapshot.sql`
   - Possible in: `workforce_after_merit`, `workforce_after_promotions`, or contribution joins

4. **Unit Conversion Error**
   - Mixing units (e.g., cents vs dollars, monthly vs annual)
   - Database storing values in different units than expected

### Investigation Findings
- The inflation occurs within the `fct_workforce_snapshot` pipeline where `current_compensation` is sourced from `employee_gross_compensation` and adjusted by event logic.
- The value `9,198,000` aligns with `100,800 * 91.25`, suggesting percentage/rate mis-scaling (percent treated as whole number).
- No 2025 raises/promotions for the example employee, pointing away from legitimate event-driven increases.
- All three compensation columns mirror the inflated value, implicating the upstream `employee_gross_compensation` assignment path.

## Solution Design

### Phase 1: Immediate Fix (Critical - Day 1)

#### A. Identify Exact Source
- Use existing debug model to trace compensation periods and baselines:
  - Run `dbt run --select int_compensation_periods_debug --vars '{"simulation_year": 2025}'`.
  - Query periods for `EMP_2024_000783` to confirm whether any event-derived salary equals the inflated value.
- Add a focused analysis query to compare `fct_workforce_snapshot.current_compensation` to `int_baseline_workforce.current_compensation` for year 1 employees and to prior-year `full_year_equivalent_compensation` for subsequent years.
- Inspect where `employee_gross_compensation` is set in `fct_workforce_snapshot.sql` (e.g., `base_workforce`, `workforce_after_*` CTEs) and verify any multiplication with rates uses decimals (0.043) not percents (4.3).

#### B. Fix Calculation
```sql
-- Example fix if percentage multiplication is the issue
-- WRONG: employee_gross_compensation * merit_increase_pct
-- RIGHT: employee_gross_compensation * (1 + merit_increase_pct)

-- Or if it's a decimal conversion issue
-- WRONG: employee_gross_compensation * (contribution_rate * 100)
-- RIGHT: employee_gross_compensation * contribution_rate
```

Notes:
- Do not change or rewrite events. Correct the transformation path where `employee_gross_compensation` feeds `current_compensation`.
- Validate changes for a sample of employees: the known case and 5–10 random employees across statuses.

### Phase 2: Validation & Testing (Day 1-2)

#### A. Add Data Quality Checks
```sql
-- Create validation model: dq_compensation_bounds_check.sql
WITH compensation_validations AS (
    SELECT
        employee_id,
        simulation_year,
        current_compensation,
        prorated_annual_compensation,
        full_year_equivalent_compensation,
        -- Check for unreasonable compensation
        CASE
            WHEN current_compensation > 10000000 THEN 'CRITICAL: Compensation > $10M'
            WHEN current_compensation > 5000000 THEN 'WARNING: Compensation > $5M'
            WHEN current_compensation < 10000 THEN 'WARNING: Compensation < $10K'
            ELSE 'OK'
        END AS compensation_flag,
        -- Check for inflation from baseline
        current_compensation / NULLIF(
            (SELECT MAX(employee_gross_compensation)
             FROM {{ ref('int_baseline_workforce') }} b
             WHERE b.employee_id = f.employee_id), 0
        ) AS inflation_factor
    FROM {{ ref('fct_workforce_snapshot') }} f
)

SELECT * FROM compensation_validations
WHERE compensation_flag != 'OK'
   OR inflation_factor > 2  -- Flag >2x increases
```

#### B. Add dbt Tests
```yaml
# models/marts/schema.yml
models:
  - name: fct_workforce_snapshot
    tests:
      - dbt_utils.expression_is_true:
          expression: "current_compensation < 10000000"
          error_if: ">0"
          warn_if: ">0"
      - dbt_utils.expression_is_true:
          expression: "current_compensation > 10000"
          error_if: ">100"
          warn_if: ">50"
```

#### C. Reuse Existing Validations
- Leverage `analysis/test_compensation_compounding_validation.sql` to ensure year-over-year carry-forward and compounding are correct.
- Add a simple monitoring model `models/monitoring/mon_compensation_inflation.sql` that surfaces per-employee inflation ratios vs baseline (year 1) and vs prior year (subsequent years) for dashboards/alerts.

### Phase 3: Comprehensive Audit (Day 2-3)

#### A. Full Employee Audit
```sql
-- Audit all employees for compensation inflation
WITH baseline_comparison AS (
    SELECT
        f.employee_id,
        f.simulation_year,
        b.employee_gross_compensation as baseline_comp,
        f.current_compensation as snapshot_comp,
        f.current_compensation / NULLIF(b.employee_gross_compensation, 0) as inflation_ratio,
        CASE
            WHEN f.current_compensation / NULLIF(b.employee_gross_compensation, 0) > 10 THEN 'CRITICAL'
            WHEN f.current_compensation / NULLIF(b.employee_gross_compensation, 0) > 2 THEN 'WARNING'
            ELSE 'NORMAL'
        END as severity
    FROM {{ ref('fct_workforce_snapshot') }} f
    LEFT JOIN {{ ref('int_baseline_workforce') }} b
        ON f.employee_id = b.employee_id
    WHERE f.simulation_year = 2025
)
SELECT
    severity,
    COUNT(*) as employee_count,
    AVG(inflation_ratio) as avg_inflation,
    MAX(inflation_ratio) as max_inflation,
    MIN(baseline_comp) as min_baseline,
    MAX(baseline_comp) as max_baseline,
    MIN(snapshot_comp) as min_snapshot,
    MAX(snapshot_comp) as max_snapshot
FROM baseline_comparison
GROUP BY severity
```

#### B. Cross-Model Integrity
- Verify row-count drift from baseline to snapshot is within 0.5% for year 1 (excludes legitimate hires/terms).
- Confirm primary-key uniqueness on `employee_id, simulation_year` for `fct_workforce_snapshot`.

### Phase 4: Prevention (Day 3-4)

#### A. Add Guardrails
```sql
-- Add to fct_workforce_snapshot.sql
final_output_with_guards AS (
    SELECT
        *,
        -- Add validation flags
        CASE
            WHEN current_compensation > 10000000 THEN 'DATA_QUALITY_ERROR'
            WHEN current_compensation / NULLIF(prior_year_comp, 0) > 3 THEN 'EXCESSIVE_INCREASE'
            ELSE 'VALID'
        END as compensation_quality_flag
    FROM final_output
)

-- Fail the model if critical errors exist
{{ config(
    post_hook="SELECT COUNT(*) FROM {{ this }} WHERE compensation_quality_flag = 'DATA_QUALITY_ERROR' HAVING COUNT(*) > 0"
) }}
```

#### B. Monitoring Dashboard
Prefer dbt-native monitoring first (no external services required):
- Expose `mon_compensation_inflation` and `mon_data_quality` in a lightweight dashboard or CLI reports.
- Track distributions, YoY changes, outliers, and inflation factors using these models.

## Implementation Plan

### Day 1: Emergency Fix
1. [ ] Run `int_compensation_periods_debug` and targeted analysis query to locate inflation source
2. [ ] Implement minimal fix in `fct_workforce_snapshot.sql` where rate scaling occurs
3. [ ] Validate on EMP_2024_000783 and a small random sample
4. [ ] Build `+fct_workforce_snapshot` with vars for the affected year(s)

### Day 2: Validation
1. [ ] Run comprehensive audit query and review severity distribution
2. [ ] Add/enable tests and `mon_compensation_inflation` monitoring model
3. [ ] Execute `analysis/test_compensation_compounding_validation` and address any mismatches
4. [ ] Document root cause and remediation in this epic and in `dbt/models/marts/schema.yml` descriptions

### Day 3: Prevention
1. [ ] Add guardrails to prevent future occurrences
2. [ ] Wire monitoring queries into existing `mon_data_quality` aggregation
3. [ ] Update documentation
4. [ ] Train team on issue and prevention

### Day 4: Remediation
1. [ ] Rerun all affected simulations
2. [ ] Update dependent reports
3. [ ] Communicate fix to stakeholders
4. [ ] Post-mortem review

## Success Criteria

1. **Immediate**: EMP_2024_000783 shows correct compensation of ~$100,800
2. **Comprehensive**: All employees show reasonable compensation values
3. **Validation**: No compensation values > $10M (unless explicitly justified)
4. **Testing**: Automated tests prevent regression
5. **Monitoring**: Dashboard alerts on anomalies
6. **Documentation**: Root cause documented and shared
7. **Data Contracts**: PK uniqueness and YOY compounding checks pass; row-count drift from baseline within 0.5% in year 1

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Fix breaks other calculations | HIGH | MEDIUM | Comprehensive testing before deployment |
| Historical data needs correction | HIGH | HIGH | Plan for historical data remediation |
| Similar issues in other models | MEDIUM | MEDIUM | Audit all compensation-related models |
| Performance impact from guards | LOW | LOW | Optimize validation queries |

## Dependencies

- Local DuckDB at repo root (`simulation_dbt.duckdb`); avoid IDE locks during runs
- dbt development environment (run from `/dbt`); no network installs
- Testing via `dbt test` and analysis models; optional Python validations if needed
- Stakeholder availability for validation

## Acceptance Criteria

- [ ] Root cause identified and documented
- [ ] Fix implemented and tested
- [ ] All affected employees corrected
- [ ] Data quality checks in place
- [ ] Tests prevent regression
- [ ] Documentation updated
- [ ] Stakeholders notified
- [ ] Historical data remediated if needed

## Verification Commands

- Build snapshot for specific year: `cd dbt && dbt run --select +fct_workforce_snapshot --vars '{"simulation_year": 2025, "start_year": 2025}'`
- Run key tests: `dbt test --select fct_workforce_snapshot`
- Run compounding validation: `dbt run --select analysis.test_compensation_compounding_validation`
- Inspect debug periods: `dbt run --select int_compensation_periods_debug`

## Post-Implementation Actions

1. **Monitoring**: Daily checks for 1 week, then weekly for 1 month
2. **Audit**: Quarterly compensation data quality audits
3. **Training**: Team training on data quality best practices
4. **Process**: Update data validation checklist for all models

## Notes

- This is a CRITICAL production issue requiring immediate attention
- The 91.25x inflation factor suggests a specific calculation error
- Similar patterns may exist in other financial calculations
- Prefer dbt-native data quality patterns (schema tests + monitoring models) and avoid ad hoc hooks when possible
