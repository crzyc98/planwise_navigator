# Story S023-01: Basic Auto-Enrollment Logic

**Epic**: E023 Enrollment Engine
**Story Points**: 6
**Status**: Ready for implementation
**Priority**: High

## User Story

**As a** plan sponsor
**I want** to model basic auto-enrollment impact
**So that** I can predict participation rates and costs

## MVP Acceptance Criteria

- ✅ SQL-based auto-enrollment processing for 100K employees in <10 seconds
- ✅ Configurable auto-enrollment default rate (3%, 6%) via dbt variables
- ✅ Simple opt-out modeling (30, 60, 90 day windows)
- ✅ Basic demographic-based opt-out rates (age/salary bands)
- ✅ Generate ENROLLMENT and OPT_OUT events in existing event model
- ✅ Deterministic random sampling for reproducibility

## Technical Implementation

### 1. Core SQL Model

Create `dbt/models/intermediate/int_auto_enrollment_events.sql`:

```sql
{{ config(
  materialized='table',
  indexes=[
    {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'},
    {'columns': ['auto_enrollment_date'], 'type': 'btree'}
  ],
  tags=["enrollment_processing", "critical"]
) }}

WITH eligible_employees AS (
  SELECT
    e.employee_id,
    e.simulation_year,
    e.plan_id,
    e.eligibility_date,
    -- Auto-enrollment effective date (30 days after eligibility)
    e.eligibility_date + INTERVAL '30 days' AS auto_enrollment_date
  FROM {{ ref('int_eligibility_determination') }} e
  WHERE e.is_eligible = true
    AND e.simulation_year = {{ var('simulation_year') }}
    -- Exclude employees already enrolled
    AND NOT EXISTS (
      SELECT 1 FROM {{ ref('fct_yearly_events') }} enroll
      WHERE enroll.employee_id = e.employee_id
        AND enroll.event_type = 'enrollment'
        AND JSON_EXTRACT_STRING(enroll.payload, '$.plan_id') = e.plan_id
        AND enroll.effective_date <= e.eligibility_date + INTERVAL '30 days'
    )
),

workforce_demographics AS (
  SELECT
    w.employee_id,
    w.current_age,
    w.annual_compensation,
    -- Age-based opt-out segments
    CASE
      WHEN w.current_age BETWEEN 18 AND 25 THEN 'young'
      WHEN w.current_age BETWEEN 26 AND 35 THEN 'mid_career'
      WHEN w.current_age BETWEEN 36 AND 50 THEN 'mature'
      ELSE 'senior'
    END as age_segment,
    -- Income-based opt-out segments
    CASE
      WHEN w.annual_compensation < 30000 THEN 'low_income'
      WHEN w.annual_compensation < 50000 THEN 'moderate'
      WHEN w.annual_compensation < 100000 THEN 'high'
      ELSE 'executive'
    END as income_segment
  FROM {{ ref('int_baseline_workforce') }} w
  WHERE w.simulation_year = {{ var('simulation_year') }}
    AND w.employment_status = 'active'
),

auto_enrollment_processing AS (
  SELECT
    ee.*,
    wd.age_segment,
    wd.income_segment,
    {{ var('auto_enrollment_default_rate', 0.06) }} AS default_deferral_rate,
    {{ var('opt_out_window_days', 90) }} AS opt_out_window_days,

    -- Calculate opt-out probability using demographic factors
    CASE age_segment
      WHEN 'young' THEN {{ var('opt_out_rate_young', 0.35) }}
      WHEN 'mid_career' THEN {{ var('opt_out_rate_mid', 0.20) }}
      WHEN 'mature' THEN {{ var('opt_out_rate_mature', 0.15) }}
      ELSE {{ var('opt_out_rate_senior', 0.10) }}
    END *
    CASE income_segment
      WHEN 'low_income' THEN {{ var('opt_out_rate_low_income', 0.40) }} / {{ var('opt_out_rate_mid', 0.20) }}
      WHEN 'moderate' THEN 1.0
      WHEN 'high' THEN {{ var('opt_out_rate_high', 0.15) }} / {{ var('opt_out_rate_mid', 0.20) }}
      ELSE {{ var('opt_out_rate_executive', 0.05) }} / {{ var('opt_out_rate_mid', 0.20) }}
    END as opt_out_probability

  FROM eligible_employees ee
  INNER JOIN workforce_demographics wd ON ee.employee_id = wd.employee_id
),

opt_out_determination AS (
  SELECT
    *,
    -- Deterministic random sampling using employee_id as seed
    (ABS(HASH(employee_id || simulation_year || 'auto_enroll')) % 1000000) / 1000000.0 as random_draw,
    random_draw < opt_out_probability as will_opt_out,

    CASE WHEN random_draw < opt_out_probability
      THEN auto_enrollment_date + INTERVAL (ABS(HASH(employee_id || 'opt_out')) % opt_out_window_days) DAY
      ELSE null
    END as opt_out_date,

    auto_enrollment_date + INTERVAL opt_out_window_days DAY as opt_out_window_expires

  FROM auto_enrollment_processing
),

final_enrollment_status AS (
  SELECT
    *,
    CASE WHEN will_opt_out THEN false ELSE true END as final_enrolled,
    CASE WHEN will_opt_out THEN 0.0 ELSE default_deferral_rate END as final_deferral_rate,
    CASE WHEN will_opt_out THEN 'opted_out' ELSE 'auto' END as final_enrollment_source,

    -- Data quality validation
    CASE
      WHEN auto_enrollment_date IS NULL THEN 'INVALID_ENROLLMENT_DATE'
      WHEN default_deferral_rate NOT BETWEEN 0.0 AND 1.0 THEN 'INVALID_DEFAULT_RATE'
      WHEN opt_out_window_expires <= auto_enrollment_date THEN 'INVALID_OPT_OUT_WINDOW'
      ELSE 'VALID'
    END as data_quality_flag

  FROM opt_out_determination
)

SELECT
  employee_id,
  simulation_year,
  plan_id,
  eligibility_date,
  auto_enrollment_date,
  final_enrolled as enrolled,
  final_deferral_rate as deferral_rate,
  final_enrollment_source as enrollment_source,
  age_segment,
  income_segment,
  opt_out_probability,
  will_opt_out,
  opt_out_date,
  opt_out_window_expires,
  random_draw as enrollment_random_seed,
  data_quality_flag,
  current_timestamp as created_at
FROM final_enrollment_status
ORDER BY employee_id
```

