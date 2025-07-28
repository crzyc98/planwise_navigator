-- Test to validate new hire status code classification in fct_workforce_snapshot
-- This test ensures employees hired during the simulation year have "new_hire_active" status
-- not "continuous_active" status

{% set simulation_year = var('simulation_year', 2025) %}

WITH status_validation AS (
    SELECT
        employee_id,
        employee_hire_date,
        simulation_year,
        employment_status,
        detailed_status_code,
        EXTRACT(YEAR FROM employee_hire_date) AS hire_year,

        -- Expected status based on hire year vs simulation year
        CASE
            WHEN employment_status = 'active' AND
                 EXTRACT(YEAR FROM employee_hire_date) = simulation_year
            THEN 'new_hire_active'

            WHEN employment_status = 'active' AND
                 EXTRACT(YEAR FROM employee_hire_date) < simulation_year
            THEN 'continuous_active'

            WHEN employment_status = 'terminated' AND
                 EXTRACT(YEAR FROM employee_hire_date) = simulation_year
            THEN 'new_hire_termination'

            WHEN employment_status = 'terminated' AND
                 EXTRACT(YEAR FROM employee_hire_date) < simulation_year
            THEN 'experienced_termination'

            ELSE 'unknown'
        END AS expected_status,

        -- Check if classification is correct
        CASE
            WHEN detailed_status_code =
                CASE
                    WHEN employment_status = 'active' AND
                         EXTRACT(YEAR FROM employee_hire_date) = simulation_year
                    THEN 'new_hire_active'

                    WHEN employment_status = 'active' AND
                         EXTRACT(YEAR FROM employee_hire_date) < simulation_year
                    THEN 'continuous_active'

                    WHEN employment_status = 'terminated' AND
                         EXTRACT(YEAR FROM employee_hire_date) = simulation_year
                    THEN 'new_hire_termination'

                    WHEN employment_status = 'terminated' AND
                         EXTRACT(YEAR FROM employee_hire_date) < simulation_year
                    THEN 'experienced_termination'

                    ELSE 'unknown'
                END
            THEN 'PASS'
            ELSE 'FAIL'
        END AS validation_result

    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

failed_validations AS (
    SELECT
        employee_id,
        hire_year,
        simulation_year,
        employment_status,
        detailed_status_code,
        expected_status,
        'Incorrect status classification' AS error_message
    FROM status_validation
    WHERE validation_result = 'FAIL'
),

summary_stats AS (
    SELECT
        'Status Classification Summary' AS test_category,
        detailed_status_code,
        COUNT(*) AS employee_count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS percentage
    FROM status_validation
    GROUP BY detailed_status_code
),

validation_summary AS (
    SELECT
        'Overall Validation Results' AS test_category,
        validation_result,
        COUNT(*) AS count
    FROM status_validation
    GROUP BY validation_result
)

-- Return any failures or validation summary
SELECT * FROM failed_validations
UNION ALL
SELECT
    test_category AS employee_id,
    NULL AS hire_year,
    NULL AS simulation_year,
    detailed_status_code AS employment_status,
    CAST(employee_count AS VARCHAR) AS detailed_status_code,
    CONCAT(CAST(percentage AS VARCHAR), '%') AS expected_status,
    'Status distribution summary' AS error_message
FROM summary_stats
UNION ALL
SELECT
    test_category AS employee_id,
    NULL AS hire_year,
    NULL AS simulation_year,
    validation_result AS employment_status,
    CAST(count AS VARCHAR) AS detailed_status_code,
    NULL AS expected_status,
    'Validation results summary' AS error_message
FROM validation_summary
