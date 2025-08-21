# Epic E052: Experienced Termination Contribution Proration Fix

**Status**: 🔴 Critical Issue Identified
**Priority**: High
**Estimated Effort**: 3-5 hours
**Affected Components**: int_employee_contributions.sql, contribution calculations

## Problem Statement

Experienced terminated employees have correctly prorated compensation but incorrectly calculated employee contributions. They are receiving full-year contribution calculations instead of prorated amounts based on their actual employment period.

## Issue Analysis

### Root Cause

The `int_employee_contributions.sql` model processes terminated employees as if they were active for the full year, leading to inflated contribution amounts that don't match their prorated compensation.

### Evidence

**Example: Employee EMP_2024_000312**
- **Termination Date**: March 15, 2025 (worked ~2.5 months)
- **Annual Salary**: $55,500
- **Prorated Compensation**: $11,100 ✅ (correct - 2.5 months)
- **Employee Contributions**: $2,775 ❌ (should be $555 = $11,100 × 5%)
- **Actual Calculation**: $55,500 × 5% = $2,775 (using full year salary!)

### Data Flow Analysis

1. **int_baseline_workforce**: Employees start as 'active'
2. **Termination events**: Generated during the year in `fct_yearly_events`
3. **int_employee_compensation_by_year**: Still shows terminated employees as 'active' (doesn't consider termination events)
4. **int_employee_contributions**:
   - Gets data from `int_employee_compensation_by_year` (lines 81-82)
   - Shows `employment_status='active'` and `contribution_duration_category='full_year'`
   - Calculates contributions on full compensation, not prorated
5. **fct_workforce_snapshot**: Correctly shows terminated status with prorated compensation but inherits wrong contributions

### Impact Assessment

- **425 experienced terminated employees** with positive deferral rates affected
- Contribution calculations are inflated by ~2-10x depending on termination timing
- Data integrity violation between compensation and contribution proration
- Potential compliance and audit issues for DC plan administration

## Technical Solution

### Files to Modify

1. **`dbt/models/intermediate/events/int_employee_contributions.sql`**

### Proposed Changes

#### 1. Enhanced Termination Awareness in snapshot_proration CTE (lines 70-83)

```sql
-- Current problematic code:
snapshot_proration AS (
    SELECT
        employee_id,
        {{ simulation_year }} AS simulation_year,
        employee_compensation AS current_compensation,
        employee_compensation AS prorated_annual_compensation, -- ❌ Not prorated for terminated
        employment_status, -- ❌ Still shows 'active'
        NULL::DATE AS termination_date,
        -- ... other fields
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
),

-- Proposed fix:
snapshot_proration AS (
    SELECT
        ecy.employee_id,
        {{ simulation_year }} AS simulation_year,
        ecy.employee_compensation AS current_compensation,
        -- ✅ Apply proration for terminated employees
        CASE
            WHEN term.termination_date IS NOT NULL THEN
                ROUND(
                    ecy.employee_compensation *
                    DATEDIFF('day', '{{ simulation_year }}-01-01'::DATE, term.termination_date) / 365.0
                , 2)
            ELSE ecy.employee_compensation
        END AS prorated_annual_compensation,
        -- ✅ Update employment status based on termination events
        CASE
            WHEN term.termination_date IS NOT NULL THEN 'terminated'
            ELSE ecy.employment_status
        END AS employment_status,
        term.termination_date,
        -- ... other fields
    FROM {{ ref('int_employee_compensation_by_year') }} ecy
    LEFT JOIN (
        SELECT
            employee_id,
            effective_date::DATE AS termination_date
        FROM {{ ref('fct_yearly_events') }}
        WHERE simulation_year = {{ simulation_year }}
          AND event_type = 'termination'
    ) term ON ecy.employee_id = term.employee_id
    WHERE ecy.simulation_year = (SELECT current_year FROM simulation_parameters)
),
```

#### 2. Fix Contribution Duration Category Logic (lines 147-188)

```sql
-- Update contribution duration category logic:
CASE
    WHEN wf.termination_date IS NOT NULL THEN 'partial_year'
    ELSE 'full_year'
END AS contribution_duration_category,
```

#### 3. Ensure Correct Base Compensation Usage

```sql
-- Use prorated compensation for contribution calculations:
wf.prorated_annual_compensation * COALESCE(dr.deferral_rate, 0.0) AS requested_contribution_amount,
```

### Testing Strategy

1. **Unit Test**: Verify specific terminated employees get correct prorated contributions
2. **Regression Test**: Ensure active employees still get full-year contributions
3. **Integration Test**: Validate consistency between `fct_workforce_snapshot` and `int_employee_contributions`

### Expected Results

**Before Fix (Employee EMP_2024_000312)**:
- Prorated Compensation: $11,100
- Employee Contributions: $2,775 (5% of $55,500 full year)
- Status: active, full_year

**After Fix**:
- Prorated Compensation: $11,100
- Employee Contributions: $555 (5% of $11,100 prorated)
- Status: terminated, partial_year

## Implementation Plan

### Phase 1: Core Fix (2-3 hours)
1. Modify `int_employee_contributions.sql` snapshot_proration CTE
2. Add termination event awareness
3. Fix contribution duration logic

### Phase 2: Testing & Validation (1-2 hours)
1. Test with known terminated employees
2. Verify contribution amounts match prorated compensation
3. Run full simulation to ensure no regressions

### Phase 3: Documentation & Cleanup (30 minutes)
1. Update model documentation
2. Add inline comments explaining termination handling
3. Update any related documentation

## Acceptance Criteria

- [ ] Experienced terminated employees have contributions calculated on prorated compensation
- [ ] Active employees continue to have full-year contributions
- [ ] `employment_status` correctly reflects termination events
- [ ] `contribution_duration_category` shows 'partial_year' for terminated employees
- [ ] All existing tests pass
- [ ] Data consistency between compensation and contribution proration models

## Risks & Mitigation

**Risk**: Breaking active employee contribution calculations
**Mitigation**: Extensive testing with both active and terminated employee samples

**Risk**: Performance impact from additional joins
**Mitigation**: Termination events table is relatively small, minimal impact expected

## Success Metrics

- 425 terminated employees with corrected contribution amounts
- Zero data integrity violations between compensation and contribution proration
- Consistent employment status across models
- Maintained performance of contribution calculations

## Related Issues

- Links to potential audit trail requirements for contribution changes
- May inform future enhancements to real-time termination processing
