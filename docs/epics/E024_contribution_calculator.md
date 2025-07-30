# Epic E024: Contribution Calculator

## Epic Overview

### Summary
Develop a high-performance contribution calculation engine using SQL/dbt that computes employee deferrals while enforcing core IRS limits for 100K+ employees. This MVP focuses on essential contribution logic while deferring complex scenarios to post-MVP phases.

### Business Value
- Ensures 100% compliance with core IRS contribution limits avoiding penalties
- Accurately projects contribution amounts for plan cost modeling
- Provides foundation for advanced contribution features and optimization

### Success Criteria
- ✅ Calculates contributions with 100% accuracy using SQL/dbt processing
- ✅ Enforces core IRS limits (402(g), catch-up) using DuckDB optimization
- ✅ Processes 100K employees in <10 seconds using columnar processing
- ✅ Generates contribution events integrated with existing event sourcing
- ✅ Achieves reproducible results with deterministic calculations
- ✅ Provides audit trail for regulatory compliance

### MVP Implementation Approach
This epic follows the proven E022/E023 pattern:

**MVP Phase (2 weeks - 18 points)**
- SQL/dbt-first implementation for maximum performance
- Core IRS limit enforcement (402(g) and catch-up)
- Basic compensation processing with simple inclusion rules
- Integration with orchestrator_mvp/run_multi_year.py simulation framework
- Focus on 95% of standard contribution scenarios

**Post-MVP Phase (Future - 42 points)**
- Advanced Roth contribution support
- Complex timing and proration logic
- Dynamic compensation definitions
- Real-time YTD tracking dashboard
- Advanced employer contribution matching

---

## User Stories

### MVP Stories (In Development)

#### Story S024-01: Basic Contribution Calculations (8 points) 🚧
**Status**: Ready for implementation
**As a** payroll administrator
**I want** accurate contribution calculations each pay period
**So that** the correct amounts are deducted from employee paychecks

**MVP Acceptance Criteria:**
- ✅ SQL-based employee deferral calculations for 100K employees in <10 seconds
- ✅ Percentage-based and dollar-based deferral elections via dbt variables
- ✅ Basic pay frequency handling (bi-weekly, monthly)
- ✅ Generate CONTRIBUTION events in existing event model
- ✅ Deterministic calculations for reproducibility
- ✅ Integration with enrollment determination from E023

**Implementation**: See `/docs/stories/S024-01-basic-contribution-calculations.md`

#### Story S024-02: Core IRS Limit Enforcement (6 points) 🚧
**Status**: Ready for implementation
**As a** compliance officer
**I want** automatic enforcement of core IRS limits
**So that** we avoid excess contributions and penalties

**MVP Acceptance Criteria:**
- ✅ 402(g) elective deferral limit enforcement ($23,500 for 2025)
- ✅ Age 50+ catch-up contributions ($7,500 for 2025) using SQL date functions
- ✅ SQL-based YTD tracking with simple accumulation
- ✅ Limit violation detection and automatic reduction
- ✅ Audit trail for all limit applications

**Implementation**: See `/docs/stories/S024-02-core-irs-limit-enforcement.md`

#### Story S024-03: Simple Compensation Processing (4 points) 🚧
**Status**: Ready for implementation
**As a** plan administrator
**I want** consistent compensation calculations
**So that** contributions are based on correct pay amounts

**MVP Acceptance Criteria:**
- ✅ W-2 wage baseline with basic inclusions (regular pay, overtime)
- ✅ Hardcoded exclusions (severance, fringe benefits)
- ✅ IRS annual compensation limit ($360,000 for 2025)
- ✅ Basic partial period proration for new hires/terminations
- ✅ Integration with workforce events from simulation

**Implementation**: See `/docs/stories/S024-03-simple-compensation-processing.md`

### Future Stories (Post-MVP)

#### Story 4: Enhanced Roth Contribution Support (8 points) 📅
**Status**: Deferred to post-MVP
**As an** employee
**I want** to split contributions between traditional and Roth
**So that** I can optimize my tax strategy

**Future Acceptance Criteria:**
- Traditional vs Roth split percentage configuration
- Combined limit enforcement across contribution types
- Roth in-plan conversions with eligibility checking
- After-tax contribution support

#### Story 5: Advanced Timing & Proration Logic (12 points) 📅
**Status**: Deferred to post-MVP
**As a** finance manager
**I want** accurate handling of complex timing scenarios
**So that** contributions are correct for all employment situations

**Future Acceptance Criteria:**
- Complex hire/termination date scenarios
- Leave of absence suspension and resumption
- Mid-year plan changes with seamless transitions
- Payroll calendar integration with holiday adjustments

#### Story 6: Dynamic Compensation Definitions (6 points) 📅
**Status**: Deferred to post-MVP
**As a** plan administrator
**I want** flexible compensation definitions
**So that** different pay types are handled per plan rules

