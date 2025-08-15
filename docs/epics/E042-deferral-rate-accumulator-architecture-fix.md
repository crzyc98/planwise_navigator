# Epic E042: Deferral Rate State Accumulator Architecture Fix

**Status**: 🔴 Critical Priority
**Epic Owner**: Engineering Team
**Business Impact**: High - Affects contribution calculations and escalation accuracy
**Technical Debt**: High - Circular dependencies and wrong source of truth

## Problem Statement

The `int_deferral_rate_state_accumulator` model has fundamental architectural flaws causing incorrect deferral rate tracking for enrolled employees:

### Critical Issue
- **Employee NH_2025_000007** auto-enrolled at 6% in 2025
- **Missing** deferral rate state for 2025
- **Wrong escalation** in 2026 (8%→9% instead of 6%→7%)
- **Root cause**: Using compensation table instead of enrollment events as source of truth

### Architectural Problems
1. **Circular Dependency**: Gets enrollment from `int_employee_compensation_by_year.is_enrolled_flag`
2. **Wrong Source of Truth**: Should use `int_enrollment_events` for actual enrollment rates
3. **Broken Temporal Pattern**: Doesn't properly accumulate state Year N-1 → Year N
4. **Complex Fallbacks**: 150+ lines of demographic hardcoded rates mask core issues

## Real-World Business Flow
1. **Hire** → Employee starts working
2. **Eligibility** → Waiting period passes
3. **Auto-Enrollment Window** → Employee has 3 choices:
   - Opt out (0% deferral)
   - Voluntarily enroll (chosen rate)
   - **Do nothing → Auto-enrolled at default rate (6%)**
4. **Auto-Escalation** → Annual increases by 1% until plan cap

## Epic Stories

### Story S042-01: Fix Source of Truth Architecture [5 points]
**Acceptance Criteria:**
- [ ] Remove dependency on `int_employee_compensation_by_year` for enrollment status
- [ ] Use `int_enrollment_events` as primary source for who enrolled and at what rate
- [ ] Maintain existing output schema for backward compatibility
- [ ] Add data quality test: every enrolled employee has enrollment event OR registry entry

**Implementation Approach:**
```sql
-- Replace current enrolled_employees CTE
enrolled_employees AS (
    SELECT DISTINCT
        employee_id,
        MIN(simulation_year) as enrollment_year,
        MIN(effective_date) as enrollment_date,
        FIRST_VALUE(employee_deferral_rate) OVER (
            PARTITION BY employee_id
            ORDER BY simulation_year, effective_date
        ) as initial_deferral_rate
    FROM {{ ref('int_enrollment_events') }}
    WHERE LOWER(event_type) = 'enrollment'
    GROUP BY employee_id
)
```

### Story S042-02: Implement Proper Temporal Accumulation [8 points]
**Acceptance Criteria:**
- [ ] Implement Year N-1 → Year N state accumulation pattern
- [ ] Follow Epic E023 enrollment architecture pattern successfully used
- [ ] Support multi-year simulation workflow
- [ ] Validate: Employee's Year N rate = Year N-1 rate + Year N escalations

**Implementation Approach:**
```sql
previous_year_state AS (
    SELECT employee_id, current_deferral_rate, escalations_received
    FROM {{ this }}
    WHERE simulation_year = {{ simulation_year - 1 }}
),
current_year_changes AS (
    -- New enrollments this year
    SELECT employee_id, employee_deferral_rate as new_rate, 'enrollment' as change_type
    FROM {{ ref('int_enrollment_events') }}
    WHERE simulation_year = {{ simulation_year }}

    UNION ALL

    -- Escalations this year
    SELECT employee_id, new_deferral_rate as new_rate, 'escalation' as change_type
    FROM {{ ref('int_deferral_rate_escalation_events') }}
    WHERE simulation_year = {{ simulation_year }}
)
```

### Story S042-03: Remove Complex Demographic Fallbacks [3 points]
**Acceptance Criteria:**
- [ ] Remove hardcoded demographic rates (lines 196-213 in current model)
- [ ] Rely on actual enrollment events for all rates
- [ ] Add data quality alerts if enrollment events missing
- [ ] Zero employees should have "demographic fallback" rates

