# Story S023-02: Simple Demographic Enrollment

**Epic**: E023 Enrollment Engine
**Story Points**: 5
**Status**: Ready for implementation
**Priority**: High

## User Story

**As a** workforce analyst
**I want** realistic voluntary enrollment rates by demographics
**So that** my projections match actual behavior patterns

## MVP Acceptance Criteria

- ✅ 3-tier demographic segmentation (young/mid-career/senior)
- ✅ Age and salary-based enrollment probabilities
- ✅ SQL-based enrollment timing distribution
- ✅ Integration with eligibility results from E022
- ✅ Enrollment events with proper audit trail

## Technical Implementation

### 1. Core SQL Model

Create `dbt/models/intermediate/int_demographic_enrollment_rates.sql`:

```sql
{{ config(
  materialized='table',
  indexes=[
    {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'},
    {'columns': ['age_segment', 'salary_segment'], 'type': 'btree'}
  ],
  tags=["enrollment_processing", "demographic_analysis"]
) }}

WITH eligible_employees AS (
  SELECT
    e.employee_id,
    e.simulation_year,
    e.plan_id,
    e.eligibility_date,
    e.entry_date
  FROM {{ ref('int_eligibility_determination') }} e
  WHERE e.is_eligible = true
    AND e.simulation_year = {{ var('simulation_year') }}
    -- Exclude employees who are auto-enrolled
    AND NOT EXISTS (
      SELECT 1 FROM {{ ref('int_auto_enrollment_events') }} ae
      WHERE ae.employee_id = e.employee_id
        AND ae.simulation_year = e.simulation_year
        AND ae.enrolled = true
    )
),

employee_demographics AS (
  SELECT
    ee.employee_id,
    ee.simulation_year,
    ee.plan_id,
    ee.eligibility_date,
    ee.entry_date,
    w.current_age,
    w.annual_compensation,
    w.tenure_months,

    -- 3-tier age demographic segmentation
    CASE
      WHEN w.current_age < 35 THEN 'young'
      WHEN w.current_age < 50 THEN 'mid_career'
      ELSE 'senior'
    END AS age_segment,

    -- 3-tier salary demographic segmentation
    CASE
      WHEN w.annual_compensation < 75000 THEN 'low'
      WHEN w.annual_compensation < 150000 THEN 'mid'
      ELSE 'high'
    END AS salary_segment,

    -- Tenure factor for enrollment probability
    LEAST(w.tenure_months / 12.0, 10.0) as tenure_years_capped,

    -- Deterministic random seed for enrollment decision
    (ABS(HASH(ee.employee_id || ee.simulation_year || 'voluntary_enroll')) % 1000000) / 1000000.0 as random_seed

  FROM eligible_employees ee
  INNER JOIN {{ ref('int_baseline_workforce') }} w
    ON ee.employee_id = w.employee_id
    AND ee.simulation_year = w.simulation_year
  WHERE w.employment_status = 'active'
),

demographic_enrollment_probabilities AS (
  SELECT * FROM (VALUES
    -- Age Segment, Salary Segment, Base Enrollment Probability
    ('young', 'low', 0.45),       -- Young, low salary: 45% enrollment
    ('young', 'mid', 0.65),       -- Young, mid salary: 65% enrollment
    ('young', 'high', 0.80),      -- Young, high salary: 80% enrollment
    ('mid_career', 'low', 0.60),  -- Mid-career, low salary: 60% enrollment
    ('mid_career', 'mid', 0.75),  -- Mid-career, mid salary: 75% enrollment
    ('mid_career', 'high', 0.85), -- Mid-career, high salary: 85% enrollment
    ('senior', 'low', 0.55),      -- Senior, low salary: 55% enrollment
    ('senior', 'mid', 0.70),      -- Senior, mid salary: 70% enrollment
    ('senior', 'high', 0.90)      -- Senior, high salary: 90% enrollment
  ) AS t(age_segment, salary_segment, base_enrollment_probability)
),

enrollment_probability_calculation AS (
  SELECT
    ed.*,
    dep.base_enrollment_probability,

    -- Apply tenure factor: +1% per year of service (up to +10%)
    LEAST(
      dep.base_enrollment_probability + (ed.tenure_years_capped * {{ var('tenure_factor_per_year', 0.01) }}),
      0.95  -- Cap at 95% enrollment probability
    ) as adjusted_enrollment_probability

  FROM employee_demographics ed
  INNER JOIN demographic_enrollment_probabilities dep
    ON ed.age_segment = dep.age_segment
    AND ed.salary_segment = dep.salary_segment
),

enrollment_timing_distribution AS (
  SELECT
    epc.*,

    -- Determine if employee enrolls based on probability
    CASE
      WHEN epc.random_seed <= epc.adjusted_enrollment_probability THEN true
      ELSE false
    END AS will_enroll,

    -- Calculate enrollment timing: days after eligibility (0-365 days weighted distribution)
    CASE
      WHEN epc.random_seed <= epc.adjusted_enrollment_probability THEN
        CASE
          -- 20% enroll immediately (within 7 days)
          WHEN (epc.random_seed / epc.adjusted_enrollment_probability) < 0.20
            THEN epc.eligibility_date + INTERVAL (FLOOR((epc.random_seed / epc.adjusted_enrollment_probability) * 7)::INT || ' days')
          -- 40% enroll within first month
          WHEN (epc.random_seed / epc.adjusted_enrollment_probability) < 0.60
            THEN epc.eligibility_date + INTERVAL (FLOOR((epc.random_seed / epc.adjusted_enrollment_probability) * 30)::INT || ' days')
          -- 30% enroll within first quarter
          WHEN (epc.random_seed / epc.adjusted_enrollment_probability) < 0.90
            THEN epc.eligibility_date + INTERVAL (FLOOR((epc.random_seed / epc.adjusted_enrollment_probability) * 90)::INT || ' days')
          -- 10% enroll within first year
          ELSE epc.eligibility_date + INTERVAL (FLOOR((epc.random_seed / epc.adjusted_enrollment_probability) * 365)::INT || ' days')
        END
      ELSE NULL
    END AS projected_enrollment_date

  FROM enrollment_probability_calculation epc
),

final_enrollment_determination AS (
  SELECT
    *,
    -- Default deferral rate for voluntary enrollees (slightly higher than auto-enrollment)
    CASE
      WHEN will_enroll THEN {{ var('voluntary_enrollment_default_rate', 0.08) }}
      ELSE 0.0
    END as voluntary_deferral_rate,

    -- Data quality validation
    CASE
      WHEN will_enroll AND projected_enrollment_date IS NULL THEN 'INVALID_ENROLLMENT_DATE'
      WHEN will_enroll AND projected_enrollment_date < eligibility_date THEN 'ENROLLMENT_BEFORE_ELIGIBILITY'
      WHEN adjusted_enrollment_probability < 0 OR adjusted_enrollment_probability > 1 THEN 'INVALID_PROBABILITY'
      ELSE 'VALID'
    END as data_quality_flag

  FROM enrollment_timing_distribution
)

SELECT
  employee_id,
  simulation_year,
  plan_id,
  eligibility_date,
  entry_date,
  current_age,
  annual_compensation,
  tenure_months,
  age_segment,
  salary_segment,
  base_enrollment_probability,
  adjusted_enrollment_probability,
  will_enroll,
  projected_enrollment_date,
  voluntary_deferral_rate,
  random_seed,
  data_quality_flag,
  current_timestamp as created_at
FROM final_enrollment_determination
ORDER BY employee_id
```

