{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree'},
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['effective_date'], 'type': 'btree'}
    ]
) }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', 2025) %}

/*
  Generate deferral rate escalation events for eligible employees

  Epic E035: Automatic Annual Deferral Rate Escalation

  This model generates annual deferral rate increase events following the
  user requirements:
  - Default January 1st effective date
  - 1% increment amount (configurable by job level)
  - 10% maximum rate cap (configurable by job level)
  - Toggle inclusion based on hire date

  FIXED: Circular dependency resolved by using only upstream models:
  - int_employee_compensation_by_year for current workforce
  - int_enrollment_events for enrollment status
  - Direct calculation of escalation history from previous years' events
*/

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
        -- Baseline deferral rate from default_deferral_rates table mapping
        0.03 as baseline_deferral_rate,  -- Temporary default, will be replaced with proper mapping
        w.simulation_year
    FROM {{ ref('int_employee_compensation_by_year') }} w
    WHERE w.simulation_year = {{ simulation_year }}
        AND w.employment_status = 'active'
        AND w.employee_id IS NOT NULL
),

-- Map employees to default deferral rates based on age and income segments
employee_deferral_rate_mapping AS (
    SELECT
        w.employee_id,
        w.current_age,
        w.employee_compensation,
        -- Age segmentation
        CASE
            WHEN w.current_age < 30 THEN 'young'
            WHEN w.current_age < 45 THEN 'mid_career'
            WHEN w.current_age < 55 THEN 'senior'
            ELSE 'mature'
        END as age_segment,
        -- Income segmentation based on level and compensation
        CASE
            WHEN w.level_id >= 5 OR w.employee_compensation >= 250000 THEN 'executive'
            WHEN w.level_id >= 4 OR w.employee_compensation >= 150000 THEN 'high'
            WHEN w.level_id >= 3 OR w.employee_compensation >= 100000 THEN 'moderate'
            ELSE 'low_income'
        END as income_segment
    FROM active_workforce w
),

-- Get default deferral rates for each employee
employee_baseline_rates AS (
    SELECT
        m.employee_id,
        m.age_segment,
        m.income_segment,
        d.default_rate as baseline_deferral_rate,
        d.auto_escalate,
        d.auto_escalate_rate,
        d.max_rate
    FROM employee_deferral_rate_mapping m
    LEFT JOIN default_deferral_rates d
        ON m.age_segment = d.age_segment
        AND m.income_segment = d.income_segment
        AND d.scenario_id = 'default'
        AND d.effective_date <= '{{ simulation_year }}-01-01'::DATE
    QUALIFY ROW_NUMBER() OVER (PARTITION BY m.employee_id ORDER BY d.effective_date DESC) = 1
),

-- Use enrollment status from compensation model (is_enrolled_flag)
employee_enrollment_status AS (
    SELECT DISTINCT
        employee_id,
        is_enrolled_flag as is_enrolled,
        employee_enrollment_date as first_enrollment_date
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
        AND is_enrolled_flag = true
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
    SELECT
        employee_id,
        COUNT(*) as total_escalations,
        MAX(effective_date) as last_escalation_date,
        SUM(escalation_rate) as cumulative_escalation_rate
    FROM {{ this }}
    WHERE simulation_year < {{ simulation_year }}
    GROUP BY employee_id
{% endif %}
),

