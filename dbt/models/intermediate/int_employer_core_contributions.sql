{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ],
    tags=['employer_contributions', 'core_contributions', 'mvp', 'BENEFIT_CALCULATION']
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
  - Contribution-specific compensation basis derived from canonical workforce state
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

  Workforce status, dates, tenure, age, and population are owned by
  int_workforce_state_accumulator. The starting-compensation fact is retained only
  to preserve the accepted core contribution basis independently of deferral state.
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}
{% set employer_core_enabled = var('employer_core_enabled', true) %}
{% set employer_core_contribution_rate = var('employer_core_contribution_rate', 0.02) %}
{% set employer_core_status = var('employer_core_status', 'flat') %}
{% set employer_core_graded_schedule = var('employer_core_graded_schedule', []) %}
{% set employer_core_points_schedule = var('employer_core_points_schedule', []) %}

-- Read nested core config for termination exceptions, with flat var fallbacks
{% set employer_core_config = var('employer_core_contribution', {}) %}
{% set core_eligibility = employer_core_config.get('eligibility', {}) %}
{% set core_allow_terminated_new_hires = core_eligibility.get('allow_terminated_new_hires', var('core_allow_terminated_new_hires', false)) %}
{% set core_allow_experienced_terminations = core_eligibility.get('allow_experienced_terminations', var('core_allow_experienced_terminations', false)) %}
{% set core_require_active_eoy = core_eligibility.get('require_active_at_year_end', var('core_require_active_eoy', true)) %}

-- E026: IRS Section 401(a)(17) compensation limit for employer contributions
WITH irs_compensation_limits AS (
    SELECT
        limit_year,
        compensation_limit AS irs_401a17_limit
    FROM {{ ref('config_irs_limits') }}
    WHERE limit_year = {{ simulation_year }}
),

starting_compensation AS (
    SELECT
        employee_id,
        ARG_MIN(
            CASE
                WHEN event_type = 'hire' THEN compensation_amount
                WHEN event_type IN ('promotion', 'raise') THEN previous_compensation
            END,
            effective_date
        ) FILTER (WHERE event_type IN ('hire', 'promotion', 'raise'))
            AS starting_compensation
    FROM {{ ref('fct_yearly_events') }}
    WHERE scenario_id = '{{ scenario_id }}'
      AND plan_design_id = '{{ plan_design_id }}'
      AND simulation_year = {{ simulation_year }}
    GROUP BY employee_id
),

population AS (
    SELECT
        workforce.employee_id,
        workforce.simulation_year,
        COALESCE(starting.starting_compensation, workforce.current_compensation)
            AS employee_compensation,
        CASE
            WHEN EXTRACT(YEAR FROM workforce.employee_hire_date)
                = {{ simulation_year }} THEN
                ROUND(
                    COALESCE(
                        starting.starting_compensation,
                        workforce.current_compensation
                    ) * LEAST(365, GREATEST(0,
                        DATEDIFF(
                            'day',
                            workforce.employee_hire_date::DATE,
                            COALESCE(
                                workforce.termination_date::DATE,
                                '{{ simulation_year }}-12-31'::DATE
                            )
                        ) + 1
                    )) / 365.0,
                    2
                )
            ELSE COALESCE(
                starting.starting_compensation,
                workforce.current_compensation
            )
        END AS prorated_annual_compensation,
        CASE
            WHEN workforce.detailed_status_code = 'experienced_termination'
                THEN 'active'
            ELSE workforce.employment_status
        END AS employment_status,
        CASE
            WHEN workforce.detailed_status_code = 'experienced_termination'
                THEN GREATEST(
                    workforce.current_tenure,
                    prior_workforce.current_tenure + 1
                )
            ELSE workforce.current_tenure
        END AS current_tenure,
        workforce.current_age,
        workforce.detailed_status_code,
        workforce.termination_date::DATE AS termination_date
    FROM {{ ref('int_workforce_state_accumulator') }} workforce
    LEFT JOIN {{ ref('int_workforce_state_accumulator') }} prior_workforce
      ON prior_workforce.scenario_id = workforce.scenario_id
     AND prior_workforce.plan_design_id = workforce.plan_design_id
     AND prior_workforce.employee_id = workforce.employee_id
     AND prior_workforce.simulation_year = {{ simulation_year - 1 }}
    LEFT JOIN starting_compensation starting
      ON workforce.employee_id = starting.employee_id
    WHERE workforce.scenario_id = '{{ scenario_id }}'
      AND workforce.plan_design_id = '{{ plan_design_id }}'
      AND workforce.simulation_year = {{ simulation_year }}
      AND workforce.employee_id IS NOT NULL
),

