# Story S053-01: Voluntary Enrollment Distribution Engine

**Epic**: E053 Realistic Voluntary Enrollment Behavior
**Story Points**: 3
**Status**: In Progress
**Priority**: High
**Estimated Time**: 20 minutes

## User Story

**As a** benefits consultant
**I want** realistic voluntary enrollment behavior based on demographics
**So that** I can accurately model participation rates for plans without auto-enrollment

## Business Context

Current enrollment logic primarily handles auto-enrollment scenarios. Plans without auto-enrollment rely entirely on voluntary participation, which follows predictable demographic patterns:

- **Age influence**: Older employees enroll at higher rates (30% young → 80% senior)
- **Income influence**: Higher earners enroll at higher rates
- **Job level influence**: Management levels show higher participation
- **Match optimization**: Employees cluster around match-maximizing rates

## Acceptance Criteria

### Core Functionality
- [ ] **Enrollment Probability Matrix**: Age/job level drives enrollment likelihood
- [ ] **Deferral Rate Selection**: 1%-10% range with demographic clustering
- [ ] **Match Optimization**: Rates cluster around match thresholds (3%, 6%)
- [ ] **Demographic Segmentation**: Young/mid-career/mature/senior categories

### Technical Requirements
- [ ] **Model**: `int_voluntary_enrollment_decision.sql` created
- [ ] **Performance**: <2 seconds execution time
- [ ] **Integration**: Works with existing `int_enrollment_events.sql`
- [ ] **Configuration**: Uses variables for tunable parameters

### Data Quality
- [ ] **Probability Validation**: 0.0-1.0 range enforcement
- [ ] **Rate Validation**: 1%-10% deferral rate boundaries
- [ ] **Null Handling**: Graceful handling of missing demographic data
- [ ] **Deterministic**: Same random seed produces identical results

## Technical Design

### Core Logic Flow

```sql
-- 1. Demographic Segmentation
age_segment: young (18-30), mid_career (31-45), mature (46-55), senior (56+)
income_segment: low (<$50k), moderate ($50k-$100k), high ($100k-$200k), executive (>$200k)
job_level_segment: individual (1-2), senior (3-4), manager (5-6), executive (7+)

-- 2. Enrollment Probability Matrix
enrollment_probability = base_rate_by_age * income_multiplier * job_level_multiplier

Base Rates by Age:
- young: 0.30 (30%)
- mid_career: 0.55 (55%)
- mature: 0.70 (70%)
- senior: 0.80 (80%)

Income Multipliers:
- low: 0.70
- moderate: 1.00
- high: 1.15
- executive: 1.25

Job Level Multipliers:
- individual: 0.90
- senior: 1.00
- manager: 1.10
- executive: 1.20

-- 3. Deferral Rate Selection with Match Optimization
IF match_threshold_exists:
  cluster_around_match_rates = [match_rate * 0.5, match_rate, match_rate * 1.5]
ELSE:
  use_demographic_rates = age_income_matrix
```

### SQL Model Structure

```sql
-- int_voluntary_enrollment_decision.sql
WITH eligible_workforce AS (
  -- Active employees not already enrolled
),
demographic_segmentation AS (
  -- Age, income, job level categorization
),
enrollment_probability_calculation AS (
  -- Matrix calculation for enrollment likelihood
),
deferral_rate_selection AS (
  -- Match optimization + demographic influences
),
enrollment_decisions AS (
  -- Final voluntary enrollment determinations
)
```

## Implementation Tasks

### 1. Create Core Model (10 minutes)
- [ ] Create `dbt/models/intermediate/int_voluntary_enrollment_decision.sql`
- [ ] Implement demographic segmentation logic
- [ ] Add enrollment probability matrix calculation
- [ ] Include deferral rate selection with match optimization

### 2. Configuration Integration (5 minutes)
- [ ] Add voluntary enrollment variables to `dbt_project.yml`
- [ ] Define tunable parameters for probability rates
- [ ] Add match threshold configuration support

### 3. Validation and Testing (5 minutes)
- [ ] Add data quality tests in `schema.yml`
- [ ] Test with sample employee data
- [ ] Validate probability distributions
- [ ] Verify deterministic behavior with fixed seed

## Configuration Parameters

```yaml
# dbt_project.yml variables
vars:
  voluntary_enrollment:
    enabled: true
    base_rates_by_age:
      young: 0.30
      mid_career: 0.55
      mature: 0.70
      senior: 0.80
    income_multipliers:
      low: 0.70
      moderate: 1.00
      high: 1.15
      executive: 1.25
    job_level_multipliers:
      individual: 0.90
      senior: 1.00
      manager: 1.10
      executive: 1.20
    deferral_rates:
      match_optimization: true
      demographic_base_rates:
        young_low: 0.03
        young_high: 0.04
        senior_executive: 0.10
```

## Success Metrics

### Functional Metrics
- **Enrollment Rate Distribution**: Aligns with demographic expectations
- **Deferral Rate Clustering**: Evidence of match optimization behavior
- **Age Progression**: Higher participation with age
- **Income Correlation**: Higher participation with income

### Performance Metrics
- **Execution Time**: <2 seconds per year
- **Memory Usage**: Efficient for 100K+ employees
- **Deterministic Results**: Identical output with same seed

## Testing Strategy

### Unit Tests
```sql
-- Test: Age segmentation accuracy
SELECT age_segment, COUNT(*)
FROM int_voluntary_enrollment_decision
GROUP BY age_segment

-- Test: Probability range validation
SELECT employee_id FROM int_voluntary_enrollment_decision
WHERE enrollment_probability < 0 OR enrollment_probability > 1

-- Test: Deferral rate boundaries
SELECT employee_id FROM int_voluntary_enrollment_decision
WHERE selected_deferral_rate < 0.01 OR selected_deferral_rate > 0.10
```

### Integration Tests
```sql
-- Test: Match optimization clustering
SELECT
  ROUND(selected_deferral_rate, 2) as rate,
  COUNT(*) as employee_count
FROM int_voluntary_enrollment_decision
WHERE will_enroll = true
GROUP BY ROUND(selected_deferral_rate, 2)
ORDER BY rate
```

## Risk Mitigation

### Technical Risks
- **Performance**: Use early filtering and efficient JOINs
- **Memory**: Process in batches if needed for large datasets
- **Dependencies**: Clear model lineage without circular references

### Business Risks
- **Over-enrollment**: Conservative initial probability rates
- **Unrealistic Clustering**: Validate against industry data
- **Edge Cases**: Handle missing demographic data gracefully

## Definition of Done

- [ ] `int_voluntary_enrollment_decision.sql` model created and tested
- [ ] Configuration variables defined and documented
- [ ] Data quality tests passing
- [ ] Performance benchmarks met (<2 seconds)
- [ ] Integration with existing enrollment pipeline verified
- [ ] Code reviewed and documented

## Future Enhancements

- **Advanced Match Optimization**: Multiple match threshold handling
- **Behavioral Economics**: Loss aversion, default bias modeling
- **External Factors**: Market conditions, company performance impact
- **Machine Learning**: Pattern recognition from historical data

---

**Created**: 2025-08-21
**Last Updated**: 2025-08-21
**Next Review**: After implementation
**Assignee**: Development Team