**Future Acceptance Criteria:**
- Configurable compensation inclusion/exclusion rules
- Multiple safe harbor compensation definitions
- Integration with real-time payroll systems
- Historical compensation tracking and corrections

#### Story 7: Advanced IRS Limit Processing (16 points) 📅
**Status**: Deferred to post-MVP
**As a** compliance officer
**I want** comprehensive IRS limit enforcement
**So that** all regulatory requirements are met

**Future Acceptance Criteria:**
- 415(c) annual additions limit with employer contributions
- Highly compensated employee (HCE) limit testing
- Real-time limit monitoring and suspension
- Year-end true-up calculations with corrections

---

## Technical Specifications

### SQL/dbt-Based Contribution Configuration

Following the proven E022/E023 pattern, E024 uses SQL/dbt-based implementation for maximum performance and maintainability.

#### dbt Variables for Contribution Processing
```yaml
# dbt_project.yml variables for contribution calculator
vars:
  # IRS Limits for 2025
  elective_deferral_limit_2025: 23500
  catch_up_limit_2025: 7500
  annual_additions_limit_2025: 70000
  irs_compensation_limit_2025: 360000

  # Compensation inclusion rules (MVP simplified)
  include_regular_pay: true
  include_overtime: true
  include_bonuses: false        # Deferred to post-MVP
  exclude_severance: true
  exclude_fringe_benefits: true

  # Pay frequency handling
  biweekly_periods_per_year: 26
  monthly_periods_per_year: 12

  # MVP contribution processing
  enable_catch_up_contributions: true
  enable_roth_contributions: false    # Deferred to post-MVP
  enable_employer_match: false        # Deferred to post-MVP
```

#### Core SQL Models

**int_contribution_calculation.sql** - Main contribution processing logic:
```sql
{{ config(materialized='table') }}

WITH eligible_employees AS (
    SELECT *
    FROM {{ ref('int_eligibility_determination') }}
    WHERE is_eligible = true
),

enrolled_employees AS (
    SELECT *
    FROM {{ ref('int_enrollment_determination') }}
    WHERE enrolled = true
),

compensation_base AS (
    SELECT
        e.employee_id,
        e.simulation_year,
        e.annual_compensation,
        e.current_age,
        -- Apply IRS compensation limit
        LEAST(e.annual_compensation, {{ var('irs_compensation_limit_2025', 360000) }}) AS eligible_compensation,

        -- Determine catch-up eligibility
        CASE
            WHEN e.current_age >= 50 AND {{ var('enable_catch_up_contributions', true) }}
                THEN {{ var('catch_up_limit_2025', 7500) }}
            ELSE 0
        END AS catch_up_eligibility,

        -- Get deferral elections from enrollment
        en.deferral_rate,
        COALESCE(en.deferral_type, 'percentage') as deferral_type,
        COALESCE(en.deferral_amount, 0.0) as deferral_amount

    FROM eligible_employees e
    INNER JOIN enrolled_employees en USING (employee_id, simulation_year)
),

deferral_calculations AS (
    SELECT
        *,
        -- Calculate requested deferral based on election type
        CASE
            WHEN deferral_type = 'percentage'
                THEN eligible_compensation * deferral_rate
            WHEN deferral_type = 'dollar'
                THEN LEAST(deferral_amount, eligible_compensation)
            ELSE 0
        END AS requested_deferral,

        -- Calculate applicable 402(g) limit
        {{ var('elective_deferral_limit_2025', 23500) }} + catch_up_eligibility AS applicable_402g_limit

    FROM compensation_base
),

limit_enforcement AS (
    SELECT
        *,
        -- Apply 402(g) limit enforcement
        LEAST(requested_deferral, applicable_402g_limit) AS final_employee_deferral,

        -- Track limit applications
        CASE
            WHEN requested_deferral > applicable_402g_limit
                THEN 'limit_applied'
            ELSE 'no_limit'
        END as limit_status,

        -- Calculate reduction amount if limited
        GREATEST(0, requested_deferral - applicable_402g_limit) as limit_reduction_amount

    FROM deferral_calculations
),

ytd_tracking AS (
    SELECT
        *,
        -- Simple YTD accumulation (MVP approach)
        final_employee_deferral as current_period_deferral,
        final_employee_deferral as ytd_deferrals,  -- Simplified for MVP

        -- Deterministic random seed for reproducibility
        (ABS(HASH(employee_id || simulation_year || 'contribution')) % 1000000) / 1000000.0 as contribution_random_seed

    FROM limit_enforcement
)

SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    deferral_rate,
    deferral_type,
    requested_deferral,
    applicable_402g_limit,
    final_employee_deferral,
    limit_status,
    limit_reduction_amount,
    catch_up_eligibility,
    current_period_deferral,
    ytd_deferrals,
    contribution_random_seed
FROM ytd_tracking
```