### 2. Voluntary Enrollment Event Generation

Add to `dbt/models/intermediate/int_voluntary_enrollment_events.sql`:

```sql
{{ config(materialized='table') }}

-- Generate ENROLLMENT events for voluntary enrollees
SELECT
  gen_random_uuid() as event_id,
  employee_id,
  'enrollment' as event_type,
  projected_enrollment_date as effective_date,
  simulation_year,
  '{{ var("scenario_id", "default") }}' as scenario_id,
  '{{ var("plan_design_id", "standard") }}' as plan_design_id,
  json_object(
    'event_type', 'enrollment',
    'plan_id', plan_id,
    'enrollment_date', projected_enrollment_date,
    'pre_tax_contribution_rate', voluntary_deferral_rate,
    'roth_contribution_rate', 0.0,
    'after_tax_contribution_rate', 0.0,
    'auto_enrollment', false,
    'enrollment_source', 'voluntary',
    'age_segment', age_segment,
    'salary_segment', salary_segment,
    'tenure_months', tenure_months
  ) as payload,
  current_timestamp as created_at
FROM {{ ref('int_demographic_enrollment_rates') }}
WHERE will_enroll = true
  AND data_quality_flag = 'VALID'
  AND projected_enrollment_date IS NOT NULL
```

### 3. dbt Configuration Variables

