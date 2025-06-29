{{ config(materialized='view') }}

-- Test model to verify parameter integration works correctly
-- Compares parameter-driven results with expected values

WITH parameter_validation AS (
    SELECT
        'default' AS scenario_id,
        2025 AS fiscal_year,
        1 AS job_level,
        'RAISE' AS event_type,
        'merit_base' AS parameter_name,
        {{ get_parameter_value('1', 'RAISE', 'merit_base', '2025') }} AS resolved_value,
        0.035 AS expected_value

    UNION ALL

    SELECT
        'default' AS scenario_id,
        2025 AS fiscal_year,
        5 AS job_level,
        'RAISE' AS event_type,
        'merit_base' AS parameter_name,
        {{ get_parameter_value('5', 'RAISE', 'merit_base', '2025') }} AS resolved_value,
        0.055 AS expected_value

    UNION ALL

    SELECT
        'default' AS scenario_id,
        2025 AS fiscal_year,
        1 AS job_level,
        'RAISE' AS event_type,
        'cola_rate' AS parameter_name,
        {{ get_parameter_value('1', 'RAISE', 'cola_rate', '2025') }} AS resolved_value,
        0.025 AS expected_value
),

validation_results AS (
    SELECT
        *,
        CASE
            WHEN ABS(resolved_value - expected_value) < 0.001 THEN 'PASS'
            ELSE 'FAIL'
        END AS test_result
    FROM parameter_validation
)

SELECT
    scenario_id,
    fiscal_year,
    job_level,
    parameter_name,
    resolved_value,
    expected_value,
    test_result,
    CASE
        WHEN test_result = 'FAIL' THEN 'Parameter resolution mismatch'
        ELSE 'Parameter resolution correct'
    END AS test_message
FROM validation_results
ORDER BY job_level, parameter_name
