{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    on_schema_change='sync_all_columns',
    pre_hook=[
      "{% if is_incremental() %}DELETE FROM {{ this }} WHERE scenario_id = '{{ var('scenario_id', 'default') }}' AND plan_design_id = '{{ var('plan_design_id', 'default') }}' AND simulation_year = {{ var('simulation_year') }}{% endif %}"
    ],
    tags=['STATE_ACCUMULATION', 'DOMAIN_STATE']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}

-- Workforce-only state. Enrollment, deferral, eligibility, and benefit values
-- remain owned by their dedicated accumulators/calculations.
WITH prior_workforce AS (
  {% if is_incremental() and simulation_year > start_year %}
  SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    full_year_equivalent_compensation AS employee_gross_compensation,
    current_age + 1 AS current_age,
    current_tenure + 1 AS current_tenure,
    level_id,
    CAST(NULL AS TIMESTAMP) AS termination_date,
    'active' AS employment_status,
    scheduled_hours_per_week
  FROM {{ this }}
  WHERE scenario_id = '{{ scenario_id }}'
    AND plan_design_id = '{{ plan_design_id }}'
    AND simulation_year = {{ simulation_year - 1 }}
    AND employment_status = 'active'
  {% else %}
  SELECT
    CAST(NULL AS VARCHAR) AS employee_id,
    CAST(NULL AS VARCHAR) AS employee_ssn,
    CAST(NULL AS TIMESTAMP) AS employee_birth_date,
    CAST(NULL AS TIMESTAMP) AS employee_hire_date,
    CAST(NULL AS DOUBLE) AS employee_gross_compensation,
    CAST(NULL AS BIGINT) AS current_age,
    CAST(NULL AS INTEGER) AS current_tenure,
    CAST(NULL AS INTEGER) AS level_id,
    CAST(NULL AS TIMESTAMP) AS termination_date,
    CAST(NULL AS VARCHAR) AS employment_status,
    CAST(NULL AS DECIMAL(5,2)) AS scheduled_hours_per_week
  WHERE FALSE
  {% endif %}
),

base_workforce AS (
  {% if simulation_year == start_year %}
  SELECT
    baseline.employee_id,
    baseline.employee_ssn,
    baseline.employee_birth_date,
    baseline.employee_hire_date,
    baseline.current_compensation AS employee_gross_compensation,
    baseline.current_age,
    baseline.current_tenure,
    baseline.level_id,
    CAST(baseline.termination_date AS TIMESTAMP) AS termination_date,
    baseline.employment_status,
    census.scheduled_hours_per_week
  FROM {{ ref('int_baseline_workforce') }} baseline
  LEFT JOIN {{ ref('stg_census_data') }} census
    ON baseline.employee_id = census.employee_id
  WHERE baseline.simulation_year = {{ simulation_year }}
  {% else %}
  SELECT * FROM prior_workforce
  {% endif %}
),

current_year_events AS (
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_age,
    level_id,
    event_category
  FROM {{ ref('fct_yearly_events') }}
  WHERE scenario_id = '{{ scenario_id }}'
    AND plan_design_id = '{{ plan_design_id }}'
    AND simulation_year = {{ simulation_year }}
),

employee_events AS (
  SELECT
    employee_id,
    MAX(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN effective_date END) AS termination_date,
    MAX(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN event_details END) AS termination_reason,
    COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) > 0 AS has_termination,
    COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' AND event_category = 'new_hire_termination' THEN 1 END) > 0 AS is_new_hire_termination,
    MAX(CASE WHEN event_type = 'hire' THEN effective_date END) AS hire_date,
    MAX(CASE WHEN event_type = 'hire' THEN compensation_amount END) AS hire_salary,
    MAX(CASE WHEN event_type = 'hire' THEN employee_age END) AS hire_age,
    MAX(CASE WHEN event_type = 'hire' THEN employee_ssn END) AS hire_ssn,
    MAX(CASE WHEN event_type = 'hire' THEN level_id END) AS hire_level_id,
    COUNT(CASE WHEN event_type = 'hire' THEN 1 END) > 0 AS is_new_hire,
    MAX(CASE WHEN event_type = 'promotion' THEN compensation_amount END) AS promotion_salary,
    MAX(CASE WHEN event_type = 'promotion' THEN level_id END) AS promotion_level_id,
    COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) > 0 AS has_promotion,
    MAX(CASE WHEN event_type = 'raise' THEN compensation_amount END) AS merit_salary,
    MAX(CASE WHEN event_type = 'raise' AND previous_compensation > 0
      THEN (compensation_amount / previous_compensation) - 1.0 END) AS merit_raise_rate,
    COUNT(CASE WHEN event_type = 'raise' THEN 1 END) > 0 AS has_merit
  FROM current_year_events
  WHERE employee_id IS NOT NULL
  GROUP BY employee_id
),

