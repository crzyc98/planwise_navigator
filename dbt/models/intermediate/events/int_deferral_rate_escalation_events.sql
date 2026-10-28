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
{% set plan_design_parameters_config = var('plan_design_parameters', none) %}

/*
  Generate deferral rate escalation events for eligible employees

  Epic E035: Automatic Annual Deferral Rate Escalation

  This model generates annual deferral rate increase events following the
  user requirements:
  - Default January 1st effective date
  - 1% increment amount (configurable by job level)
  - 10% maximum rate cap (configurable by job level)
  - Toggle inclusion based on hire date (employees hired ON OR AFTER cutoff are eligible)

  Simplified configuration:
  - Controlled by vars set from simulation_config.yaml (no demographic-based rates for escalation)
  - esc_rate, esc_cap, effective MM-DD, optional hire date cutoff, and enable toggle
  - Previous escalation history computed from prior years of this model (no circular deps)
*/

{% if not esc_enabled and not var('easy_enroll_enabled', true) and not var('reenrollment_sweep_enabled', false) and not plan_design_parameters_config %}
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
WITH parameter_rows AS (
{% if plan_design_parameters_config %}
    {{ get_plan_design_parameters(plan_design_parameters_config) }}
{% else %}
    SELECT
        '{{ var('plan_design_id', 'default') }}'::VARCHAR AS plan_design_id,
        {{ esc_rate }}::DECIMAL(10,6) AS deferral_escalation_increment,
        {{ esc_cap }}::DECIMAL(10,6) AS deferral_escalation_cap
{% endif %}
),

active_workforce AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_hire_date,
        w.employee_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.employment_status,
        w.simulation_year,
        assignment.plan_design_id,
        parameters.deferral_escalation_increment,
        parameters.deferral_escalation_cap
    FROM {{ ref('int_employee_compensation_by_year') }} w
    INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
        ON w.employee_id = assignment.employee_id
       AND w.simulation_year = assignment.simulation_year
       AND assignment.scenario_id = '{{ var('scenario_id', 'default') }}'
    INNER JOIN parameter_rows parameters
        ON assignment.plan_design_id = parameters.plan_design_id
    WHERE w.simulation_year = {{ simulation_year }}
        AND w.employment_status = 'active'
        AND w.employee_id IS NOT NULL
    {%- if esc_hire_cutoff is not none %}
        AND (w.employee_hire_date >= '{{ esc_hire_cutoff }}'::DATE
          OR {{ prior_reenrollment_aip_member('w.employee_id') }})
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
        AND scenario_id = '{{ var('scenario_id', 'default') }}'
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

-- The latest decision must win over an older enrollment, even if state is missing.
latest_enrollment_decisions AS (
    SELECT
        employee_id,
        event_type,
        simulation_year,
        employee_deferral_rate
    FROM {{ ref('int_enrollment_events') }}
    WHERE simulation_year <= {{ simulation_year }}
        AND scenario_id = '{{ var('scenario_id', 'default') }}'
        AND event_type IN ('enrollment', 'enrollment_change')
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY employee_id
        ORDER BY effective_date DESC, simulation_year DESC, event_type DESC
    ) = 1
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
        initial_deferral_rate > 0 AS is_enrolled_flag,
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
        is_enrolled_flag,
        aip_participant,
        employee_enrollment_date,
        -- For employees with no prior escalations, use enrollment date as baseline for timing
        -- This ensures the 365-day check measures from when they first enrolled, not end of previous year
        COALESCE(last_escalation_date, employee_enrollment_date) as last_rate_change_date
    FROM {{ target.schema }}.int_deferral_rate_state_accumulator
    WHERE simulation_year = {{ prev_year }}
      AND employee_id IS NOT NULL
      AND scenario_id = '{{ var('scenario_id', 'default') }}'
),
{% endif %}

