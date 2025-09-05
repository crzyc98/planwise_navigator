{{ config(
  materialized='ephemeral',
  tags=['E068A_EPHEMERAL']
) }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', 2025) %}
{% set prev_year = (simulation_year | int) - 1 %}
{% set esc_enabled = var('deferral_escalation_enabled', true) %}
{% set esc_mmdd = var('deferral_escalation_effective_mmdd', '01-01') %}
{% set esc_rate = var('deferral_escalation_increment', 0.01) %}
{% set esc_cap = var('deferral_escalation_cap', 0.10) %}
{% set esc_hire_cutoff = var('deferral_escalation_hire_date_cutoff', none) %}
{% set require_enrollment = var('deferral_escalation_require_enrollment', true) %}

/*
  Generate deferral rate escalation events for eligible employees

  Epic E035: Automatic Annual Deferral Rate Escalation

  This model generates annual deferral rate increase events following the
  user requirements:
  - Default January 1st effective date
  - 1% increment amount (configurable by job level)
  - 10% maximum rate cap (configurable by job level)
  - Toggle inclusion based on hire date

  Simplified configuration:
  - Controlled by vars set from simulation_config.yaml (no demographic-based rates for escalation)
  - esc_rate, esc_cap, effective MM-DD, optional hire date cutoff, and enable toggle
  - Previous escalation history computed from prior years of this model (no circular deps)
*/

{% if not esc_enabled %}
-- Escalation disabled via config; return no rows but preserve fused-events schema
SELECT
    CAST(NULL AS VARCHAR)           AS employee_id,
    CAST(NULL AS VARCHAR)           AS employee_ssn,
    CAST('deferral_escalation' AS VARCHAR) AS event_type,
    CAST(NULL AS INTEGER)           AS simulation_year,
    CAST(NULL AS DATE)              AS effective_date,
    CAST(NULL AS VARCHAR)           AS event_details,
    -- Back-compat columns for state accumulator
    CAST(NULL AS DECIMAL(5,4))      AS new_deferral_rate,
    CAST(NULL AS DECIMAL(5,4))      AS previous_deferral_rate,
    CAST(NULL AS DECIMAL(5,4))      AS escalation_rate,
    CAST(NULL AS INTEGER)           AS new_escalation_count,
    CAST(NULL AS INTEGER)           AS max_escalations,
    CAST(NULL AS DECIMAL(5,4))      AS max_escalation_rate,
    CAST(NULL AS DECIMAL(15,2))     AS compensation_amount,
    CAST(NULL AS DECIMAL(15,2))     AS previous_compensation,
    CAST(NULL AS DECIMAL(5,4))      AS employee_deferral_rate,
    CAST(NULL AS DECIMAL(5,4))      AS prev_employee_deferral_rate,
    CAST(NULL AS SMALLINT)          AS employee_age,
    CAST(NULL AS DECIMAL(10,2))     AS employee_tenure,
    CAST(NULL AS SMALLINT)          AS level_id,
    CAST(NULL AS VARCHAR)           AS age_band,
    CAST(NULL AS VARCHAR)           AS tenure_band,
    CAST(NULL AS DECIMAL(5,4))      AS event_probability,
    'deferral_escalation'           AS event_category
WHERE FALSE
{% else %}

-- Get current year active workforce with compensation
WITH active_workforce AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_hire_date,
        w.employee_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.employment_status,
        w.simulation_year
    FROM {{ ref('int_employee_compensation_by_year') }} w
    WHERE w.simulation_year = {{ simulation_year }}
        AND w.employment_status = 'active'
        AND w.employee_id IS NOT NULL
    {%- if esc_hire_cutoff is not none %}
        AND w.employee_hire_date > '{{ esc_hire_cutoff }}'::DATE
    {%- endif %}
),

-- First year we see each employee in compensation snapshot (freeze baseline year)
first_seen_year AS (
    SELECT employee_id, MIN(simulation_year) AS first_year
    FROM {{ ref('int_employee_compensation_by_year') }}
    GROUP BY employee_id
),

-- Attributes from first seen year for baseline mapping (frozen)
first_year_attrs AS (
    SELECT
        c.employee_id,
        c.current_age,
        c.level_id,
        c.employee_compensation,
        f.first_year
    FROM {{ ref('int_employee_compensation_by_year') }} c
    JOIN first_seen_year f ON c.employee_id = f.employee_id AND c.simulation_year = f.first_year
),

