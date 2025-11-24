# Epic E065: Fix New Hire Core Contribution Proration Bug

**Epic ID**: E065
**Status**: 🔧 In Progress
**Priority**: High
**Epic Type**: Critical Bug Fix
**Created**: 2025-01-15
**Assignee**: Claude Code
**Estimated Effort**: 5 story points
**GitHub Issue**: [#45](https://github.com/crzyc98/planalign_engine/issues/45)

## Problem Statement

New hires are receiving employer core contributions calculated on their full annual compensation instead of prorated compensation based on actual hours worked. This represents a critical violation of the 1000-hour minimum requirement and results in approximately 2x the intended core contribution amounts.

### Current Impact
- **Financial Impact**: ~$400,000+ annually in excess employer contributions
- **Affected Employees**: 392 new hires in 2025 (44.9% of all new hires)
- **Configuration Violation**: Defeats the purpose of the 1000-hour minimum requirement
- **Multi-Year Issue**: Problem persists across all simulation years

### Evidence from Data Analysis
```sql
-- Example: July hire NH_2025_000554
-- Full compensation: $86,832.90
-- Prorated compensation: $41,870.11 (for ~5 months employment)
-- Core contribution received: $868.33 (1% of FULL compensation)
-- Core contribution should be: $418.70 (1% of PRORATED compensation)
-- Over-contribution: $449.63 (107% excess)
```

### Behavioral Impact Analysis

| Hire Month | Hours Worked | Should Qualify | Current Behavior | Expected Behavior |
|------------|--------------|----------------|------------------|-------------------|
| January | ~1990 | ✅ Yes | ✅ Gets core (correct) | ✅ Gets core |
| July | ~1000 | ✅ Barely | ❌ Gets 2x core | ✅ Gets 1x core |
| August | ~800 | ❌ No | ❌ Gets 2x core | ❌ Gets $0 |
| December | ~95 | ❌ No | ❌ Gets 21x core | ❌ Gets $0 |

## Root Cause Analysis

### Technical Root Cause
**Location**: `dbt/models/intermediate/int_employer_core_contributions.sql`, lines 133-157

The `workforce_proration` CTE has a critical logic error:

1. **Line 139**: All employees (including new hires) get `employee_compensation AS prorated_annual_compensation` (no proration applied)
2. **Lines 155-156**: The `WHERE employee_id NOT IN` clause excludes properly prorated new hire entries from `new_hire_proration`
3. **Result**: New hires use their full annual compensation instead of prorated compensation for core contribution calculations

### Code Analysis
```sql
-- PROBLEMATIC CODE (lines 133-157)
workforce_proration AS (
    -- Snapshot population for existing employees
    SELECT
        employee_id,
        simulation_year,
        employee_compensation AS current_compensation,
        employee_compensation AS prorated_annual_compensation, -- ❌ NO PRORATION!
        employment_status,
        NULL::DATE AS termination_date
    FROM employee_compensation

    UNION ALL

    -- Current-year new hires with independent proration
    SELECT
        employee_id,
        simulation_year,
        current_compensation,
        prorated_annual_compensation, -- ✅ PROPERLY PRORATED
        employment_status,
        termination_date
    FROM new_hire_proration
    WHERE employee_id NOT IN (
        SELECT employee_id FROM employee_compensation -- ❌ EXCLUDES ALL NEW HIRES!
    )
)
```

### Data Flow Issue
1. New hires appear in `int_employee_compensation_by_year` (875 employees in 2025)
2. They get included in `employee_compensation` CTE with full compensation
3. The `workforce_proration` CTE uses full compensation (line 139) instead of prorated
4. The properly prorated `new_hire_proration` entries are excluded (lines 155-156)
5. Core contribution calculation uses full compensation via COALESCE fallback

## Configuration Context

From `config/simulation_config.yaml`:
```yaml
employer_core_contribution:
  enabled: true
  contribution_rate: 0.01  # 1% core contribution rate
  eligibility:
    minimum_tenure_years: 0
    require_active_at_year_end: true
    minimum_hours_annual: 1000     # 1000-hour requirement
    allow_new_hires: true
    allow_terminated_new_hires: false
```

The intent is clear: new hires should only receive core contributions if they work ≥1000 hours, and the contribution should be 1% of their **prorated** compensation.

## Proposed Solution

### Fix Strategy: Properly Handle New Hire Proration

**Objective**: Ensure new hires use prorated compensation for core contribution calculations while maintaining existing employee logic.

### Implementation Approach

1. **Modify `workforce_proration` CTE** to distinguish between existing employees and new hires
2. **Use prorated compensation** for new hires from `new_hire_proration`
3. **Maintain existing logic** for continuous employees
4. **Add data quality validation** to prevent regression

### Detailed Fix

```sql
-- PROPOSED FIX
workforce_proration AS (
    -- Existing employees (NOT hired this year) - use full compensation
    SELECT
        employee_id,
        simulation_year,
        employee_compensation AS current_compensation,
        employee_compensation AS prorated_annual_compensation,
        employment_status,
        NULL::DATE AS termination_date
    FROM employee_compensation
    WHERE employee_id NOT IN (
        -- Exclude current-year new hires to avoid duplication
        SELECT employee_id FROM hire_events
    )

    UNION ALL

    -- Current-year new hires - use properly prorated compensation
    SELECT
        employee_id,
        simulation_year,
        current_compensation,
        prorated_annual_compensation,  -- ✅ PROPERLY PRORATED
        employment_status,
        termination_date
    FROM new_hire_proration
)
```

## Stories Breakdown

### Story S065-01: Fix Workforce Proration Logic (3 points)
**Status**: Pending
**Acceptance Criteria**:
- Modify `workforce_proration` CTE to exclude new hires from full compensation path
- Ensure new hires use prorated compensation from `new_hire_proration`
- Verify no regression in existing employee calculations
- All dbt models compile successfully

### Story S065-02: Add Data Quality Validation (1 point)
**Status**: Pending
**Acceptance Criteria**:
- Create `dq_new_hire_core_proration_validation.sql` model
- Validate that new hire core contributions are ~1% of prorated compensation
- Add automated tests to prevent regression
- Include validation in CI/CD pipeline

### Story S065-03: Multi-Year Regression Testing (1 point)
**Status**: Pending
**Acceptance Criteria**:
- Test fix across all simulation years (2025-2027)
- Verify July/August hire behavior is correct
- Confirm financial impact reduction
- Document expected vs actual results

## Expected Impact

### Financial Impact
- **Annual Savings**: ~$400,000 reduction in excess core contributions
- **Per Employee**: $400-500 reduction for mid-year hires
- **July Hires**: ~50% reduction in core contribution amounts
- **August-December Hires**: Core contributions reduced to $0 (correct)

### Data Quality Improvements
- **Compliance**: Core contributions align with prorated compensation
- **Hours Requirement**: 1000-hour minimum properly enforced
- **Configuration Integrity**: `minimum_hours_annual: 1000` works as intended

## Validation Criteria

### Success Metrics
1. **Proration Accuracy**: New hire core = 1% of prorated compensation
2. **Hour Enforcement**: Employees with <1000 hours get $0 core
3. **Financial Alignment**: July hires receive ~50% of current core amounts
4. **No Regression**: Existing employees maintain current behavior

### Validation Queries
```sql
-- Verify proper proration for new hires
SELECT
    employee_id,
    employee_hire_date,
    prorated_annual_compensation,
    employer_core_amount,
    ROUND(employer_core_amount / prorated_annual_compensation, 4) as core_rate
FROM fct_workforce_snapshot
WHERE simulation_year = 2025
  AND employee_hire_date >= '2025-01-01'
  AND employer_core_amount > 0
  AND ABS(employer_core_amount / prorated_annual_compensation - 0.01) > 0.001;
-- Should return 0 rows after fix

-- Verify <1000 hour employees get $0 core
SELECT COUNT(*) as violations
FROM fct_workforce_snapshot
WHERE simulation_year = 2025
  AND annual_hours_worked < 1000
  AND employer_core_amount > 0;
-- Should return 0 after fix
```

## Dependencies

### Prerequisites
- Understanding of dbt model dependencies
- Access to simulation configuration
- Multi-year test data availability

### Models Affected
- `int_employer_core_contributions.sql` (primary fix)
- `fct_workforce_snapshot.sql` (inherits fix)
- New: `dq_new_hire_core_proration_validation.sql`

## Risks and Mitigation

### Technical Risks
- **Risk**: Breaking existing employee calculations
- **Mitigation**: Comprehensive testing on existing employees before deployment

- **Risk**: Performance impact from CTE changes
- **Mitigation**: Monitor query execution times; optimize if needed

### Business Risks
- **Risk**: Delayed fix increases financial impact
- **Mitigation**: Prioritize as high-priority fix; implement in next release cycle

## Implementation Plan

### Phase 1: Code Fix (2-3 days)
1. Update `workforce_proration` CTE logic
2. Add comprehensive inline comments
3. Test compilation across all years
4. Create data quality validation model

### Phase 2: Testing (1-2 days)
1. Run multi-year regression tests
2. Validate financial impact calculations
3. Verify no impact on existing employees
4. Document test results

### Phase 3: Deployment (1 day)
1. Create pull request with comprehensive description
2. Code review with emphasis on data quality
3. Deploy to production environment
4. Monitor validation model results

## Acceptance Criteria

### Functional Requirements
- New hires receive core contributions based on prorated compensation
- Employees with <1000 hours receive $0 core contributions
- July hires receive approximately 50% of current core amounts
- August-December hires receive $0 core contributions
- Existing employees maintain identical behavior

### Technical Requirements
- All dbt models compile without errors
- Data quality validation model passes
- Performance impact <5% increase in execution time
- Comprehensive test coverage for new logic

### Business Requirements
- ~$400,000 annual cost reduction in employer contributions
- Full compliance with 1000-hour minimum requirement
- Configuration settings work as documented and intended

## Epic Success Criteria

1. ✅ **Proration Accuracy**: All new hires receive core based on prorated compensation
2. ✅ **Hours Compliance**: Zero employees with <1000 hours receiving core
3. ✅ **Financial Impact**: ~$400K annual savings in excess contributions
4. ✅ **Data Quality**: Validation model shows 100% compliance
5. ✅ **No Regression**: Existing employees maintain exact same core amounts

## Implementation Notes

### Key Technical Considerations
- New hire detection must be consistent across all CTEs
- Proration logic must align with hours worked calculations
- COALESCE fallback order is critical for correct behavior
- Multi-year testing required due to cumulative effects

### Monitoring and Observability
- Data quality validation model for ongoing monitoring
- Financial impact tracking for cost benefit analysis
- Performance monitoring for query execution times
- Automated alerts for validation failures

**Epic Priority**: **HIGH** - Financial impact and configuration compliance issue affecting hundreds of employees and significant employer contribution amounts.

---

**Related Issues**:
- GitHub Issue #45: https://github.com/crzyc98/planalign_engine/issues/45
- Related: E061 (New Hire Termination Match Fix) - Similar eligibility enforcement patterns

**Epic Status**: 🔧 **Ready for Implementation** - Root cause identified, solution designed, comprehensive testing plan prepared.
