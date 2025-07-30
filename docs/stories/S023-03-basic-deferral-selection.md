# Story S023-03: Basic Deferral Rate Selection

**Epic**: E023 Enrollment Engine
**Story Points**: 5
**Status**: Ready for implementation
**Priority**: High

## User Story

**As a** benefits consultant
**I want** to model initial deferral elections
**So that** I can project employee contributions

## MVP Acceptance Criteria

- ✅ Simple deferral rate distribution (3%, 6%, 10%)
- ✅ Demographic-based rate selection (age/salary influence)
- ✅ Hardcoded common rate clustering
- ✅ IRS limit validation for high earners
- ✅ Deferral rate tracking in enrollment events

## Technical Implementation

### 1. Core SQL Model

Create `dbt/models/intermediate/int_deferral_rate_selection.sql`:

```sql
{{ config(
  materialized='table',
  indexes=[
    {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'},
    {'columns': ['age_segment', 'salary_segment'], 'type': 'btree'}
  ],
  tags=["enrollment_processing", "deferral_modeling"]
) }}

WITH enrolled_employees AS (
  -- Get all enrolled employees from both auto-enrollment and voluntary enrollment
  SELECT
    employee_id,
    simulation_year,
    plan_id,
    age_segment,
    CASE
      WHEN annual_compensation < 75000 THEN 'low'
      WHEN annual_compensation < 150000 THEN 'mid'
      ELSE 'high'
    END as salary_segment,
    annual_compensation,
    current_age,
    enrollment_source
  FROM {{ ref('int_auto_enrollment_events') }}
  WHERE enrolled = true

  UNION ALL

  SELECT
    employee_id,
    simulation_year,
    plan_id,
    age_segment,
    salary_segment,
    annual_compensation,
    current_age,
    'voluntary' as enrollment_source
  FROM {{ ref('int_demographic_enrollment_rates') }}
  WHERE will_enroll = true
),

deferral_rate_distribution AS (
  -- Common deferral rate clustering based on industry data
  SELECT * FROM (VALUES
    (0.03, 0.35, 'match_threshold'),   -- 3%: 35% of participants (common match threshold)
    (0.06, 0.40, 'safe_harbor'),       -- 6%: 40% of participants (safe harbor default)
    (0.10, 0.25, 'round_number')       -- 10%: 25% of participants (psychological round number)
  ) AS t(deferral_rate, distribution_weight, rate_category)
),

employee_deferral_context AS (
  SELECT
    ee.*,

    -- Age-based deferral tendency multipliers
    CASE
      WHEN ee.current_age < 30 THEN 0.85   -- Younger employees: tend toward lower rates
      WHEN ee.current_age < 40 THEN 0.95   -- Early career: slightly below baseline
      WHEN ee.current_age < 50 THEN 1.05   -- Mid-career: slightly above baseline
      ELSE 1.20                            -- Pre-retirement: significantly higher rates
    END AS age_multiplier,

    -- Salary-based deferral tendency multipliers
    CASE
      WHEN ee.salary_segment = 'low' THEN 0.90    -- Lower salary: constrained capacity
      WHEN ee.salary_segment = 'mid' THEN 1.00    -- Mid salary: baseline behavior
      ELSE 1.15                                   -- High salary: higher rates
    END AS salary_multiplier,

    -- Enrollment source influence (auto vs voluntary)
    CASE
      WHEN ee.enrollment_source = 'auto' THEN 0.95    -- Auto-enrolled: slightly lower rates
      ELSE 1.05                                       -- Voluntary: higher engagement
    END AS enrollment_source_multiplier,

    -- IRS limit validation for high earners (2025 limits)
    CASE
      WHEN ee.annual_compensation > 300000 THEN true
      WHEN ee.current_age >= 50 AND ee.annual_compensation > 200000 THEN true  -- Catch-up eligible
      ELSE false
    END AS needs_irs_limit_validation,

    -- Annual IRS limits for 2025
    CASE
      WHEN ee.current_age >= 50 THEN 31000  -- $23,500 + $7,500 catch-up
      ELSE 23500                            -- Standard limit
    END AS irs_annual_limit,

    -- Deterministic random seed for rate selection
    (ABS(HASH(ee.employee_id || ee.simulation_year || 'deferral_rate')) % 1000000) / 1000000.0 AS rate_random_seed

  FROM enrolled_employees ee
),

cumulative_distribution AS (
  -- Build cumulative distribution for rate selection
  SELECT
    deferral_rate,
    distribution_weight,
    rate_category,
    SUM(distribution_weight) OVER (ORDER BY deferral_rate) AS cumulative_weight
  FROM deferral_rate_distribution
),

rate_selection AS (
  SELECT
    edc.*,
    cd.deferral_rate as base_selected_rate,
    cd.rate_category,

    -- Apply demographic multipliers to influence rate selection
    -- (but keep within the 3 standard rates)
    CASE
      WHEN (edc.rate_random_seed * edc.age_multiplier * edc.salary_multiplier * edc.enrollment_source_multiplier) < 0.35
        THEN 0.03
      WHEN (edc.rate_random_seed * edc.age_multiplier * edc.salary_multiplier * edc.enrollment_source_multiplier) < 0.75
        THEN 0.06
      ELSE 0.10
    END AS demographically_adjusted_rate

  FROM employee_deferral_context edc
  CROSS JOIN cumulative_distribution cd
  WHERE edc.rate_random_seed * edc.age_multiplier * edc.salary_multiplier * edc.enrollment_source_multiplier
        <= cd.cumulative_weight
    AND cd.cumulative_weight = (
      SELECT MIN(cd2.cumulative_weight)
      FROM cumulative_distribution cd2
      WHERE edc.rate_random_seed * edc.age_multiplier * edc.salary_multiplier * edc.enrollment_source_multiplier <= cd2.cumulative_weight
    )
),

irs_limit_validation AS (
  SELECT
    rs.*,

    -- Calculate annual deferral amount
    rs.annual_compensation * rs.demographically_adjusted_rate AS projected_annual_deferral,

    -- Apply IRS limits where needed
    CASE
      WHEN rs.needs_irs_limit_validation
        AND (rs.annual_compensation * rs.demographically_adjusted_rate) > rs.irs_annual_limit
      THEN rs.irs_annual_limit / rs.annual_compensation  -- Cap at IRS limit
      ELSE rs.demographically_adjusted_rate
    END AS final_deferral_rate,

    -- Track IRS limit applications
    CASE
      WHEN rs.needs_irs_limit_validation
        AND (rs.annual_compensation * rs.demographically_adjusted_rate) > rs.irs_annual_limit
      THEN true
      ELSE false
    END AS irs_limit_applied,

    -- Calculate savings from original rate
    CASE
      WHEN rs.needs_irs_limit_validation
        AND (rs.annual_compensation * rs.demographically_adjusted_rate) > rs.irs_annual_limit
      THEN (rs.annual_compensation * rs.demographically_adjusted_rate) - rs.irs_annual_limit
      ELSE 0
    END AS irs_limit_reduction_amount

  FROM rate_selection rs
),

final_deferral_determination AS (
  SELECT
    *,

    -- Final annual deferral amount
    annual_compensation * final_deferral_rate AS final_annual_deferral,

    -- Data quality validation
    CASE
      WHEN final_deferral_rate < 0 OR final_deferral_rate > 1 THEN 'INVALID_DEFERRAL_RATE'
      WHEN irs_limit_applied AND (annual_compensation * final_deferral_rate) > (irs_annual_limit * 1.01) THEN 'IRS_LIMIT_VIOLATION'
      WHEN final_deferral_rate > demographically_adjusted_rate * 1.01 THEN 'RATE_INCREASED_ERROR'
      ELSE 'VALID'
    END AS data_quality_flag,

    -- Rate selection reason for audit trail
    CASE
      WHEN irs_limit_applied THEN 'irs_limit_applied'
      WHEN enrollment_source = 'auto' THEN 'auto_enrollment_demographic'
      ELSE 'voluntary_demographic'
    END AS rate_selection_reason

  FROM irs_limit_validation
)

SELECT
  employee_id,
  simulation_year,
  plan_id,
  enrollment_source,
  age_segment,
  salary_segment,
  current_age,
  annual_compensation,
  demographically_adjusted_rate,
  final_deferral_rate,
  final_annual_deferral,
  rate_category,
  irs_limit_applied,
  irs_limit_reduction_amount,
  needs_irs_limit_validation,
  irs_annual_limit,
  age_multiplier,
  salary_multiplier,
  enrollment_source_multiplier,
  rate_selection_reason,
  data_quality_flag,
  rate_random_seed,
  current_timestamp as created_at
FROM final_deferral_determination
ORDER BY employee_id
```

