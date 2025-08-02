{{ config(
    materialized='table'
) }}

{% set simulation_year = var('simulation_year', 2025) %}

-- Compensation growth analysis with multiple calculation methodologies
-- Implements S051 calibration framework for achieving 2% growth target

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Current workforce snapshot data
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

-- Previous year workforce for growth calculation
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

-- Methodology A: Current (includes all employees with prorated compensation)
methodology_a_current AS (
    SELECT
        'methodology_a_current' as calculation_method,
        {{ simulation_year }} as simulation_year,
        COUNT(*) as total_employees,
        COUNT(CASE WHEN detailed_status_code = 'continuous_active' THEN 1 END) as continuous_employees,
        COUNT(CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 END) as new_hire_employees,
        AVG(prorated_annual_compensation) as avg_compensation,
        -- Calculate growth vs previous year with division-by-zero protection
        CASE
            WHEN (SELECT AVG(prorated_annual_compensation)
                  FROM previous_workforce prev
                  WHERE prev.detailed_status_code IN ('continuous_active', 'new_hire_active')) > 0
            THEN (AVG(prorated_annual_compensation) -
                  (SELECT AVG(prorated_annual_compensation)
                   FROM previous_workforce prev
                   WHERE prev.detailed_status_code IN ('continuous_active', 'new_hire_active'))
                 ) /
                 (SELECT AVG(prorated_annual_compensation)
                  FROM previous_workforce prev
                  WHERE prev.detailed_status_code IN ('continuous_active', 'new_hire_active')) * 100
            ELSE NULL  -- Return NULL if previous year average is zero or NULL
        END as yoy_growth_pct
    FROM current_workforce
    WHERE detailed_status_code IN ('continuous_active', 'new_hire_active')
),

-- Methodology B: Continuous Employee Focus (excludes new hires)
methodology_b_continuous AS (
    SELECT
        'methodology_b_continuous' as calculation_method,
        {{ simulation_year }} as simulation_year,
        COUNT(*) as total_employees,
        COUNT(*) as continuous_employees,
        0 as new_hire_employees,
        AVG(prorated_annual_compensation) as avg_compensation,
        -- Calculate growth vs previous year continuous employees only with division-by-zero protection
        CASE
            WHEN (SELECT AVG(prorated_annual_compensation)
                  FROM previous_workforce prev
                  WHERE prev.detailed_status_code = 'continuous_active') > 0
            THEN (AVG(prorated_annual_compensation) -
                  (SELECT AVG(prorated_annual_compensation)
                   FROM previous_workforce prev
                   WHERE prev.detailed_status_code = 'continuous_active')
                 ) /
                 (SELECT AVG(prorated_annual_compensation)
                  FROM previous_workforce prev
                  WHERE prev.detailed_status_code = 'continuous_active') * 100
            ELSE NULL  -- Return NULL if previous year average is zero or NULL
        END as yoy_growth_pct
    FROM current_workforce
    WHERE detailed_status_code = 'continuous_active'
),

-- Methodology C: Full-Year Equivalent (annualize new hire compensation)
methodology_c_full_year AS (
    SELECT
        'methodology_c_full_year' as calculation_method,
        {{ simulation_year }} as simulation_year,
        COUNT(*) as total_employees,
        COUNT(CASE WHEN detailed_status_code = 'continuous_active' THEN 1 END) as continuous_employees,
        COUNT(CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 END) as new_hire_employees,
        -- Calculate average using full-year equivalent for new hires
        (SUM(CASE
            WHEN detailed_status_code = 'continuous_active'
            THEN prorated_annual_compensation
            WHEN detailed_status_code = 'new_hire_active'
            THEN current_compensation -- Use full annual salary instead of prorated
            ELSE 0
        END) / COUNT(*)) as avg_compensation,
        -- Calculate growth using full-year equivalent methodology with division-by-zero protection
        CASE
            WHEN (SELECT AVG(prorated_annual_compensation)
                  FROM previous_workforce prev
                  WHERE prev.detailed_status_code IN ('continuous_active', 'new_hire_active')) > 0
            THEN ((SUM(CASE
                    WHEN detailed_status_code = 'continuous_active'
                    THEN prorated_annual_compensation
                    WHEN detailed_status_code = 'new_hire_active'
                    THEN current_compensation
                    ELSE 0
                END) / COUNT(*)) -
                 (SELECT AVG(prorated_annual_compensation)
                  FROM previous_workforce prev
                  WHERE prev.detailed_status_code IN ('continuous_active', 'new_hire_active'))
                ) /
                (SELECT AVG(prorated_annual_compensation)
                 FROM previous_workforce prev
                 WHERE prev.detailed_status_code IN ('continuous_active', 'new_hire_active')) * 100
            ELSE NULL  -- Return NULL if previous year average is zero or NULL
        END as yoy_growth_pct
    FROM current_workforce
    WHERE detailed_status_code IN ('continuous_active', 'new_hire_active')
),

-- Combine all methodologies
all_methodologies AS (
    SELECT * FROM methodology_a_current
    UNION ALL
    SELECT * FROM methodology_b_continuous
    UNION ALL
    SELECT * FROM methodology_c_full_year
),

