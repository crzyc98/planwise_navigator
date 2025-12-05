{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ],
    tags=['match_engine', 'critical', 'core_calculation', 'STATE_ACCUMULATION']
) }}

/*
  Employee Match Calculation Model - Story S025-02
  Enhanced with Epic E058 Phase 2: Match Calculation Integration

  Calculates employer match amounts based on configurable formulas:
  - Simple percentage match (e.g., 50% of deferrals)
  - Tiered match (100% on first 3%, 50% on next 2%)
  - Maximum match caps (% of compensation)

  Epic E058 Phase 2 Enhancements:
  - Integrates with int_employer_eligibility for match eligibility determination
  - Applies eligibility filtering: ineligible employees receive $0 match
  - Adds match_status tracking: 'ineligible', 'no_deferrals', 'calculated'
  - Maintains backward compatibility with existing formula logic
  - Preserves audit trail with eligibility reason codes

  Key Features:
  - Zero match for ineligible employees when apply_eligibility=true
  - Preserves existing match formulas and calculation logic
  - Efficient LEFT JOIN on indexed columns (employee_id, simulation_year)
  - Clear audit trail for match calculation outcomes
  - Backward compatibility: identical behavior when apply_eligibility=false

  Performance: Optimized for 100K+ employees using DuckDB columnar processing
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

/*
  E084 Phase B: Match configuration now accepts custom tiers directly
  Variables:
  - match_tiers: Array of tier definitions [{ employee_min, employee_max, match_rate }, ...]
  - match_cap_percent: Maximum employer match as percentage of compensation (decimal)
  - match_template: Template name for audit trail (simple, tiered, stretch, safe_harbor, qaca)

  Backward Compatibility:
  - Falls back to tiered match (100% on 0-3%, 50% on 3-5%) if no custom tiers provided
*/

-- E084 Phase B: Direct tier configuration (replaces formula name lookup)
{% set match_tiers = var('match_tiers', [
    {'employee_min': 0.00, 'employee_max': 0.03, 'match_rate': 1.00},
    {'employee_min': 0.03, 'employee_max': 0.05, 'match_rate': 0.50}
]) %}
{% set match_cap_percent = var('match_cap_percent', 0.04) %}
{% set match_template = var('match_template', 'tiered') %}

-- Debug: Current match configuration
-- Template: {{ match_template }}
-- Match cap: {{ match_cap_percent * 100 }}% of compensation
-- Tiers: {{ match_tiers | length }} defined

WITH employee_contributions AS (
    -- Get ALL employee contribution data with eligibility determination (Epic E058 Phase 2)
    SELECT
        ec.employee_id,
        ec.simulation_year,
        ec.annual_contribution_amount AS annual_deferrals,
        ec.prorated_annual_compensation AS eligible_compensation,
        ec.effective_annual_deferral_rate AS deferral_rate,
        ec.is_enrolled_flag AS is_enrolled,
        ec.first_contribution_date AS enrollment_date,
        ec.current_age AS age_as_of_december_31,
        ec.employment_status,
        -- Epic E058 Phase 2: Join with employer eligibility determination
        COALESCE(elig.eligible_for_match, FALSE) AS is_eligible_for_match,
        elig.match_eligibility_reason,
        elig.match_apply_eligibility AS eligibility_config_applied
    FROM {{ ref('int_employee_contributions') }}  ec
    LEFT JOIN {{ ref('int_employer_eligibility') }} elig
        ON ec.employee_id = elig.employee_id
       AND ec.simulation_year = elig.simulation_year
    WHERE ec.simulation_year = {{ simulation_year }}
        AND ec.employee_id IS NOT NULL
),

-- E084 Phase B: Unified tiered match calculation using custom tiers
-- All formulas (simple, tiered, stretch, safe_harbor, qaca) can be expressed as tiers
tiered_match AS (
    SELECT
        ec.employee_id,
        ec.simulation_year,
        ec.eligible_compensation,
        ec.deferral_rate,
        ec.annual_deferrals,
        -- Calculate match for each tier from match_tiers variable
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
        '{{ match_template }}' AS formula_type
    FROM employee_contributions ec
    CROSS JOIN (
        {% for tier in match_tiers %}
        SELECT
            {{ loop.index }} AS tier_number,
            {{ tier['employee_min'] }} AS employee_min,
            {{ tier['employee_max'] }} AS employee_max,
            {{ tier['match_rate'] }} AS match_rate
        {% if not loop.last %}UNION ALL{% endif %}
        {% endfor %}
    ) AS tier
    GROUP BY ec.employee_id, ec.simulation_year, ec.eligible_compensation,
             ec.deferral_rate, ec.annual_deferrals
),

-- Unified all_matches CTE
all_matches AS (
    SELECT * FROM tiered_match
),

-- Apply match caps and eligibility filtering (Epic E058 Phase 2, E084 Phase B)
final_match AS (
    SELECT
        am.employee_id,
        am.simulation_year,
        am.eligible_compensation,
        am.deferral_rate,
        am.annual_deferrals,
        am.formula_type,
        -- Join eligibility data back from employee_contributions CTE
        ec.is_eligible_for_match,
        ec.match_eligibility_reason,
        ec.eligibility_config_applied,
        -- E084 Phase B: Apply maximum match cap using match_cap_percent variable
        LEAST(
            am.match_amount,
            am.eligible_compensation * {{ match_cap_percent }}
        ) AS capped_match_amount,
        -- Epic E058 Phase 2: Apply eligibility filtering - ineligible employees get $0 match
        CASE
            WHEN ec.is_eligible_for_match THEN
                LEAST(
                    am.match_amount,
                    am.eligible_compensation * {{ match_cap_percent }}
                )
            ELSE 0
        END AS employer_match_amount,
        -- Epic E058 Phase 2: Match status tracking field
        CASE
            WHEN NOT ec.is_eligible_for_match THEN 'ineligible'
            WHEN ec.is_eligible_for_match AND am.annual_deferrals = 0 THEN 'no_deferrals'
            WHEN ec.is_eligible_for_match AND am.annual_deferrals > 0 THEN 'calculated'
            ELSE 'calculated'  -- Default fallback
        END AS match_status,
        -- Track if cap was applied (before eligibility filtering)
        am.match_amount > am.eligible_compensation * {{ match_cap_percent }} AS match_cap_applied,
        -- Calculate uncapped match for analysis
        am.match_amount AS uncapped_match_amount
    FROM all_matches am
    -- Join back to get eligibility information
    JOIN employee_contributions ec ON am.employee_id = ec.employee_id AND am.simulation_year = ec.simulation_year
)

SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    ROUND(deferral_rate, 4) AS deferral_rate,
    ROUND(annual_deferrals, 2) AS annual_deferrals,
    ROUND(employer_match_amount, 2) AS employer_match_amount,
    ROUND(uncapped_match_amount, 2) AS uncapped_match_amount,
    ROUND(capped_match_amount, 2) AS capped_match_amount,
    formula_type,
    match_cap_applied,
    -- Epic E058 Phase 2: Eligibility integration fields
    is_eligible_for_match,
    match_eligibility_reason,
    match_status,
    eligibility_config_applied,
    '{{ match_template }}' AS formula_id,
    '{{ match_template }}' AS formula_name,  -- E084 Phase B: Using template name
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