### 2. Update Enrollment Events with Final Deferral Rates

Create `dbt/models/intermediate/int_enrollment_events_with_deferral.sql`:

```sql
{{ config(materialized='table') }}

-- Update enrollment events with final deferral rate selections
WITH enrollment_events AS (
  -- Auto-enrollment events
  SELECT
    ae.employee_id,
    ae.simulation_year,
    ae.plan_id,
    ae.auto_enrollment_date as enrollment_date,
    ae.enrollment_source,
    'enrollment' as event_type,
    ae.age_segment,
    ae.income_segment as salary_segment
  FROM {{ ref('int_auto_enrollment_events') }} ae
  WHERE ae.enrolled = true

  UNION ALL

  -- Voluntary enrollment events
  SELECT
    der.employee_id,
    der.simulation_year,
    der.plan_id,
    der.projected_enrollment_date as enrollment_date,
    'voluntary' as enrollment_source,
    'enrollment' as event_type,
    der.age_segment,
    der.salary_segment
  FROM {{ ref('int_demographic_enrollment_rates') }} der
  WHERE der.will_enroll = true
),

enhanced_enrollment_events AS (
  SELECT
    ee.*,
    drs.final_deferral_rate,
    drs.final_annual_deferral,
    drs.rate_category,
    drs.irs_limit_applied,
    drs.rate_selection_reason,
    COALESCE(drs.data_quality_flag, 'NO_DEFERRAL_DATA') as data_quality_flag
  FROM enrollment_events ee
  LEFT JOIN {{ ref('int_deferral_rate_selection') }} drs
    ON ee.employee_id = drs.employee_id
    AND ee.simulation_year = drs.simulation_year
    AND ee.plan_id = drs.plan_id
)

-- Generate final enrollment events for event sourcing
SELECT
  gen_random_uuid() as event_id,
  employee_id,
  event_type,
  enrollment_date as effective_date,
  simulation_year,
  '{{ var("scenario_id", "default") }}' as scenario_id,
  '{{ var("plan_design_id", "standard") }}' as plan_design_id,
  json_object(
    'event_type', 'enrollment',
    'plan_id', plan_id,
    'enrollment_date', enrollment_date,
    'pre_tax_contribution_rate', COALESCE(final_deferral_rate, 0.0),
    'roth_contribution_rate', 0.0,
    'after_tax_contribution_rate', 0.0,
    'auto_enrollment', enrollment_source = 'auto',
    'enrollment_source', enrollment_source,
    'age_segment', age_segment,
    'salary_segment', salary_segment,
    'rate_category', rate_category,
    'irs_limit_applied', COALESCE(irs_limit_applied, false),
    'rate_selection_reason', rate_selection_reason,
    'annual_deferral_amount', COALESCE(final_annual_deferral, 0.0)
  ) as payload,
  current_timestamp as created_at
FROM enhanced_enrollment_events
WHERE data_quality_flag = 'VALID'
  AND enrollment_date IS NOT NULL
ORDER BY employee_id, enrollment_date
```