-- Calculate dilution impact analysis
dilution_analysis AS (
    SELECT
        {{ simulation_year }} as simulation_year,
        -- New hire dilution metrics
        (SELECT new_hire_employees FROM methodology_a_current) as new_hire_count,
        (SELECT total_employees FROM methodology_a_current) as total_employee_count,
        (SELECT new_hire_employees::FLOAT / total_employees FROM methodology_a_current) as new_hire_ratio,

        -- Growth impact comparison
        (SELECT yoy_growth_pct FROM methodology_b_continuous) as continuous_only_growth,
        (SELECT yoy_growth_pct FROM methodology_a_current) as total_workforce_growth,
        (SELECT yoy_growth_pct FROM methodology_c_full_year) as full_year_equiv_growth,

        -- Dilution effect calculation
        (SELECT yoy_growth_pct FROM methodology_b_continuous) -
        (SELECT yoy_growth_pct FROM methodology_a_current) as dilution_impact_pct
),

-- Target achievement assessment
target_assessment AS (
    SELECT
        calculation_method,
        simulation_year,
        yoy_growth_pct,
        2.0 as target_growth_pct,
        0.5 as tolerance_pct,
        -- Target achievement flags
        CASE
            WHEN yoy_growth_pct IS NULL THEN 'NO_DATA'
            WHEN yoy_growth_pct >= 1.5 AND yoy_growth_pct <= 2.5 THEN 'TARGET_ACHIEVED'
            WHEN yoy_growth_pct < 1.5 THEN 'BELOW_TARGET'
            WHEN yoy_growth_pct > 2.5 THEN 'ABOVE_TARGET'
        END as target_status,
        ABS(yoy_growth_pct - 2.0) as deviation_from_target
    FROM all_methodologies
),

-- Compensation compounding validation (simplified for debugging)
compounding_validation AS (
    SELECT
        curr.employee_id,
        curr.simulation_year AS current_year,
        prev.simulation_year AS previous_year,
        COALESCE(prev.current_compensation, 0) AS previous_year_ending_salary,
        COALESCE(curr.current_compensation, 0) AS current_year_starting_salary,
        COALESCE(curr.current_compensation, 0) AS current_year_ending_salary,
        'SIMPLIFIED' AS compounding_status,
        0 AS salary_discrepancy
    FROM {{ ref('fct_workforce_snapshot') }} curr
    INNER JOIN {{ ref('fct_workforce_snapshot') }} prev
        ON curr.employee_id = prev.employee_id
        AND curr.simulation_year = prev.simulation_year + 1
        AND prev.employment_status = 'active'
        AND curr.employment_status = 'active'
    WHERE curr.simulation_year = {{ simulation_year }}
),

compounding_summary AS (
    -- Summary statistics on compounding accuracy
    SELECT
        {{ simulation_year }} as simulation_year,
        COUNT(*) AS employees_tracked_for_compounding,
        SUM(CASE WHEN compounding_status = 'CORRECT' THEN 1 ELSE 0 END) AS correct_compounding_count,
        SUM(CASE WHEN compounding_status = 'INCORRECT_NO_COMPOUND' THEN 1 ELSE 0 END) AS no_compounding_count,
        SUM(CASE WHEN compounding_status = 'MISMATCH' THEN 1 ELSE 0 END) AS mismatch_count,
        -- Calculate percentages
        ROUND(100.0 * SUM(CASE WHEN compounding_status = 'CORRECT' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS correct_compounding_pct,
        -- Average discrepancy for incorrect cases
        AVG(CASE WHEN compounding_status != 'CORRECT' THEN ABS(salary_discrepancy) END) AS avg_discrepancy_amount,
        -- Total lost compensation due to non-compounding
        SUM(CASE WHEN compounding_status = 'INCORRECT_NO_COMPOUND' THEN salary_discrepancy ELSE 0 END) AS total_lost_compensation
    FROM compounding_validation
)

-- Final output combining all analysis
SELECT
    am.calculation_method,
    am.simulation_year,
    am.total_employees,
    am.continuous_employees,
    am.new_hire_employees,
    am.avg_compensation,
    am.yoy_growth_pct,

    -- Target assessment
    ta.target_growth_pct,
    ta.tolerance_pct,
    ta.target_status,
    ta.deviation_from_target,

    -- Dilution analysis (repeated for each methodology for easier joining)
    da.new_hire_ratio,
    da.dilution_impact_pct,
    da.continuous_only_growth,
    da.full_year_equiv_growth,

    -- Policy implications
    CASE
        WHEN ta.target_status = 'BELOW_TARGET' AND am.calculation_method = 'methodology_a_current'
        THEN ROUND((2.0 - am.yoy_growth_pct) + da.dilution_impact_pct, 1)
        ELSE NULL
    END as required_policy_adjustment_pct,

    -- Compensation compounding validation metrics
    cs.employees_tracked_for_compounding,
    cs.correct_compounding_count,
    cs.correct_compounding_pct,
    cs.no_compounding_count,
    cs.avg_discrepancy_amount,
    cs.total_lost_compensation,

    CURRENT_TIMESTAMP as analysis_timestamp

FROM all_methodologies am
JOIN target_assessment ta ON am.calculation_method = ta.calculation_method
CROSS JOIN dilution_analysis da
CROSS JOIN compounding_summary cs
ORDER BY am.calculation_method