**Technical Debt Cleanup:**
- Remove `employee_deferral_rate_mapping` CTE
- Remove `employee_baseline_rates` CTE
- Simplify final rate calculation to: escalation_rate → enrollment_rate → error

### Story S042-04: Registry Integration & Validation [3 points]
**Acceptance Criteria:**
- [ ] Integrate with existing `enrollment_registry` for consistency checks
- [ ] Add comprehensive data quality validation
- [ ] Test case: NH_2025_000007 shows 6% rate in 2025, 7% in 2026
- [ ] Multi-year regression test suite

**Data Quality Tests:**
```sql
-- Test: No orphaned deferral rates without enrollment
SELECT COUNT(*) FROM int_deferral_rate_state_accumulator drsa
LEFT JOIN int_enrollment_events ee ON drsa.employee_id = ee.employee_id
WHERE ee.employee_id IS NULL
-- Should be 0

-- Test: NH_2025_000007 specific validation
SELECT simulation_year, current_deferral_rate
FROM int_deferral_rate_state_accumulator
WHERE employee_id = 'NH_2025_000007'
-- 2025: 0.0600, 2026: 0.0700
```

## Implementation Strategy

### Phase 1: Parallel Implementation (Low Risk)
- Create `int_deferral_rate_state_accumulator_v2`
- Implement all fixes in parallel model
- Run validation against current results
- Focus on NH_2025_000007 test case

### Phase 2: Validation & Testing (Medium Risk)
- Comprehensive testing with multi-year scenarios
- Validate escalation timing and accuracy
- Performance testing with 100K+ employee dataset
- Stakeholder review of contribution calculation changes

### Phase 3: Cutover (High Risk)
- Update model references to use v2
- Remove old model after validation period
- Update downstream model contracts if needed
- Monitor production metrics

## Success Metrics

### Functional Validation
- [ ] NH_2025_000007 shows correct 6% → 7% escalation path
- [ ] Zero employees with missing deferral rates who have enrollment events
- [ ] Multi-year simulation produces identical results on re-run
- [ ] All downstream contribution calculations remain accurate

### Performance Validation
- [ ] Model execution time < 5 seconds (current SLA)
- [ ] No increase in memory usage
- [ ] Incremental strategy maintains performance

### Architecture Validation
- [ ] No circular dependencies in DAG
- [ ] Proper separation of concerns: events → state → contributions
- [ ] Clear audit trail from enrollment event to final rate

## Risk Assessment

### **High Risk Areas**
- **Downstream Impact**: 12+ models depend on this accumulator
- **Multi-Year Complexity**: State accumulation across years is complex
- **Data Quality**: Wrong rates affect contribution calculations and IRS compliance

### **Mitigation Strategies**
- Parallel implementation with validation period
- Comprehensive regression testing
- Stakeholder sign-off on test results
- Rollback plan if issues detected

## Dependencies

### **Upstream Dependencies**
- `int_enrollment_events` - must be reliable and complete
- `int_deferral_rate_escalation_events` - timing and sequencing critical
- `enrollment_registry` - orchestrator state management

### **Downstream Dependencies**
- `int_employee_contributions` - primary consumer
- `fct_workforce_snapshot` - includes deferral rates
- All contribution and matching calculations

## Timeline

- **Week 1**: Story S042-01 (Source of Truth Fix)
- **Week 2**: Story S042-02 (Temporal Accumulation)
- **Week 3**: Story S042-03 (Remove Fallbacks)
- **Week 4**: Story S042-04 (Validation & Testing)
- **Week 5**: Phase 3 Cutover

## Notes

This epic addresses a **critical architectural debt** that affects the accuracy of the entire deferral rate and contribution calculation system. The fix aligns the model with event sourcing principles and the real-world business process.

**Key Insight**: The model should follow the business flow - enrollment events create the initial state, escalation events modify it over time. Everything else is unnecessary complexity.

---

**Related Epics:**
- Epic E023: Enrollment Architecture Fix (completed - similar pattern)
- Epic E036: Deferral Rate State Accumulator Performance (superseded by this epic)
- Epic E039: Employer Contribution Integration (dependent)
