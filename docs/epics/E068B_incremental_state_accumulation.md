# Epic E068B: Incremental State Accumulation (t-1 → t only)

## Goal
Eliminate O(n²) recursion by persisting employee_state_by_year and computing each year t from t-1 + events(t) only.

## Rationale
State Accum ≈ 35% of total runtime; recursive re-reads of all prior years increase quadratically.

## Scope
- **In**: `models/state/employee_state_by_year.sql` with materialized: incremental, unique_key=['employee_id','sim_year'], incremental_strategy='delete+insert'.
- **Out**: Event generation logic (E068A), orchestrator threading (E068C).

## Deliverables
- Non-recursive state model; delete/insert per target year partition.
- Tests: conservation (count_t = count_t-1 + hires − terms), uniqueness on (employee_id, sim_year).

## Implementation Notes
- **Full refresh**: builds Y0 (baseline) + first year.
- **Incremental run**: read only sim_year = t-1 + events(t); produce t; append/replace partition.
- **Explicit ORDER BY**: employee_id, sim_year.

## Tasks / Stories

### 1. Implement state transitions
- Active flag changes (hire → active, termination → inactive)
- Level changes (promotion events)
- Deferral rate updates (deferral/escalation events)
- Balance deltas (contribution events)

### 2. Partition delete pre-hook (optional)
- Pre-hook: `DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}`
- Alternative: rely on delete+insert incremental strategy

### 3. Add tests
- Row conservation tests
- Uniqueness tests on composite key
- NOT NULL validation on key columns

## Acceptance Criteria
- Per-year State Accum ≤ 6–8s (5k×5).
- Equality vs baseline on fixed seed; conservation tests pass.

## Runbook

```bash
dbt run --select state.employee_state_by_year --vars '{"simulation_year": 2027, "start_year": 2025}' --threads 6
```

## Example Implementation

