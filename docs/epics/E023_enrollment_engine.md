# Epic E023: Enrollment Engine

## Epic Overview

### Summary
Develop a high-performance enrollment simulation engine using SQL/dbt that models participant enrollment behavior including auto-enrollment, opt-out rates, and voluntary enrollment patterns. This MVP focuses on core enrollment logic while deferring complex behavioral modeling to post-MVP phases.

### Business Value
- Enables accurate participation rate projections for plan design decisions
- Models the financial impact of auto-enrollment features saving $1-5M annually
- Provides foundation for enrollment analytics and optimization

### Success Criteria
- ✅ Models enrollment with 90% accuracy using simplified demographic segments
- ✅ Supports auto-enrollment with configurable default rates using SQL processing
- ✅ Processes 100K employees in <10 seconds using DuckDB optimization
- ✅ Generates enrollment events integrated with existing event sourcing
- ✅ Achieves reproducible results with deterministic random sampling
- ✅ Provides audit trail for regulatory compliance

### MVP Implementation Approach
This epic follows the proven E022 Eligibility Engine pattern:

**MVP Phase (2 weeks - 16 points)**
- SQL/dbt-first implementation for maximum performance
- Simplified demographic segmentation (no ML clustering)
- Core auto-enrollment and voluntary enrollment logic
- Integration with orchestrator_mvp framework
- Focus on 95% of standard enrollment scenarios

**Post-MVP Phase (Future - 40 points)**
- Advanced behavioral segmentation with ML clustering
- Auto-escalation and complex deferral modeling
- Real-time analytics dashboard
- A/B testing framework
- Psychological behavioral modeling

---

## User Stories

### MVP Stories (In Development)

#### Story S023-01: Basic Auto-Enrollment Logic (6 points) 🚧
**Status**: Ready for implementation
**As a** plan sponsor
**I want** to model basic auto-enrollment impact
**So that** I can predict participation rates and costs

**MVP Acceptance Criteria:**
- ✅ SQL-based auto-enrollment processing for 100K employees in <10 seconds
- ✅ Configurable auto-enrollment default rate (3%, 6%) via dbt variables
- ✅ Simple opt-out modeling (30, 60, 90 day windows)
- ✅ Basic demographic-based opt-out rates (age/salary bands)
- ✅ Generate ENROLLMENT and OPT_OUT events in existing event model
- ✅ Deterministic random sampling for reproducibility

**Implementation**: See `/docs/stories/S023-01-basic-auto-enrollment.md`

#### Story S023-02: Simple Demographic Enrollment (5 points) 🚧
**Status**: Ready for implementation
**As a** workforce analyst
**I want** realistic voluntary enrollment rates by demographics
**So that** my projections match actual behavior patterns

**MVP Acceptance Criteria:**
- ✅ 3-tier demographic segmentation (young/mid-career/senior)
- ✅ Age and salary-based enrollment probabilities
- ✅ SQL-based enrollment timing distribution
- ✅ Integration with eligibility results from E022
- ✅ Enrollment events with proper audit trail

**Implementation**: See `/docs/stories/S023-02-simple-demographic-enrollment.md`

#### Story S023-03: Basic Deferral Rate Selection (5 points) 🚧
**Status**: Ready for implementation
**As a** benefits consultant
**I want** to model initial deferral elections
**So that** I can project employee contributions

**MVP Acceptance Criteria:**
- ✅ Simple deferral rate distribution (3%, 6%, 10%)
- ✅ Demographic-based rate selection (age/salary influence)
- ✅ Hardcoded common rate clustering
- ✅ IRS limit validation for high earners
- ✅ Deferral rate tracking in enrollment events

**Implementation**: See `/docs/stories/S023-03-basic-deferral-selection.md`

### Future Stories (Post-MVP)

#### Story 4: Advanced Behavioral Segmentation (12 points) 📅
**Status**: Deferred to post-MVP
**As a** workforce analyst
**I want** ML-based behavioral clustering
**So that** I can model complex enrollment patterns

**Future Acceptance Criteria:**
- K-means clustering for behavioral segments
- Machine learning-enhanced probability curves
- Automated calibration against historical data
- A/B testing framework for enrollment strategies

#### Story 5: Auto-Escalation Features (8 points) 📅
**Status**: Deferred to post-MVP
**As a** retirement committee member
**I want** to model automatic increase programs
**So that** I can assess long-term savings improvements

**Future Acceptance Criteria:**
- Annual escalation processing with configurable amounts
- Behavioral opt-out rates for increases
- Integration with salary increase events

#### Story 6: Real-Time Analytics Dashboard (8 points) 📅
**Status**: Deferred to post-MVP
**As a** CFO
**I want** clear enrollment projections
**So that** I can budget for retirement contributions

**Future Acceptance Criteria:**
- Interactive participation rate dashboards
- Scenario comparison reports
- Executive-level enrollment metrics


