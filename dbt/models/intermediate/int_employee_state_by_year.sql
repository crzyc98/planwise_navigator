{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    pre_hook=[
      "{% if is_incremental() %}DELETE FROM int_employee_state_by_year WHERE simulation_year = {{ var('simulation_year') }}{% endif %}"
    ],
    tags=['STATE_ACCUMULATION'],
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree', 'unique': true},
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['is_active'], 'type': 'btree'},
        {'columns': ['scenario_id', 'plan_design_id'], 'type': 'btree'}
    ]
) }}

/*
  Epic E068B: Incremental Employee State Accumulation

  Eliminates O(n²) recursion by persisting employee_state_by_year and computing
  each year t from t-1 + events(t) only.

  Performance Target:
  - State Accumulation: 19.9s → 6-8s per year (60%+ improvement)
  - O(n) linear scaling vs O(n²) quadratic growth

  Pattern:
  - Full refresh: builds Y0 (baseline) + first year
  - Incremental run: read only simulation_year = t-1 + events(t); produce t
  - Explicit ORDER BY: employee_id, simulation_year for scan locality
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- Get previous year state (t-1) for incremental builds
WITH previous_year_state AS (
  {% if is_incremental() %}
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
    years_of_service,
    -- Additional workforce state
    current_age,
    employment_status,
    level_id,
    created_at
  FROM {{ this }}
  WHERE simulation_year = {{ simulation_year }} - 1
  {% else %}
  SELECT
    NULL::VARCHAR AS scenario_id,
    NULL::VARCHAR AS plan_design_id,
    NULL::VARCHAR AS employee_id,
    NULL::INTEGER AS simulation_year,
    -- Core state attributes
    NULL::BOOLEAN AS is_active,
    NULL::DATE AS hire_date,
    NULL::DATE AS termination_date,
    NULL::VARCHAR AS current_level,
    NULL::DECIMAL AS current_salary,
    -- Benefits state
    NULL::BOOLEAN AS is_enrolled,
    NULL::DATE AS enrollment_date,
    NULL::DECIMAL AS deferral_rate,
    NULL::DECIMAL AS account_balance,
    -- Calculated attributes
    NULL::INTEGER AS tenure_months,
    NULL::INTEGER AS years_of_service,
    -- Additional workforce state
    NULL::INTEGER AS current_age,
    NULL::VARCHAR AS employment_status,
    NULL::INTEGER AS level_id,
    NULL::TIMESTAMP AS created_at
  WHERE FALSE
  {% endif %}
),

-- Get all events for current simulation year
current_year_events AS (
  SELECT
    'default' AS scenario_id,  -- Use default scenario
    'main' AS plan_design_id,  -- Use main plan design
    employee_id,
    event_type,
    effective_date AS event_date,
    event_details AS event_payload,
    compensation_amount,
    level_id,
    employee_age,
    employee_ssn,
    employee_deferral_rate,
    simulation_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE simulation_year = {{ simulation_year }}
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
    MAX(CASE WHEN event_type = 'raise' THEN 1 ELSE 0 END) AS had_merit,
    MAX(CASE WHEN event_type = 'enrollment' THEN 1 ELSE 0 END) AS had_enrollment,
    MAX(CASE WHEN event_type = 'enrollment_change' THEN 1 ELSE 0 END) AS had_deferral_change,

    -- Latest event values (use MAX for deterministic results)
    MAX(CASE WHEN event_type = 'hire' THEN event_date END) AS hire_date,
    MAX(CASE WHEN event_type = 'termination' THEN event_date END) AS termination_date,
    MAX(CASE WHEN event_type = 'promotion' THEN level_id END) AS new_level,
    MAX(CASE WHEN event_type = 'promotion' OR event_type = 'raise' THEN compensation_amount END) AS new_salary,
    MAX(CASE WHEN event_type = 'enrollment' THEN event_date END) AS enrollment_date,
    MAX(CASE WHEN event_type = 'enrollment' OR event_type = 'enrollment_change' THEN employee_deferral_rate END) AS new_deferral_rate,
    MAX(CASE WHEN event_type = 'hire' THEN employee_age END) AS hire_age,
    MAX(CASE WHEN event_type = 'hire' THEN employee_ssn END) AS hire_ssn,

    -- Balance changes from contributions (sum all contribution events)
    SUM(CASE WHEN event_type = 'employee_contribution'
             THEN CAST(COALESCE(json_extract_string(event_payload, '$.amount'), '0') AS DECIMAL)
             ELSE 0 END) AS employee_contributions,
    SUM(CASE WHEN event_type = 'employer_match'
             THEN CAST(COALESCE(json_extract_string(event_payload, '$.amount'), '0') AS DECIMAL)
             ELSE 0 END) AS employer_contributions
  FROM current_year_events
  GROUP BY scenario_id, plan_design_id, employee_id
),

-- Handle baseline data for full refresh (first year only)
baseline_state AS (
  {% if not is_incremental() or simulation_year == start_year %}
  SELECT
    'default' AS scenario_id,
    'main' AS plan_design_id,
    employee_id,
    {{ simulation_year }} AS simulation_year,
    CASE WHEN employment_status = 'active' THEN TRUE ELSE FALSE END AS is_active,
    employee_hire_date AS hire_date,
    CAST(termination_date AS DATE) AS termination_date,
    CAST(level_id AS VARCHAR) AS current_level,
    current_compensation AS current_salary,
    CASE WHEN employee_enrollment_date IS NOT NULL THEN TRUE ELSE FALSE END AS is_enrolled,
    CAST(employee_enrollment_date AS DATE) AS enrollment_date,
    0.0 AS deferral_rate,  -- Initialize deferral rate to 0
    0.0 AS account_balance,  -- Start with zero balance
    DATEDIFF('month', employee_hire_date, CAST('{{ simulation_year }}-12-31' AS DATE)) AS tenure_months,
    DATEDIFF('year', employee_hire_date, CAST('{{ simulation_year }}-12-31' AS DATE)) AS years_of_service,
    current_age,
    employment_status,
    level_id,
    CURRENT_TIMESTAMP AS created_at
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ simulation_year }}
  {% else %}
  SELECT
    NULL::VARCHAR AS scenario_id, NULL::VARCHAR AS plan_design_id, NULL::VARCHAR AS employee_id, NULL::INTEGER AS simulation_year,
    NULL::BOOLEAN AS is_active, NULL::DATE AS hire_date, NULL::DATE AS termination_date, NULL::VARCHAR AS current_level,
    NULL::DECIMAL AS current_salary, NULL::BOOLEAN AS is_enrolled, NULL::DATE AS enrollment_date, NULL::DECIMAL AS deferral_rate,
    NULL::DECIMAL AS account_balance, NULL::INTEGER AS tenure_months, NULL::INTEGER AS years_of_service,
    NULL::INTEGER AS current_age, NULL::VARCHAR AS employment_status, NULL::INTEGER AS level_id, NULL::TIMESTAMP AS created_at
  WHERE FALSE  -- Empty result for incremental builds
  {% endif %}
),

-- Full outer join to handle new hires and existing employees
state_transitions AS (
  SELECT
    COALESCE(p.scenario_id, e.scenario_id, b.scenario_id) AS scenario_id,
    COALESCE(p.plan_design_id, e.plan_design_id, b.plan_design_id) AS plan_design_id,
    COALESCE(p.employee_id, e.employee_id, b.employee_id) AS employee_id,
    {{ simulation_year }} AS simulation_year,

    -- Active status logic
    CASE
      WHEN e.had_hire = 1 THEN TRUE
      WHEN e.had_termination = 1 THEN FALSE
      ELSE COALESCE(p.is_active, b.is_active, FALSE)
    END AS is_active,

    -- Date fields with event-driven updates
    CASE
      WHEN e.had_hire = 1 THEN e.hire_date
      ELSE COALESCE(p.hire_date, b.hire_date)
    END AS hire_date,

    CASE
      WHEN e.had_termination = 1 THEN e.termination_date
      ELSE COALESCE(p.termination_date, b.termination_date)
    END AS termination_date,

    -- Level and salary with promotion/merit updates
    CASE
      WHEN e.had_promotion = 1 THEN CAST(e.new_level AS VARCHAR)
      ELSE COALESCE(p.current_level, CAST(b.current_level AS VARCHAR))
    END AS current_level,

    CASE
      WHEN e.had_merit = 1 OR e.had_promotion = 1 THEN e.new_salary
      ELSE COALESCE(p.current_salary, b.current_salary)
    END AS current_salary,

    -- Enrollment status
    CASE
      WHEN e.had_enrollment = 1 THEN TRUE
      ELSE COALESCE(p.is_enrolled, b.is_enrolled, FALSE)
    END AS is_enrolled,

    CASE
      WHEN e.had_enrollment = 1 THEN e.enrollment_date
      ELSE COALESCE(p.enrollment_date, b.enrollment_date)
    END AS enrollment_date,

    -- Deferral rate with changes
    CASE
      WHEN e.had_deferral_change = 1 OR e.had_enrollment = 1 THEN COALESCE(e.new_deferral_rate, 0.0)
      ELSE COALESCE(p.deferral_rate, b.deferral_rate, 0.0)
    END AS deferral_rate,

    -- Account balance accumulation
    COALESCE(p.account_balance, b.account_balance, 0.0) +
    COALESCE(e.employee_contributions, 0.0) +
    COALESCE(e.employer_contributions, 0.0) AS account_balance,

    -- Calculated tenure (assuming end-of-year calculation)
    CASE
      WHEN e.had_hire = 1 THEN
        DATEDIFF('month', e.hire_date, CAST('{{ simulation_year }}-12-31' AS DATE))
      ELSE
        COALESCE(p.tenure_months + 12, b.tenure_months, 0)  -- Add 12 months from previous year
    END AS tenure_months,

    -- Years of service calculation
    CASE
      WHEN e.had_hire = 1 THEN
        DATEDIFF('year', e.hire_date, CAST('{{ simulation_year }}-12-31' AS DATE))
      ELSE
        COALESCE(p.years_of_service + 1, b.years_of_service, 0)
    END AS years_of_service,

    -- Additional workforce attributes
    CASE
      WHEN e.had_hire = 1 THEN e.hire_age + DATEDIFF('year', e.hire_date, CAST('{{ simulation_year }}-12-31' AS DATE))
      ELSE COALESCE(p.current_age + 1, b.current_age + 1, 0)  -- Age one year from previous/baseline
    END AS current_age,

    CASE
      WHEN e.had_hire = 1 THEN 'active'
      WHEN e.had_termination = 1 THEN 'terminated'
      ELSE COALESCE(p.employment_status, b.employment_status, 'active')
    END AS employment_status,

    CASE
      WHEN e.had_promotion = 1 THEN e.new_level
      ELSE COALESCE(p.level_id, b.level_id, 1)
    END AS level_id,

    CURRENT_TIMESTAMP AS created_at

  FROM previous_year_state p
  FULL OUTER JOIN employee_year_events e
    ON p.scenario_id = e.scenario_id
    AND p.plan_design_id = e.plan_design_id
    AND p.employee_id = e.employee_id
  {% if not is_incremental() or simulation_year == start_year %}
  FULL OUTER JOIN baseline_state b
    ON COALESCE(p.employee_id, e.employee_id) = b.employee_id
  {% else %}
  LEFT JOIN baseline_state b ON FALSE  -- No baseline join for incremental years
  {% endif %}

  -- Filter out null employee_ids
  WHERE COALESCE(p.employee_id, e.employee_id, b.employee_id) IS NOT NULL
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
  current_age,
  employment_status,
  level_id,
  created_at
FROM state_transitions
WHERE scenario_id IS NOT NULL
  AND plan_design_id IS NOT NULL
  AND employee_id IS NOT NULL
ORDER BY scenario_id, plan_design_id, employee_id, simulation_year
