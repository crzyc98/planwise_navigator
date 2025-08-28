# Epic E066: Late Prior-Year Hire Compensation Annualization Fix

**Status**: 🔄 In Progress
**Priority**: High
**Epic Type**: Bug Fix
**GitHub Issue**: #48

## Problem Statement

Employees hired late in the prior year (e.g., December 2024) are not having their compensation properly annualized for the first simulation year. This causes significant undervaluation of their compensation and cascading errors in all downstream calculations.

### Impact Analysis

**Data Integrity Issues:**
- Late prior-year hires show partial-year earnings as their full salary
- Employer core contributions calculated on incorrect (partial) compensation
- Wrong job level assignments due to understated compensation
- All downstream calculations (merit, promotions, etc.) use incorrect baseline

**Example Case:**
- Employee `EMP_2024_003851` hired on `2024-12-25` (7 days before year-end)
- Census shows `$55,900` in `employee_gross_compensation` (7 days of actual earnings)
- `stg_census_data` correctly calculates `$2,914,785` as `employee_annualized_compensation`
- **BUT** `int_baseline_workforce` ignores the annualized value and uses the raw `$55,900`

### Root Cause Analysis

**Location**: `dbt/models/intermediate/int_baseline_workforce.sql` line 25

**Current Logic**:
```sql
COALESCE(stg.employee_gross_compensation, stg.employee_annualized_compensation) AS current_compensation,
```

**Problem**: This preferentially uses `gross` (partial year) over `annualized` (full year equivalent).

**Comment Context** (lines 23-24):
```sql
-- Use gross compensation to avoid inflation from short-term employees
-- Note: Annualized compensation can be 365x inflated for employees hired near year-end
```

This comment reveals the original intent was to avoid "inflation" from annualization, but this approach creates the opposite problem - deflation for legitimate late hires.

## Solution Architecture

### Primary Fix

**Approach**: Switch preference order to use annualized compensation for simulation purposes.

**Updated Logic**:
```sql
-- For simulation purposes, use annualized compensation to represent full-year equivalent
-- This ensures late prior-year hires have correct compensation for the simulation year
COALESCE(stg.employee_annualized_compensation, stg.employee_gross_compensation) AS current_compensation,
```

**Rationale**:
- For simulation purposes, we want full-year equivalent compensation
- `employee_annualized_compensation` represents what the employee would earn working a full year
- This is the correct baseline for all workforce modeling calculations

### Secondary Fixes

**Level Matching Logic** (lines 76-77):
```sql
ON COALESCE(stg_inner.employee_annualized_compensation, stg_inner.employee_gross_compensation) >= levels.min_compensation
AND (COALESCE(stg_inner.employee_annualized_compensation, stg_inner.employee_gross_compensation) < levels.max_compensation OR levels.max_compensation IS NULL)
```

### Bounds Checking (Optional Enhancement)

**Problem**: Annualization can produce extreme values (e.g., $2.9M for 7-day employees)

**Potential Solutions**:
1. Cap annualized values at industry maximums (e.g., $1M)
2. Use alternative logic for very late hires (assume gross IS annual for Dec hires)
3. Add reasonableness validation in `stg_census_data.sql`

## Implementation Plan

### Phase 1: Core Fix
- [x] Create GitHub issue #48
- [x] Create feature branch `feature/E066-compensation-annualization-fix`
- [x] Update epic documentation
- [ ] Modify `int_baseline_workforce.sql` to prefer annualized compensation
- [ ] Test with example employee `EMP_2024_003851`
- [ ] Validate downstream impact on core contributions

### Phase 2: Validation & Testing
- [ ] Create validation query to compare before/after compensation values
- [ ] Test with multiple late-year hire cases
- [ ] Validate employer core contribution calculations
- [ ] Ensure job level assignments are correct
- [ ] Run full simulation to check for cascading effects

### Phase 3: Documentation & Cleanup
- [ ] Update model documentation
- [ ] Add data quality tests for compensation bounds
- [ ] Update CLAUDE.md with compensation handling guidance
- [ ] Create pull request

## Files Modified

### Primary Files
- `dbt/models/intermediate/int_baseline_workforce.sql` - Switch to prefer annualized compensation

### Testing Files
- New validation queries to verify fix effectiveness

### Documentation Files
- `docs/epics/E066_compensation_annualization_fix.md` (this file)
- Update relevant model documentation

## Acceptance Criteria

- [ ] Employee `EMP_2024_003851` shows annualized compensation ($2,914,785) as baseline
- [ ] All late prior-year hires use annualized compensation for simulation baseline
- [ ] Employer core contributions calculate correctly using annualized values
- [ ] Job level assignments use full-year equivalent compensation
- [ ] All downstream calculations (merit, promotions, etc.) use correct compensation base
- [ ] No regression in compensation handling for other employee types
- [ ] Data quality tests pass for compensation bounds

## Risk Assessment

**Low Risk**: This is a straightforward preference order change that aligns with existing system design.

**Mitigation Strategies**:
- Comprehensive testing with multiple employee scenarios
- Validation queries to compare before/after values
- Bounds checking to prevent extreme annualization values

## Dependencies

**Upstream**:
- `stg_census_data.sql` - Provides both gross and annualized compensation
- Census data quality and annualization logic

**Downstream**:
- `int_employee_compensation_by_year.sql` - Uses baseline compensation
- `int_employer_core_contributions.sql` - Calculates contributions based on compensation
- All event generation models that reference employee compensation

## Success Metrics

- Late prior-year hires show realistic compensation values for simulation
- Employer contribution calculations align with expected amounts
- Job level assignments become accurate for affected employees
- No downstream calculation errors or anomalies

## Implementation Notes

**Database**: Changes affect DuckDB models only, no schema changes required.

**Backward Compatibility**: This change improves data accuracy without breaking existing interfaces.

**Performance**: No performance impact expected - same underlying data access patterns.

---

**Created**: 2025-01-28
**Last Updated**: 2025-01-28
**Assignee**: Claude Code
**Reviewer**: TBD
