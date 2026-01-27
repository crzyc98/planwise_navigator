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

  E010: Service-Based Match Contribution Tiers (NEW)
  Variables:
  - employer_match_status: 'deferral_based' (default) or 'graded_by_service'
  - employer_match_graded_schedule: Array of service tier definitions when graded_by_service
    Each tier: {min_years, max_years (null for infinity), rate (percentage), max_deferral_pct (percentage)}

  Match Calculation Modes:
  - deferral_based: Match rate varies by employee deferral percentage (existing behavior)
  - graded_by_service: Match rate varies by employee years of service (new feature)

  Backward Compatibility:
  - Falls back to tiered match (100% on 0-3%, 50% on 3-5%) if no custom tiers provided
  - Default employer_match_status='deferral_based' preserves existing behavior
*/

-- E084 Phase B: Direct tier configuration (replaces formula name lookup)
{% set match_tiers = var('match_tiers', [
    {'employee_min': 0.00, 'employee_max': 0.03, 'match_rate': 1.00},
    {'employee_min': 0.03, 'employee_max': 0.05, 'match_rate': 0.50}
]) %}
{% set match_cap_percent = var('match_cap_percent', 0.04) %}
{% set match_template = var('match_template', 'tiered') %}

-- E010: Service-based match configuration
{% set employer_match_status = var('employer_match_status', 'deferral_based') %}
{% set employer_match_graded_schedule = var('employer_match_graded_schedule', []) %}

-- Debug: Current match configuration
-- Match Status: {{ employer_match_status }}
-- Template: {{ match_template }}
-- Match cap: {{ match_cap_percent * 100 }}% of compensation
-- Deferral-based Tiers: {{ match_tiers | length }} defined
-- Service-based Tiers: {{ employer_match_graded_schedule | length }} defined

-- E026: IRS Section 401(a)(17) compensation limit for employer contributions
WITH irs_compensation_limits AS (
    SELECT
        limit_year,
        compensation_limit AS irs_401a17_limit
    FROM {{ ref('config_irs_limits') }}
    WHERE limit_year = {{ simulation_year }}
),

employee_contributions AS (
    -- Get ALL employee contribution data with eligibility determination (Epic E058 Phase 2)
    -- E010: Also join years of service from workforce snapshot for service-based matching
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
        elig.match_apply_eligibility AS eligibility_config_applied,
        -- E010: Years of service from workforce snapshot (integer years)
        FLOOR(COALESCE(snap.current_tenure, 0))::INT AS years_of_service
    FROM {{ ref('int_employee_contributions') }}  ec
    LEFT JOIN {{ ref('int_employer_eligibility') }} elig
        ON ec.employee_id = elig.employee_id
       AND ec.simulation_year = elig.simulation_year
    -- E010: Join workforce snapshot for years of service
    LEFT JOIN {{ ref('int_workforce_snapshot_optimized') }} snap
        ON ec.employee_id = snap.employee_id
       AND ec.simulation_year = snap.simulation_year
    WHERE ec.simulation_year = {{ simulation_year }}
        AND ec.employee_id IS NOT NULL
),

{% if employer_match_status == 'graded_by_service' %}
-- E010: Service-based match calculation
-- Match rate varies by employee years of service
-- Formula: match = tier_rate × min(deferral%, tier_max_deferral_pct) × capped_compensation
-- E026: Apply IRS 401(a)(17) compensation limit
service_based_match AS (
    SELECT
        ec.employee_id,
        ec.simulation_year,
        ec.eligible_compensation,
        ec.deferral_rate,
        ec.annual_deferrals,
        ec.years_of_service,
        -- E026: Get the 401(a)(17) limit for capping
        lim.irs_401a17_limit,
        -- Get the match rate for this employee's service tier
        {{ get_tiered_match_rate('ec.years_of_service', employer_match_graded_schedule, 0.50) }} AS tier_rate,
        -- Get the max deferral cap for this employee's service tier
        {{ get_tiered_match_max_deferral('ec.years_of_service', employer_match_graded_schedule, 0.06) }} AS tier_max_deferral_pct,
        -- Calculate match: rate × min(deferral%, max_deferral_pct) × capped_compensation
        -- E026: Use LEAST(compensation, 401a17_limit) to cap at IRS limit
        {{ get_tiered_match_rate('ec.years_of_service', employer_match_graded_schedule, 0.50) }}
            * LEAST(ec.deferral_rate, {{ get_tiered_match_max_deferral('ec.years_of_service', employer_match_graded_schedule, 0.06) }})
            * LEAST(ec.eligible_compensation, lim.irs_401a17_limit) AS match_amount,
        'graded_by_service' AS formula_type
    FROM employee_contributions ec
    -- E026: CROSS JOIN is safe here because irs_compensation_limits CTE filters to a single
    -- simulation_year, guaranteeing exactly one row. This provides the 401(a)(17) limit constant.
    CROSS JOIN irs_compensation_limits lim
),