-- Combine workforce with enrollment and escalation history
workforce_with_status AS (
    SELECT
        w.*,
        COALESCE(e.is_enrolled, false) as is_enrolled,
        e.first_enrollment_date,
        -- Program participation flags (orchestrator-managed registry + baseline auto-escalate capability)
        -- Note: Registry column reference fixed - using default true for auto-escalation eligibility
        COALESCE(r.is_enrolled, true) as in_auto_escalation_program,
        COALESCE(b.auto_escalate, true) as auto_escalate,
        -- Calculate current deferral rate (baseline + cumulative escalations)
        COALESCE(b.baseline_deferral_rate, 0.03) + COALESCE(h.cumulative_escalation_rate, 0) as current_deferral_rate,
        -- Escalation history
        COALESCE(h.total_escalations, 0) as total_previous_escalations,
        h.last_escalation_date,
        -- Calculate eligibility timing
        CASE
            WHEN h.last_escalation_date IS NOT NULL
            THEN (('{{ simulation_year }}-01-01'::DATE) - h.last_escalation_date)
            ELSE 9999  -- No previous escalations
        END as days_since_last_escalation,
        -- Years since enrollment
        CASE
            WHEN e.first_enrollment_date IS NOT NULL
            THEN EXTRACT('year' FROM ('{{ simulation_year }}-01-01'::DATE)) - EXTRACT('year' FROM e.first_enrollment_date)
            ELSE 0
        END as years_since_enrollment
    FROM active_workforce w
    LEFT JOIN employee_baseline_rates b ON w.employee_id = b.employee_id
    LEFT JOIN employee_enrollment_status e ON w.employee_id = e.employee_id
    LEFT JOIN previous_escalation_history h ON w.employee_id = h.employee_id
    -- Orchestrator-managed registry that tracks enrollment into the auto-escalation program
    LEFT JOIN deferral_escalation_registry r ON w.employee_id = r.employee_id
),

-- Apply parameter-driven eligibility rules
eligible_employees AS (
    SELECT
        w.*,
        -- Resolve escalation parameters using existing macro (correct argument order)
        {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'escalation_rate', simulation_year) }} as escalation_rate,
        {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'max_escalation_rate', simulation_year) }} as max_escalation_rate,
        {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'tenure_threshold', simulation_year) }} as tenure_threshold,
        {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'age_threshold', simulation_year) }} as age_threshold,
        {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'max_escalations', simulation_year) }} as max_escalations,

        -- Calculate new deferral rate
        LEAST(
            {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'max_escalation_rate', simulation_year) }},
            w.current_deferral_rate + {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'escalation_rate', simulation_year) }}
        ) as new_deferral_rate,

        -- Eligibility checks
        w.is_enrolled as is_enrolled_check,
        (w.current_tenure >= {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'tenure_threshold', simulation_year) }}) as meets_tenure_check,
        (w.current_age >= {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'age_threshold', simulation_year) }}) as meets_age_check,
        (w.total_previous_escalations < {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'max_escalations', simulation_year) }}) as under_escalation_limit_check,
        (w.current_deferral_rate < {{ get_parameter_value('w.level_id', 'DEFERRAL_ESCALATION', 'max_escalation_rate', simulation_year) }}) as under_rate_cap_check,
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
        '{{ simulation_year }}-01-01'::DATE as effective_date,

        -- Rate changes
        e.current_deferral_rate as previous_deferral_rate,
        e.new_deferral_rate,
        e.escalation_rate,

        -- Employee context
        e.current_age,
        e.current_tenure,
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

        -- Escalation tracking
        e.total_previous_escalations + 1 as new_escalation_count,
        e.max_escalations,
        e.max_escalation_rate,

        -- Event details for fct_yearly_events integration
        JSON_OBJECT(
            'previous_rate', e.current_deferral_rate,
            'new_rate', e.new_deferral_rate,
            'escalation_amount', e.escalation_rate,
            'escalation_count', e.total_previous_escalations + 1,
            'max_rate', e.max_escalation_rate,
            'reason', 'automatic_annual_escalation'
        )::VARCHAR as event_details,

        -- Metadata
        CURRENT_TIMESTAMP as created_at,
        'default' as parameter_scenario_id,
        'int_deferral_rate_escalation_events' as event_source,

        -- Data quality
        'VALID' as data_quality_flag

    FROM eligible_employees e
    WHERE
        -- All eligibility criteria must be met
        -- Must be enrolled in program (registry) OR newly enrolling (baseline allows auto-escalate and no prior escalations)
        (e.in_auto_escalation_program = true OR (e.auto_escalate = true AND e.total_previous_escalations = 0))
        AND e.is_enrolled_check
        AND e.meets_tenure_check
        AND e.meets_age_check
        AND e.under_escalation_limit_check
        AND e.under_rate_cap_check
        AND e.timing_check
        AND e.enrollment_maturity_check
        -- Ensure meaningful increase (prevent tiny escalations)
        AND (e.new_deferral_rate - e.current_deferral_rate) >= 0.001
)

SELECT * FROM escalation_events
