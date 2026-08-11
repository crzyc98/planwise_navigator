/*
  Test: Service-Based Match Tier Boundaries

  This test verifies that service-based employer match tiers are applied
  correctly based on employee years of service when graded_by_service mode is active.

  Configuration tested:
    - employer_match_status: 'graded_by_service'
    - employer_match_graded_schedule:
      - 0-5 years: 50% rate, 6% max deferral
      - 5+ years: 100% rate, 6% max deferral

  Test Cases:
    1. Employee with 4 years tenure should get 50% match rate (0.50)
    2. Employee with 5 years tenure should get 100% match rate (1.00) - boundary test
    3. Employee with 10 years tenure should get 100% match rate (1.00)
    4. applied_years_of_service field should be populated in service-based mode

  Expected: No rows returned (all assertions pass)

  Rate boundaries are checked for graded_by_service. Exact service audit
  reconciliation also runs for tenure_graded and points_based modes.

  Feature: E010 - Service-Based Match Contribution Tiers
*/

{% set employer_match_status = var('employer_match_status', 'deferral_based') %}
{% set employer_match_graded_schedule = var('employer_match_graded_schedule', []) %}
{% set simulation_year = var('simulation_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}

WITH match_calculations AS (
    SELECT
        mc.employee_id,
        mc.simulation_year,
        mc.employer_match_amount,
        mc.eligible_compensation,
        mc.deferral_rate,
        mc.formula_type,
        mc.applied_years_of_service,
        -- Get actual years of service from workforce snapshot
        snap.current_tenure
    FROM {{ ref('int_employee_match_calculations') }} mc
    LEFT JOIN (
        SELECT
            employee_id,
            simulation_year,
            FLOOR(COALESCE(current_tenure, 0))::INT AS current_tenure
        FROM {{ ref('int_workforce_state_accumulator') }}
        WHERE scenario_id = '{{ scenario_id }}'
          AND plan_design_id = '{{ plan_design_id }}'
          AND simulation_year = {{ simulation_year }}
    ) snap ON mc.employee_id = snap.employee_id
            AND mc.simulation_year = snap.simulation_year
    WHERE mc.scenario_id = '{{ scenario_id }}'
        AND mc.simulation_year = {{ simulation_year }}
        AND mc.is_eligible_for_match = TRUE
        AND mc.employer_match_amount > 0
),

boundary_checks AS (
    SELECT
        employee_id,
        simulation_year,
        employer_match_amount,
        eligible_compensation,
        deferral_rate,
        formula_type,
        applied_years_of_service,
        current_tenure,
        -- Expected tier rate based on years of service
        -- Using [min, max) convention: 5+ years means >= 5
        CASE
            WHEN COALESCE(current_tenure, 0) >= 5 THEN 1.00  -- 100% tier
            ELSE 0.50  -- 50% tier
        END AS expected_tier_rate,
        -- Calculate the actual match rate applied
        -- Formula: match = rate × min(deferral, max_deferral_pct) × comp
        -- With 6% max deferral cap: rate × LEAST(deferral, 0.06) × comp
        CASE
            WHEN eligible_compensation > 0 AND deferral_rate > 0 THEN
                employer_match_amount / (LEAST(deferral_rate, 0.06) * eligible_compensation)
            ELSE 0
        END AS actual_tier_rate
    FROM match_calculations
    WHERE '{{ employer_match_status }}' IN (
        'graded_by_service', 'tenure_graded', 'points_based'
    )
),

assertions AS (
    SELECT
        *,
        ABS(actual_tier_rate - expected_tier_rate) AS rate_difference,
        -- Validate applied_years_of_service is populated and matches actual tenure
        CASE
            WHEN applied_years_of_service IS NULL THEN 'MISSING_YEARS_OF_SERVICE'
            WHEN applied_years_of_service IS DISTINCT FROM current_tenure THEN 'TENURE_MISMATCH'
            ELSE 'OK'
        END AS tenure_audit_status
    FROM boundary_checks
)

-- Return rows where tier rate doesn't match expected or audit field is missing
SELECT *
FROM assertions
WHERE (
    rate_difference > 0.01  -- 1% tolerance for floating point rounding
    AND '{{ employer_match_status }}' = 'graded_by_service'
)
   OR tenure_audit_status != 'OK'