existing_workforce AS (
  SELECT
    b.employee_id,
    b.employee_ssn,
    b.employee_birth_date,
    b.employee_hire_date,
    CASE
      WHEN e.has_promotion AND e.has_merit AND e.merit_raise_rate IS NOT NULL
        THEN ROUND(e.promotion_salary * (1 + e.merit_raise_rate), 2)
      WHEN e.has_merit THEN e.merit_salary
      WHEN e.has_promotion THEN e.promotion_salary
      ELSE b.employee_gross_compensation
    END AS employee_gross_compensation,
    b.current_age,
    b.current_tenure,
    CASE WHEN e.has_promotion THEN CAST(e.promotion_level_id AS INTEGER)
      ELSE CAST(b.level_id AS INTEGER) END AS level_id,
    CASE WHEN e.has_termination THEN CAST(e.termination_date AS TIMESTAMP)
      ELSE b.termination_date END AS termination_date,
    CASE WHEN e.has_termination THEN {{ status_terminated() }}
      ELSE b.employment_status END AS employment_status,
    e.termination_reason,
    FALSE AS is_new_hire,
    b.scheduled_hours_per_week
  FROM base_workforce b
  LEFT JOIN employee_events e ON b.employee_id = e.employee_id
),

new_hires AS (
  SELECT
    CAST(e.employee_id AS VARCHAR) AS employee_id,
    e.hire_ssn AS employee_ssn,
    CAST('{{ simulation_year }}-01-01' AS DATE)
      - INTERVAL (e.hire_age * 365) DAY AS employee_birth_date,
    e.hire_date AS employee_hire_date,
    e.hire_salary AS employee_gross_compensation,
    e.hire_age AS current_age,
    0 AS current_tenure,
    CAST(e.hire_level_id AS INTEGER) AS level_id,
    CASE WHEN e.is_new_hire_termination OR e.has_termination
      THEN CAST(e.termination_date AS TIMESTAMP) END AS termination_date,
    CASE WHEN e.is_new_hire_termination OR e.has_termination
      THEN {{ status_terminated() }} ELSE {{ status_active() }} END AS employment_status,
    e.termination_reason,
    TRUE AS is_new_hire,
    hiring.scheduled_hours_per_week
  FROM employee_events e
  LEFT JOIN {{ ref('int_hiring_events') }} hiring
    ON e.employee_id = hiring.employee_id
   AND hiring.simulation_year = {{ simulation_year }}
  WHERE e.is_new_hire
),

deduplicated_workforce AS (
  SELECT * EXCLUDE (record_rank)
  FROM (
    SELECT
      workforce.*,
      ROW_NUMBER() OVER (
        PARTITION BY employee_id
        ORDER BY is_new_hire DESC, employee_gross_compensation DESC,
          termination_date ASC NULLS LAST
      ) AS record_rank
    FROM (
      SELECT * FROM existing_workforce
      UNION ALL
      SELECT * FROM new_hires
    ) workforce
  ) ranked
  WHERE record_rank = 1
),

compensation_events AS (
  SELECT
    employee_id,
    event_type,
    effective_date AS event_date,
    compensation_amount AS new_compensation,
    previous_compensation,
    ROW_NUMBER() OVER (
      PARTITION BY employee_id
      ORDER BY effective_date,
        CASE event_type
          WHEN {{ evt_hire() }} THEN 1
          WHEN {{ evt_promotion() }} THEN 2
          WHEN {{ evt_raise() }} THEN 3
          WHEN {{ evt_termination() }} THEN 4
        END
    ) AS event_sequence
  FROM current_year_events
  WHERE event_type IN (
    {{ evt_hire() }}, {{ evt_promotion() }}, {{ evt_raise() }}, {{ evt_termination() }}
  )
),

event_boundaries AS (
  SELECT
    *,
    LEAD(event_date) OVER (
      PARTITION BY employee_id ORDER BY event_sequence
    ) AS next_event_date,
    LEAD(event_type) OVER (
      PARTITION BY employee_id ORDER BY event_sequence
    ) AS next_event_type
  FROM compensation_events
),