### 3. dbt Configuration Variables

Add to `dbt/dbt_project.yml`:

```yaml
vars:
  # Deferral rate distribution (industry-standard clustering)
  deferral_rate_3pct_prob: 0.35      # 35% choose 3% (match threshold)
  deferral_rate_6pct_prob: 0.40      # 40% choose 6% (common default)
  deferral_rate_10pct_prob: 0.25     # 25% choose 10% (round number)

  # Demographic multipliers for rate selection
  age_young_multiplier: 0.85         # <30 years: lower rates
  age_early_career_multiplier: 0.95  # 30-39 years: slightly below baseline
  age_mid_career_multiplier: 1.05    # 40-49 years: slightly above baseline
  age_pre_retirement_multiplier: 1.20 # 50+ years: higher rates

  salary_low_multiplier: 0.90        # Low salary: constrained capacity
  salary_mid_multiplier: 1.00        # Mid salary: baseline behavior
  salary_high_multiplier: 1.15       # High salary: higher rates

  auto_enrollment_multiplier: 0.95   # Auto-enrolled: slightly lower engagement
  voluntary_enrollment_multiplier: 1.05 # Voluntary: higher engagement

  # IRS limits for 2025
  irs_elective_deferral_limit_2025: 23500    # Standard limit
  irs_catch_up_limit_2025: 7500             # Age 50+ catch-up

  # Validation thresholds
  high_earner_threshold: 300000      # Compensation requiring IRS validation
  catch_up_earner_threshold: 200000  # Age 50+ requiring validation
```

