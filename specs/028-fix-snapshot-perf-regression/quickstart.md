# Quickstart: Fix Workforce Snapshot Performance Regression

**Feature**: 028-fix-snapshot-perf-regression
**Estimated Effort**: 1-2 hours implementation + 1 hour validation

## Overview

This fix addresses a 5.6x performance regression in `fct_workforce_snapshot.sql` by:
1. Replacing O(n²) scalar subqueries with O(n) JOIN
2. Adding missing `simulation_year` filters

## Prerequisites

- dbt development environment configured
- Access to `dbt/simulation.duckdb` database
- Ability to run multi-year simulations for validation

## Quick Implementation Steps

### Step 1: Capture Pre-Optimization Baseline

```bash
# Record current performance
cd /workspace
time planalign simulate 2025-2029 --dry-run  # Note: actual timing requires real run

# Export baseline data for comparison
cd dbt
duckdb simulation.duckdb "
COPY (
    SELECT employee_id, simulation_year, compensation_quality_flag, current_compensation
    FROM fct_workforce_snapshot
    ORDER BY employee_id, simulation_year
) TO 'baseline_snapshot.csv' (HEADER);
"
```

### Step 2: Apply Fix 1 - Replace Scalar Subqueries

Edit `dbt/models/marts/fct_workforce_snapshot.sql`:

1. **Add CTE** (before `final_output` CTE, around line 930):
```sql
baseline_comp_for_quality AS (
    SELECT
        employee_id,
        current_compensation AS baseline_compensation
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
```

2. **Add JOIN** (in `final_output` FROM clause):
```sql
LEFT JOIN baseline_comp_for_quality bcq
    ON final_workforce_with_contributions.employee_id = bcq.employee_id
```

3. **Replace scalar subqueries** (lines 971-1025) with:
```sql
CASE
    WHEN bcq.baseline_compensation IS NULL THEN 'NORMAL'
    WHEN bcq.baseline_compensation <= 0 THEN 'NORMAL'
    WHEN (current_compensation / bcq.baseline_compensation) > 100.0 THEN 'CRITICAL_INFLATION_100X'
    WHEN (current_compensation / bcq.baseline_compensation) > 50.0 THEN 'CRITICAL_INFLATION_50X'
    WHEN (current_compensation / bcq.baseline_compensation) > 10.0 THEN 'SEVERE_INFLATION_10X'
    WHEN (current_compensation / bcq.baseline_compensation) > 5.0 THEN 'WARNING_INFLATION_5X'
    ELSE 'NORMAL'
END AS compensation_quality_flag,
```

### Step 3: Apply Fix 2 - Add simulation_year Filters

Add `simulation_year = {{ var('simulation_year') }}` to three locations:

1. **Line ~373**: Year 1 baseline eligibility WHERE clause
2. **Line ~423**: NOT IN subquery WHERE clause
3. **Line ~472**: Baseline fallback WHERE clause

### Step 4: Validate

```bash
# Run dbt tests
cd dbt
dbt test --select fct_workforce_snapshot --threads 1

# Compare output data
duckdb simulation.duckdb "
COPY (
    SELECT employee_id, simulation_year, compensation_quality_flag, current_compensation
    FROM fct_workforce_snapshot
    ORDER BY employee_id, simulation_year
) TO 'optimized_snapshot.csv' (HEADER);
"

# Verify identical output
diff baseline_snapshot.csv optimized_snapshot.csv
# Expected: no differences

# Measure performance improvement
time planalign simulate 2025-2029
# Expected: <15 minutes (down from 45 minutes)
```

## Success Criteria Checklist

- [ ] 5-year simulation completes in <15 minutes
- [ ] Single-year model build <30 seconds
- [ ] 100% data consistency with baseline
- [ ] All dbt tests pass
- [ ] No division-by-zero errors

## Rollback

If issues occur:
```bash
git checkout -- dbt/models/marts/fct_workforce_snapshot.sql
```

## Files Modified

| File | Change Type |
|------|-------------|
| `dbt/models/marts/fct_workforce_snapshot.sql` | Modified (performance optimization) |