### 2. Event Generation Integration

Add to `dbt/models/intermediate/int_enrollment_events_generation.sql`:

```sql
-- Generate ENROLLMENT events for auto-enrolled participants
SELECT
  gen_random_uuid() as event_id,
  employee_id,
  'enrollment' as event_type,
  auto_enrollment_date as effective_date,
  simulation_year,
  '{{ var("scenario_id", "default") }}' as scenario_id,
  '{{ var("plan_design_id", "standard") }}' as plan_design_id,
  json_object(
    'event_type', 'enrollment',
    'plan_id', plan_id,
    'enrollment_date', auto_enrollment_date,
    'pre_tax_contribution_rate', deferral_rate,
    'roth_contribution_rate', 0.0,
    'after_tax_contribution_rate', 0.0,
    'auto_enrollment', true,
    'opt_out_window_expires', opt_out_window_expires
  ) as payload,
  current_timestamp as created_at
FROM {{ ref('int_auto_enrollment_events') }}
WHERE enrolled = true

UNION ALL

-- Generate OPT_OUT events for those who opted out
SELECT
  gen_random_uuid() as event_id,
  employee_id,
  'enrollment_change' as event_type,
  opt_out_date as effective_date,
  simulation_year,
  '{{ var("scenario_id", "default") }}' as scenario_id,
  '{{ var("plan_design_id", "standard") }}' as plan_design_id,
  json_object(
    'event_type', 'enrollment_change',
    'plan_id', plan_id,
    'change_type', 'opt_out',
    'new_pre_tax_rate', 0.0,
    'previous_rate', {{ var('auto_enrollment_default_rate', 0.06) }},
    'opt_out_date', opt_out_date
  ) as payload,
  current_timestamp as created_at
FROM {{ ref('int_auto_enrollment_events') }}
WHERE will_opt_out = true
```

### 3. dbt Configuration Variables

Add to `dbt/dbt_project.yml`:

```yaml
vars:
  # Auto-enrollment configuration
  auto_enrollment_enabled: true
  auto_enrollment_default_rate: 0.06    # 6% default rate
  opt_out_window_days: 90               # 90-day opt-out window

  # Demographic-based opt-out rates
  opt_out_rate_young: 0.35      # Ages 18-25: 35% opt-out rate
  opt_out_rate_mid: 0.20        # Ages 26-35: 20% opt-out rate (baseline)
  opt_out_rate_mature: 0.15     # Ages 36-50: 15% opt-out rate
  opt_out_rate_senior: 0.10     # Ages 51+: 10% opt-out rate

  # Income-based opt-out rate adjustments
  opt_out_rate_low_income: 0.40     # <$30k: 40% opt-out rate
  opt_out_rate_moderate: 0.25       # $30k-$50k: 25% opt-out rate
  opt_out_rate_high: 0.15           # $50k-$100k: 15% opt-out rate
  opt_out_rate_executive: 0.05      # >$100k: 5% opt-out rate
```

