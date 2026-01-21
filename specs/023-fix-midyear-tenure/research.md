# Research: Fix Mid-Year Termination Tenure Calculation

**Feature**: 023-fix-midyear-tenure
**Date**: 2026-01-21

## Root Cause Analysis

### Bug #1: Tenure Band Uses Pre-Recalculated Tenure

**Location**: `dbt/models/marts/fct_workforce_snapshot.sql` (lines 748-754)

**Problem**: The tenure band calculation uses `fwc.current_tenure` which is the input value from the CTE chain, NOT the recalculated tenure value.

```sql
-- Current (buggy) code at line 748-754:
CASE
    WHEN fwc.current_tenure < 2 THEN '< 2'
    WHEN fwc.current_tenure < 5 THEN '2-4'
    ...
END AS tenure_band
```

The recalculation happens at lines 684-689:
```sql
CASE
    WHEN fwc.employment_status = 'terminated' AND fwc.termination_date IS NOT NULL THEN
        {{ calculate_tenure('fwc.employee_hire_date', ..., 'fwc.termination_date') }}
    ELSE
        fwc.current_tenure
END AS current_tenure
```

**Issue**: The recalculated `current_tenure` is computed in the SELECT list but the `tenure_band` calculation still references `fwc.current_tenure` (the original value), not the recalculated value. This causes mismatched tenure/tenure_band for terminated employees.

**Decision**: Refactor `final_workforce` CTE to use a subquery or intermediate CTE that calculates tenure first, then derives tenure_band from the recalculated tenure.

**Rationale**: SQL SELECT clause column aliases cannot reference each other in the same SELECT. A subquery pattern solves this cleanly.

**Alternatives Considered**:
1. Use a window function - Rejected: Unnecessarily complex for this use case
2. Duplicate the tenure calculation logic in tenure_band - Rejected: DRY violation, error-prone

### Bug #2: New Hire Tenure Hardcoded to 0

**Location**: `dbt/models/marts/fct_workforce_snapshot.sql` (line 208)

**Problem**: The `new_hires` CTE hardcodes tenure to 0:
```sql
0 AS current_tenure, -- New hires start with 0 tenure
```

For new hires who are terminated mid-year, the tenure should be calculated from their hire date to their termination date, not remain at 0.

**Decision**: Calculate tenure for new hires using the same `calculate_tenure` macro, with termination_date handling.

**Rationale**: New hires who work 6+ months and then terminate should show tenure > 0 for accurate reporting.

**Alternatives Considered**:
1. Keep 0 for new hires, adjust in `final_workforce` CTE - Rejected: The recalculation at line 684-689 should already handle this, but need to verify it does.
2. Calculate tenure inline in new_hires CTE - Accepted: More explicit and self-documenting.

### Bug #3: Year-over-Year +1 Increment

**Location**: `dbt/models/intermediate/int_active_employees_prev_year_snapshot.sql` (line 65)

**Analysis**: Line 65 shows:
```sql
current_tenure + 1 as current_tenure, -- Increment tenure for the new year
```

This blindly adds +1 to all employees entering a new year. For employees who are terminated mid-year in Year N, this inflated tenure value propagates before the recalculation in `fct_workforce_snapshot` can correct it.

**Decision**: The recalculation logic at lines 684-689 of `fct_workforce_snapshot.sql` SHOULD correct this for terminated employees. The issue is that tenure_band doesn't use the corrected value.

**Rationale**: The +1 increment is correct for active employees who persist through the year. The fix should focus on ensuring tenure_band uses the recalculated tenure.

### Polars Pipeline Analysis

**Location**: `planalign_orchestrator/polars_state_pipeline.py` (lines 1862-1872)

**Analysis**: The Polars pipeline calculates tenure correctly:
```python
pl.when(pl.col('employee_hire_date').is_null())
.then(0)
.when(pl.col('termination_date').is_not_null())
.then(
    (pl.col('termination_date').cast(pl.Date) - pl.col('employee_hire_date').cast(pl.Date)).dt.total_days() / 365.25
)
.otherwise(
    (pl.lit(year_end) - pl.col('employee_hire_date').cast(pl.Date)).dt.total_days() / 365.25
)
.cast(pl.Int32)
.alias('current_tenure')
```

**Tenure Band Calculation** (lines 1944-1949):
```python
tenure_band_expr = pl.lit('20+')  # Default
for min_tenure, max_tenure, band_label in reversed(self.TENURE_BANDS):
    tenure_band_expr = pl.when(
        (pl.col('current_tenure') >= min_tenure) & (pl.col('current_tenure') < max_tenure)
    ).then(pl.lit(band_label)).otherwise(tenure_band_expr)
```

**Decision**: The Polars pipeline correctly calculates tenure_band AFTER current_tenure is computed, using `pl.col('current_tenure')`. This means Polars should be correct IF the `with_columns` call for tenure_band happens AFTER the tenure calculation.

**Verification Needed**: Confirm the order of `with_columns` calls in `SnapshotBuilder.build()` ensures tenure is calculated before tenure_band.

## Implementation Strategy

### Primary Fix (SQL Pipeline)

1. **Refactor `final_workforce` CTE** to use a subquery pattern:
   - Create inner SELECT that calculates `current_tenure`
   - Outer SELECT derives `tenure_band` from the calculated tenure

2. **Pattern**:
```sql
final_workforce AS (
    SELECT
        *,
        -- Derive tenure_band from recalculated current_tenure
        CASE
            WHEN current_tenure < 2 THEN '< 2'
            WHEN current_tenure < 5 THEN '2-4'
            ...
        END AS tenure_band
    FROM (
        SELECT
            fwc.employee_id,
            ...,
            -- Recalculate tenure
            CASE
                WHEN fwc.employment_status = 'terminated' AND fwc.termination_date IS NOT NULL THEN
                    {{ calculate_tenure('fwc.employee_hire_date', ..., 'fwc.termination_date') }}
                ELSE
                    fwc.current_tenure
            END AS current_tenure,
            ...
        FROM final_workforce_corrected fwc
        ...
    ) tenure_calculated
)
```

### Secondary Fix (New Hires)

Update the `new_hires` CTE to calculate tenure:
```sql
-- Instead of: 0 AS current_tenure
{{ calculate_tenure('ye.effective_date', "MAKE_DATE(" ~ var('simulation_year') ~ ", 12, 31)", 'ec.termination_date') }} AS current_tenure
```

### Polars Pipeline Verification

1. Verify the order of operations in `SnapshotBuilder.build()`
2. Ensure `TENURE_BANDS` constant matches SQL macro definitions
3. Add assertion test for SQL/Polars parity

## Testing Strategy

1. **Unit Tests** (pytest):
   - Test `calculate_tenure` logic with various edge cases
   - Test tenure band assignment consistency

2. **dbt Tests**:
   - Add `test_tenure_band_consistency.sql` to validate tenure/band match
   - Add specific tests for mid-year termination scenarios

3. **Parity Tests**:
   - Run same simulation in SQL and Polars modes
   - Compare `current_tenure` and `tenure_band` for all terminated employees

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Performance regression | Low | Medium | Subquery pattern is simple; benchmark before/after |
| Other CTEs depend on old tenure value | Low | High | Search for `fwc.current_tenure` references and verify |
| Polars/SQL parity breaks | Medium | High | Add explicit parity test |