all_compensation_periods AS (
  SELECT
    e.employee_id,
    '{{ simulation_year }}-01-01'::DATE AS period_start,
    CASE
      WHEN e.event_type = 'termination' AND NOT EXISTS (
        SELECT 1 FROM compensation_events c
        WHERE c.employee_id = e.employee_id
          AND {{ is_compensation_event('c.event_type') }}
      ) THEN e.event_date
      ELSE e.event_date - INTERVAL 1 DAY
    END AS period_end,
    COALESCE(e.previous_compensation, w.employee_gross_compensation, 0) AS period_salary
  FROM event_boundaries e
  LEFT JOIN deduplicated_workforce w ON e.employee_id = w.employee_id
  WHERE e.event_sequence = 1
    AND e.event_date > '{{ simulation_year }}-01-01'::DATE
    AND e.event_type != 'hire'

  UNION ALL

  SELECT
    employee_id,
    event_date AS period_start,
    CASE WHEN next_event_type = 'termination' THEN next_event_date
      ELSE COALESCE(next_event_date - INTERVAL 1 DAY,
        '{{ simulation_year }}-12-31'::DATE) END AS period_end,
    new_compensation AS period_salary
  FROM event_boundaries
  WHERE {{ is_compensation_event('event_type') }}
    AND new_compensation IS NOT NULL
    AND new_compensation > 0
),

prorated_with_events AS (
  SELECT
    employee_id,
    SUM(period_salary * (DATE_DIFF('day', period_start, period_end) + 1) / 365.0)
      AS prorated_annual_compensation
  FROM all_compensation_periods
  WHERE period_start IS NOT NULL
    AND period_end IS NOT NULL
    AND period_salary > 0
    AND period_start <= period_end
    AND period_start >= '{{ simulation_year }}-01-01'::DATE
    AND period_end <= '{{ simulation_year }}-12-31'::DATE
  GROUP BY employee_id
),

prorated_without_events AS (
  SELECT
    w.employee_id,
    CASE
      WHEN EXTRACT(YEAR FROM w.employee_hire_date) = {{ simulation_year }}
        THEN w.employee_gross_compensation
          * (DATE_DIFF('day', w.employee_hire_date,
            COALESCE(w.termination_date, '{{ simulation_year }}-12-31'::DATE)) + 1)
          / 365.0
      WHEN w.employment_status = {{ status_terminated() }}
        AND EXTRACT(YEAR FROM w.termination_date) = {{ simulation_year }}
        THEN w.employee_gross_compensation
          * (DATE_DIFF('day', '{{ simulation_year }}-01-01'::DATE,
            w.termination_date) + 1) / 365.0
      ELSE w.employee_gross_compensation
    END AS prorated_annual_compensation
  FROM deduplicated_workforce w
  WHERE w.employee_id NOT IN (SELECT employee_id FROM compensation_events)
    AND w.employment_status = {{ status_active() }}
),

prorated_compensation AS (
  SELECT * FROM prorated_with_events
  UNION ALL
  SELECT * FROM prorated_without_events
)

SELECT
  '{{ scenario_id }}'::VARCHAR AS scenario_id,
  '{{ plan_design_id }}'::VARCHAR AS plan_design_id,
  w.employee_id,
  w.employee_ssn,
  CAST(w.employee_birth_date AS TIMESTAMP) AS employee_birth_date,
  CAST(w.employee_hire_date AS TIMESTAMP) AS employee_hire_date,
  CAST(w.termination_date AS TIMESTAMP) AS termination_date,
  w.termination_reason,
  w.employment_status,
  CASE
    WHEN w.is_new_hire AND w.employment_status = {{ status_active() }}
      AND EXTRACT(YEAR FROM w.employee_hire_date) = {{ simulation_year }}
      THEN 'new_hire_active'
    WHEN w.is_new_hire AND w.employment_status = {{ status_terminated() }}
      AND EXTRACT(YEAR FROM w.employee_hire_date) = {{ simulation_year }}
      THEN 'new_hire_termination'
    WHEN w.employment_status = {{ status_terminated() }}
      AND EXTRACT(YEAR FROM w.employee_hire_date) < {{ simulation_year }}
      THEN 'experienced_termination'
    ELSE 'continuous_active'
  END AS detailed_status_code,
  w.employee_gross_compensation AS current_compensation,
  COALESCE(p.prorated_annual_compensation, w.employee_gross_compensation)
    AS prorated_annual_compensation,
  w.employee_gross_compensation AS full_year_equivalent_compensation,
  w.current_age,
  CASE
    WHEN w.employment_status = {{ status_terminated() }}
      AND w.termination_date IS NOT NULL
      THEN {{ calculate_tenure('w.employee_hire_date', "MAKE_DATE(" ~ simulation_year ~ ", 12, 31)", 'w.termination_date') }}
    ELSE w.current_tenure
  END AS current_tenure,
  w.level_id,
  {{ assign_age_band('w.current_age') }} AS age_band,
  {{ assign_tenure_band('w.current_tenure') }} AS tenure_band,
  {{ simulation_year }}::INTEGER AS simulation_year,
  w.scheduled_hours_per_week
FROM deduplicated_workforce w
LEFT JOIN prorated_compensation p ON w.employee_id = p.employee_id
ORDER BY 1, 2, 3, 19