Add to `dbt/dbt_project.yml`:

```yaml
vars:
  # Voluntary enrollment configuration
  voluntary_enrollment_default_rate: 0.08  # 8% default rate (higher than auto-enrollment)
  tenure_factor_per_year: 0.01             # +1% enrollment probability per year of tenure

  # Demographic enrollment probabilities (can be overridden for scenarios)
  young_low_enrollment_rate: 0.45          # Young + Low salary base rate
  young_mid_enrollment_rate: 0.65          # Young + Mid salary base rate
  young_high_enrollment_rate: 0.80         # Young + High salary base rate
  mid_career_low_enrollment_rate: 0.60     # Mid-career + Low salary base rate
  mid_career_mid_enrollment_rate: 0.75     # Mid-career + Mid salary base rate
  mid_career_high_enrollment_rate: 0.85    # Mid-career + High salary base rate
  senior_low_enrollment_rate: 0.55         # Senior + Low salary base rate
  senior_mid_enrollment_rate: 0.70         # Senior + Mid salary base rate
  senior_high_enrollment_rate: 0.90        # Senior + High salary base rate

  # Enrollment timing distribution parameters
  immediate_enrollment_pct: 0.20           # 20% enroll within 7 days
  first_month_enrollment_pct: 0.40         # 40% enroll within 30 days
  first_quarter_enrollment_pct: 0.30       # 30% enroll within 90 days
  first_year_enrollment_pct: 0.10          # 10% enroll within 365 days
```

### 4. Data Quality Tests

Add to `dbt/models/intermediate/schema.yml`:

```yaml
models:
  - name: int_demographic_enrollment_rates
    description: "Demographic-based voluntary enrollment modeling with timing distribution"
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - employee_id
            - simulation_year
      - dbt_utils.expression_is_true:
          expression: "adjusted_enrollment_probability BETWEEN 0.0 AND 1.0"
      - dbt_utils.expression_is_true:
          expression: "NOT (will_enroll AND projected_enrollment_date IS NULL)"
      - dbt_utils.expression_is_true:
          expression: "NOT (will_enroll AND projected_enrollment_date < eligibility_date)"
      - dbt_utils.expression_is_true:
          expression: "data_quality_flag = 'VALID'"

    columns:
      - name: employee_id
        description: "Unique employee identifier"
        tests:
          - not_null
      - name: age_segment
        description: "3-tier age demographic segment"
        tests:
          - not_null
          - accepted_values:
              values: ['young', 'mid_career', 'senior']
      - name: salary_segment
        description: "3-tier salary demographic segment"
        tests:
          - not_null
          - accepted_values:
              values: ['low', 'mid', 'high']
      - name: adjusted_enrollment_probability
        description: "Final enrollment probability including tenure adjustment"
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1
      - name: voluntary_deferral_rate
        description: "Deferral rate for voluntary enrollees"
        tests:
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1
```

### 5. Analytics and Reporting Views

Create `dbt/models/marts/reporting/rpt_enrollment_demographics.sql`:

```sql
{{ config(materialized='view') }}

WITH enrollment_summary AS (
  SELECT
    age_segment,
    salary_segment,
    COUNT(*) as total_eligible,
    SUM(CASE WHEN will_enroll THEN 1 ELSE 0 END) as enrolled_count,
    AVG(adjusted_enrollment_probability) as avg_enrollment_probability,
    AVG(CASE WHEN will_enroll THEN voluntary_deferral_rate ELSE 0 END) as avg_deferral_rate,
    AVG(CASE WHEN will_enroll THEN
      DATE_DIFF('day', eligibility_date, projected_enrollment_date)
      ELSE NULL END) as avg_days_to_enroll
  FROM {{ ref('int_demographic_enrollment_rates') }}
  WHERE simulation_year = {{ var('simulation_year') }}
  GROUP BY age_segment, salary_segment
)

SELECT
  age_segment,
  salary_segment,
  total_eligible,
  enrolled_count,
  ROUND(enrolled_count::DECIMAL / total_eligible, 4) as actual_enrollment_rate,
  ROUND(avg_enrollment_probability, 4) as predicted_enrollment_rate,
  ROUND(avg_deferral_rate, 4) as avg_deferral_rate,
  ROUND(avg_days_to_enroll, 1) as avg_days_to_enroll,
  -- Variance analysis
  ROUND(
    ABS(enrolled_count::DECIMAL / total_eligible - avg_enrollment_probability),
    4
  ) as prediction_variance
FROM enrollment_summary
ORDER BY age_segment, salary_segment
```

