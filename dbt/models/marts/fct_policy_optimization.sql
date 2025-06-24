{{ config(
    materialized='table'
) }}

{% set simulation_year = var('simulation_year', 2026) %}
{% set test_scenario = var('test_scenario', 'scenario_001') %}
{% set test_cola_rate = var('test_cola_rate', 0.025) %}
{% set test_merit_budget = var('test_merit_budget', 0.040) %}

-- Policy Parameter Optimization Testing Framework
-- Tests specific COLA/Merit combinations and calculates compensation growth impact
-- Part of S052 systematic policy parameter optimization

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Test scenario configuration - now uses dbt variables for flexibility
test_scenario_config AS (
    SELECT
        '{{ test_scenario }}' as scenario_name,
        {{ test_cola_rate }} as test_cola_rate,
        {{ test_merit_budget }} as test_merit_budget
),

-- Current workforce snapshot
current_workforce AS (
    SELECT
        simulation_year,
        employee_id,
        detailed_status_code,
        prorated_annual_compensation,
        current_compensation,
        EXTRACT(YEAR FROM employee_hire_date) as hire_year
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- Previous year baseline for growth calculation
previous_workforce AS (
    SELECT
        simulation_year,
        employee_id,
        detailed_status_code,
        prorated_annual_compensation,
        current_compensation
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year - 1 }}
),

-- Simulate compensation adjustments under test scenario
-- This models what compensation would be with different COLA/Merit rates
-- CORRECTED: Apply policy adjustments to previous year baseline, not current year
simulated_compensation AS (
    SELECT
        cw.employee_id,
        cw.detailed_status_code,
        cw.prorated_annual_compensation as baseline_compensation,
        cw.current_compensation,
        tsc.scenario_name,
        tsc.test_cola_rate,
        tsc.test_merit_budget,

        -- Calculate simulated compensation impact
        -- Apply policy adjustments to previous year baseline for realistic simulation
        CASE
            WHEN cw.detailed_status_code = 'continuous_active' THEN
                -- For continuous employees: apply policy adjustments to previous year baseline
                -- This simulates what would happen if we applied different COLA/Merit rates
                COALESCE(pw.prorated_annual_compensation, cw.prorated_annual_compensation) *
                (1 + tsc.test_cola_rate + tsc.test_merit_budget)
            WHEN cw.detailed_status_code = 'new_hire_active' THEN
                -- For new hires: use current compensation (hired at market rates)
                cw.prorated_annual_compensation
            ELSE cw.prorated_annual_compensation
        END as simulated_compensation

    FROM current_workforce cw
    CROSS JOIN test_scenario_config tsc
    LEFT JOIN previous_workforce pw ON cw.employee_id = pw.employee_id
    WHERE cw.detailed_status_code IN ('continuous_active', 'new_hire_active')
),

-- Pre-calculate previous year baseline to avoid subqueries in aggregates
previous_year_baseline AS (
    SELECT
        AVG(prorated_annual_compensation) as prev_year_avg_compensation
    FROM previous_workforce
    WHERE detailed_status_code IN ('continuous_active', 'new_hire_active')
),

-- Calculate growth metrics under test scenario
methodology_a_simulated AS (
    SELECT
        'methodology_a_current' as calculation_method,
        sc.scenario_name,
        sc.test_cola_rate,
        sc.test_merit_budget,
        {{ simulation_year }} as simulation_year,
        COUNT(*) as total_employees,
        COUNT(CASE WHEN sc.detailed_status_code = 'continuous_active' THEN 1 END) as continuous_employees,
        COUNT(CASE WHEN sc.detailed_status_code = 'new_hire_active' THEN 1 END) as new_hire_employees,

        -- Baseline metrics
        AVG(sc.baseline_compensation) as baseline_avg_compensation,

        -- Simulated metrics
        AVG(sc.simulated_compensation) as simulated_avg_compensation,

        -- Growth calculation vs previous year baseline
        COALESCE(
            (AVG(sc.simulated_compensation) - pyb.prev_year_avg_compensation) /
            pyb.prev_year_avg_compensation * 100,
            NULL
        ) as simulated_yoy_growth_pct,

        -- Compare to baseline (current policy) growth
        COALESCE(
            (AVG(sc.baseline_compensation) - pyb.prev_year_avg_compensation) /
            pyb.prev_year_avg_compensation * 100,
            NULL
        ) as baseline_yoy_growth_pct

    FROM simulated_compensation sc
    CROSS JOIN previous_year_baseline pyb
    GROUP BY sc.scenario_name, sc.test_cola_rate, sc.test_merit_budget, pyb.prev_year_avg_compensation
),