-- Frozen initial baseline (no re-basing in later years)
initial_baseline_rates AS (
    SELECT
        fa.employee_id,
        COALESCE(d.default_rate, 0.03) as baseline_deferral_rate  -- Default 3% fallback
    FROM first_year_attrs fa
    LEFT JOIN (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY age_segment, income_segment ORDER BY effective_date DESC) rn
        FROM (
            SELECT scenario_id, age_segment, income_segment, default_rate, effective_date FROM default_deferral_rates WHERE 1=1
            UNION ALL
            -- Fallback defaults if seed table is empty
            SELECT 'default' as scenario_id, 'young' as age_segment, 'low_income' as income_segment, 0.03 as default_rate, CURRENT_DATE as effective_date
            UNION ALL
            SELECT 'default' as scenario_id, 'mid_career' as age_segment, 'moderate' as income_segment, 0.05 as default_rate, CURRENT_DATE as effective_date
            UNION ALL
            SELECT 'default' as scenario_id, 'senior' as age_segment, 'high' as income_segment, 0.07 as default_rate, CURRENT_DATE as effective_date
            UNION ALL
            SELECT 'default' as scenario_id, 'mature' as age_segment, 'executive' as income_segment, 0.10 as default_rate, CURRENT_DATE as effective_date
        )
        WHERE scenario_id = 'default'
    ) d
      ON d.rn = 1
      AND (
           CASE WHEN fa.current_age < 30 THEN 'young'
                WHEN fa.current_age < 45 THEN 'mid_career'
                WHEN fa.current_age < 55 THEN 'senior'
                ELSE 'mature' END
          ) = d.age_segment
      AND (
           CASE WHEN fa.level_id >= 5 OR fa.employee_compensation >= 250000 THEN 'executive'
                WHEN fa.level_id >= 4 OR fa.employee_compensation >= 150000 THEN 'high'
                WHEN fa.level_id >= 3 OR fa.employee_compensation >= 100000 THEN 'moderate'
                ELSE 'low_income' END
          ) = d.income_segment
),

-- Use enrollment status from compensation model (is_enrolled_flag)
employee_enrollment_status AS (
    SELECT DISTINCT
        employee_id,
        is_enrolled_flag as is_enrolled,
        employee_enrollment_date as first_enrollment_date
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
        {%- if require_enrollment %}
        AND is_enrolled_flag = true
        {%- endif %}
),

-- Calculate previous escalation history from this same model in prior years
previous_escalation_history AS (
{% if simulation_year == start_year %}
    -- Base case: No previous escalations for first simulation year
    SELECT
        'dummy' as employee_id,
        0 as total_escalations,
        NULL::DATE as last_escalation_date,
        0.00 as cumulative_escalation_rate
    WHERE 1=0  -- Empty result set
{% else %}
    -- Get escalation history from previous years
    -- Only reference existing table if it exists and has data
    {% set escalation_relation = adapter.get_relation(database=this.database, schema=this.schema, identifier=this.identifier) %}
    {% if escalation_relation is not none %}
    SELECT
        employee_id,
        COUNT(*) as total_escalations,
        MAX(effective_date) as last_escalation_date,
        SUM(escalation_rate) as cumulative_escalation_rate
    FROM {{ this }}
    WHERE simulation_year < {{ simulation_year }}
    GROUP BY employee_id
    {% else %}
    -- Table doesn't exist yet, return empty result
    SELECT
        'dummy' as employee_id,
        0 as total_escalations,
        NULL::DATE as last_escalation_date,
        0.00 as cumulative_escalation_rate
    WHERE 1=0  -- Empty result set
    {% endif %}
{% endif %}
),

-- No external registry gating in simplified mode
deferral_escalation_registry AS (
    SELECT CAST(NULL AS VARCHAR) as employee_id, CAST(NULL AS BOOLEAN) as is_enrolled
    WHERE FALSE
),

-- Combine workforce with enrollment and escalation history
workforce_with_status AS (
    SELECT
        w.*,
        COALESCE(e.is_enrolled, false) as is_enrolled,
        e.first_enrollment_date,
        -- Program participation flags (orchestrator-managed registry + baseline auto-escalate capability)
        -- Note: Since registry is empty by default, all employees default to auto-escalation eligible
        TRUE as in_auto_escalation_program,
        -- Current deferral rate basis: frozen baseline + cumulative prior escalations (no re-basing)
        COALESCE(b.baseline_deferral_rate, 0.0) + COALESCE(h.cumulative_escalation_rate, 0.0) as current_deferral_rate,
        -- Escalation history
        COALESCE(h.total_escalations, 0) as total_previous_escalations,
        h.last_escalation_date,
        -- Calculate eligibility timing
        CASE
            WHEN h.last_escalation_date IS NOT NULL
            THEN (('{{ simulation_year }}-{{ esc_mmdd }}'::DATE) - h.last_escalation_date)
            ELSE 9999
        END as days_since_last_escalation,
        -- Years since enrollment
        CASE
            WHEN e.first_enrollment_date IS NOT NULL
            THEN EXTRACT('year' FROM ('{{ simulation_year }}-01-01'::DATE)) - EXTRACT('year' FROM e.first_enrollment_date)
            ELSE 0
        END as years_since_enrollment
    FROM active_workforce w
    LEFT JOIN initial_baseline_rates b ON w.employee_id = b.employee_id
    LEFT JOIN employee_enrollment_status e ON w.employee_id = e.employee_id
    LEFT JOIN previous_escalation_history h ON w.employee_id = h.employee_id
    -- Orchestrator-managed registry that tracks enrollment into the auto-escalation program
    LEFT JOIN deferral_escalation_registry r ON w.employee_id = r.employee_id
),