---

## Technical Specifications

### SQL/dbt-Based Enrollment Configuration

Following the proven E022 pattern, E023 uses SQL/dbt-based implementation for maximum performance and maintainability.

#### dbt Variables for Auto-Enrollment
```yaml
# dbt_project.yml variables for enrollment engine
vars:
  # Auto-enrollment defaults
  auto_enrollment_enabled: true
  default_deferral_rate: 0.06
  opt_out_window_days: 90

  # Demographic-based opt-out rates
  opt_out_rate_young: 0.35    # Ages 18-25
  opt_out_rate_mid: 0.20      # Ages 26-35
  opt_out_rate_mature: 0.15   # Ages 36-50
  opt_out_rate_senior: 0.10   # Ages 51+

  # Salary-based adjustments
  opt_out_rate_low_income: 0.40     # <$30k
  opt_out_rate_moderate: 0.25       # $30k-$50k
  opt_out_rate_high: 0.15           # $50k-$100k
  opt_out_rate_executive: 0.05      # >$100k

  # Voluntary enrollment probabilities
  baseline_enrollment_probability: 0.60
  age_factor_per_year: 0.01    # +1% per year over 25
  tenure_factor_per_year: 0.05 # +5% per year of service

  # Common deferral rate distributions
  deferral_rate_3pct_prob: 0.25    # Match threshold
  deferral_rate_6pct_prob: 0.35    # Common default
  deferral_rate_10pct_prob: 0.20   # Round number
  deferral_rate_15pct_prob: 0.10   # High savers
  deferral_rate_max_prob: 0.10     # Max contributors
```

#### Core SQL Models

**int_enrollment_determination.sql** - Main enrollment processing logic:
```sql
{{ config(materialized='table') }}

WITH eligible_population AS (
    SELECT *
    FROM {{ ref('int_eligibility_determination') }}
    WHERE is_eligible = true
),

demographic_segments AS (
    SELECT
        *,
        CASE
            WHEN current_age BETWEEN 18 AND 25 THEN 'young'
            WHEN current_age BETWEEN 26 AND 35 THEN 'mid_career'
            WHEN current_age BETWEEN 36 AND 50 THEN 'mature'
            ELSE 'senior'
        END as age_segment,

        CASE
            WHEN annual_compensation < 30000 THEN 'low_income'
            WHEN annual_compensation < 50000 THEN 'moderate'
            WHEN annual_compensation < 100000 THEN 'high'
            ELSE 'executive'
        END as income_segment
    FROM eligible_population
),

auto_enrollment_processing AS (
    SELECT
        *,
        true as auto_enrolled,
        entry_date as enrollment_date,
        {{ var('default_deferral_rate') }} as initial_deferral_rate,
        'auto' as enrollment_source,

        -- Calculate opt-out probability using demographic factors
        CASE age_segment
            WHEN 'young' THEN {{ var('opt_out_rate_young') }}
            WHEN 'mid_career' THEN {{ var('opt_out_rate_mid') }}
            WHEN 'mature' THEN {{ var('opt_out_rate_mature') }}
            ELSE {{ var('opt_out_rate_senior') }}
        END *
        CASE income_segment
            WHEN 'low_income' THEN {{ var('opt_out_rate_low_income') }} / {{ var('opt_out_rate_mid') }}
            WHEN 'moderate' THEN 1.0
            WHEN 'high' THEN {{ var('opt_out_rate_high') }} / {{ var('opt_out_rate_mid') }}
            ELSE {{ var('opt_out_rate_executive') }} / {{ var('opt_out_rate_mid') }}
        END as opt_out_probability

    FROM demographic_segments
    WHERE {{ var('auto_enrollment_enabled') }} = true
),

opt_out_determination AS (
    SELECT
        *,
        -- Deterministic random sampling using employee_id as seed
        (ABS(HASH(employee_id || simulation_year)) % 1000000) / 1000000.0 as random_draw,
        random_draw < opt_out_probability as will_opt_out,

        CASE WHEN will_opt_out
            THEN enrollment_date + INTERVAL (ABS(HASH(employee_id || 'opt_out')) % {{ var('opt_out_window_days') }}) DAY
            ELSE null
        END as opt_out_date

    FROM auto_enrollment_processing
),

final_enrollment_status AS (
    SELECT
        *,
        CASE WHEN will_opt_out THEN false ELSE auto_enrolled END as final_enrolled,
        CASE WHEN will_opt_out THEN 0.0 ELSE initial_deferral_rate END as final_deferral_rate,
        CASE WHEN will_opt_out THEN 'opted_out' ELSE enrollment_source END as final_enrollment_source
    FROM opt_out_determination
)

SELECT
    employee_id,
    simulation_year,
    entry_date,
    enrollment_date,
    final_enrolled as enrolled,
    final_deferral_rate as deferral_rate,
    final_enrollment_source as enrollment_source,
    age_segment,
    income_segment,
    opt_out_probability,
    will_opt_out,
    opt_out_date,
    random_draw as enrollment_random_seed
FROM final_enrollment_status
```