### Incremental State Model
```sql
-- models/state/int_employee_state_by_year.sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
  pre_hook="DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}",
  tags=['STATE_ACCUMULATION']
) }}

WITH previous_year_state AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    simulation_year,
    -- Core state attributes
    is_active,
    hire_date,
    termination_date,
    current_level,
    current_salary,
    -- Benefits state
    is_enrolled,
    enrollment_date,
    deferral_rate,
    account_balance,
    -- Calculated attributes
    tenure_months,
    years_of_service
  FROM {{ this }}
  WHERE simulation_year = {{ var('simulation_year') }} - 1
  {% if is_incremental() %}
    AND simulation_year = {{ var('simulation_year') }} - 1
  {% endif %}
),

current_year_events AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    event_type,
    event_date,
    event_payload,
    simulation_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

-- Aggregate events by employee for state transitions
employee_year_events AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    -- Event flags for state transitions
    MAX(CASE WHEN event_type = 'hire' THEN 1 ELSE 0 END) AS had_hire,
    MAX(CASE WHEN event_type = 'termination' THEN 1 ELSE 0 END) AS had_termination,
    MAX(CASE WHEN event_type = 'promotion' THEN 1 ELSE 0 END) AS had_promotion,
    MAX(CASE WHEN event_type = 'merit' THEN 1 ELSE 0 END) AS had_merit,
    MAX(CASE WHEN event_type = 'benefit_enrollment' THEN 1 ELSE 0 END) AS had_enrollment,
    MAX(CASE WHEN event_type = 'deferral_change' THEN 1 ELSE 0 END) AS had_deferral_change,
    -- Latest event values
    MAX(CASE WHEN event_type = 'hire' THEN event_date END) AS hire_date,
    MAX(CASE WHEN event_type = 'termination' THEN event_date END) AS termination_date,
    MAX(CASE WHEN event_type = 'promotion' THEN JSON_EXTRACT_SCALAR(event_payload, '$.new_level') END) AS new_level,
    MAX(CASE WHEN event_type = 'merit' THEN CAST(JSON_EXTRACT_SCALAR(event_payload, '$.new_salary') AS DECIMAL) END) AS new_salary,
    MAX(CASE WHEN event_type = 'benefit_enrollment' THEN event_date END) AS enrollment_date,
    MAX(CASE WHEN event_type = 'deferral_change' THEN CAST(JSON_EXTRACT_SCALAR(event_payload, '$.new_deferral_rate') AS DECIMAL) END) AS new_deferral_rate,
    -- Balance changes from contributions
    SUM(CASE WHEN event_type = 'employee_contribution' THEN CAST(JSON_EXTRACT_SCALAR(event_payload, '$.amount') AS DECIMAL) ELSE 0 END) AS employee_contributions,
    SUM(CASE WHEN event_type = 'employer_match' THEN CAST(JSON_EXTRACT_SCALAR(event_payload, '$.amount') AS DECIMAL) ELSE 0 END) AS employer_contributions
  FROM current_year_events
  GROUP BY scenario_id, plan_design_id, employee_id
),

-- Full outer join to handle new hires and existing employees
state_transitions AS (
  SELECT
    COALESCE(p.scenario_id, e.scenario_id) AS scenario_id,
    COALESCE(p.plan_design_id, e.plan_design_id) AS plan_design_id,
    COALESCE(p.employee_id, e.employee_id) AS employee_id,
    {{ var('simulation_year') }} AS simulation_year,

    -- Active status logic
    CASE
      WHEN e.had_hire = 1 THEN TRUE
      WHEN e.had_termination = 1 THEN FALSE
      ELSE COALESCE(p.is_active, FALSE)
    END AS is_active,

    -- Date fields with event-driven updates
    CASE
      WHEN e.had_hire = 1 THEN e.hire_date
      ELSE p.hire_date
    END AS hire_date,

    CASE
      WHEN e.had_termination = 1 THEN e.termination_date
      ELSE p.termination_date
    END AS termination_date,

    -- Level and salary with promotion/merit updates
    CASE
      WHEN e.had_promotion = 1 THEN e.new_level
      ELSE p.current_level
    END AS current_level,

    CASE
      WHEN e.had_merit = 1 THEN e.new_salary
      WHEN e.had_promotion = 1 AND e.new_salary IS NOT NULL THEN e.new_salary
      ELSE p.current_salary
    END AS current_salary,

    -- Enrollment status
    CASE
      WHEN e.had_enrollment = 1 THEN TRUE
      ELSE COALESCE(p.is_enrolled, FALSE)
    END AS is_enrolled,

    CASE
      WHEN e.had_enrollment = 1 THEN e.enrollment_date
      ELSE p.enrollment_date
    END AS enrollment_date,

    -- Deferral rate with changes
    CASE
      WHEN e.had_deferral_change = 1 THEN e.new_deferral_rate
      ELSE COALESCE(p.deferral_rate, 0.0)
    END AS deferral_rate,

    -- Account balance accumulation
    COALESCE(p.account_balance, 0.0) +
    COALESCE(e.employee_contributions, 0.0) +
    COALESCE(e.employer_contributions, 0.0) AS account_balance,

    -- Calculated tenure (assuming mid-year for current year)
    CASE
      WHEN e.had_hire = 1 THEN 6  -- Mid-year hire assumption
      ELSE p.tenure_months + 12   -- Add 12 months from previous year
    END AS tenure_months,

    -- Years of service calculation
    CASE
      WHEN e.had_hire = 1 THEN 0.5  -- Mid-year hire
      ELSE COALESCE(p.years_of_service, 0) + 1
    END AS years_of_service

  FROM previous_year_state p
  FULL OUTER JOIN employee_year_events e
    ON p.scenario_id = e.scenario_id
    AND p.plan_design_id = e.plan_design_id
    AND p.employee_id = e.employee_id

  -- Include baseline for full refresh (year 1) or new hires
  {% if not is_incremental() %}
  UNION ALL

  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    {{ var('simulation_year') }} AS simulation_year,
    TRUE AS is_active,
    hire_date,
    NULL AS termination_date,
    level AS current_level,
    salary AS current_salary,
    FALSE AS is_enrolled,
    NULL AS enrollment_date,
    0.0 AS deferral_rate,
    0.0 AS account_balance,
    DATEDIFF('month', hire_date, CURRENT_DATE) AS tenure_months,
    DATEDIFF('year', hire_date, CURRENT_DATE) AS years_of_service
  FROM {{ ref('stg_census_data') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employee_id NOT IN (SELECT employee_id FROM employee_year_events)
  {% endif %}
)

SELECT
  scenario_id,
  plan_design_id,
  employee_id,
  simulation_year,
  is_active,
  hire_date,
  termination_date,
  current_level,
  current_salary,
  is_enrolled,
  enrollment_date,
  deferral_rate,
  account_balance,
  tenure_months,
  years_of_service,
  -- Audit fields
  CURRENT_TIMESTAMP AS created_at
FROM state_transitions
ORDER BY scenario_id, plan_design_id, employee_id, simulation_year
```