-- Apply parameter-driven eligibility rules
eligible_employees AS (
    SELECT
        w.*,
        {{ esc_rate }} as escalation_rate,
        {{ esc_cap }} as max_escalation_rate,
        0 as tenure_threshold,
        0 as age_threshold,
        1000 as max_escalations,

        -- Calculate new deferral rate (only if under cap)
        CASE
            WHEN w.current_deferral_rate >= {{ esc_cap }} THEN w.current_deferral_rate
            ELSE LEAST({{ esc_cap }}, w.current_deferral_rate + {{ esc_rate }})
        END as new_deferral_rate,

        -- Eligibility checks
        COALESCE(w.is_enrolled, false) as is_enrolled_check,
        TRUE as meets_tenure_check,
        TRUE as meets_age_check,
        (w.total_previous_escalations < 1000) as under_escalation_limit_check,
        (w.current_deferral_rate < {{ esc_cap }}) as under_rate_cap_check,
        (w.days_since_last_escalation >= 365) as timing_check,
        (w.years_since_enrollment >= 1) as enrollment_maturity_check

    FROM workforce_with_status w
),

-- Generate escalation events for eligible employees
escalation_events AS (
    SELECT
        e.employee_id,
        e.employee_ssn,
        'deferral_escalation' as event_type,
        {{ simulation_year }} as simulation_year,
        '{{ simulation_year }}-{{ esc_mmdd }}'::DATE as effective_date,
    'Deferral escalation: ' || ROUND(e.current_deferral_rate * 100, 1) || '% → ' || ROUND(e.new_deferral_rate * 100, 1) || '% (+' || ROUND(e.escalation_rate * 100, 1) || '%)' AS event_details,
    -- Back-compat columns for state accumulator
    e.new_deferral_rate AS new_deferral_rate,
    e.current_deferral_rate AS previous_deferral_rate,
    e.escalation_rate AS escalation_rate,
    1 AS new_escalation_count,
    1000 AS max_escalations,
    e.max_escalation_rate AS max_escalation_rate,
    NULL::DECIMAL(15,2) AS compensation_amount,
    NULL::DECIMAL(15,2) AS previous_compensation,
    e.new_deferral_rate AS employee_deferral_rate,
    e.current_deferral_rate AS prev_employee_deferral_rate,
        e.current_age AS employee_age,
        e.current_tenure AS employee_tenure,
        e.level_id,
        -- Age and tenure bands for analysis
        CASE
            WHEN e.current_age < 25 THEN '< 25'
            WHEN e.current_age < 35 THEN '25-34'
            WHEN e.current_age < 45 THEN '35-44'
            WHEN e.current_age < 55 THEN '45-54'
            WHEN e.current_age < 65 THEN '55-64'
            ELSE '65+'
        END as age_band,
        CASE
            WHEN e.current_tenure < 2 THEN '< 2'
            WHEN e.current_tenure < 5 THEN '2-4'
            WHEN e.current_tenure < 10 THEN '5-9'
            WHEN e.current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END as tenure_band,
        e.escalation_rate AS event_probability,
        'deferral_escalation' AS event_category

    FROM eligible_employees e
    WHERE
        -- All eligibility criteria must be met
        -- Must be enrolled in program (registry) OR newly enrolling (baseline allows auto-escalate and no prior escalations)
        (e.in_auto_escalation_program = true)
        AND (CASE WHEN {{ require_enrollment }} THEN e.is_enrolled_check ELSE TRUE END)
        AND e.meets_tenure_check
        AND e.meets_age_check
        AND e.under_escalation_limit_check
        AND e.under_rate_cap_check
        AND e.timing_check
        AND e.enrollment_maturity_check
        -- Ensure meaningful increase (prevent tiny escalations and cap violations)
        AND (e.new_deferral_rate - e.current_deferral_rate) >= 0.001
)

SELECT * FROM escalation_events
{% endif %}