workforce_proration AS (
    SELECT
        employee_id,
        simulation_year,
        employee_compensation AS current_compensation,
        prorated_annual_compensation,
        employment_status,
        termination_date
    FROM population
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
    SELECT
        employee_id,
        detailed_status_code = 'new_hire_termination'
            AS has_new_hire_termination,
        detailed_status_code = 'experienced_termination'
            AS has_experienced_termination
    FROM population
),

-- Snapshot-derived status flags to align with final classification
-- Extended to include years_of_service for service-based core contribution tiers
snapshot_flags AS (
    SELECT
        employee_id,
        detailed_status_code,
        FLOOR(COALESCE(current_tenure, 0))::INT AS years_of_service,
        current_age
    FROM population
),

-- Main query with window function for deduplication
-- E026: Added IRS 401(a)(17) compensation limit enforcement
core_contributions AS (
SELECT
    pop.employee_id,
    pop.simulation_year,
    -- Prefer workforce proration; else use population prorated value; else fall back to employee compensation
    COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation) AS eligible_compensation,
    COALESCE(wf.employment_status, pop.employment_status) AS employment_status,
    elig.eligible_for_core,
    elig.annual_hours_worked,
    -- E026: IRS 401(a)(17) limit for audit trail
    lim.irs_401a17_limit,
    -- E026: Track if 401(a)(17) limit was applied
    COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation) > lim.irs_401a17_limit AS irs_401a17_limit_applied,

    -- Core contribution calculation
    -- Configurable rate for eligible employees
    -- E026: Apply 401(a)(17) cap to compensation used in calculation
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
            -- E026: Use LEAST(compensation, 401a17_limit) to cap at IRS limit
            LEAST(
                COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation),
                lim.irs_401a17_limit
            ) *
            {% if employer_core_status == 'points_based' and employer_core_points_schedule | length > 0 %}
            {{ get_points_based_match_rate('(FLOOR(COALESCE(snap.current_age, 0))::INT + FLOOR(COALESCE(snap.years_of_service, FLOOR(COALESCE(pop.current_tenure, 0))::INT))::INT)', employer_core_points_schedule, employer_core_contribution_rate) }}
            {% elif employer_core_status == 'graded_by_service' and employer_core_graded_schedule | length > 0 %}
            {{ get_tiered_core_rate('COALESCE(snap.years_of_service, FLOOR(COALESCE(pop.current_tenure, 0))::INT)', employer_core_graded_schedule, employer_core_contribution_rate) }}
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
            {% if employer_core_status == 'points_based' and employer_core_points_schedule | length > 0 %}
            {{ get_points_based_match_rate('(FLOOR(COALESCE(snap.current_age, 0))::INT + FLOOR(COALESCE(snap.years_of_service, FLOOR(COALESCE(pop.current_tenure, 0))::INT))::INT)', employer_core_points_schedule, employer_core_contribution_rate) }}
            {% elif employer_core_status == 'graded_by_service' and employer_core_graded_schedule | length > 0 %}
            {{ get_tiered_core_rate('COALESCE(snap.years_of_service, FLOOR(COALESCE(pop.current_tenure, 0))::INT)', employer_core_graded_schedule, employer_core_contribution_rate) }}
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
    COALESCE(snap.years_of_service, FLOOR(COALESCE(pop.current_tenure, 0))::INT) AS applied_years_of_service,
    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id,
    ROW_NUMBER() OVER (
        PARTITION BY pop.employee_id, pop.simulation_year
        ORDER BY pop.employee_id
    ) AS rn

FROM population pop
-- E026: CROSS JOIN is safe here because irs_compensation_limits CTE filters to a single
-- simulation_year, guaranteeing exactly one row. This provides the 401(a)(17) limit constant.
CROSS JOIN irs_compensation_limits lim
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
    -- E026: IRS 401(a)(17) compliance fields
    irs_401a17_limit,
    irs_401a17_limit_applied,
    created_at,
    scenario_id,
    parameter_scenario_id
FROM core_contributions
WHERE rn = 1