### Schema Validation
```yaml
# schema.yml for state accumulator
version: 2

models:
  - name: int_employee_state_by_year
    description: "Incremental employee state tracking - year N computed from year N-1 + events(N)"
    config:
      contract: true
    columns:
      - name: scenario_id
        data_type: varchar
        tests: [not_null]
      - name: plan_design_id
        data_type: varchar
        tests: [not_null]
      - name: employee_id
        data_type: varchar
        tests: [not_null]
      - name: simulation_year
        data_type: integer
        tests: [not_null]
      - name: is_active
        data_type: boolean
        tests: [not_null]
      - name: hire_date
        data_type: date
      - name: current_level
        data_type: varchar
      - name: current_salary
        data_type: decimal(10,2)
      - name: is_enrolled
        data_type: boolean
      - name: deferral_rate
        data_type: decimal(5,4)
      - name: account_balance
        data_type: decimal(12,2)
    tests:
      - unique:
          column_name: "scenario_id || '-' || plan_design_id || '-' || employee_id || '-' || simulation_year"
      - dbt_utils.expression_is_true:
          expression: "deferral_rate >= 0.0 AND deferral_rate <= 1.0"
      - dbt_utils.expression_is_true:
          expression: "account_balance >= 0.0"
```

### Conservation Test
```sql
-- tests/conservation_employee_state_by_year.sql
SELECT
  simulation_year,
  COUNT(*) - LAG(COUNT(*)) OVER (ORDER BY simulation_year) AS net_change,
  SUM(CASE WHEN is_active AND hire_date >= DATE('{{ var("simulation_year") }}-01-01') THEN 1 ELSE 0 END) AS new_hires,
  SUM(CASE WHEN NOT is_active AND termination_date >= DATE('{{ var("simulation_year") }}-01-01') THEN 1 ELSE 0 END) AS terminations,
  -- Net change should equal hires - terminations (approximately)
  ABS((COUNT(*) - LAG(COUNT(*)) OVER (ORDER BY simulation_year)) -
      (SUM(CASE WHEN is_active AND hire_date >= DATE('{{ var("simulation_year") }}-01-01') THEN 1 ELSE 0 END) -
       SUM(CASE WHEN NOT is_active AND termination_date >= DATE('{{ var("simulation_year") }}-01-01') THEN 1 ELSE 0 END))) AS conservation_error
FROM {{ ref('int_employee_state_by_year') }}
WHERE simulation_year IN ({{ var('simulation_year') }} - 1, {{ var('simulation_year') }})
GROUP BY simulation_year
HAVING conservation_error > 10  -- Allow small tolerance for rounding/timing
```

## Success Metrics
- State Accumulation time per year: Current 19.9s → Target 6-8s (60-70% improvement)
- Memory usage: Eliminate O(n²) growth pattern
- Complexity: O(n) linear scaling with employee count
- Data integrity: 100% conservation test pass rate

## Dependencies
- E068A (Fused events) - Provides input events for state transitions
- Baseline workforce model - Provides initial employee state for full refresh
- Event payload structure - Must support JSON extraction for state updates

## Risk Mitigation
- **State transition logic errors**: Comprehensive unit tests for each event type's state impact
- **Missing baseline employees**: Full outer join pattern handles new hires and existing employees
- **Performance degradation**: Monitor query execution plans and optimize joins if needed

---

**Epic**: E068B
**Parent Epic**: E068 - Database Query Optimization
**Status**: 🔴 NOT STARTED
**Priority**: Critical
**Estimated Effort**: 5 story points
**Target Performance**: 60-70% improvement in State Accumulation stage