### 4. Data Quality Tests

Add to `dbt/models/intermediate/schema.yml`:

```yaml
models:
  - name: int_deferral_rate_selection
    description: "Deferral rate selection with demographic influence and IRS limit validation"
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - employee_id
            - simulation_year
            - plan_id
      - dbt_utils.expression_is_true:
          expression: "final_deferral_rate BETWEEN 0.0 AND 1.0"
      - dbt_utils.expression_is_true:
          expression: "NOT (irs_limit_applied AND (annual_compensation * final_deferral_rate) > irs_annual_limit * 1.01)"
      - dbt_utils.expression_is_true:
          expression: "final_deferral_rate <= demographically_adjusted_rate * 1.01"
      - dbt_utils.expression_is_true:
          expression: "data_quality_flag = 'VALID'"

    columns:
      - name: employee_id
        description: "Unique employee identifier"
        tests:
          - not_null
      - name: final_deferral_rate
        description: "Final deferral rate after IRS limit validation"
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1
      - name: final_annual_deferral
        description: "Projected annual deferral amount"
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 31000  # Max with catch-up
      - name: rate_category
        description: "Deferral rate category"
        tests:
          - not_null
          - accepted_values:
              values: ['match_threshold', 'safe_harbor', 'round_number']
```

### 5. Analytics and Reporting Views

Create `dbt/models/marts/reporting/rpt_deferral_rate_analysis.sql`:

```sql
{{ config(materialized='view') }}

WITH deferral_summary AS (
  SELECT
    age_segment,
    salary_segment,
    enrollment_source,
    rate_category,
    COUNT(*) as participant_count,
    AVG(final_deferral_rate) as avg_deferral_rate,
    AVG(final_annual_deferral) as avg_annual_deferral,
    SUM(CASE WHEN irs_limit_applied THEN 1 ELSE 0 END) as irs_limited_count,
    AVG(CASE WHEN irs_limit_applied THEN irs_limit_reduction_amount ELSE 0 END) as avg_irs_reduction
  FROM {{ ref('int_deferral_rate_selection') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND data_quality_flag = 'VALID'
  GROUP BY age_segment, salary_segment, enrollment_source, rate_category
),

rate_distribution AS (
  SELECT
    final_deferral_rate,
    COUNT(*) as count,
    COUNT(*)::DECIMAL / SUM(COUNT(*)) OVER () as percentage
  FROM {{ ref('int_deferral_rate_selection') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND data_quality_flag = 'VALID'
  GROUP BY final_deferral_rate
  ORDER BY final_deferral_rate
)

SELECT
  'demographic_summary' as report_type,
  age_segment,
  salary_segment,
  enrollment_source,
  rate_category,
  participant_count,
  ROUND(avg_deferral_rate, 4) as avg_deferral_rate,
  ROUND(avg_annual_deferral, 2) as avg_annual_deferral,
  irs_limited_count,
  ROUND(avg_irs_reduction, 2) as avg_irs_reduction,
  ROUND(irs_limited_count::DECIMAL / participant_count, 4) as irs_limit_rate
FROM deferral_summary

UNION ALL

SELECT
  'rate_distribution' as report_type,
  NULL as age_segment,
  NULL as salary_segment,
  NULL as enrollment_source,
  final_deferral_rate::VARCHAR as rate_category,
  count as participant_count,
  final_deferral_rate as avg_deferral_rate,
  NULL as avg_annual_deferral,
  NULL as irs_limited_count,
  NULL as avg_irs_reduction,
  ROUND(percentage, 4) as irs_limit_rate
FROM rate_distribution
ORDER BY report_type, age_segment, salary_segment, enrollment_source
```

### 6. Orchestrator Integration

Add to `orchestrator_mvp/steps/enrollment_step.py`:

