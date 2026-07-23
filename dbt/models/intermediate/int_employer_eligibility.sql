{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ],
    tags=['employer_contributions', 'eligibility', 'BENEFIT_CALCULATION']
) }}

/*
  Employer Contribution Eligibility Model - Story S039-01
  Enhanced with Epic E058: Employer Match Eligibility Configuration

  Determines eligibility for employer contributions (both match and core)
  with sophisticated business rules:
  - Prorated hours calculation based on actual employment periods
  - Configurable tenure, hours, and employment status requirements
  - Support for new hire and termination exceptions
  - Independent configuration for match vs core eligibility

  Epic E058 Phase 1 Changes:
  - Added sophisticated match eligibility logic with backward compatibility
  - Configurable parameters via employer_match.eligibility in simulation_config.yaml
  - Backward compatibility toggle (apply_eligibility: false by default)
  - Match eligibility reason codes for auditability
  - Independent from core eligibility configuration

  Key Features:
  - Backward compatibility: When apply_eligibility=false, uses simple active+1000 hours rule
  - Sophisticated eligibility: When apply_eligibility=true, applies configurable rules
  - Audit trail: match_eligibility_reason provides detailed reason codes
  - Metadata: All configuration parameters included for transparency
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}

-- Read employer core contribution config from nested structure
{% set employer_core_config = var('employer_core_contribution', {}) %}
{% set core_eligibility = employer_core_config.get('eligibility', {}) %}

-- Extract core eligibility parameters with defaults
{% set core_minimum_tenure_years = core_eligibility.get('minimum_tenure_years', 1) | int %}
{% set core_require_active_eoy = core_eligibility.get('require_active_at_year_end', true) %}
{% set core_minimum_hours = core_eligibility.get('minimum_hours_annual', 1000) | int %}
{# E047: Default allow_new_hires to false when tenure requirement exists #}
{% set core_allow_new_hires_raw = core_eligibility.get('allow_new_hires', none) %}
{% if core_allow_new_hires_raw is none %}
    {% set core_allow_new_hires = (core_minimum_tenure_years == 0) %}
{% else %}
    {% set core_allow_new_hires = core_allow_new_hires_raw %}
{% endif %}
{% set core_allow_terminated_new_hires = core_eligibility.get('allow_terminated_new_hires', false) %}
{% set core_allow_experienced_terminations = core_eligibility.get('allow_experienced_terminations', false) %}

-- Epic E058: Read employer match eligibility configuration
{% set employer_match_config = var('employer_match', {}) %}
{% set match_apply_eligibility = employer_match_config.get('apply_eligibility', false) %}
{% set match_eligibility = employer_match_config.get('eligibility', {}) %}

-- Extract match eligibility parameters with defaults
{% set match_minimum_tenure_years = match_eligibility.get('minimum_tenure_years', 0) | int %}
{% set match_require_active_eoy = match_eligibility.get('require_active_at_year_end', true) %}
{% set match_minimum_hours = match_eligibility.get('minimum_hours_annual', 1000) | int %}
{# E047: Default allow_new_hires to false when tenure requirement exists #}
{% set match_allow_new_hires_raw = match_eligibility.get('allow_new_hires', none) %}
{% if match_allow_new_hires_raw is none %}
    {% set match_allow_new_hires = (match_minimum_tenure_years == 0) %}
{% else %}
    {% set match_allow_new_hires = match_allow_new_hires_raw %}
{% endif %}
{% set match_allow_terminated_new_hires = match_eligibility.get('allow_terminated_new_hires', false) %}
{% set match_allow_experienced_terminations = match_eligibility.get('allow_experienced_terminations', false) %}

-- Eligibility consumes canonical end-of-year workforce state. It no longer
-- reconstructs workforce status, tenure, scheduling, or event dates independently.
WITH hours_calculation AS (
SELECT
    workforce.employee_id,
    {{ simulation_year }} AS simulation_year,
    -- Preserve the existing decision-year tenure convention: later-year
    -- compensation helpers increment prior accepted tenure twice.
    COALESCE(prior_workforce.current_tenure + 2, workforce.current_tenure)
        AS current_tenure,
    workforce.employee_hire_date,
    workforce.termination_date,
    workforce.detailed_status_code = 'new_hire_termination'
        AS has_new_hire_termination,
    workforce.detailed_status_code = 'experienced_termination'
        AS has_experienced_termination,
    workforce.scheduled_hours_per_week,

    -- Identify new hires within the simulation year
    EXTRACT(YEAR FROM workforce.employee_hire_date) = {{ simulation_year }}
        AS is_new_hire_this_year,

    workforce.employment_status AS employment_status_eoy,

    -- Calculate prorated annual hours based on actual employment period
    CASE
        WHEN EXTRACT(YEAR FROM workforce.employee_hire_date) = {{ simulation_year }}
             AND (
               workforce.termination_date IS NULL
               OR workforce.detailed_status_code = 'new_hire_termination'
             ) THEN
            GREATEST(0,
                DATEDIFF('day',
                    workforce.employee_hire_date::DATE,
                    '{{ simulation_year }}-12-31'::DATE
                ) + 1
            ) * (COALESCE(workforce.scheduled_hours_per_week, 40.0) * 52.0 / 365.0)

        WHEN workforce.termination_date IS NOT NULL
             AND workforce.termination_date::DATE <= '{{ simulation_year }}-12-31'::DATE THEN
            GREATEST(0,
                DATEDIFF('day',
                    GREATEST(
                        COALESCE(workforce.employee_hire_date::DATE, '{{ simulation_year }}-01-01'::DATE),
                        '{{ simulation_year }}-01-01'::DATE
                    ),
                    workforce.termination_date::DATE
                ) + 1
            ) * (COALESCE(workforce.scheduled_hours_per_week, 40.0) * 52.0 / 365.0)

        ELSE COALESCE(workforce.scheduled_hours_per_week, 40.0) * 52.0
    END AS annual_hours_worked
FROM {{ ref('int_workforce_state_accumulator') }} workforce
LEFT JOIN {{ ref('int_workforce_state_accumulator') }} prior_workforce
  ON prior_workforce.scenario_id = workforce.scenario_id
 AND prior_workforce.plan_design_id = workforce.plan_design_id
 AND prior_workforce.employee_id = workforce.employee_id
 AND prior_workforce.simulation_year = {{ simulation_year - 1 }}
WHERE workforce.scenario_id = '{{ scenario_id }}'
  AND workforce.plan_design_id = '{{ plan_design_id }}'
  AND workforce.simulation_year = {{ simulation_year }}
  AND workforce.employee_id IS NOT NULL
)

SELECT
    employee_id,
    simulation_year,
    employment_status_eoy AS employment_status,
    current_tenure,
    scheduled_hours_per_week,
    ROUND(annual_hours_worked, 0)::INTEGER AS annual_hours_worked,

    -- Epic E058: Match eligibility with backward compatibility and sophisticated logic
    CASE
        -- Backward compatibility mode: use simple logic when apply_eligibility is false
        WHEN NOT {{ match_apply_eligibility }} THEN
            CASE
                WHEN employment_status_eoy = 'active' AND annual_hours_worked >= 1000 THEN TRUE
                ELSE FALSE
            END
        -- Sophisticated match eligibility logic when apply_eligibility is true
        WHEN annual_hours_worked >= {{ match_minimum_hours }}
         AND (
              -- Meets tenure normally
              current_tenure >= {{ match_minimum_tenure_years }}
              -- or allowed as a new hire this year
              OR ({{ 'true' if match_allow_new_hires else 'false' }} AND is_new_hire_this_year)
         )
         AND (
              -- Require active at EOY unless exceptions are allowed
              {% if match_require_active_eoy %}
                  employment_status_eoy = 'active'
                  OR ({{ 'true' if match_allow_terminated_new_hires else 'false' }} AND is_new_hire_this_year AND employment_status_eoy = 'terminated')
                  OR ({{ 'true' if match_allow_experienced_terminations else 'false' }} AND NOT is_new_hire_this_year AND employment_status_eoy = 'terminated')
              {% else %}
                  TRUE
              {% endif %}
         )
         -- If not allowed, exclude employees flagged as new-hire terminations even when termination is next year
         AND (
               {% if match_allow_terminated_new_hires %}
                   TRUE
               {% else %}
                   NOT (is_new_hire_this_year AND COALESCE(has_new_hire_termination, FALSE))
               {% endif %}
         )
         -- If not allowed, exclude employees with experienced termination in the current year
         AND (
                {% if match_allow_experienced_terminations %}
                    TRUE
                {% else %}
                    NOT (NOT is_new_hire_this_year AND COALESCE(has_experienced_termination, FALSE))
                {% endif %}
         )
        THEN TRUE
        ELSE FALSE
    END AS eligible_for_match,

    -- Epic E058: Match eligibility reason codes for auditability
    CASE
        -- Backward compatibility mode
        WHEN NOT {{ match_apply_eligibility }} THEN
            CASE
                WHEN employment_status_eoy = 'active' AND annual_hours_worked >= 1000 THEN 'backward_compatibility_simple_rule'
                WHEN employment_status_eoy != 'active' THEN 'backward_compatibility_simple_rule'
                WHEN annual_hours_worked < 1000 THEN 'backward_compatibility_simple_rule'
                ELSE 'backward_compatibility_simple_rule'
            END
        -- Sophisticated eligibility mode reasons
        WHEN annual_hours_worked < {{ match_minimum_hours }} THEN 'insufficient_hours'
        WHEN current_tenure < {{ match_minimum_tenure_years }}
             AND NOT ({{ 'true' if match_allow_new_hires else 'false' }} AND is_new_hire_this_year) THEN 'insufficient_tenure'
        {% if match_require_active_eoy %}
        WHEN employment_status_eoy != 'active'
             AND NOT ({{ 'true' if match_allow_terminated_new_hires else 'false' }} AND is_new_hire_this_year AND employment_status_eoy = 'terminated')
             AND NOT ({{ 'true' if match_allow_experienced_terminations else 'false' }} AND NOT is_new_hire_this_year AND employment_status_eoy = 'terminated') THEN 'inactive_eoy'
        {% endif %}
        {% if not match_allow_terminated_new_hires %}
        WHEN is_new_hire_this_year AND COALESCE(has_new_hire_termination, FALSE) THEN 'inactive_eoy'
        {% endif %}
        {% if not match_allow_experienced_terminations %}
        WHEN NOT is_new_hire_this_year AND COALESCE(has_experienced_termination, FALSE) THEN 'inactive_eoy'
        {% endif %}
        ELSE 'eligible'
    END AS match_eligibility_reason,

    -- Core eligibility: allow configurable exceptions for new hires and their terminations
    CASE
        WHEN annual_hours_worked >= {{ core_minimum_hours }}
         AND (
              -- Meets tenure normally
              current_tenure >= {{ core_minimum_tenure_years }}
              -- or allowed as a new hire this year
              OR ({{ 'true' if core_allow_new_hires else 'false' }} AND is_new_hire_this_year)
         )
         AND (
              -- Require active at EOY unless exceptions are allowed
              {% if core_require_active_eoy %}
                  employment_status_eoy = 'active'
                  OR ({{ 'true' if core_allow_terminated_new_hires else 'false' }} AND is_new_hire_this_year AND employment_status_eoy = 'terminated')
                  OR ({{ 'true' if core_allow_experienced_terminations else 'false' }} AND NOT is_new_hire_this_year AND employment_status_eoy = 'terminated')
              {% else %}
                  TRUE
              {% endif %}
         )
         -- If not allowed, exclude employees flagged as new-hire terminations even when termination is next year
         AND (
               {% if core_allow_terminated_new_hires %}
                   TRUE
               {% else %}
                   NOT (is_new_hire_this_year AND COALESCE(has_new_hire_termination, FALSE))
               {% endif %}
         )
         -- If not allowed, exclude employees with experienced termination in the current year
         AND (
                {% if core_allow_experienced_terminations %}
                    TRUE
                {% else %}
                    NOT (NOT is_new_hire_this_year AND COALESCE(has_experienced_termination, FALSE))
                {% endif %}
         )
        THEN TRUE
        ELSE FALSE
    END AS eligible_for_core,

    -- Combined eligibility flag for convenience (uses match criteria for backward compatibility)
    CASE
        WHEN employment_status_eoy = 'active' AND annual_hours_worked >= 1000 THEN TRUE
        ELSE FALSE
    END AS eligible_for_contributions,

    -- Metadata
    'prorated_hours_with_tenure' AS eligibility_method,

    -- Core eligibility metadata
    {{ core_minimum_tenure_years }} AS core_tenure_requirement,
    {{ core_minimum_hours }} AS core_hours_requirement,
    {{ core_require_active_eoy }} AS core_requires_active_eoy,
    {{ core_allow_new_hires }} AS core_allow_new_hires,
    {{ core_allow_terminated_new_hires }} AS core_allow_terminated_new_hires,
    {{ core_allow_experienced_terminations }} AS core_allow_experienced_terminations,

    -- Epic E058: Match eligibility metadata
    {{ match_apply_eligibility }} AS match_apply_eligibility,
    {{ match_minimum_tenure_years }} AS match_tenure_requirement,
    {{ match_minimum_hours }} AS match_hours_requirement,
    {{ match_require_active_eoy }} AS match_requires_active_eoy,
    {{ match_allow_new_hires }} AS match_allow_new_hires,
    {{ match_allow_terminated_new_hires }} AS match_allow_terminated_new_hires,
    {{ match_allow_experienced_terminations }} AS match_allow_experienced_terminations,

    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id

FROM hours_calculation
ORDER BY employee_id
