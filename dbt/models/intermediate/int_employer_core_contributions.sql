{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ],
    tags=['employer_contributions', 'core_contributions', 'mvp', 'STATE_ACCUMULATION']
) }}

/*
  Employer Core Contributions Model - Enhanced with Configuration

  FIXED (Issue #009): Added support for service-based (graded by service) core contribution tiers.
  FIXED: Decoupled from deferral rate calculations to prevent auto-escalation from affecting core contributions.

  Calculates employer core (non-elective) contribution amounts
  based on configurable business rules:
  - Configurable contribution rate (default 2%) via simulation_config.yaml
  - Support for graded-by-service tiered rates (e.g., 0-9 years: 6%, 10+ years: 8%)
  - Enhanced eligibility criteria including minimum tenure requirements
  - Can be enabled/disabled via configuration
  - 0% for ineligible employees
  - Independent compensation proration logic (not affected by deferral rates)
  - Audit trail field (applied_years_of_service) for compliance tracking

  Configuration driven via dbt variables:
  - employer_core_enabled: Master on/off switch
  - employer_core_status: 'none', 'flat', or 'graded_by_service'
  - employer_core_contribution_rate: Flat contribution rate (e.g., 0.02 for 2%)
  - employer_core_graded_schedule: List of service tiers with min_years, max_years, rate
  - core_minimum_tenure_years: Minimum years of service required
  - core_require_active_eoy: Must be active at year-end
  - core_minimum_hours: Minimum annual hours requirement

  Service Tier Logic:
  - When employer_core_status = 'graded_by_service', the model uses get_tiered_core_rate macro
  - Tiers are sorted descending by min_years for correct CASE evaluation
  - Uses [min, max) interval convention (min_years inclusive, max_years exclusive)
  - Rate is divided by 100 to convert from percentage (6.0) to decimal (0.06)
  - applied_years_of_service field provides audit trail for tier selection

  Bug Fix: Previously used int_employee_contributions for proration, which created
  unwanted dependency on deferral rate calculations. New hire terminations were
  incorrectly getting core contributions when auto-escalation was enabled for all
  employees, because the deferral rate logic was affecting compensation proration.

  Now uses independent proration logic to ensure core contributions are only
  affected by employment status and eligibility rules, not deferral settings.
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set employer_core_enabled = var('employer_core_enabled', true) %}
{% set employer_core_contribution_rate = var('employer_core_contribution_rate', 0.02) %}
{% set employer_core_status = var('employer_core_status', 'flat') %}
{% set employer_core_graded_schedule = var('employer_core_graded_schedule', []) %}

-- Read nested core config for termination exceptions, with flat var fallbacks
{% set employer_core_config = var('employer_core_contribution', {}) %}
{% set core_eligibility = employer_core_config.get('eligibility', {}) %}
{% set core_allow_terminated_new_hires = core_eligibility.get('allow_terminated_new_hires', var('core_allow_terminated_new_hires', false)) %}
{% set core_allow_experienced_terminations = core_eligibility.get('allow_experienced_terminations', var('core_allow_experienced_terminations', false)) %}
{% set core_require_active_eoy = core_eligibility.get('require_active_at_year_end', var('core_require_active_eoy', true)) %}

WITH employee_compensation AS (
    -- Get current year compensation for all employees
    SELECT
        employee_id,
        simulation_year,
        employee_compensation,
        employment_status
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
),

-- Include current-year new hires who may not be present in compensation_by_year (years > start)
-- Use hire events as the source of compensation and calculate prorated compensation
new_hires_curr_year AS (
    SELECT
        ye.employee_id,
        ye.simulation_year,
        -- Assume event compensation is annual salary; prorate from hire date to year end
        ye.compensation_amount AS employee_compensation,
        ROUND(
            ye.compensation_amount *
            GREATEST(0,
                DATEDIFF('day', ye.effective_date::DATE, (ye.simulation_year || '-12-31')::DATE) + 1
            ) / 365.0, 2
        ) AS prorated_annual_compensation,
        'active' AS employment_status
    FROM {{ ref('fct_yearly_events') }} ye
    WHERE ye.simulation_year = {{ simulation_year }}
      AND ye.event_type = 'hire'
      AND ye.employee_id IS NOT NULL
),

-- Unified population for the year: compensation snapshot plus new hires
population AS (
    SELECT employee_id, simulation_year, employee_compensation, NULL::DOUBLE AS prorated_annual_compensation, employment_status
    FROM employee_compensation
    UNION ALL
    SELECT employee_id, simulation_year, employee_compensation, prorated_annual_compensation, employment_status
    FROM new_hires_curr_year
),

-- Independent workforce proration logic (decoupled from deferral rates)
-- This ensures core contributions are not affected by auto-escalation settings
hire_events AS (
    SELECT
        employee_id,
        effective_date::DATE AS hire_date,
        compensation_amount AS annual_salary,
        employee_age
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND event_type = 'hire'
),

termination_events AS (
    SELECT
        employee_id,
        effective_date::DATE AS termination_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND event_type = 'termination'
),

-- Calculate independent proration for new hires
new_hire_proration AS (
    SELECT
        h.employee_id,
        {{ simulation_year }} AS simulation_year,
        h.annual_salary AS current_compensation,
        -- Prorate from hire to termination (if any) else year end
        ROUND(
            h.annual_salary *
            LEAST(365, GREATEST(0,
                DATEDIFF('day', h.hire_date, COALESCE(t.termination_date, ({{ simulation_year }} || '-12-31')::DATE)) + 1
            )) / 365.0
        , 2) AS prorated_annual_compensation,
        CASE WHEN t.termination_date IS NULL THEN 'active' ELSE 'terminated' END AS employment_status,
        t.termination_date
    FROM hire_events h
    LEFT JOIN termination_events t USING (employee_id)
),

-- Independent workforce proration logic (decoupled from deferral rates)
workforce_proration AS (
    -- Existing employees (NOT new hires in current year) - use full annual compensation
    -- FIXED: Exclude current-year new hires to prevent double-counting and ensure they use prorated compensation
    SELECT
        employee_id,
        simulation_year,
        employee_compensation AS current_compensation,
        employee_compensation AS prorated_annual_compensation, -- Full year compensation for existing employees
        employment_status,
        NULL::DATE AS termination_date
    FROM employee_compensation
    WHERE employee_id NOT IN (
        -- Exclude current-year new hires - they will be processed separately with proper proration
        SELECT employee_id FROM hire_events WHERE employee_id IS NOT NULL
    )

    UNION ALL

    -- Current-year new hires with proper proration from hire date
    -- FIXED: These employees get prorated compensation based on actual hire date, not full annual
    SELECT
        employee_id,
        simulation_year,
        current_compensation,
        prorated_annual_compensation, -- Properly prorated from hire date to year-end (or termination)
        employment_status,
        termination_date
    FROM new_hire_proration
    -- All new hires should be included here since they were excluded from the first SELECT above
),

eligibility_check AS (
    -- Get eligibility status for all employees
    SELECT
        employee_id,
        simulation_year,
        eligible_for_core,
        eligible_for_contributions,
        annual_hours_worked
    FROM {{ ref('int_employer_eligibility') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
),

-- Termination flags for the year (to defensively prevent leakage)
termination_flags AS (
    -- Use consolidated yearly events to align with snapshot status and avoid gaps
    SELECT
        emp.employee_id,
        MAX(CASE WHEN fe.event_category = 'new_hire_termination' THEN TRUE ELSE FALSE END) AS has_new_hire_termination,
        MAX(CASE WHEN fe.event_category = 'experienced_termination' THEN TRUE ELSE FALSE END) AS has_experienced_termination
    FROM (
        SELECT DISTINCT employee_id FROM population WHERE simulation_year = {{ simulation_year }}
    ) emp
    LEFT JOIN {{ ref('fct_yearly_events') }} fe
        ON emp.employee_id = fe.employee_id AND fe.simulation_year = {{ simulation_year }}
    GROUP BY emp.employee_id
),

-- Snapshot-derived status flags to align with final classification
-- Extended to include years_of_service for service-based core contribution tiers
snapshot_flags AS (
    SELECT
        employee_id,
        detailed_status_code,
        FLOOR(COALESCE(current_tenure, 0))::INT AS years_of_service
    FROM {{ ref('int_workforce_snapshot_optimized') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- Main query with window function for deduplication
core_contributions AS (
SELECT
    pop.employee_id,
    pop.simulation_year,
    -- Prefer workforce proration; else use population prorated value; else fall back to employee compensation
    COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation) AS eligible_compensation,
    COALESCE(wf.employment_status, pop.employment_status) AS employment_status,
    elig.eligible_for_core,
    elig.annual_hours_worked,

    -- Core contribution calculation
    -- Configurable rate for eligible employees
    CASE
        WHEN {{ employer_core_enabled }}
            AND COALESCE(elig.eligible_for_core, FALSE) = TRUE
            AND COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation) > 0
            -- Enforce EOY active unless exceptions are allowed
            AND (
                {% if core_require_active_eoy %}
                    COALESCE(wf.employment_status, pop.employment_status) = 'active'
                    OR (
                        (COALESCE(term.has_new_hire_termination, FALSE) AND ({{ 'true' if core_allow_terminated_new_hires else 'false' }}))
                        OR (COALESCE(term.has_experienced_termination, FALSE) AND ({{ 'true' if core_allow_experienced_terminations else 'false' }}))
                    )
                {% else %}
                    TRUE
                {% endif %}
            )
            -- Defensive guardrails: disallow terminations unless explicitly enabled
            -- STRENGTHENED: Ensure new hire terminations are properly excluded when not allowed
            AND (
                (COALESCE(term.has_new_hire_termination, FALSE) = FALSE OR ({{ 'true' if core_allow_terminated_new_hires else 'false' }}))
            )
            AND (
                (COALESCE(term.has_experienced_termination, FALSE) = FALSE OR ({{ 'true' if core_allow_experienced_terminations else 'false' }}))
            )
            AND (
                -- Align with snapshot classification when available
                COALESCE(snap.detailed_status_code NOT IN ('experienced_termination', 'new_hire_termination'), TRUE)
                OR (
                    (snap.detailed_status_code = 'new_hire_termination' AND ({{ 'true' if core_allow_terminated_new_hires else 'false' }}))
                    OR (snap.detailed_status_code = 'experienced_termination' AND ({{ 'true' if core_allow_experienced_terminations else 'false' }}))
                )
            )
        THEN ROUND(
            COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation) *
            {% if employer_core_status == 'graded_by_service' and employer_core_graded_schedule | length > 0 %}
            {{ get_tiered_core_rate('COALESCE(snap.years_of_service, 0)', employer_core_graded_schedule, employer_core_contribution_rate) }}
            {% else %}
            {{ employer_core_contribution_rate }}
            {% endif %}
        , 2)
        ELSE 0.00
    END AS employer_core_amount,

    -- Contribution rate for reference
    CASE
        WHEN {{ employer_core_enabled }}
             AND COALESCE(elig.eligible_for_core, FALSE) = TRUE
             AND (
                {% if core_require_active_eoy %}
                    COALESCE(wf.employment_status, pop.employment_status) = 'active'
                    OR (
                        (COALESCE(term.has_new_hire_termination, FALSE) AND ({{ 'true' if core_allow_terminated_new_hires else 'false' }}))
                        OR (COALESCE(term.has_experienced_termination, FALSE) AND ({{ 'true' if core_allow_experienced_terminations else 'false' }}))
                    )
                {% else %}
                    TRUE
                {% endif %}
             )
             AND (COALESCE(term.has_new_hire_termination, FALSE) = FALSE OR ({{ 'true' if core_allow_terminated_new_hires else 'false' }}))
             AND (COALESCE(term.has_experienced_termination, FALSE) = FALSE OR ({{ 'true' if core_allow_experienced_terminations else 'false' }}))
             AND (
                COALESCE(snap.detailed_status_code NOT IN ('experienced_termination', 'new_hire_termination'), TRUE)
                OR (
                    (snap.detailed_status_code = 'new_hire_termination' AND ({{ 'true' if core_allow_terminated_new_hires else 'false' }}))
                    OR (snap.detailed_status_code = 'experienced_termination' AND ({{ 'true' if core_allow_experienced_terminations else 'false' }}))
                )
             )
        THEN
            {% if employer_core_status == 'graded_by_service' and employer_core_graded_schedule | length > 0 %}
            {{ get_tiered_core_rate('COALESCE(snap.years_of_service, 0)', employer_core_graded_schedule, employer_core_contribution_rate) }}
            {% else %}
            {{ employer_core_contribution_rate }}
            {% endif %}
        ELSE 0.00
    END AS core_contribution_rate,

    -- Metadata
    CASE
        WHEN {{ employer_core_enabled }} THEN 'configurable_rate'
        ELSE 'disabled'
    END AS contribution_method,
    {{ employer_core_contribution_rate }} AS standard_core_rate,
    -- Audit trail: years of service used for tier lookup
    COALESCE(snap.years_of_service, 0) AS applied_years_of_service,
    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id,
    ROW_NUMBER() OVER (
        PARTITION BY pop.employee_id, pop.simulation_year
        ORDER BY pop.employee_id
    ) AS rn

FROM population pop
LEFT JOIN workforce_proration wf
    ON pop.employee_id = wf.employee_id AND pop.simulation_year = wf.simulation_year
LEFT JOIN eligibility_check elig
    ON pop.employee_id = elig.employee_id
    AND pop.simulation_year = elig.simulation_year
LEFT JOIN termination_flags term
    ON pop.employee_id = term.employee_id
LEFT JOIN snapshot_flags snap
    ON pop.employee_id = snap.employee_id
)

-- Final SELECT - deduplicate in case a new hire is also present in compensation snapshot (year 1)
SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    employment_status,
    eligible_for_core,
    annual_hours_worked,
    employer_core_amount,
    core_contribution_rate,
    contribution_method,
    standard_core_rate,
    applied_years_of_service,
    created_at,
    scenario_id,
    parameter_scenario_id
FROM core_contributions
WHERE rn = 1