### Event Generation Integration

Unlike E022 (eligibility as filters) and similar to E023 (enrollment events), E024 generates actual contribution events:

```sql
-- Generate CONTRIBUTION events for calculated amounts
INSERT INTO fct_yearly_events
SELECT
    gen_random_uuid() as event_id,
    employee_id,
    'contribution' as event_type,
    DATE_TRUNC('month', CURRENT_DATE) as effective_date,
    simulation_year,
    '{{ var("scenario_id", "default") }}' as scenario_id,
    '{{ var("plan_design_id", "standard") }}' as plan_design_id,
    json_object(
        'event_type', 'contribution',
        'plan_id', 'plan_001',  -- TODO: Link to actual plan
        'source', 'employee_pre_tax',
        'amount', final_employee_deferral,
        'pay_period_end', DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month' - INTERVAL '1 day',
        'contribution_date', DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month',
        'ytd_amount', ytd_deferrals,
        'payroll_id', employee_id || '_' || simulation_year || '_monthly',
        'irs_limit_applied', limit_status = 'limit_applied',
        'inferred_value', false
    ) as payload,
    current_timestamp as created_at
FROM {{ ref('int_contribution_calculation') }}
WHERE final_employee_deferral > 0;
```

### Performance Optimizations

Following the E022/E023 pattern:

1. **Vectorized Operations**: SQL CASE statements for maximum DuckDB optimization
2. **Deterministic Randomness**: Hash-based seed generation for reproducible results
3. **Columnar Processing**: DuckDB's columnar storage optimizes limit calculations
4. **Batch Processing**: Single SQL statement processes entire eligible population
5. **Simple YTD Tracking**: Simplified accumulation logic for MVP speed

### Integration with orchestrator_mvp/run_multi_year.py

```python
# orchestrator_mvp multi-year simulation framework integration pattern
def process_contribution_calculations(context: Dict[str, Any],
                                    duckdb_connection,
                                    year_state: Dict[str, Any]) -> pd.DataFrame:
    """
    Process contribution calculations for the current year using SQL/dbt approach.

    Step 6 of orchestrator_mvp/run_multi_year.py: Calculate employee contributions with IRS limits.
    """

    # Run contribution calculation model via orchestrator_mvp
    duckdb_connection.execute("CALL dbt_run_model('int_contribution_calculation')")

    # Generate contribution events
    contribution_events = duckdb_connection.execute("""
        SELECT * FROM generate_contribution_events(?)
    """, [year_state['simulation_year']]).df()

        # Update year state with contribution metrics
        year_state['contribution_metrics'] = {
            'total_participants': len(contribution_events),
            'total_deferrals': contribution_events['final_employee_deferral'].sum(),
            'avg_deferral_rate': contribution_events['deferral_rate'].mean(),
            'limits_applied_count': len(contribution_events[contribution_events['limit_status'] == 'limit_applied']),
            'avg_deferral_amount': contribution_events['final_employee_deferral'].mean()
        }

    return contribution_events
```

---

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Contribution Processing | <10 seconds for 100K employees | SQL/dbt with DuckDB columnar processing |
| IRS Limit Enforcement | <5 seconds for limit calculations | Vectorized SQL CASE statements |
| Random Sampling | Reproducible with seed control | Hash-based deterministic functions |
| Memory Usage | <4GB for 100K employee simulation | Efficient SQL operations with optimized dtypes |
| Event Generation | <2 seconds for contribution events | Batch INSERT operations |

## Dependencies
- E021: DC Plan Data Model (event schema)
- E022: Eligibility Engine (eligible population)
- E023: Enrollment Engine (deferral elections)
- Historical compensation data for YTD tracking
- Annual IRS limit updates (manual for MVP)
- DuckDB for high-performance columnar processing

## Risks
- **Risk**: Complex IRS limit scenarios
- **Mitigation**: Focus on 95% of standard cases for MVP
- **Risk**: YTD tracking accuracy
- **Mitigation**: Simplified accumulation with comprehensive testing

## Estimated Effort
**Total Story Points**: 18 points (MVP)
**Estimated Duration**: 2 weeks

---

## Definition of Done
- [ ] Basic contribution calculations implemented in SQL/dbt
- [ ] Core IRS limits (402(g), catch-up) enforced correctly
- [ ] Simple compensation processing working with basic inclusions
- [ ] Performance targets met (<10 seconds for 100K employees)
- [ ] Event generation integrated with existing event sourcing
- [ ] Data quality tests implemented and passing
- [ ] Integration with orchestrator_mvp/run_multi_year.py simulation framework complete
- [ ] Documentation includes SQL model examples and usage patterns