### 6. Orchestrator Integration

Add to `orchestrator_mvp/steps/enrollment_step.py`:

```python
def process_demographic_enrollment(context: AssetExecutionContext,
                                 duckdb: DuckDBResource,
                                 year_state: Dict[str, Any]) -> pd.DataFrame:
    """
    Process demographic-based voluntary enrollment using SQL/dbt approach.

    Step 5.2 of orchestrator_mvp: Generate voluntary enrollment events by demographics.
    """

    with duckdb.get_connection() as conn:
        # Run demographic enrollment determination model
        conn.execute("CALL dbt_run_model('int_demographic_enrollment_rates')")

        # Generate voluntary enrollment events
        enrollment_events = conn.execute("""
            SELECT * FROM generate_voluntary_enrollment_events(?)
        """, [year_state['simulation_year']]).df()

        # Generate enrollment analytics
        demographics_summary = conn.execute("""
            SELECT * FROM rpt_enrollment_demographics
        """).df()

        # Update year state with demographic enrollment metrics
        year_state['demographic_enrollment_metrics'] = {
            'total_voluntary_eligible': len(enrollment_events),
            'voluntary_enrolled_count': len(enrollment_events[enrollment_events['will_enroll']]),
            'demographic_segments': len(demographics_summary),
            'avg_enrollment_probability': enrollment_events['adjusted_enrollment_probability'].mean(),
            'enrollment_rate_by_segment': demographics_summary.to_dict('records')
        }

        context.log.info(f"Demographic enrollment processed: {year_state['demographic_enrollment_metrics']}")

    return enrollment_events, demographics_summary
```

## Performance Requirements

- **Target**: Process demographic segmentation for 100K employees in <3 seconds
- **Method**: Hash-based partitioning with optimized JOIN operations
- **Memory**: <1.5GB for demographic calculations
- **Scalability**: Support up to 9 demographic segments (3x3 matrix)

## Testing Strategy

### Unit Tests
- Validate demographic segmentation logic (age and salary boundaries)
- Test enrollment probability calculations with tenure adjustments
- Verify enrollment timing distribution calculations

### Integration Tests
- Test integration with E022 eligibility results
- Validate exclusion of auto-enrolled employees
- Performance testing with various demographic distributions

### Data Quality Tests
- Enrollment probability bounds (0.0 - 1.0)
- Enrollment timing validation (>= eligibility date)
- Demographic segment completeness

## Business Logic Validation

### Enrollment Probabilities by Segment
- **Young + Low**: 45% (reflects financial constraints)
- **Young + High**: 80% (high earners more engaged)
- **Mid-Career + Mid**: 75% (balanced approach)
- **Senior + High**: 90% (pre-retirement savings focus)

### Timing Distribution
- **Immediate (0-7 days)**: 20% (highly motivated)
- **First Month (8-30 days)**: 40% (standard decision time)
- **First Quarter (31-90 days)**: 30% (slower decision makers)
- **First Year (91-365 days)**: 10% (procrastinators)

## Dependencies

- **E022**: Eligibility Engine (provides eligible population)
- **S023-01**: Auto-enrollment (excludes auto-enrolled employees)
- **E021**: DC Plan Event Schema (for event generation)
- **orchestrator_mvp**: Pipeline integration framework

## Risks and Mitigation

**Risk**: Demographic probabilities not reflecting actual behavior
**Mitigation**: Calibrate against historical enrollment data by segment

**Risk**: Enrollment timing distribution causing downstream processing issues
**Mitigation**: Cap enrollment dates within simulation year boundaries

**Risk**: Tenure adjustment creating unrealistic probabilities (>100%)
**Mitigation**: Cap adjusted probabilities at 95%

## Definition of Done

- [ ] 3-tier demographic segmentation working correctly
- [ ] Enrollment probabilities calculated with tenure adjustments
- [ ] Timing distribution generating realistic enrollment dates
- [ ] Voluntary enrollment events generated with proper audit trail
- [ ] Data quality tests passing with 100% coverage
- [ ] Integration with E022 eligibility and S023-01 auto-enrollment complete
- [ ] Performance target met (<3 seconds for 100K employees)
- [ ] Reporting dashboard shows enrollment rates by demographic segment
