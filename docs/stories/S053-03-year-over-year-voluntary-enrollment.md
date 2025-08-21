# Story S053-03: Year-Over-Year Voluntary Enrollment

**Epic**: E053 Realistic Voluntary Enrollment Behavior
**Story Points**: 2
**Status**: In Progress
**Priority**: Medium
**Estimated Time**: 20 minutes

## User Story

**As a** benefits consultant
**I want** non-participating employees to voluntarily enroll in subsequent years
**So that** I can model realistic participation growth over multi-year simulations

## Business Context

In real-world 401(k) plans, some employees who didn't initially participate will voluntarily enroll in subsequent years. This behavior is driven by:

- **Financial situation changes**: Salary increases, debt reduction, life events
- **Education and awareness**: Ongoing communication and financial literacy
- **Peer influence**: Seeing colleagues participate and benefit
- **Age progression**: Increasing retirement awareness with age

Industry data shows single-digit annual conversion rates (typically 3-8% of non-participants).

## Acceptance Criteria

### Core Functionality
- [ ] **Non-Participant Identification**: Find active employees not currently enrolled
- [ ] **Conversion Rate**: Single-digit percentage (3-8%) annual voluntary enrollment
- [ ] **Demographic Influence**: Higher conversion rates with age and income progression
- [ ] **Multi-Year Continuity**: Track enrollment state across simulation years

### Technical Requirements
- [ ] **State Tracking**: Use enrollment state accumulator for multi-year consistency
- [ ] **Event Generation**: Create voluntary enrollment events for converters
- [ ] **Attribution**: Clear source tracking for year-over-year conversions
- [ ] **Performance**: Efficient processing for large employee populations

### Business Logic
- [ ] **Eligibility**: Active employees not currently enrolled
- [ ] **Exclusions**: Recent hires (covered by new hire enrollment logic)
- [ ] **Timing**: Mid-year enrollment events to simulate awareness campaigns
- [ ] **Deferral Rates**: Conservative rates for new voluntary enrollees

## Technical Design

### Conversion Rate Matrix

```
Base Conversion Rates by Age:
- young (18-30): 3% annually
- mid_career (31-45): 5% annually
- mature (46-55): 7% annually
- senior (56+): 8% annually

Income Multipliers:
- low_income: 0.8x (financial constraints)
- moderate: 1.0x (baseline)
- high: 1.2x (increased financial capacity)
- executive: 1.3x (financial sophistication)

Tenure Multipliers:
- < 2 years: 0.7x (still adjusting)
- 2-5 years: 1.0x (baseline)
- 5+ years: 1.1x (company loyalty/stability)
```

### Implementation Logic

```sql
-- Enhanced int_enrollment_events.sql logic

-- 1. Identify non-participating employees eligible for conversion
year_over_year_candidates AS (
  SELECT
    w.employee_id,
    w.current_age,
    w.current_tenure,
    w.current_compensation,
    w.level_id,
    -- Exclude recent hires (handled by new hire logic)
    CASE WHEN w.employee_hire_date >= DATE(w.simulation_year || '-01-01')
         THEN false ELSE true END as eligible_for_conversion
  FROM current_workforce w
  LEFT JOIN enrollment_state_accumulator esa
    ON w.employee_id = esa.employee_id
    AND esa.simulation_year = w.simulation_year
  WHERE
    w.employment_status = 'active'
    AND COALESCE(esa.enrollment_status, false) = false  -- Not currently enrolled
),

-- 2. Calculate conversion probabilities
conversion_probability_calculation AS (
  SELECT
    *,
    -- Base rate by age
    CASE
      WHEN current_age < 31 THEN 0.03
      WHEN current_age < 46 THEN 0.05
      WHEN current_age < 56 THEN 0.07
      ELSE 0.08
    END as base_conversion_rate,

    -- Income multiplier
    CASE
      WHEN current_compensation < 50000 THEN 0.8
      WHEN current_compensation < 100000 THEN 1.0
      WHEN current_compensation < 200000 THEN 1.2
      ELSE 1.3
    END as income_multiplier,

    -- Tenure multiplier
    CASE
      WHEN current_tenure < 2 THEN 0.7
      WHEN current_tenure < 5 THEN 1.0
      ELSE 1.1
    END as tenure_multiplier

  FROM year_over_year_candidates
  WHERE eligible_for_conversion = true
),

-- 3. Generate year-over-year voluntary enrollment events
year_over_year_enrollment_events AS (
  SELECT
    employee_id,
    'enrollment' as event_type,
    'year_over_year_voluntary' as event_category,
    -- Mid-year enrollment (simulating education campaigns)
    DATE(simulation_year || '-06-15') as effective_date,

    -- Conservative deferral rates for new voluntary enrollees
    CASE
      WHEN current_age < 31 THEN 0.03  -- 3%
      WHEN current_age < 46 THEN 0.04  -- 4%
      WHEN current_age < 56 THEN 0.05  -- 5%
      ELSE 0.06                        -- 6%
    END as employee_deferral_rate,

    simulation_year,
    current_compensation as compensation_amount

  FROM conversion_probability_calculation
  WHERE
    -- Apply conversion probability with deterministic randomness
    (HASH(employee_id || 'yoy_conversion' || simulation_year) % 1000) / 1000.0
    < (base_conversion_rate * income_multiplier * tenure_multiplier)
)
```

## Implementation Tasks

### 1. Enhance Enrollment Events Model (12 minutes)
- [ ] Add year-over-year conversion logic to `int_enrollment_events.sql`
- [ ] Implement conversion probability matrix
- [ ] Add event generation for converters
- [ ] Ensure proper integration with enrollment state accumulator