-- Combine workforce with enrollment and previous year's rates
workforce_with_status AS (
    SELECT
        w.*,
        (COALESCE(pyr.is_enrolled_flag, false)
          OR (decision.event_type = 'enrollment'
            AND decision.simulation_year = {{ simulation_year }}
            AND decision.employee_deferral_rate > 0)) AS is_enrolled,
        {{ prior_reenrollment_aip_member('w.employee_id') }} AS is_sweep_aip,
        -- Initialize membership in year 1; carry state thereafter.
        {% if var('easy_enroll_enabled', true) %}
        {{ easy_enroll_member(ref('int_enrollment_events'), 'w.employee_id', simulation_year,
          "'" ~ var('scenario_id', 'default') ~ "'") }} AS is_easy_enroll,
        {{ easy_enroll_member(ref('int_enrollment_events'), 'w.employee_id', simulation_year,
          "'" ~ var('scenario_id', 'default') ~ "'",
          current_year_only=var('deferral_rate_changes_enabled', true)
            and var('deferral_rate_changes_post_escalation_decrease_leaves_escalation', false)) }} OR
        {% endif %}
        {% if simulation_year == start_year %}
        {{ aip_initial_membership(var('deferral_escalation_mode', 'automatic'), 'oo.auto_escalation_opt_out', 'w.employee_id') }}
        {% else %}
        COALESCE(pyr.aip_participant,
          {{ aip_initial_membership(var('deferral_escalation_mode', 'automatic'), 'oo.auto_escalation_opt_out', 'w.employee_id') }})
        {% endif %} AS in_auto_escalation_program,
        -- Only contributing prior state or a new enrollment can supply a rate.
        -- Never resurrect a historical rate after the latest decision is an opt-out.
        CASE
            WHEN decision.event_type = 'enrollment_change' THEN 0.0
            WHEN pyr.is_enrolled_flag AND pyr.current_deferral_rate > 0
                THEN pyr.current_deferral_rate
            WHEN decision.event_type = 'enrollment'
                AND decision.simulation_year = {{ simulation_year }}
                THEN COALESCE(decision.employee_deferral_rate, 0.0)
            ELSE 0.0
        END AS current_deferral_rate,
        -- Escalation timing
        0 as total_previous_escalations,  -- Tracked via accumulator, not needed here
        pyr.last_rate_change_date,
        CASE
            WHEN pyr.last_rate_change_date IS NOT NULL
            THEN DATE_DIFF('day', pyr.last_rate_change_date, '{{ simulation_year }}-{{ esc_mmdd }}'::DATE)
            ELSE 9999
        END as days_since_last_escalation,
        -- Years since enrollment for escalation eligibility
        -- Uses actual enrollment year so pre-enrolled census employees are immediately eligible
        -- (they've been enrolled for years already) while new hires must wait the configured delay
        CASE
            WHEN ier.enrollment_date IS NOT NULL
            THEN {{ simulation_year }} - EXTRACT('year' FROM ier.enrollment_date)
            ELSE 0
        END as years_since_enrollment
    FROM active_workforce w
    LEFT JOIN initial_enrollment_rates ier ON w.employee_id = ier.employee_id AND ier.rn = 1
    LEFT JOIN latest_enrollment_decisions decision ON w.employee_id = decision.employee_id
    LEFT JOIN previous_year_rates pyr ON w.employee_id = pyr.employee_id
    LEFT JOIN deferral_escalation_registry r ON w.employee_id = r.employee_id
    -- Issue #316: static per-employee auto-escalation opt-out from census
    LEFT JOIN {{ ref('stg_census_data') }} oo ON w.employee_id = oo.employee_id
),

{% set effective_cap = "CASE WHEN w.is_easy_enroll THEN " ~ var('easy_enroll_escalation_cap', 0.10) ~ " ELSE w.deferral_escalation_cap END"
  if var('easy_enroll_enabled', true) else 'w.deferral_escalation_cap' %}

-- Apply parameter-driven eligibility rules
eligible_employees AS (
    SELECT
        w.*,
        w.deferral_escalation_increment as escalation_rate,
        ({{ effective_cap }}) as max_escalation_rate,
        0 as tenure_threshold,
        0 as age_threshold,
        1000 as max_escalations,

        -- Calculate new deferral rate (only if under cap)
        CASE
            WHEN w.current_deferral_rate >= ({{ effective_cap }}) THEN w.current_deferral_rate
            ELSE LEAST(
                ({{ effective_cap }}),
                w.current_deferral_rate + w.deferral_escalation_increment
            )
        END as new_deferral_rate,

        -- Eligibility checks
        COALESCE(w.is_enrolled, false) as is_enrolled_check,
        TRUE as meets_tenure_check,
        TRUE as meets_age_check,
        (w.total_previous_escalations < 1000) as under_escalation_limit_check,
        -- FIX: Ensure employees already at/above maximum are NOT enrolled in escalation
        -- This prevents the bug where census rates of 15% would be reduced to 6%
        (w.current_deferral_rate > 0 AND w.current_deferral_rate < ({{ effective_cap }})) as under_rate_cap_check,
        -- Timing check: use calendar year (not days) so escalations happen on configured date each year
        (w.last_rate_change_date IS NULL OR EXTRACT('year' FROM w.last_rate_change_date) < {{ simulation_year }}) as timing_check,
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
        -- Age and tenure bands using centralized macros
        {{ assign_age_band('e.current_age') }} as age_band,
        {{ assign_tenure_band('e.current_tenure') }} as tenure_band,
        e.escalation_rate AS event_probability,
        'deferral_escalation' AS event_category

    FROM eligible_employees e
    LEFT JOIN {{ ref('int_employee_termination_dates') }} t
        ON e.employee_id = t.employee_id
        AND t.simulation_year = {{ simulation_year }}
    WHERE
        -- All eligibility criteria must be met
        -- Must be enrolled in program (registry) OR newly enrolling (baseline allows auto-escalate and no prior escalations)
        (e.in_auto_escalation_program = true)
        {% if not esc_enabled %}
        AND (e.is_sweep_aip{% if var('easy_enroll_enabled', true) %} OR e.is_easy_enroll{% endif %})
        {% endif %}
        AND (CASE WHEN {{ require_enrollment }} THEN e.is_enrolled_check ELSE TRUE END)
        AND e.meets_tenure_check
        AND e.meets_age_check
        AND e.under_escalation_limit_check
        AND e.under_rate_cap_check
        AND e.timing_check
        AND e.enrollment_maturity_check
        AND (
            t.termination_date IS NULL
            OR '{{ simulation_year }}-{{ esc_mmdd }}'::DATE <= t.termination_date
        )
        -- Ensure meaningful increase (prevent tiny escalations and cap violations)
        AND (e.new_deferral_rate - e.current_deferral_rate) >= 0.001
)

SELECT * FROM escalation_events
{% endif %}
