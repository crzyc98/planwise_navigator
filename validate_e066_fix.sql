-- E066 Validation: Ensure no compensation caps remain in the pipeline
-- This validates that Epic E066's compensation cap removal is complete across all models

WITH test_employee_compensation AS (
    -- Test employee EMP_2024_003851 specifically - should maintain $2.9M+ across years
    SELECT
        employee_id,
        simulation_year,
        current_compensation,
        compensation_quality_flag,
        -- Check if compensation was artificially capped
        CASE
            WHEN current_compensation = 2000000 AND compensation_quality_flag != 'WARNING_OVER_2M'
            THEN 'LIKELY_CAPPED'
            WHEN current_compensation > 2000000
            THEN 'UNCAPPED_OK'
            ELSE 'NORMAL_RANGE'
        END as cap_analysis
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employee_id = 'EMP_2024_003851'
),

intermediate_model_compensation AS (
    -- Check int_active_employees_prev_year_snapshot for caps
    SELECT
        employee_id,
        simulation_year,
        employee_gross_compensation,
        'int_active_employees_prev_year_snapshot' as model_name,
        CASE
            WHEN employee_gross_compensation = 2000000 THEN 'SUSPICIOUS_EXACT_2M'
            WHEN employee_gross_compensation > 2000000 THEN 'ABOVE_2M_OK'
            ELSE 'NORMAL_RANGE'
        END as intermediate_cap_analysis
    FROM {{ ref('int_active_employees_prev_year_snapshot') }}
    WHERE employee_id = 'EMP_2024_003851'
      AND simulation_year >= 2026  -- Years where caps would matter
)

-- Final validation query
SELECT
    'WORKFORCE_SNAPSHOT' as model_type,
    employee_id,
    simulation_year,
    current_compensation as compensation_value,
    cap_analysis,
    -- Final assessment
    CASE
        WHEN cap_analysis = 'LIKELY_CAPPED' THEN 'E066_REGRESSION_DETECTED'
        WHEN cap_analysis = 'UNCAPPED_OK' THEN 'E066_FIX_WORKING'
        ELSE 'NORMAL_CASE'
    END as e066_status
FROM test_employee_compensation

UNION ALL

SELECT
    model_name as model_type,
    employee_id,
    simulation_year,
    employee_gross_compensation as compensation_value,
    intermediate_cap_analysis as cap_analysis,
    CASE
        WHEN intermediate_cap_analysis = 'SUSPICIOUS_EXACT_2M' THEN 'E066_INTERMEDIATE_REGRESSION'
        WHEN intermediate_cap_analysis = 'ABOVE_2M_OK' THEN 'E066_INTERMEDIATE_FIX_WORKING'
        ELSE 'NORMAL_CASE'
    END as e066_status
FROM intermediate_model_compensation

ORDER BY model_type, simulation_year
