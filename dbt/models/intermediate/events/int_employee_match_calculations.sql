{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ],
    tags=['match_engine', 'critical', 'core_calculation']
) }}

/*
  Employee Match Calculation Model - Story S025-02

  Calculates employer match amounts based on configurable formulas:
  - Simple percentage match (e.g., 50% of deferrals)
  - Tiered match (100% on first 3%, 50% on next 2%)
  - Maximum match caps (% of compensation)

  Integrates with employee contributions from int_employee_contributions
  to determine match amounts based on actual deferral rates.

  Performance: Optimized for 100K+ employees using DuckDB columnar processing
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

-- Get match formula configuration from variables
-- These variables should be passed from the orchestrator which reads from simulation_config.yaml
-- Fallback values match the default configuration in simulation_config.yaml
{% set active_formula = var('active_match_formula', 'simple_match') %}
{% set match_formulas = var('match_formulas', {
    'simple_match': {
        'name': 'Simple Match',
        'type': 'simple',
        'match_rate': 0.50,
        'max_match_percentage': 0.03
    },
    'tiered_match': {
        'name': 'Tiered Match',
        'type': 'tiered',
        'tiers': [
            {'tier': 1, 'employee_min': 0.00, 'employee_max': 0.03, 'match_rate': 1.00},
            {'tier': 2, 'employee_min': 0.03, 'employee_max': 0.05, 'match_rate': 0.50}
        ],
        'max_match_percentage': 0.04
    },
    'stretch_match': {
        'name': 'Stretch Match (Encourages Higher Deferrals)',
        'type': 'tiered',
        'tiers': [
            {'tier': 1, 'employee_min': 0.00, 'employee_max': 0.12, 'match_rate': 0.25}
        ],
        'max_match_percentage': 0.03
    },
    'enhanced_tiered': {
        'name': 'Enhanced Tiered Match',
        'type': 'tiered',
        'tiers': [
            {'tier': 1, 'employee_min': 0.00, 'employee_max': 0.03, 'match_rate': 1.00},
            {'tier': 2, 'employee_min': 0.03, 'employee_max': 0.05, 'match_rate': 0.50}
        ],
        'max_match_percentage': 0.04
    }
}) %}

-- Debug: Current match formula configuration
-- Active formula: {{ active_formula }}
-- Formula type: {{ match_formulas[active_formula]['type'] }}

WITH employee_contributions AS (
    -- Get ALL employee contribution data (including non-enrolled with 0 contributions)
    SELECT
        ec.employee_id,
        ec.simulation_year,
        ec.annual_contribution_amount AS annual_deferrals,
        ec.prorated_annual_compensation AS eligible_compensation,
        ec.effective_annual_deferral_rate AS deferral_rate,
        ec.is_enrolled_flag AS is_enrolled,
        ec.first_contribution_date AS enrollment_date,
        ec.current_age AS age_as_of_december_31,
        ec.employment_status
    FROM {{ ref('int_employee_contributions') }}  ec
    WHERE ec.simulation_year = {{ simulation_year }}
        AND ec.employee_id IS NOT NULL
),

{% if match_formulas[active_formula]['type'] == 'simple' %}
-- Simple match calculation
simple_match AS (
    SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        -- Simple percentage match with correct cap semantics:
        -- Employer match = match_rate * min(deferral_rate, max_match_percentage) * eligible_compensation,
        -- but never more than match_rate * (max_match_percentage * eligible_compensation)
        -- Using annual_deferrals ensures match is based on actual deferrals made (IRS-limited when applicable)
        LEAST(
            annual_deferrals * {{ match_formulas[active_formula]['match_rate'] }},
            (eligible_compensation * {{ match_formulas[active_formula]['max_match_percentage'] }}) * {{ match_formulas[active_formula]['match_rate'] }}
        ) AS match_amount,
        'simple' AS formula_type
    FROM employee_contributions
),

{% elif match_formulas[active_formula]['type'] == 'tiered' %}
-- Tiered match calculation using DuckDB's powerful window functions
tiered_match AS (
    SELECT
        ec.employee_id,
        ec.simulation_year,
        ec.eligible_compensation,
        ec.deferral_rate,
        ec.annual_deferrals,
        -- Calculate match for each tier
        SUM(
            CASE
                WHEN ec.deferral_rate > tier.employee_min
                THEN LEAST(
                    ec.deferral_rate - tier.employee_min,
                    tier.employee_max - tier.employee_min
                ) * tier.match_rate * ec.eligible_compensation
                ELSE 0
            END
        ) AS match_amount,
        'tiered' AS formula_type
    FROM employee_contributions ec
    CROSS JOIN (
        {% for tier in match_formulas[active_formula]['tiers'] %}
        SELECT
            {{ tier['tier'] }} AS tier_number,
            {{ tier['employee_min'] }} AS employee_min,
            {{ tier['employee_max'] }} AS employee_max,
            {{ tier['match_rate'] }} AS match_rate
        {% if not loop.last %}UNION ALL{% endif %}
        {% endfor %}
    ) AS tier
    GROUP BY ec.employee_id, ec.simulation_year, ec.eligible_compensation,
             ec.deferral_rate, ec.annual_deferrals
),

{% endif %}

-- Unified all_matches CTE - selects from the appropriate match calculation above
all_matches AS (
    {% if match_formulas[active_formula]['type'] == 'simple' %}
    SELECT * FROM simple_match
    {% elif match_formulas[active_formula]['type'] == 'tiered' %}
    SELECT * FROM tiered_match
    {% else %}
    SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        0 AS match_amount,
        'none' AS formula_type
    FROM employee_contributions
    {% endif %}
),

-- Apply match caps
final_match AS (
    SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        formula_type,
        -- Apply maximum match cap. For 'simple', cap is match_rate × (max matched deferral % × comp).
        -- For 'tiered' and other types, cap is employer % of comp directly.
        LEAST(
            match_amount,
            CASE
                WHEN formula_type = 'simple' THEN
                    (eligible_compensation * {{ match_formulas[active_formula]['max_match_percentage'] }}) * {{ match_formulas[active_formula]['match_rate'] }}
                ELSE
                    eligible_compensation * {{ match_formulas[active_formula]['max_match_percentage'] }}
            END
        ) AS employer_match_amount,
        -- Track if cap was applied
        CASE
            WHEN formula_type = 'simple' THEN
                match_amount > (eligible_compensation * {{ match_formulas[active_formula]['max_match_percentage'] }}) * {{ match_formulas[active_formula]['match_rate'] }}
            ELSE
                match_amount > eligible_compensation * {{ match_formulas[active_formula]['max_match_percentage'] }}
            END AS match_cap_applied,
        -- Calculate uncapped match for analysis
        match_amount AS uncapped_match_amount
    FROM all_matches
)

SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    ROUND(deferral_rate, 4) AS deferral_rate,
    ROUND(annual_deferrals, 2) AS annual_deferrals,
    ROUND(employer_match_amount, 2) AS employer_match_amount,
    ROUND(uncapped_match_amount, 2) AS uncapped_match_amount,
    formula_type,
    match_cap_applied,
    '{{ active_formula }}' AS formula_id,
    '{{ match_formulas[active_formula]["name"] }}' AS formula_name,
    -- Calculate effective match rate
    CASE
        WHEN annual_deferrals > 0
        THEN ROUND(employer_match_amount / annual_deferrals, 4)
        ELSE 0
    END AS effective_match_rate,
    -- Calculate match as percentage of compensation
    CASE
        WHEN eligible_compensation > 0
        THEN ROUND(employer_match_amount / eligible_compensation, 4)
        ELSE 0
    END AS match_percentage_of_comp,
    -- Metadata
    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id
FROM final_match
WHERE employee_id IS NOT NULL
ORDER BY employee_id
