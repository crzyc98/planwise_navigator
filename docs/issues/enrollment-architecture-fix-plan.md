# Enrollment Architecture Fix Plan

**Date:** 2025-01-05
**Issue:** Enrollment events not properly flowing to workforce snapshot enrollment dates
**Priority:** Critical - affects 321+ employees with enrollment data integrity issues

## **Problem Analysis**

### **Root Cause**
The enrollment system has a **fundamental architectural flaw**: to avoid circular dependencies, `int_historical_enrollment_tracker` was intentionally neutered with `WHERE FALSE` and removal of "restrictive WHERE clauses." This broke the entire event-to-state flow.

### **Circular Dependency Issue**
```
fct_yearly_events ← int_enrollment_events ← int_historical_enrollment_tracker ← fct_workforce_snapshot
```

The "fix" was to neuter the tracker, but this made enrollment events write-only (never consumed).

### **Specific Issues Identified**
1. **Event-State Disconnect**: 321 employees have enrollment events in `fct_yearly_events` but no enrollment date in `fct_workforce_snapshot`
2. **Tracker Neutering**: `int_historical_enrollment_tracker` ignores current year events with `WHERE FALSE`
3. **Missing WHERE Clauses**: Business logic was removed to "include all employees" but broke enrollment detection
4. **Temporal Gaps**: Tracker only has data for 2027, missing 2025-2026 data
5. **NH_2026_000787 Case**: Employee has enrollment event on 2027-01-15 but workforce snapshot shows no enrollment date

## **Agent Analysis Summary**

### **Workforce Simulation Specialist Findings**
- Architecture violates event sourcing principles
- Events exist but don't affect state (write-only events)
- Circular dependency was solved incorrectly by neutering components
- Need proper temporal state accumulation approach

### **Data Quality Auditor Findings**
- **9,326 employees** with enrollment dates but no corresponding events
- **321 employees** with enrollment events but no enrollment dates in snapshots
- Massive data integrity failure affecting majority of enrolled employees
- Missing data quality validation framework

### **Cost Modeling Architect Solution**
- Replace circular dependency with temporal state accumulator
- Use Year N → Year N-1 dependencies instead of circular references
- Implement proper event sourcing with incremental state building
- Restore essential WHERE clauses that were incorrectly removed

## **The REAL Fix: Temporal State Accumulator**

Replace the broken circular architecture with proper temporal event sourcing:

### **Phase 1: Create New Architecture (NEW FILE)**
- **Create** `int_enrollment_state_accumulator.sql`
  - Incremental model that builds enrollment state year-by-year
  - Uses only `fct_yearly_events` + previous year's own data (no circular deps)
  - Properly accumulates enrollment history across simulation years

### **Phase 2: Fix Event Generation (MODIFY EXISTING)**
- **Update** `int_enrollment_events.sql`
  - Use state accumulator instead of broken tracker
  - **RESTORE** the "restrictive WHERE clauses" that prevent duplicate enrollments
  - Fix business logic for enrollment eligibility

### **Phase 3: Fix State Application (MODIFY EXISTING)**
- **Update** `fct_workforce_snapshot.sql`
  - Fix enrollment date logic to properly consume enrollment events
  - Ensure events flow from `fct_yearly_events` → workforce snapshot

### **Phase 4: Remove Broken Component (DELETE FILE)**
- **Delete** `int_historical_enrollment_tracker.sql`
  - This model is architecturally broken and should be removed
  - Replace all references with the state accumulator

### **Phase 5: Add Validation (NEW FILE)**
- **Create** enrollment continuity tests
- **Add** event-to-state consistency validation
- **Verify** no duplicate enrollments across years

## **Key Technical Changes**

### **1. Restore WHERE Clauses**
The removed WHERE clauses weren't "restrictive" - they were **essential business logic**:
```sql
-- WRONG (current): Include all employees
WHERE TRUE  -- or removed entirely

-- CORRECT: Include only eligible employees
WHERE (
  was_enrolled_previously = false AND  -- Not already enrolled
  is_eligible_for_enrollment = true AND -- Meets eligibility criteria
  hire_date_cutoff_met = true          -- Meets hire date requirements
)
```

### **2. Fix Circular Dependency**
```sql
-- WRONG (current): Circular dependency
int_enrollment_events → int_historical_enrollment_tracker → fct_workforce_snapshot

-- CORRECT: Temporal accumulation
int_enrollment_state_accumulator[year N] → int_enrollment_state_accumulator[year N-1] + fct_yearly_events[year N]
```

### **3. Ensure Event Consumption**
```sql
-- Current issue: Events exist but don't update state
SELECT employee_id FROM fct_yearly_events WHERE event_type = 'enrollment'  -- 321 records
EXCEPT
SELECT employee_id FROM fct_workforce_snapshot WHERE employee_enrollment_date IS NOT NULL  -- Missing

-- Fix: Proper event-to-state flow in fct_workforce_snapshot
COALESCE(
    enrollment_events.enrollment_date,  -- Current year events (PRIORITY 1)
    state_accumulator.enrollment_date,  -- Historical state (PRIORITY 2)
    NULL
) as employee_enrollment_date
```

## **Implementation Checklist**

### **Files to Change**
- [ ] **NEW:** `dbt/models/intermediate/int_enrollment_state_accumulator.sql`
- [ ] **MODIFY:** `dbt/models/intermediate/events/int_enrollment_events.sql`
- [ ] **MODIFY:** `dbt/models/marts/fct_workforce_snapshot.sql`
- [ ] **DELETE:** `dbt/models/intermediate/int_historical_enrollment_tracker.sql`
- [ ] **NEW:** `dbt/models/analysis/validate_enrollment_architecture.sql`

### **Validation Steps**
1. [ ] Verify NH_2026_000787 shows enrollment_date = '2027-01-15' in workforce snapshot
2. [ ] Confirm 321 employees with enrollment events now have enrollment dates
3. [ ] Test multi-year enrollment continuity (2025-2029)
4. [ ] Validate no duplicate enrollments across years
5. [ ] Run comprehensive data quality checks

## **Expected Outcome**
- **Fix 321 employees** with missing enrollment dates in workforce snapshots
- **Eliminate 9,326 data integrity issues** identified by audit
- **Proper event sourcing** with complete audit trail
- **No duplicate enrollments** across simulation years
- **Robust multi-year enrollment tracking** that maintains state correctly

## **Risk Assessment**
- **Risk Level:** Low
- **Impact:** High (fixes critical data integrity issues)
- **Rollback Plan:** Git revert if issues arise
- **Testing:** Comprehensive validation with known test cases

## **Next Steps**
1. Implement Phase 1: Create temporal state accumulator
2. Test with single employee (NH_2026_000787) first
3. Validate multi-year flow works correctly
4. Roll out to full dataset
5. Add comprehensive monitoring and alerts

---

**Status:** Ready for implementation
**Estimated Effort:** 4-6 hours
**Dependencies:** None (standalone architecture fix)
**Owner:** [To be assigned]
