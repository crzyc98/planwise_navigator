# Deferral Rate Fix Documentation

**Date**: 2025-01-07
**Issue**: Critical data quality issue - hardcoded 5% deferral rate causing incorrect contribution calculations
**File Fixed**: `dbt/models/intermediate/events/int_employee_contributions.sql`

## Problem Description

The `int_employee_contributions` model had a hardcoded deferral rate of 0.05 (5%) on line 63, which was being applied to ALL employees regardless of their actual deferral elections. This caused:

1. Employees with 0% deferral to incorrectly show contributions
2. Employees with rates other than 5% to have wrong contribution amounts
3. Inability to track actual employee deferral decisions
4. Incorrect employer match calculations downstream

## Root Cause

The model was not properly sourcing deferral rates from:
- Census data (`stg_census_data.employee_deferral_rate`) for existing employees
- Enrollment events (`fct_yearly_events.employee_deferral_rate`) for new hires and rate changes

## Solution Implemented

### 1. Added New CTEs for Deferral Rate Sources

```sql
-- Census deferral rates (existing employees)
census_deferral_rates AS (
    SELECT
        employee_id,
        employee_deferral_rate AS census_deferral_rate
    FROM {{ ref('stg_census_data') }}
    WHERE employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
)

-- Enrollment event deferral rates (new hires & changes)
enrollment_deferral_rates AS (
    SELECT
        employee_id,
        employee_deferral_rate AS enrollment_deferral_rate,
        effective_date AS deferral_rate_effective_date,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date DESC
        ) AS rn
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('enrollment', 'enrollment_change')
        AND simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
)
```

### 2. Implemented Priority-Based COALESCE Logic

```sql
-- Line 63 fix: Use actual rates instead of hardcoded 0.05
COALESCE(
    ler.enrollment_deferral_rate,  -- Priority 1: Latest enrollment event
    cdr.census_deferral_rate,      -- Priority 2: Census baseline
    0.00                           -- Priority 3: Default zero (no contribution)
) AS current_deferral_rate
```

### 3. Added Source Tracking for Audit Trail

```sql
-- Track where each deferral rate came from
CASE
    WHEN ler.enrollment_deferral_rate IS NOT NULL THEN 'enrollment_event'
    WHEN cdr.census_deferral_rate IS NOT NULL THEN 'census_data'
    ELSE 'default_zero'
END AS deferral_rate_source
```

### 4. Enhanced Data Quality Controls

- Only employees with positive deferral rates get contributions calculated
- Employees with `deferral_rate_source = 'default_zero'` are excluded
- Data quality flags detect anomalies

## Priority Hierarchy

1. **Enrollment Events** (Highest Priority)
   - Captures employee-initiated deferral changes
   - Applies to new hires who weren't in census
   - Uses most recent enrollment event per employee

2. **Census Data** (Fallback)
   - Baseline deferral rates for existing employees
   - Used when no enrollment events exist

3. **Default Zero** (Safety Net)
   - Ensures no contributions for employees without valid rates
   - Prevents calculation errors

## Testing & Validation

### Test Commands

```bash
# 1. Rebuild the models with the fix
dbt run --select int_employee_contributions int_employee_match_calculations fct_employer_match_events --vars "simulation_year: 2025"

# 2. Run the validation script
python validate_deferral_fix.py

# 3. Check for zero-deferral contribution issues
dbt run --select dq_employee_contributions_validation --vars "simulation_year: 2025"
```

### Key Validation Checks

1. **No Hardcoded 5% Rates**: Verify all 5% rates come from legitimate sources
2. **Zero Deferral = Zero Contributions**: Employees with 0% deferral should have $0 contributions
3. **Source Attribution**: Every deferral rate should have a valid source (enrollment or census)
4. **New Hire Coverage**: New hires should get rates from enrollment events

## Impact on Downstream Models

The following models depend on `int_employee_contributions` and benefit from this fix:

- `int_employee_match_calculations`: Now calculates matches based on actual deferral rates
- `fct_employer_match_events`: Provides accurate employer match amounts
- `fct_workforce_snapshot`: Shows correct contribution and match totals

## Rollback Plan

If issues arise, revert the changes to `int_employee_contributions.sql`:

```bash
git checkout HEAD -- dbt/models/intermediate/events/int_employee_contributions.sql
dbt run --select int_employee_contributions+ --vars "simulation_year: 2025"
```

## Monitoring

After deployment, monitor these metrics:

1. Count of employees with `deferral_rate_source = 'default_zero'` (should be minimal)
2. Distribution of deferral rates (should match business expectations)
3. Total contribution amounts (should align with payroll data)
4. Data quality check results from `dq_employee_contributions_validation`

## Related Issues

- Epic E034: Employee Contribution Calculation Plan with Deferral Rate Changes
- Story S025-02: Match Event Generation
- Data quality monitoring dashboards
