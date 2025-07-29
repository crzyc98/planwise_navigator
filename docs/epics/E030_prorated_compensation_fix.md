# Epic E030: Prorated Compensation Double-Counting Fix

**Status**: 🔴 Critical Issue - In Progress
**Priority**: P0 - Data Integrity
**Created**: 2025-07-29
**Epic Owner**: System Architecture
**Estimated Points**: 13 points

## Problem Statement

The `fct_workforce_snapshot` model's prorated annual compensation calculation contains a critical bug that **inflates compensation by 83-126% for employees with multiple compensation events** in the same year (promotion + merit raise).

### Evidence of Issue

**Employee EMP_000003 Example:**
```
2026: promotion (Feb 1) + merit raise (July 15)
Expected prorated compensation: ~67K
Actual calculated: 126K (83% inflation)

2027: promotion (Feb 1) + merit raise (July 15)
Expected prorated compensation: ~86K
Actual calculated: 162K (88% inflation)
```

### Root Cause Analysis

The current `all_compensation_periods` CTE creates **overlapping periods** when multiple events occur:

1. **Promotion event** (Feb 1): Creates period Feb 1 - Dec 31 at promotion salary
2. **Merit raise event** (July 15): Creates period July 15 - Dec 31 at merit salary
3. **Overlap**: July 15 - Dec 31 gets **double-counted** in prorated calculation

This violates the fundamental principle that each day should contribute exactly once to annual compensation.

## Business Impact

- **Analytics Accuracy**: Workforce cost projections are significantly overstated
- **Budget Planning**: Compensation budgets based on inflated figures
- **Compliance Risk**: Inaccurate compensation reporting for audits
- **Decision Making**: Strategic decisions based on incorrect workforce costs

## Technical Solution

### Current Architecture Issue
```sql
-- PROBLEM: These CTEs create overlapping periods
raise_after_periods AS (
    -- Creates: July 15 -> Dec 31 at merit salary
),
promotion_periods AS (
    -- Creates: Feb 1 -> Dec 31 at promotion salary
    -- OVERLAP: July 15 -> Dec 31 counted twice!
)
```

### Proposed Fix: Sequential Event-Based Periods

Replace overlapping period logic with **chronological event sequencing**:

```sql
-- NEW APPROACH: Sequential non-overlapping periods
employee_compensation_timeline AS (
    -- Get all events in chronological order
    SELECT employee_id, event_date, compensation_rate,
           LEAD(event_date) OVER (...) AS next_event_date
    FROM all_employee_events
    ORDER BY employee_id, event_date
),

sequential_periods AS (
    -- Create non-overlapping periods between consecutive events
    SELECT
        employee_id,
        event_date AS period_start,
        COALESCE(next_event_date - 1, year_end) AS period_end,
        compensation_rate
    FROM employee_compensation_timeline
)
```

### Key Design Principles

1. **Non-Overlapping Periods**: Each day contributes exactly once
2. **Chronological Sequencing**: Events applied in proper date order
3. **Event Chain Integrity**: Merit raises use post-promotion compensation
4. **Termination Boundaries**: All periods respect termination dates

## Implementation Plan

### Story S030-01: Compensation Timeline Foundation (5 points)
- Create `employee_compensation_timeline` CTE
- Implement event chronological ordering
- Handle start-of-year baseline compensation

### Story S030-02: Sequential Period Generation (5 points)
- Replace overlapping period CTEs with sequential logic
- Implement proper period boundaries
- Add termination date handling

### Story S030-03: Validation & Testing (3 points)
- Test against EMP_000003 example data
- Run comprehensive dbt test suite
- Validate no regressions in data quality

## Acceptance Criteria

### Primary Success Metrics
- [ ] EMP_000003's 2026 prorated compensation: ~67K (not 126K)
- [ ] EMP_000003's 2027 prorated compensation: ~86K (not 162K)
- [ ] No overlapping compensation periods for any employee
- [ ] All existing dbt tests pass

### Data Quality Gates
- [ ] Zero overlapping periods in compensation calculation
- [ ] Prorated compensation ≤ full_year_equivalent for all employees
- [ ] Sum of period days = actual employment days for each employee
- [ ] Compensation event chain integrity maintained

## Risk Assessment

### High Risk
- **Data Pipeline Disruption**: Changes to core workforce snapshot model
- **Downstream Dependencies**: Multiple models depend on fct_workforce_snapshot

### Mitigation Strategies
- **Comprehensive Testing**: Full dbt test suite before deployment
- **Incremental Rollout**: Test with single simulation year first
- **Rollback Plan**: Git branch allows immediate revert if issues
- **Validation**: Manual spot-checks on known problematic employees

## Files Modified

### Primary Changes
- `dbt/models/marts/fct_workforce_snapshot.sql` (lines 308-393)
  - Replace `all_compensation_periods` CTE logic
  - Implement sequential period generation

### Testing Files
- Existing validation test files will verify fix effectiveness
- `tests/validation/test_compensation_event_chains.sql`

## Dependencies

### Upstream
- Event sequencing logic in `fct_yearly_events` (already correct)
- Event chaining in `int_merit_events` and `int_promotion_events` (already correct)

### Downstream
- All models consuming `fct_workforce_snapshot.prorated_annual_compensation`
- Streamlit dashboards displaying compensation metrics
- Multi-year simulation aggregations

## Definition of Done

- [ ] Sequential compensation periods implemented
- [ ] Zero period overlaps for all employees
- [ ] EMP_000003 example calculations correct
- [ ] All dbt tests passing
- [ ] Code reviewed and documented
- [ ] Performance impact assessed and acceptable

---

**Next Actions**: Implement Story S030-01 with chronological event timeline creation.
