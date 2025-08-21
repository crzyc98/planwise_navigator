# Story S053-02: Proactive Pre-Auto Enrollment Path

**Epic**: E053 Realistic Voluntary Enrollment Behavior
**Story Points**: 3
**Status**: In Progress
**Priority**: High
**Estimated Time**: 20 minutes

## User Story

**As a** benefits consultant
**I want** employees to voluntarily enroll before auto-enrollment deadlines
**So that** I can model realistic proactive enrollment behavior in auto-enrollment plans

## Business Context

In plans with auto-enrollment, some employees proactively enroll before the auto-enrollment window closes. This is important because:

- **Proactive enrollees** often select higher deferral rates than the auto-enrollment default
- **Early adoption** indicates higher financial engagement
- **Prevents auto-enrollment** for these employees (no duplicate events)
- **Analytics impact**: Distinguishes voluntary vs auto-enrolled populations

Based on the existing issue `2025-08-20_voluntary_pre_ae_enrollment_path.md`, this addresses the gap where "Voluntary" enrollment counts are 0 in auto-enrollment scenarios.

## Acceptance Criteria

### Core Functionality
- [ ] **Pre-AE Window**: 7-35 days after hire date for new hires
- [ ] **Proactive Events**: Generate voluntary enrollment events before auto-enrollment
- [ ] **Registry Deduplication**: Prevent duplicate auto-enrollment for proactive enrollees
- [ ] **Higher Deferral Rates**: Proactive enrollees select above auto-enrollment default

### Technical Requirements
- [ ] **Integration**: Works with existing `int_enrollment_events.sql`
- [ ] **Timing Logic**: Proper event sequencing and date validation
- [ ] **Event Attribution**: `event_category = 'voluntary_enrollment'`
- [ ] **Performance**: Minimal impact on existing enrollment processing

### Business Logic
- [ ] **Eligibility**: Only new hires eligible for auto-enrollment
- [ ] **Probability**: Demographic-based proactive enrollment rates
- [ ] **Deferral Selection**: Higher rates than auto-enrollment default
- [ ] **Window Validation**: Events occur before auto-enrollment deadline

## Technical Design

### Timeline Logic

```
Employee Hire Date: Day 0
├── Day 7-35: Proactive Enrollment Window
├── Day 45: Auto-Enrollment Deadline
└── Result: Proactive enrollees skip auto-enrollment
```

### Configuration Integration

Uses existing `proactive_enrollment` configuration from `simulation_config.yaml`:

```yaml
proactive_enrollment:
  enabled: true
  timing_window:
    min_days: 7   # Earliest proactive enrollment
    max_days: 35  # Latest (10 days before auto-enrollment)
  probability_by_demographics:
    young: 0.15      # 15% of young employees enroll proactively
    mid_career: 0.25 # 25% of mid-career employees
    mature: 0.35     # 35% of mature employees
    senior: 0.45     # 45% of senior employees
```

### Implementation Logic

```sql
-- Enhanced int_enrollment_events.sql logic

-- 1. Identify proactive enrollment candidates
proactive_candidates AS (
  SELECT *
  FROM eligible_new_hires
  WHERE
    auto_enrollment_scope IN ('new_hires_only', 'all_eligible_employees')
    AND proactive_enrollment_enabled = true
    AND is_already_enrolled = false
),

-- 2. Generate proactive enrollment events
proactive_enrollment_events AS (
  SELECT
    employee_id,
    'enrollment' as event_type,
    'voluntary_enrollment' as event_category,  -- Key distinction
    -- Timing: Random day within proactive window
    hire_date + INTERVAL (
      proactive_min_days +
      (HASH(employee_id || 'proactive') % (proactive_max_days - proactive_min_days))
    ) DAY as effective_date,

    -- Higher deferral rates than auto-enrollment default
    CASE age_segment
      WHEN 'young' THEN auto_enrollment_default_rate + 0.01
      WHEN 'mid_career' THEN auto_enrollment_default_rate + 0.02
      WHEN 'mature' THEN auto_enrollment_default_rate + 0.03
      ELSE auto_enrollment_default_rate + 0.04
    END as employee_deferral_rate

  FROM proactive_candidates
  WHERE proactive_random < proactive_probability_by_age
),

-- 3. Update auto-enrollment to exclude proactive enrollees
auto_enrollment_events AS (
  SELECT *
  FROM auto_enrollment_candidates
  WHERE employee_id NOT IN (
    SELECT employee_id FROM proactive_enrollment_events
  )
)
```

## Implementation Tasks

### 1. Enhance Enrollment Events Model (15 minutes)
- [ ] Update `int_enrollment_events.sql` with proactive enrollment logic
- [ ] Add timing window calculations for new hires
- [ ] Implement demographic-based proactive probabilities
- [ ] Ensure registry prevents duplicate auto-enrollment