### 2. State Tracking Integration (5 minutes)
- [ ] Verify integration with `int_enrollment_state_accumulator`
- [ ] Ensure non-participants are properly identified
- [ ] Validate multi-year state consistency

### 3. Validation and Testing (3 minutes)
- [ ] Test conversion rate calculations
- [ ] Verify event timing and attribution
- [ ] Validate multi-year enrollment continuity

## Configuration Parameters

```yaml
# simulation_config.yaml addition
enrollment:
  year_over_year_conversion:
    enabled: true
    base_rates_by_age:
      young: 0.03      # 3% annual conversion
      mid_career: 0.05 # 5% annual conversion
      mature: 0.07     # 7% annual conversion
      senior: 0.08     # 8% annual conversion
    income_multipliers:
      low_income: 0.8
      moderate: 1.0
      high: 1.2
      executive: 1.3
    tenure_multipliers:
      new_employee: 0.7  # < 2 years
      established: 1.0   # 2-5 years
      veteran: 1.1       # 5+ years
    timing:
      enrollment_month: 6  # Mid-year enrollment events
      enrollment_day: 15
```

## Expected Behavior

### Multi-Year Enrollment Growth
```
Year 1 (2025):
- New Hires: 1,000 enrollments
- Year-over-Year: 0 (baseline year)
- Total New Enrollments: 1,000

Year 2 (2026):
- New Hires: 1,000 enrollments
- Year-over-Year: ~300 conversions (5% of 6,000 non-participants)
- Total New Enrollments: 1,300

Year 3 (2027):
- New Hires: 1,000 enrollments
- Year-over-Year: ~270 conversions (5% of 5,400 remaining non-participants)
- Total New Enrollments: 1,270
```

### Validation Queries

```sql
-- Test 1: Conversion rate validation
SELECT
  simulation_year,
  COUNT(*) as yoy_conversions,
  COUNT(*) * 100.0 / LAG(COUNT(*)) OVER (ORDER BY simulation_year) as growth_rate
FROM fct_yearly_events
WHERE event_category = 'year_over_year_voluntary'
GROUP BY simulation_year
ORDER BY simulation_year;

-- Test 2: Age distribution of converters
SELECT
  age_segment,
  COUNT(*) as conversions,
  ROUND(AVG(employee_deferral_rate), 3) as avg_deferral_rate
FROM year_over_year_enrollment_events
GROUP BY age_segment
ORDER BY age_segment;

-- Test 3: Multi-year enrollment continuity
SELECT
  simulation_year,
  enrollment_status,
  COUNT(*) as employee_count
FROM int_enrollment_state_accumulator
WHERE simulation_year BETWEEN 2025 AND 2027
GROUP BY simulation_year, enrollment_status
ORDER BY simulation_year, enrollment_status;
```

## Risk Mitigation

### Technical Risks
- **State Consistency**: Use enrollment state accumulator for accurate non-participant identification
- **Performance**: Efficient filtering and probability calculations
- **Circular Dependencies**: Clear model lineage and dependencies

### Business Risks
- **Over-conversion**: Conservative conversion rates initially
- **Unrealistic Growth**: Monitor cumulative enrollment rates
- **Double-counting**: Ensure no overlap with new hire enrollment logic

## Success Metrics

### Functional Metrics
- **Conversion Rates**: 3-8% annually for non-participants
- **Age Progression**: Higher conversion rates with age
- **Multi-Year Growth**: Realistic enrollment growth trajectories
- **Event Attribution**: Clear source tracking for analytics

### Performance Metrics
- **Processing Time**: <1 second additional overhead per year
- **Memory Usage**: Efficient for large non-participant populations
- **State Accuracy**: Consistent enrollment tracking across years

## Testing Strategy

### Unit Tests
```sql
-- Test conversion probability calculations
SELECT
  employee_id,
  base_conversion_rate,
  income_multiplier,
  tenure_multiplier,
  base_conversion_rate * income_multiplier * tenure_multiplier as final_probability
FROM conversion_probability_calculation
WHERE final_probability > 1.0;  -- Should be empty

-- Test demographic influences
SELECT
  age_segment,
  AVG(final_probability) as avg_probability
FROM conversion_probability_calculation
GROUP BY age_segment
ORDER BY avg_probability;  -- Should show increasing trend with age
```

### Integration Tests
```sql
-- Test multi-year enrollment state consistency
WITH enrollment_changes AS (
  SELECT
    employee_id,
    simulation_year,
    enrollment_status,
    LAG(enrollment_status) OVER (PARTITION BY employee_id ORDER BY simulation_year) as prev_status
  FROM int_enrollment_state_accumulator
  WHERE simulation_year BETWEEN 2025 AND 2027
)
SELECT COUNT(*) as invalid_transitions
FROM enrollment_changes
WHERE enrollment_status = false AND prev_status = true;  -- Should be 0 (no unenrollments)
```

## Definition of Done

- [ ] Year-over-year conversion logic added to enrollment events model
- [ ] Conversion probability matrix implemented
- [ ] Integration with enrollment state accumulator verified
- [ ] Event generation and attribution working correctly
- [ ] Multi-year state consistency validated
- [ ] Performance benchmarks met
- [ ] Code reviewed and tested

## Future Enhancements

- **Seasonal Patterns**: Enrollment campaigns at specific times
- **Communication Impact**: Model effect of employer education programs
- **Life Event Triggers**: Marriage, birth, salary changes affecting enrollment
- **Plan Feature Impact**: Match changes, vesting modifications driving enrollment

---

**Created**: 2025-08-21
**Last Updated**: 2025-08-21
**Dependencies**: S053-01, S053-02
**Assignee**: Development Team
