{{ config(
  materialized='ephemeral',
  tags=['EVENT_GENERATION', 'E068A_EPHEMERAL']
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
{% set first_delay_years = var('deferral_escalation_first_delay_years', 1) %}

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

-- FIX: Get initial enrollment rates from enrollment events (includes census data via synthetic baseline)
-- This breaks the circular dependency with the state accumulator
initial_enrollment_rates AS (
    SELECT
        employee_id,
        employee_deferral_rate as initial_deferral_rate,
        effective_date as enrollment_date,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date
        ) as rn
    FROM {{ ref('int_enrollment_events') }}
    WHERE LOWER(event_type) = 'enrollment'
        AND employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
        AND simulation_year <= {{ simulation_year }}

    UNION ALL

    -- Include synthetic baseline enrollments for pre-enrolled census employees
    SELECT
        employee_id,
        employee_deferral_rate as initial_deferral_rate,
        effective_date as enrollment_date,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date
        ) as rn
    FROM {{ ref('int_synthetic_baseline_enrollment_events') }}
    WHERE employee_id IS NOT NULL
        AND employee_deferral_rate > 0
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

-- No external registry gating in simplified mode
deferral_escalation_registry AS (
    SELECT CAST(NULL AS VARCHAR) as employee_id, CAST(NULL AS BOOLEAN) as is_enrolled
    WHERE FALSE
),

{% if simulation_year == start_year %}
-- Year 1: Calculate rates from enrollment events (no previous accumulator)
previous_year_rates AS (
    SELECT
        employee_id,
        initial_deferral_rate as current_deferral_rate,
        enrollment_date as last_rate_change_date
    FROM initial_enrollment_rates
    WHERE rn = 1
),
{% else %}
-- Year 2+: Read current rates from previous year's state accumulator
-- Use direct table reference to avoid circular dependency in dbt's dependency graph
-- (dbt doesn't understand temporal filtering, so ref() would create a cycle)
previous_year_rates AS (
    SELECT
        employee_id,
        current_deferral_rate,
        COALESCE(last_escalation_date, '{{ prev_year }}-12-31'::DATE) as last_rate_change_date
    FROM {{ target.schema }}.int_deferral_rate_state_accumulator_v2
    WHERE simulation_year = {{ prev_year }}
      AND employee_id IS NOT NULL
),
{% endif %}

-- Combine workforce with enrollment and previous year's rates
workforce_with_status AS (
    SELECT
        w.*,
        COALESCE(e.is_enrolled, false) as is_enrolled,
        e.first_enrollment_date,
        -- Program participation flags
        TRUE as in_auto_escalation_program,
        -- Use previous year's rate (includes all prior escalations via accumulator)
        COALESCE(pyr.current_deferral_rate, ier.initial_deferral_rate, 0.0) as current_deferral_rate,
        -- Escalation timing
        0 as total_previous_escalations,  -- Tracked via accumulator, not needed here
        pyr.last_rate_change_date,
        CASE
            WHEN pyr.last_rate_change_date IS NOT NULL
            THEN DATE_DIFF('day', pyr.last_rate_change_date, '{{ simulation_year }}-{{ esc_mmdd }}'::DATE)
            ELSE 9999
        END as days_since_last_escalation,
        -- Years since enrollment
        CASE
            WHEN ier.enrollment_date IS NOT NULL
            THEN EXTRACT('year' FROM ('{{ simulation_year }}-01-01'::DATE)) - EXTRACT('year' FROM ier.enrollment_date)
            ELSE 0
        END as years_since_enrollment
    FROM active_workforce w
    LEFT JOIN initial_enrollment_rates ier ON w.employee_id = ier.employee_id AND ier.rn = 1
    LEFT JOIN employee_enrollment_status e ON w.employee_id = e.employee_id
    LEFT JOIN previous_year_rates pyr ON w.employee_id = pyr.employee_id
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
        -- FIX: Ensure employees already at/above maximum are NOT enrolled in escalation
        -- This prevents the bug where census rates of 15% would be reduced to 6%
        (w.current_deferral_rate > 0 AND w.current_deferral_rate < {{ esc_cap }}) as under_rate_cap_check,
        (w.days_since_last_escalation >= 365) as timing_check,
        -- FEATURE: Configurable first escalation delay (default 1 year)
        (w.years_since_enrollment >= {{ first_delay_years }}) as enrollment_maturity_check

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