### 2. Configuration Validation (3 minutes)
- [ ] Verify `proactive_enrollment` config in `simulation_config.yaml`
- [ ] Add missing probability parameters if needed
- [ ] Validate timing window logic

### 3. Testing and Validation (2 minutes)
- [ ] Test proactive enrollment event generation
- [ ] Verify no duplicate enrollments occur
- [ ] Validate event timing and attribution

## Expected Behavior Changes

### Before Implementation
```sql
-- Participation Method Breakdown (Active EOY)
SELECT participation_status_detail, COUNT(*)
FROM fct_workforce_snapshot
WHERE simulation_year = 2025 AND employment_status = 'active'
GROUP BY participation_status_detail;

-- Results:
-- Auto: 4,500
-- Voluntary: 0        <-- Problem: No voluntary enrollments
-- Census: 1,200
-- Not Auto: 2,800
```

### After Implementation
```sql
-- Expected Results:
-- Auto: 3,800        <-- Reduced (proactive enrollees removed)
-- Voluntary: 700     <-- New: Proactive enrollees
-- Census: 1,200
-- Not Auto: 2,800
```

## Integration Points

### Existing Models (Modified)
- **`int_enrollment_events.sql`**: Add proactive enrollment logic
- **`enrollment_registry`**: Unchanged (handles deduplication)

### Configuration Files (Read-Only)
- **`simulation_config.yaml`**: Use existing `proactive_enrollment` section
- **`dbt_project.yml`**: Use existing auto-enrollment variables

### Event Output (Enhanced)
- **`fct_yearly_events`**: Include voluntary enrollment events
- **`fct_workforce_snapshot`**: Show voluntary participation method

## Testing Strategy

### Validation Queries

```sql
-- Test 1: Proactive enrollment timing
SELECT
  employee_id,
  hire_date,
  enrollment_date,
  enrollment_date - hire_date as days_after_hire
FROM proactive_enrollments
WHERE days_after_hire NOT BETWEEN 7 AND 35;  -- Should be empty

-- Test 2: No duplicate enrollments
SELECT employee_id, simulation_year, COUNT(*)
FROM fct_yearly_events
WHERE event_type = 'enrollment'
GROUP BY employee_id, simulation_year
HAVING COUNT(*) > 1;  -- Should be empty

-- Test 3: Event category distribution
SELECT
  event_category,
  COUNT(*) as event_count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as percentage
FROM fct_yearly_events
WHERE event_type = 'enrollment' AND simulation_year = 2025
GROUP BY event_category;
```

### Expected Results
- **Proactive enrollments**: 15-20% of auto-enrollment eligible new hires
- **Timing validation**: All proactive events within 7-35 day window
- **No duplicates**: Zero employees with multiple enrollment events
- **Higher deferral rates**: Proactive > auto-enrollment default rates

## Risk Mitigation

### Technical Risks
- **Timing Conflicts**: Validate proactive window is before auto-enrollment
- **Registry Integration**: Ensure existing deduplication logic works
- **Performance**: Minimize impact on existing enrollment processing

### Business Risks
- **Over-enrollment**: Conservative proactive probability rates
- **Unrealistic Timing**: Use business day adjustments if needed
- **Event Attribution**: Clear distinction between voluntary and auto events

## Success Metrics

### Functional Metrics
- **Voluntary Count > 0**: Non-zero voluntary enrollments in auto-enrollment plans
- **Proper Timing**: All proactive events within configured window
- **Rate Distribution**: Proactive rates higher than auto-enrollment default
- **No Duplicates**: Clean event registry without conflicts

### Performance Metrics
- **Processing Time**: <1 second additional overhead
- **Memory Usage**: Minimal increase for timing calculations
- **Event Volume**: Expected increase in total enrollment events

## Definition of Done

- [ ] Proactive enrollment logic added to `int_enrollment_events.sql`
- [ ] Timing window calculations implemented correctly
- [ ] Registry deduplication verified working
- [ ] Event category attribution implemented
- [ ] Validation queries passing
- [ ] No performance regression
- [ ] Code reviewed and tested

## Follow-up Stories

- **Enhanced Demographics**: More sophisticated proactive probability modeling
- **Business Day Logic**: Skip weekends/holidays for enrollment dates
- **Plan-Specific Rules**: Different proactive behavior by plan type
- **Analytics Dashboard**: Proactive vs auto-enrollment metrics

---

**Created**: 2025-08-21
**Last Updated**: 2025-08-21
**Dependencies**: S053-01 (Voluntary Enrollment Distribution Engine)
**Assignee**: Development Team