### Event Generation Integration

Unlike E022 (which uses eligibility as filters), E023 generates actual enrollment events in the event sourcing system:

```sql
-- Generate enrollment events for enrolled participants
INSERT INTO fct_yearly_events
SELECT
    gen_random_uuid() as event_id,
    employee_id,
    'enrollment' as event_type,
    enrollment_date as effective_date,
    simulation_year,
    scenario_id,
    plan_design_id,
    json_object(
        'event_type', 'enrollment',
        'plan_id', plan_id,
        'enrollment_date', enrollment_date,
        'pre_tax_contribution_rate', deferral_rate,
        'roth_contribution_rate', 0.0,
        'auto_enrollment', enrollment_source = 'auto',
        'opt_out_window_expires', enrollment_date + INTERVAL {{ var('opt_out_window_days') }} DAY
    ) as payload,
    current_timestamp as created_at
FROM {{ ref('int_enrollment_determination') }}
WHERE enrolled = true;

-- Generate opt-out events for those who opted out
INSERT INTO fct_yearly_events
SELECT
    gen_random_uuid() as event_id,
    employee_id,
    'enrollment_change' as event_type,
    opt_out_date as effective_date,
    simulation_year,
    scenario_id,
    plan_design_id,
    json_object(
        'event_type', 'enrollment_change',
        'plan_id', plan_id,
        'change_type', 'opt_out',
        'new_pre_tax_rate', 0.0,
        'previous_rate', {{ var('default_deferral_rate') }}
    ) as payload,
    current_timestamp as created_at
FROM {{ ref('int_enrollment_determination') }}
WHERE will_opt_out = true;
```

### Performance Optimizations

Following the E022 pattern:

1. **Vectorized Operations**: All probability calculations use SQL CASE statements for maximum DuckDB optimization
2. **Deterministic Randomness**: Hash-based random generation ensures reproducible results
3. **Columnar Processing**: DuckDB's columnar storage optimizes demographic segmentation queries
4. **Batch Processing**: Single SQL statement processes entire eligible population

### Integration with orchestrator_mvp

```python
# orchestrator_mvp integration pattern
def process_enrollment_simulation(context: AssetExecutionContext,
                                duckdb: DuckDBResource,
                                year_state: Dict[str, Any]) -> pd.DataFrame:
    """
    Process enrollment simulation for the current year using SQL/dbt approach.

    Step 4 of orchestrator_mvp: Generate enrollment events for eligible employees.
    """

    with duckdb.get_connection() as conn:
        # Run enrollment determination model
        conn.execute("CALL dbt_run_model('int_enrollment_determination')")

        # Generate enrollment events
        enrollment_events = conn.execute("""
            SELECT * FROM generate_enrollment_events(?)
        """, [year_state['simulation_year']]).df()

        # Update year state with enrollment metrics
        year_state['enrollment_metrics'] = {
            'total_eligible': len(enrollment_events),
            'enrolled_count': len(enrollment_events[enrollment_events['enrolled']]),
            'opt_out_count': len(enrollment_events[enrollment_events['will_opt_out']]),
            'avg_deferral_rate': enrollment_events['deferral_rate'].mean()
        }

    return enrollment_events
```

---

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Batch Enrollment Processing | <30 seconds for 100K employees | Vectorized behavioral segmentation with clustering |
| Behavioral Segment Assignment | <5 seconds for population clustering | Pre-computed feature matrices with K-means |
| Random Sampling | Reproducible with seed control | NumPy RandomState for deterministic results |
| Memory Usage | <6GB for 100K employee simulation | Efficient DataFrame operations with optimized dtypes |
| Real-time Queries | <50ms for enrollment analytics | Materialized behavioral segment summaries |

## Dependencies
- E021: DC Plan Data Model (event schema)
- E022: Eligibility Engine (eligible population)
- Historical enrollment data for calibration and ML training
- Pandas/Polars for vectorized DataFrame operations
- NumPy for efficient random number generation
- Scikit-learn for behavioral segmentation clustering
- Statistical libraries for distribution sampling

## Risks
- **Risk**: Behavioral modeling accuracy
- **Mitigation**: Calibrate against 3+ years of actual data
- **Risk**: Auto-enrollment legal compliance
- **Mitigation**: Include all required notices and timing

## Estimated Effort
**Total Story Points**: 56 points
**Estimated Duration**: 3-4 sprints

---

## Definition of Done
- [ ] Auto-enrollment logic fully implemented
- [ ] Voluntary enrollment modeling calibrated
- [ ] Deferral rate distributions validated
- [ ] Auto-escalation features complete
- [ ] Analytics reports designed and tested
- [ ] Performance targets met
- [ ] User documentation complete