-- Unified all_matches CTE for service-based mode
all_matches AS (
    SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        match_amount,
        formula_type,
        years_of_service,  -- E010: Include for audit trail
        irs_401a17_limit   -- E026: Include for audit trail
    FROM service_based_match
),
{% else %}
-- E084 Phase B: Deferral-based tiered match calculation (default mode)
-- All formulas (simple, tiered, stretch, safe_harbor, qaca) can be expressed as tiers
-- E026: Apply IRS 401(a)(17) compensation limit
tiered_match AS (
    SELECT
        ec.employee_id,
        ec.simulation_year,
        ec.eligible_compensation,
        ec.deferral_rate,
        ec.annual_deferrals,
        ec.years_of_service,
        -- E026: Get the 401(a)(17) limit for capping
        lim.irs_401a17_limit,
        -- Calculate match for each tier from match_tiers variable
        -- E026: Use LEAST(compensation, 401a17_limit) to cap at IRS limit
        SUM(
            CASE
                WHEN ec.deferral_rate > tier.employee_min
                THEN LEAST(
                    ec.deferral_rate - tier.employee_min,
                    tier.employee_max - tier.employee_min
                ) * tier.match_rate * LEAST(ec.eligible_compensation, lim.irs_401a17_limit)
                ELSE 0
            END
        ) AS match_amount,
        '{{ match_template }}' AS formula_type
    FROM employee_contributions ec
    -- E026: CROSS JOIN is safe here because irs_compensation_limits CTE filters to a single
    -- simulation_year, guaranteeing exactly one row. This provides the 401(a)(17) limit constant.
    CROSS JOIN irs_compensation_limits lim
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
             ec.deferral_rate, ec.annual_deferrals, ec.years_of_service, lim.irs_401a17_limit
),

-- Unified all_matches CTE for deferral-based mode
all_matches AS (
    SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        match_amount,
        formula_type,
        years_of_service,  -- E010: Include for completeness (NULL-like behavior in deferral mode)
        irs_401a17_limit   -- E026: Include for audit trail
    FROM tiered_match
),
{% endif %}

-- Apply match caps and eligibility filtering (Epic E058 Phase 2, E084 Phase B, E010, E026)
final_match AS (
    SELECT
        am.employee_id,
        am.simulation_year,
        am.eligible_compensation,
        am.deferral_rate,
        am.annual_deferrals,
        am.formula_type,
        -- E010: Years of service for service-based matching audit trail
        am.years_of_service,
        -- E026: IRS 401(a)(17) limit for audit trail
        am.irs_401a17_limit,
        -- E026: Track if 401(a)(17) limit was applied
        am.eligible_compensation > am.irs_401a17_limit AS irs_401a17_limit_applied,
        -- Join eligibility data back from employee_contributions CTE
        ec.is_eligible_for_match,
        ec.match_eligibility_reason,
        ec.eligibility_config_applied,
        {% if employer_match_status == 'graded_by_service' %}
        -- E010: Service-based mode - no match cap, tier already includes max_deferral_pct
        -- E026: 401(a)(17) cap already applied in match_amount calculation
        am.match_amount AS capped_match_amount,
        -- E010: Apply eligibility filtering
        CASE
            WHEN ec.is_eligible_for_match THEN am.match_amount
            ELSE 0
        END AS employer_match_amount,
        -- E010: Track if cap was applied (no cap in service-based mode)
        FALSE AS match_cap_applied,
        {% else %}
        -- E084 Phase B: Apply maximum match cap using match_cap_percent variable
        -- E026: Match cap is already based on 401(a)(17)-capped compensation from match_amount
        LEAST(
            am.match_amount,
            LEAST(am.eligible_compensation, am.irs_401a17_limit) * {{ match_cap_percent }}
        ) AS capped_match_amount,
        -- Epic E058 Phase 2: Apply eligibility filtering - ineligible employees get $0 match
        -- E026: Use 401(a)(17)-capped compensation for cap calculation
        CASE
            WHEN ec.is_eligible_for_match THEN
                LEAST(
                    am.match_amount,
                    LEAST(am.eligible_compensation, am.irs_401a17_limit) * {{ match_cap_percent }}
                )
            ELSE 0
        END AS employer_match_amount,
        -- Track if cap was applied (before eligibility filtering)
        am.match_amount > LEAST(am.eligible_compensation, am.irs_401a17_limit) * {{ match_cap_percent }} AS match_cap_applied,
        {% endif %}
        -- Epic E058 Phase 2: Match status tracking field
        CASE
            WHEN NOT ec.is_eligible_for_match THEN 'ineligible'
            WHEN ec.is_eligible_for_match AND am.annual_deferrals = 0 THEN 'no_deferrals'
            WHEN ec.is_eligible_for_match AND am.annual_deferrals > 0 THEN 'calculated'
            ELSE 'calculated'  -- Default fallback
        END AS match_status,
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
    -- E026: IRS 401(a)(17) compliance fields
    irs_401a17_limit,
    irs_401a17_limit_applied,
    -- Epic E058 Phase 2: Eligibility integration fields
    is_eligible_for_match,
    match_eligibility_reason,
    match_status,
    eligibility_config_applied,
    {% if employer_match_status == 'graded_by_service' %}
    -- E010: Service-based mode identifiers
    'graded_by_service' AS formula_id,
    'graded_by_service' AS formula_name,
    -- E010: Years of service audit field (populated in service-based mode)
    years_of_service AS applied_years_of_service,
    {% else %}
    -- E084 Phase B: Deferral-based mode identifiers
    '{{ match_template }}' AS formula_id,
    '{{ match_template }}' AS formula_name,
    -- E010: Years of service audit field (NULL in deferral-based mode)
    NULL::INT AS applied_years_of_service,
    {% endif %}
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
