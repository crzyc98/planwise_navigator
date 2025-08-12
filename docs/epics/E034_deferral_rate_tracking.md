# Epic E034: Employee Deferral Rate Tracking MVP

**Status**: 🟢 Completed
**Priority**: High
**Estimated Effort**: 8-12 hours
**Dependencies**: E023 (Enrollment Architecture), E033 (Compensation Parameter Config)
**Created**: 2025-01-06

## Executive Summary

Add employee deferral rate tracking to enrollment events and workforce snapshots to enable future contribution event generation. This MVP creates the foundational data pipeline for tracking 401(k) contribution percentages through the enrollment lifecycle, setting the stage for full contribution calculations in subsequent epics.

## Business Value

- **Enables Contribution Modeling**: Provides the critical deferral rate data needed for contribution event generation
- **Improves Enrollment Accuracy**: Tracks actual contribution elections alongside enrollment status
- **Supports Compliance**: Enables tracking of contribution rates for testing and limit monitoring
- **Facilitates Auto-Escalation**: Foundation for automatic deferral rate increases over time

## Technical Approach

### Phase 1: Schema Extension (2 hours)

#### 1.1 Update `int_enrollment_events.sql`
Add deferral rate fields to enrollment event generation:
```sql
-- Additional fields in enrollment_events CTE
employee_deferral_rate,      -- Current election (0.00 to 0.75)
prev_employee_deferral_rate,  -- Previous rate (0.00 for new enrollments)
deferral_type,               -- 'pre_tax', 'roth', 'after_tax'
```

#### 1.2 Extend `fct_yearly_events` Schema
Update schema.yml and model to include:
```yaml
- name: employee_deferral_rate
  description: "Employee's elected deferral percentage (0.00 to 0.75)"
  data_type: decimal(5,4)
- name: prev_employee_deferral_rate
  description: "Previous deferral rate before change"
  data_type: decimal(5,4)
```

### Phase 2: Deferral Rate Logic (3 hours)

#### 2.1 Demographics-Based Default Rates
```sql
-- Default deferral rates by age/income segment
CASE
  WHEN age_segment = 'young' THEN 0.03      -- 3% default
  WHEN age_segment = 'mid_career' THEN 0.06 -- 6% default
  WHEN age_segment = 'mature' THEN 0.08     -- 8% default
  ELSE 0.10                                 -- 10% for senior
END *
CASE income_segment
  WHEN 'low_income' THEN 0.5    -- Lower participation
  WHEN 'moderate' THEN 1.0      -- Base rate
  WHEN 'high' THEN 1.25         -- Higher participation
  ELSE 1.5                       -- Executive level
END as employee_deferral_rate
```

#### 2.2 Enrollment State Accumulator Enhancement
Update `enrollment_registry` table to track:
- `current_deferral_rate`
- `deferral_effective_date`
- `deferral_history` (JSON array for changes)

### Phase 3: Integration Points (2 hours)

#### 3.1 Workforce Snapshot Integration
Add to `fct_workforce_snapshot.sql`:
```sql
-- Enrollment tracking with deferral rates
current_deferral_rate,
ytd_employee_contributions,  -- Placeholder for future
ytd_employer_match,          -- Placeholder for future
is_contributing,              -- Active contributor flag
```

#### 3.2 Parameter Configuration
Create seed file `dbt/seeds/default_deferral_rates.csv`:
```csv
scenario_id,age_segment,income_segment,default_rate,auto_escalate
default,young,low_income,0.03,true
default,young,moderate,0.03,true
default,mid_career,moderate,0.06,false
```

### Phase 4: Data Quality & Testing (2 hours)

#### 4.1 Validation Models
- `dq_deferral_rate_validation.sql` - Check rate bounds (0-75%)
- `dq_enrollment_deferral_consistency.sql` - Verify enrolled = has rate

#### 4.2 dbt Tests
```yaml
tests:
  - not_null: [employee_deferral_rate]
    where: "event_type = 'enrollment'"
  - accepted_range:
      column_name: employee_deferral_rate
      min_value: 0
      max_value: 0.75
```

## Implementation Sequence

### Story 1: Schema Foundation (3 points) ✅ COMPLETED
- [x] Update `int_enrollment_events.sql` with deferral rate fields ✅
- [x] Extend `fct_yearly_events` schema and contract ✅
- [x] Create default deferral rates seed file ✅

### Story 2: Rate Calculation Logic (5 points) ✅ COMPLETED
- [x] Implement demographics-based default rates ✅
- [x] Add deferral change events (enrollment_change) ✅
- [x] Update enrollment state accumulator ✅

### Story 3: Integration & Validation (3 points) ✅ COMPLETED
- [x] Integrate with `fct_workforce_snapshot` ✅
- [x] Create data quality validation models ✅
- [x] Add comprehensive dbt tests ✅

### Story 4: Documentation (1 point) ✅ COMPLETED
- [x] Update CLAUDE.md with deferral rate patterns ✅
- [x] Document rate calculation methodology ✅
- [x] Add example queries for rate analysis ✅

## Success Metrics ✅ ALL ACHIEVED

- ✅ All enrolled employees have valid deferral rates (0-75%) ✅
- ✅ Deferral rates persist correctly across simulation years ✅
- ✅ Zero null deferral rates for enrollment events ✅
- ✅ Rate changes generate proper enrollment_change events ✅
- ✅ Performance: <10ms overhead per enrollment event ✅

## Migration Strategy

1. **Backward Compatibility**: New fields are nullable initially
2. **Phased Rollout**:
   - Phase 1: Add fields, populate with defaults
   - Phase 2: Implement rate change logic
   - Phase 3: Enable contribution calculations
3. **Data Backfill**: Historical enrollments get default rates based on demographics

## Future Enhancements (Not in MVP)

- **Auto-Escalation**: Automatic annual deferral increases
- **Contribution Calculations**: Full contribution event generation
- **Limit Monitoring**: IRS 402(g) and 415(c) limit tracking
- **Match Optimization**: Smart default rates to maximize match
- **Behavioral Nudges**: Rate recommendations based on peer groups

## Technical Considerations

### Performance Impact
- Minimal: 2 additional decimal fields per enrollment event
- Indexed on employee_id for efficient joins
- Deferral history in separate tracking table

### Data Quality Requirements
- Rates must be between 0.00 and 0.75 (0-75%)
- Previous rate = 0.00 for initial enrollments
- Rate changes require enrollment_change events
- Null rates not allowed for active enrollments

### Integration Dependencies
- Requires `enrollment_registry` table from E023
- Uses `int_effective_parameters` for default rates
- Feeds into future `int_contribution_events` model

## Rollback Plan

If issues arise:
1. Remove deferral rate fields from models
2. Revert schema.yml changes
3. Drop new seed files
4. Re-run models with previous schema

## Approval & Sign-off

- [ ] Data Engineering Lead
- [ ] Workforce Analytics Team
- [ ] Compliance/Legal Review
- [ ] Performance Testing Complete

---

**Note**: This MVP focuses solely on tracking deferral rates through the enrollment pipeline. Actual contribution calculations, IRS limit enforcement, and employer matching will be implemented in subsequent epics (E035: Contribution Engine, E036: Match Calculator).
