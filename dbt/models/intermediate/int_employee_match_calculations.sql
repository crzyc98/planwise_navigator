{{ config(
    materialized='table',
    tags=['match_engine', 'critical', 'core_calculation', 'BENEFIT_CALCULATION']
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
{% set scenario_id = var('scenario_id', 'default') %}

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

-- E046: Points-based match configuration
{% set points_match_tiers = var('points_match_tiers', []) %}

-- Feature 099: Tenure-graded multi-tier match configuration (supersedes the
-- legacy single-tier tenure_based mode / tenure_match_tiers)
{% set tenure_graded_bands = var('tenure_graded_bands', []) %}

-- E069: Master match enable/disable flag (mirrors employer_core_enabled pattern)
{% set employer_match_enabled = var('employer_match_enabled', true) %}
{% set plan_design_parameters_config = var('plan_design_parameters', none) %}

-- Debug: Current match configuration
-- Match Status: {{ employer_match_status }}
-- Template: {{ match_template }}
-- Match cap: {{ match_cap_percent * 100 }}% of compensation
-- Deferral-based Tiers: {{ match_tiers | length }} defined
-- Service-based Tiers: {{ employer_match_graded_schedule | length }} defined
-- Points-based Tiers: {{ points_match_tiers | length }} defined
-- Tenure-Graded Bands: {{ tenure_graded_bands | length }} defined

-- E026: IRS Section 401(a)(17) compensation limit for employer contributions
WITH irs_compensation_limits AS (
    SELECT
        limit_year,
        compensation_limit AS irs_401a17_limit
    FROM {{ ref('config_irs_limits') }}
    WHERE limit_year = {{ simulation_year }}
),

{% if plan_design_parameters_config %}
plan_design_parameters AS (
    {{ get_plan_design_parameters(plan_design_parameters_config) }}
),

plan_design_match_tiers AS (
    {{ get_plan_design_match_tiers(plan_design_parameters_config) }}
),
{% endif %}

employee_contributions AS (
    -- Get ALL employee contribution data with eligibility determination (Epic E058 Phase 2)
    -- E010: Also join years of service from workforce snapshot for service-based matching
    SELECT
        ec.employee_id,
        ec.plan_design_id,
        ec.simulation_year,
        ec.annual_contribution_amount AS annual_deferrals,
        -- Feature 101: use the active-enrollment-window base so employer match follows
        -- the windowed contribution for same-year enroll→opt-out employees
        -- (equals prorated_annual_compensation for everyone else).
        ec.total_contribution_base_compensation AS eligible_compensation,
        ec.effective_annual_deferral_rate AS deferral_rate,
        ec.is_enrolled_flag AS is_enrolled,
        ec.first_contribution_date AS enrollment_date,
        ec.current_age AS age_as_of_december_31,
        ec.employment_status,
        -- Epic E058 Phase 2: Join with employer eligibility determination
        COALESCE(elig.eligible_for_match, FALSE) AS is_eligible_for_match,
        elig.match_eligibility_reason,
        elig.match_apply_eligibility AS eligibility_config_applied,
        -- Exact completed service used by eligibility and all service-based rates.
        FLOOR(COALESCE(workforce.current_tenure, 0))::INT AS years_of_service
    FROM {{ ref('int_employee_contributions') }}  ec
    LEFT JOIN {{ ref('int_employer_eligibility') }} elig
        ON ec.employee_id = elig.employee_id
       AND ec.simulation_year = elig.simulation_year
       AND ec.plan_design_id = elig.plan_design_id
       AND elig.scenario_id = '{{ scenario_id }}'
    LEFT JOIN {{ ref('int_workforce_state_accumulator') }} workforce
        ON ec.employee_id = workforce.employee_id
       AND ec.simulation_year = workforce.simulation_year
       AND ec.plan_design_id = workforce.plan_design_id
       AND workforce.scenario_id = '{{ scenario_id }}'
    WHERE ec.simulation_year = {{ simulation_year }}
        AND ec.employee_id IS NOT NULL
),

{% if plan_design_parameters_config %}
{% set referenced_match_families = [] %}
{% for design_id, parameters in plan_design_parameters_config | dictsort %}
  {% set family = parameters['match']['family'] %}
  {% if family not in referenced_match_families %}
    {% set _ = referenced_match_families.append(family) %}
  {% endif %}
{% endfor %}
{% for family in referenced_match_families %}
match_arm_{{ family }} AS (
    {{ match_family_arm(family) }}
),
{% endfor %}
all_matches AS (
{% for family in referenced_match_families %}
    SELECT * FROM match_arm_{{ family }}
    {% if not loop.last %}UNION ALL{% endif %}
{% endfor %}
),
{% else %}
{% if employer_match_status == 'graded_by_service' %}
-- E010: Service-based match calculation
-- Match rate varies by employee years of service
-- Formula: match = tier_rate × min(deferral%, tier_max_deferral_pct) × capped_compensation
-- E026: Apply IRS 401(a)(17) compensation limit
service_based_match AS (
    SELECT
        ec.employee_id,
        ec.plan_design_id,
        ec.simulation_year,
        ec.eligible_compensation,
        ec.deferral_rate,
        ec.annual_deferrals,
        ec.years_of_service,
        -- E026: Get the 401(a)(17) limit for capping
        lim.irs_401a17_limit,
        -- Get the match rate for this employee's service tier
{% if plan_design_parameters_config %}
        tier.match_rate AS tier_rate,
{% else %}
        {{ get_tiered_match_rate('ec.years_of_service', employer_match_graded_schedule, 0.50) }} AS tier_rate,
{% endif %}
        -- Get the max deferral cap for this employee's service tier
{% if plan_design_parameters_config %}
        tier.max_deferral_pct AS tier_max_deferral_pct,
{% else %}
        {{ get_tiered_match_max_deferral('ec.years_of_service', employer_match_graded_schedule, 0.06) }} AS tier_max_deferral_pct,
{% endif %}
        -- Calculate match: rate × min(deferral%, max_deferral_pct) × capped_compensation
        -- E026: Use LEAST(compensation, 401a17_limit) to cap at IRS limit
{% if plan_design_parameters_config %}
        tier.match_rate * LEAST(ec.deferral_rate, tier.max_deferral_pct)
{% else %}
        {{ get_tiered_match_rate('ec.years_of_service', employer_match_graded_schedule, 0.50) }}
            * LEAST(ec.deferral_rate, {{ get_tiered_match_max_deferral('ec.years_of_service', employer_match_graded_schedule, 0.06) }})
{% endif %}
            * LEAST(ec.eligible_compensation, lim.irs_401a17_limit) AS match_amount,
        'graded_by_service' AS formula_type,
        -- E046: applied_points is NULL for non-points modes
        NULL::INT AS applied_points
    FROM employee_contributions ec
    CROSS JOIN irs_compensation_limits lim
{% if plan_design_parameters_config %}
    INNER JOIN plan_design_match_tiers tier
      ON tier.plan_design_id = ec.plan_design_id
     AND tier.formula_family = 'graded_by_service'
     AND ec.years_of_service >= tier.band_min_value
     AND (tier.band_max_value IS NULL OR ec.years_of_service < tier.band_max_value)
{% endif %}
),

-- Unified all_matches CTE for service-based mode
all_matches AS (
    SELECT
        employee_id,
        plan_design_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        match_amount,
        formula_type,
        'graded_by_service'::VARCHAR AS formula_family,
        years_of_service,
        irs_401a17_limit,
        applied_points,
        1::INTEGER AS resolution_count
    FROM service_based_match
),

{% elif employer_match_status == 'tenure_graded' %}
-- Feature 099: Tenure-graded multi-tier match calculation
-- Match rate AND deferral-tier schedule both vary by employee years of service.
-- Each tenure band carries its own ordered, cumulative list of deferral-rate
-- tiers (e.g. 100% on first 2%, 50% on next 6%), unlike tenure_based mode
-- which only varies a single flat rate + single max deferral cap per band.
-- Formula: match = SUM over the employee's band's tiers of
--   tier_rate × min(deferral% above tier floor, tier width) × capped_compensation
tenure_graded_match AS (
    SELECT
        ec.employee_id,
        ec.plan_design_id,
        ec.simulation_year,
        ec.eligible_compensation,
        ec.deferral_rate,
        ec.annual_deferrals,
        ec.years_of_service,
        lim.irs_401a17_limit,
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
        'tenure_graded' AS formula_type,
        NULL::INT AS applied_points
    FROM employee_contributions ec
    CROSS JOIN irs_compensation_limits lim
{% if plan_design_parameters_config %}
    INNER JOIN plan_design_match_tiers tier
      ON tier.plan_design_id = ec.plan_design_id
     AND tier.formula_family = 'tenure_graded'
     AND ec.years_of_service >= tier.band_min_value
     AND (tier.band_max_value IS NULL OR ec.years_of_service < tier.band_max_value)
{% else %}
    CROSS JOIN ({{ get_tenure_graded_match_tiers(tenure_graded_bands) }}) AS tier
    WHERE ec.years_of_service >= tier.band_min_years
      AND (tier.band_max_years IS NULL OR ec.years_of_service < tier.band_max_years)
{% endif %}
    GROUP BY ec.employee_id, ec.plan_design_id, ec.simulation_year, ec.eligible_compensation,
             ec.deferral_rate, ec.annual_deferrals, ec.years_of_service, lim.irs_401a17_limit
),

all_matches AS (
    SELECT
        employee_id,
        plan_design_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        match_amount,
        formula_type,
        'tenure_graded'::VARCHAR AS formula_family,
        years_of_service,
        irs_401a17_limit,
        applied_points,
        1::INTEGER AS resolution_count
    FROM tenure_graded_match
),

{% elif employer_match_status == 'points_based' %}
-- E046: Points-based match calculation
-- Points = FLOOR(current_age) + years_of_service (years_of_service is already FLOOR(tenure))
-- Match rate varies by employee points, using points_match_tiers config
-- Formula: match = tier_rate × min(deferral%, tier_max_deferral_pct) × capped_compensation
points_based_match AS (
    SELECT
        ec.employee_id,
        ec.plan_design_id,
        ec.simulation_year,
        ec.eligible_compensation,
        ec.deferral_rate,
        ec.annual_deferrals,
        ec.years_of_service,
        lim.irs_401a17_limit,
        -- E046: Calculate applied_points = FLOOR(age) + FLOOR(tenure)
        -- age_as_of_december_31 is current_age; years_of_service is already FLOOR(tenure)
        (FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service) AS applied_points,
        -- Get the match rate for this employee's points tier
{% if plan_design_parameters_config %}
        tier.match_rate AS tier_rate,
{% else %}
        {{ get_points_based_match_rate(
            '(FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service)',
            points_match_tiers, 0.0) }} AS tier_rate,
{% endif %}
        -- Get the max deferral cap for this employee's points tier
{% if plan_design_parameters_config %}
        tier.max_deferral_pct AS tier_max_deferral_pct,
{% else %}
        {{ get_points_based_max_deferral(
            '(FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service)',
            points_match_tiers, 0.06) }} AS tier_max_deferral_pct,
{% endif %}
        -- Calculate match: rate × min(deferral%, max_deferral_pct) × capped_compensation
{% if plan_design_parameters_config %}
        tier.match_rate * LEAST(ec.deferral_rate, tier.max_deferral_pct)
{% else %}
        {{ get_points_based_match_rate(
            '(FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service)',
            points_match_tiers, 0.0) }}
            * LEAST(ec.deferral_rate, {{ get_points_based_max_deferral(
                '(FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service)',
                points_match_tiers, 0.06) }})
{% endif %}
            * LEAST(ec.eligible_compensation, lim.irs_401a17_limit) AS match_amount,
        'points_based' AS formula_type
    FROM employee_contributions ec
    CROSS JOIN irs_compensation_limits lim
{% if plan_design_parameters_config %}
    INNER JOIN plan_design_match_tiers tier
      ON tier.plan_design_id = ec.plan_design_id
     AND tier.formula_family = 'points_based'
     AND (FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service) >= tier.band_min_value
     AND (
       tier.band_max_value IS NULL
       OR (FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service) < tier.band_max_value
     )
{% endif %}
),

all_matches AS (
    SELECT
        employee_id,
        plan_design_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        match_amount,
        formula_type,
        'points_based'::VARCHAR AS formula_family,
        years_of_service,
        irs_401a17_limit,
        applied_points,
        1::INTEGER AS resolution_count
    FROM points_based_match
),

{% else %}
-- E084 Phase B: Deferral-based tiered match calculation (default mode)
-- All formulas (simple, tiered, stretch, safe_harbor, qaca) can be expressed as tiers
-- E026: Apply IRS 401(a)(17) compensation limit
tiered_match AS (
    SELECT
        ec.employee_id,
        ec.plan_design_id,
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
        '{{ match_template }}' AS formula_type,
        NULL::INT AS applied_points
    FROM employee_contributions ec
    -- E026: CROSS JOIN is safe here because irs_compensation_limits CTE filters to a single
    -- simulation_year, guaranteeing exactly one row. This provides the 401(a)(17) limit constant.
    CROSS JOIN irs_compensation_limits lim
    {% if plan_design_parameters_config %}
    INNER JOIN plan_design_match_tiers tier
      ON tier.plan_design_id = ec.plan_design_id
     AND tier.formula_family = 'deferral_based'
    {% else %}
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
    {% endif %}
    GROUP BY ec.employee_id, ec.plan_design_id, ec.simulation_year, ec.eligible_compensation,
             ec.deferral_rate, ec.annual_deferrals, ec.years_of_service, lim.irs_401a17_limit
),

-- Unified all_matches CTE for deferral-based mode
all_matches AS (
    SELECT
        employee_id,
        plan_design_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        match_amount,
        formula_type,
        'deferral_based'::VARCHAR AS formula_family,
        years_of_service,
        irs_401a17_limit,
        NULL::INT AS applied_points,
        1::INTEGER AS resolution_count
    FROM tiered_match
),
{% endif %}
{% endif %}

{% if plan_design_parameters_config %}
match_resolution AS (
    SELECT
        ec.employee_id,
        ec.plan_design_id,
        ec.simulation_year,
        pdp.match_formula_family AS formula_family,
        ec.years_of_service,
        (FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service)
            AS applied_points,
        COUNT(am.employee_id)::INTEGER AS arm_count,
        COALESCE(MAX(am.resolution_count), 0)::INTEGER AS resolution_count
    FROM employee_contributions ec
    INNER JOIN plan_design_parameters pdp
      ON pdp.plan_design_id = ec.plan_design_id
    LEFT JOIN all_matches am
      ON am.employee_id = ec.employee_id
     AND am.plan_design_id = ec.plan_design_id
     AND am.simulation_year = ec.simulation_year
    WHERE ec.is_eligible_for_match
    GROUP BY ec.employee_id, ec.plan_design_id, ec.simulation_year,
             pdp.match_formula_family, ec.years_of_service,
             ec.age_as_of_december_31
),
multi_design_formula_guard AS (
    SELECT CASE WHEN COUNT(*) = 0 THEN 1 ELSE CAST(
        'invocation_id={{ invocation_id }}; match side formula resolution failed; '
        || 'employee_id=' || MIN(employee_id)
        || '; plan_design_id=' || MIN(plan_design_id)
        || '; simulation_year=' || MIN(simulation_year)::VARCHAR
        || '; formula_family=' || MIN(formula_family)
        || '; arm_count=' || MIN(arm_count)::VARCHAR
        || '; resolution_count=' || MIN(resolution_count)::VARCHAR
        || '; observed_value=' || MIN(
            CASE WHEN formula_family = 'points_based'
                 THEN applied_points ELSE years_of_service END
        )::VARCHAR
        || '; correct match.' || MIN(
            CASE formula_family
              WHEN 'deferral_based' THEN 'tiers'
              WHEN 'graded_by_service' THEN 'graded_schedule'
              WHEN 'tenure_graded' THEN 'tenure_graded_bands'
              ELSE 'points_tiers' END
        )
        AS INTEGER) END AS guard_ok
    FROM match_resolution
    WHERE arm_count <> 1 OR resolution_count <> 1
),
{% endif %}

-- Apply match caps and eligibility filtering (Epic E058 Phase 2, E084 Phase B, E010, E026)
final_match AS (
    SELECT
        am.employee_id,
        am.plan_design_id,
        am.simulation_year,
        am.eligible_compensation,
        am.deferral_rate,
        am.annual_deferrals,
        am.formula_type,
        am.formula_family,
        -- E010: Years of service for service-based matching audit trail
        am.years_of_service,
        -- E046: Points for points-based matching audit trail
        am.applied_points,
        -- E026: IRS 401(a)(17) limit for audit trail
        am.irs_401a17_limit,
        -- E026: Track if 401(a)(17) limit was applied
        am.eligible_compensation > am.irs_401a17_limit AS irs_401a17_limit_applied,
        -- Join eligibility data back from employee_contributions CTE
        ec.is_eligible_for_match,
        ec.match_eligibility_reason,
        ec.eligibility_config_applied,
        {% if not employer_match_enabled %}
        -- E069: Match disabled — all amounts zeroed, status = 'disabled'
        0 AS capped_match_amount,
        0 AS employer_match_amount,
        FALSE AS match_cap_applied,
        'disabled' AS match_status,
        0 AS uncapped_match_amount
        {% else %}
        CASE WHEN am.formula_family = 'deferral_based' THEN LEAST(
            am.match_amount, LEAST(am.eligible_compensation, am.irs_401a17_limit)
            * {% if plan_design_parameters_config %}pdp.match_cap_percent{% else %}{{ match_cap_percent }}{% endif %}
        ) ELSE am.match_amount END AS capped_match_amount,
        CASE
            WHEN ec.is_eligible_for_match AND am.formula_family = 'deferral_based'
            THEN LEAST(am.match_amount,
                LEAST(am.eligible_compensation, am.irs_401a17_limit)
                * {% if plan_design_parameters_config %}pdp.match_cap_percent{% else %}{{ match_cap_percent }}{% endif %})
            WHEN ec.is_eligible_for_match THEN am.match_amount
            ELSE 0
        END AS employer_match_amount,
        am.formula_family = 'deferral_based'
          AND am.match_amount > LEAST(am.eligible_compensation, am.irs_401a17_limit)
              * {% if plan_design_parameters_config %}pdp.match_cap_percent{% else %}{{ match_cap_percent }}{% endif %}
          AS match_cap_applied,
        CASE
            WHEN NOT ec.is_eligible_for_match THEN 'ineligible'
            WHEN ec.is_eligible_for_match AND am.annual_deferrals = 0 THEN 'no_deferrals'
            WHEN ec.is_eligible_for_match AND am.annual_deferrals > 0 THEN 'calculated'
            ELSE 'calculated'
        END AS match_status,
        am.match_amount AS uncapped_match_amount
        {% endif %}
    FROM all_matches am
    -- Join back to get eligibility information
    JOIN employee_contributions ec
      ON am.employee_id = ec.employee_id
     AND am.simulation_year = ec.simulation_year
     AND am.plan_design_id = ec.plan_design_id
    {% if plan_design_parameters_config %}
    INNER JOIN plan_design_parameters pdp
      ON pdp.plan_design_id = am.plan_design_id
    CROSS JOIN multi_design_formula_guard
    WHERE multi_design_formula_guard.guard_ok = 1
    {% endif %}
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
    formula_type AS formula_id,
    formula_type AS formula_name,
    CASE WHEN formula_family = 'deferral_based' THEN NULL
         ELSE years_of_service END::INT AS applied_years_of_service,
    CASE WHEN formula_family = 'points_based' THEN applied_points
         ELSE NULL END::INT AS applied_points,
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
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id,
    plan_design_id
FROM final_match
WHERE employee_id IS NOT NULL