### 4. Data Quality Tests

Add to `dbt/models/intermediate/schema.yml`:

```yaml
models:
  - name: int_auto_enrollment_events
    description: "Auto-enrollment events with opt-out modeling and demographic segmentation"
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - employee_id
            - simulation_year
            - plan_id
      - dbt_utils.expression_is_true:
          expression: "deferral_rate BETWEEN 0.0 AND 1.0"
      - dbt_utils.expression_is_true:
          expression: "opt_out_window_expires > auto_enrollment_date"
      - dbt_utils.expression_is_true:
          expression: "data_quality_flag = 'VALID'"

    columns:
      - name: employee_id
        description: "Unique employee identifier"
        tests:
          - not_null
      - name: deferral_rate
        description: "Employee deferral rate (0.0 - 1.0)"
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1
      - name: opt_out_probability
        description: "Calculated opt-out probability based on demographics"
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1
```

### 5. Orchestrator Integration

Add to `orchestrator_mvp/steps/enrollment_step.py`:

```python
def process_auto_enrollment(context: AssetExecutionContext,
                           duckdb: DuckDBResource,
                           year_state: Dict[str, Any]) -> pd.DataFrame:
    """
    Process auto-enrollment for eligible employees using SQL/dbt approach.

    Step 5 of orchestrator_mvp: Generate auto-enrollment events.
    """

    with duckdb.get_connection() as conn:
        # Run auto-enrollment determination model
        conn.execute("CALL dbt_run_model('int_auto_enrollment_events')")

        # Generate enrollment events
        enrollment_events = conn.execute("""
            SELECT * FROM generate_auto_enrollment_events(?)
        """, [year_state['simulation_year']]).df()

        # Update year state with auto-enrollment metrics
        year_state['auto_enrollment_metrics'] = {
            'total_eligible': len(enrollment_events),
            'auto_enrolled_count': len(enrollment_events[enrollment_events['enrolled']]),
            'opt_out_count': len(enrollment_events[enrollment_events['will_opt_out']]),
            'participation_rate': len(enrollment_events[enrollment_events['enrolled']]) / len(enrollment_events) if len(enrollment_events) > 0 else 0,
            'avg_deferral_rate': enrollment_events['deferral_rate'].mean()
        }

        context.log.info(f"Auto-enrollment processed: {year_state['auto_enrollment_metrics']}")

    return enrollment_events
```

## Performance Requirements

- **Target**: Process 100K employees in <5 seconds
- **Method**: DuckDB columnar processing with vectorized operations
- **Memory**: <2GB for full population processing
- **Reproducibility**: Deterministic results using hash-based random seeds

## Testing Strategy

### Unit Tests
- Validate opt-out probability calculations by demographic segment
- Test deterministic random seed generation
- Verify event payload structure and types

### Integration Tests
- Test with E022 eligibility engine output
- Validate event generation integration
- Performance benchmarking with 100K employee dataset

### Data Quality Tests
- Enrollment date validation (must be >= eligibility date)
- Deferral rate bounds checking (0.0 - 1.0)
- Opt-out window validation (expires > enrollment date)

## Dependencies

- **E022**: Eligibility Engine (provides eligible population)
- **E021**: DC Plan Event Schema (for event generation)
- **orchestrator_mvp**: Pipeline integration framework
- **dbt**: SQL transformation engine

## Risks and Mitigation

**Risk**: Performance degradation with large populations
**Mitigation**: Implement batch processing and DuckDB optimization

**Risk**: Random seed collision causing non-deterministic results
**Mitigation**: Use compound hash (employee_id + simulation_year + context)

**Risk**: Demographic segment edge cases
**Mitigation**: Comprehensive test coverage for boundary conditions

## Definition of Done

- [ ] SQL model processes 100K employees in <5 seconds
- [ ] Auto-enrollment events generated with proper audit trail
- [ ] Opt-out modeling working with demographic segmentation
- [ ] Data quality tests passing with 100% coverage
- [ ] Integration with orchestrator_mvp complete
- [ ] Performance benchmarking complete
- [ ] Documentation and examples provided