-- Full-Year Equivalent methodology simulation
methodology_c_simulated AS (
    SELECT
        'methodology_c_full_year' as calculation_method,
        sc.scenario_name,
        sc.test_cola_rate,
        sc.test_merit_budget,
        {{ simulation_year }} as simulation_year,
        COUNT(*) as total_employees,
        COUNT(CASE WHEN sc.detailed_status_code = 'continuous_active' THEN 1 END) as continuous_employees,
        COUNT(CASE WHEN sc.detailed_status_code = 'new_hire_active' THEN 1 END) as new_hire_employees,

        -- Baseline full-year equivalent
        (SUM(CASE
            WHEN sc.detailed_status_code = 'continuous_active'
            THEN sc.baseline_compensation
            WHEN sc.detailed_status_code = 'new_hire_active'
            THEN sc.current_compensation  -- Use full annual salary for new hires
            ELSE 0
        END) / COUNT(*)) as baseline_avg_compensation,

        -- Simulated full-year equivalent
        (SUM(CASE
            WHEN sc.detailed_status_code = 'continuous_active'
            THEN sc.simulated_compensation
            WHEN sc.detailed_status_code = 'new_hire_active'
            THEN sc.current_compensation * (1 + sc.test_cola_rate)  -- Apply COLA to new hire full salary
            ELSE 0
        END) / COUNT(*)) as simulated_avg_compensation,

        -- Growth calculation using full-year equivalent
        COALESCE(
            ((SUM(CASE
                WHEN sc.detailed_status_code = 'continuous_active'
                THEN sc.simulated_compensation
                WHEN sc.detailed_status_code = 'new_hire_active'
                THEN sc.current_compensation * (1 + sc.test_cola_rate)
                ELSE 0
            END) / COUNT(*)) - pyb.prev_year_avg_compensation) /
            pyb.prev_year_avg_compensation * 100,
            NULL
        ) as simulated_yoy_growth_pct,

        -- Baseline full-year equivalent growth
        COALESCE(
            ((SUM(CASE
                WHEN sc.detailed_status_code = 'continuous_active'
                THEN sc.baseline_compensation
                WHEN sc.detailed_status_code = 'new_hire_active'
                THEN sc.current_compensation
                ELSE 0
            END) / COUNT(*)) - pyb.prev_year_avg_compensation) /
            pyb.prev_year_avg_compensation * 100,
            NULL
        ) as baseline_yoy_growth_pct

    FROM simulated_compensation sc
    CROSS JOIN previous_year_baseline pyb
    GROUP BY sc.scenario_name, sc.test_cola_rate, sc.test_merit_budget, pyb.prev_year_avg_compensation
),

-- Combine methodology results
all_methodology_results AS (
    SELECT * FROM methodology_a_simulated
    UNION ALL
    SELECT * FROM methodology_c_simulated
),

-- Target achievement analysis
target_analysis AS (
    SELECT
        *,
        2.0 as target_growth_pct,
        0.5 as tolerance_pct,

        -- Target achievement assessment
        CASE
            WHEN simulated_yoy_growth_pct IS NULL THEN 'NO_DATA'
            WHEN simulated_yoy_growth_pct >= 1.5 AND simulated_yoy_growth_pct <= 2.5 THEN 'TARGET_ACHIEVED'
            WHEN simulated_yoy_growth_pct < 1.5 THEN 'BELOW_TARGET'
            WHEN simulated_yoy_growth_pct > 2.5 THEN 'ABOVE_TARGET'
        END as target_status,

        ABS(simulated_yoy_growth_pct - 2.0) as deviation_from_target,

        -- Policy efficiency metrics
        (test_cola_rate - 0.025) + (test_merit_budget - 0.040) as total_policy_adjustment,
        simulated_yoy_growth_pct - baseline_yoy_growth_pct as growth_improvement,

        -- Budget impact estimation (simplified)
        (test_cola_rate + test_merit_budget) * 100 as estimated_budget_impact_pct

    FROM all_methodology_results
)

-- Final results with comprehensive analysis
SELECT
    calculation_method,
    scenario_name,
    ROUND(test_cola_rate * 100, 1) as cola_rate_pct,
    ROUND(test_merit_budget * 100, 1) as merit_budget_pct,
    simulation_year,
    total_employees,
    continuous_employees,
    new_hire_employees,

    -- Compensation metrics
    ROUND(baseline_avg_compensation, 0) as baseline_avg_compensation,
    ROUND(simulated_avg_compensation, 0) as simulated_avg_compensation,

    -- Growth metrics
    ROUND(baseline_yoy_growth_pct, 2) as baseline_growth_pct,
    ROUND(simulated_yoy_growth_pct, 2) as simulated_growth_pct,
    ROUND(growth_improvement, 2) as growth_improvement_pct,

    -- Target achievement
    target_growth_pct,
    tolerance_pct,
    target_status,
    ROUND(deviation_from_target, 2) as deviation_from_target,

    -- Policy metrics
    ROUND(total_policy_adjustment * 100, 1) as total_policy_adjustment_pct,
    ROUND(estimated_budget_impact_pct, 1) as estimated_budget_impact_pct,

    -- Efficiency score (lower is better for minimal adjustment)
    ROUND(deviation_from_target / NULLIF(total_policy_adjustment, 0), 2) as efficiency_score,

    CURRENT_TIMESTAMP as analysis_timestamp

FROM target_analysis
ORDER BY calculation_method, deviation_from_target