```python
def process_deferral_rate_selection(context: AssetExecutionContext,
                                   duckdb: DuckDBResource,
                                   year_state: Dict[str, Any]) -> pd.DataFrame:
    """
    Process deferral rate selection for enrolled employees using SQL/dbt approach.

    Step 5.3 of orchestrator_mvp: Determine deferral rates with demographic influence.
    """

    with duckdb.get_connection() as conn:
        # Run deferral rate selection model
        conn.execute("CALL dbt_run_model('int_deferral_rate_selection')")

        # Generate final enrollment events with deferral rates
        conn.execute("CALL dbt_run_model('int_enrollment_events_with_deferral')")

        # Get deferral analysis
        deferral_analysis = conn.execute("""
            SELECT * FROM rpt_deferral_rate_analysis
        """).df()

        # Get deferral selection results
        deferral_results = conn.execute("""
            SELECT
                COUNT(*) as total_participants,
                AVG(final_deferral_rate) as avg_deferral_rate,
                AVG(final_annual_deferral) as avg_annual_deferral,
                SUM(CASE WHEN irs_limit_applied THEN 1 ELSE 0 END) as irs_limited_count,
                COUNT(DISTINCT rate_category) as rate_categories
            FROM int_deferral_rate_selection
            WHERE simulation_year = ? AND data_quality_flag = 'VALID'
        """, [year_state['simulation_year']]).fetchone()

        # Update year state with deferral metrics
        year_state['deferral_selection_metrics'] = {
            'total_participants': deferral_results[0],
            'avg_deferral_rate': round(deferral_results[1], 4) if deferral_results[1] else 0,
            'avg_annual_deferral': round(deferral_results[2], 2) if deferral_results[2] else 0,
            'irs_limited_count': deferral_results[3],
            'irs_limit_rate': round(deferral_results[3] / deferral_results[0], 4) if deferral_results[0] > 0 else 0,
            'rate_categories': deferral_results[4]
        }

        context.log.info(f"Deferral rate selection processed: {year_state['deferral_selection_metrics']}")

    return deferral_analysis
```

## Performance Requirements

- **Target**: Process deferral rate selection for 100K employees in <2 seconds
- **Method**: Hash-based rate selection with optimized demographic lookups
- **Memory**: <1GB for rate calculations
- **IRS Validation**: <100ms for high earner limit checks

## Testing Strategy

### Unit Tests
- Validate rate distribution probabilities (35%, 40%, 25%)
- Test demographic multiplier calculations
- Verify IRS limit validation logic for various compensation levels

### Integration Tests
- Test with both auto-enrollment and voluntary enrollment inputs
- Validate rate selection determinism with same random seeds
- Performance testing with various demographic distributions

### Data Quality Tests
- Deferral rate bounds (0.0 - 1.0)
- IRS limit compliance validation
- Rate selection reason tracking

## Business Logic Validation

### Rate Distribution
- **3% Match Threshold**: 35% of participants (maximizes employer match)
- **6% Safe Harbor**: 40% of participants (common default rate)
- **10% Round Number**: 25% of participants (psychological appeal)

### Demographic Influence
- **Young Employees**: 15% lower rates (financial constraints)
- **Pre-retirement**: 20% higher rates (catch-up mentality)
- **High Earners**: 15% higher rates (tax efficiency)
- **Auto-enrolled**: 5% lower rates (less engagement)

### IRS Limit Validation
- **Standard Limit**: $23,500 (2025)
- **With Catch-up**: $31,000 (age 50+)
- **High Earner Threshold**: $300,000 annual compensation
- **Catch-up Earner Threshold**: $200,000 with age 50+

## Dependencies

- **S023-01**: Auto-enrollment (provides enrolled population)
- **S023-02**: Demographic enrollment (provides voluntary enrollees)
- **E021**: DC Plan Event Schema (for final event generation)
- **orchestrator_mvp**: Pipeline integration framework

## Risks and Mitigation

**Risk**: Rate distribution not reflecting actual participant behavior
**Mitigation**: Calibrate against historical deferral rate data by demographics

**Risk**: IRS limit validation creating unrealistic concentrations at limit
**Mitigation**: Apply graduated reduction rather than hard caps

**Risk**: Demographic multipliers causing extreme rate selections
**Mitigation**: Cap multiplier effects and validate final distributions

## Definition of Done

- [ ] 3-rate distribution (3%, 6%, 10%) working with proper weighting
- [ ] Demographic multipliers influencing rate selection appropriately
- [ ] IRS limit validation preventing excess deferrals for high earners
- [ ] Final enrollment events generated with accurate deferral rates
- [ ] Data quality tests passing with 100% coverage
- [ ] Integration with auto-enrollment and voluntary enrollment complete
- [ ] Performance target met (<2 seconds for 100K employees)
- [ ] Reporting dashboard shows deferral rate distribution by demographics
