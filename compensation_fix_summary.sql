-- E066 Fix Impact Summary
-- Shows how many employees are affected and the overall impact

WITH compensation_comparison AS (
    SELECT
        employee_id,
        employee_hire_date,
        employee_gross_compensation,
        employee_annualized_compensation,

        -- OLD vs NEW logic
        COALESCE(employee_gross_compensation, employee_annualized_compensation) AS old_compensation,
        COALESCE(employee_annualized_compensation, employee_gross_compensation) AS new_compensation,

        -- Identify affected employees (where old != new)
        CASE
            WHEN COALESCE(employee_gross_compensation, employee_annualized_compensation) !=
                 COALESCE(employee_annualized_compensation, employee_gross_compensation)
            THEN 1 ELSE 0
        END AS is_affected,

        -- Categorize by hire timing
        CASE
            WHEN employee_hire_date >= '2024-10-01' THEN 'Q4 2024 (Late Hire)'
            WHEN employee_hire_date >= '2024-01-01' THEN 'Earlier 2024'
            ELSE 'Pre-2024'
        END AS hire_period

    FROM {{ ref('stg_census_data') }}
    WHERE employee_termination_date IS NULL
)

SELECT
    hire_period,
    COUNT(*) as total_employees,
    SUM(is_affected) as affected_employees,
    ROUND(SUM(is_affected) * 100.0 / COUNT(*), 1) as pct_affected,

    -- Compensation impact for affected employees only
    ROUND(AVG(CASE WHEN is_affected = 1 THEN old_compensation END), 0) as avg_old_compensation_affected,
    ROUND(AVG(CASE WHEN is_affected = 1 THEN new_compensation END), 0) as avg_new_compensation_affected,
    ROUND(AVG(CASE WHEN is_affected = 1 THEN (new_compensation - old_compensation) END), 0) as avg_compensation_increase,

    -- Total compensation impact
    ROUND(SUM(CASE WHEN is_affected = 1 THEN (new_compensation - old_compensation) END), 0) as total_compensation_increase

FROM compensation_comparison
GROUP BY hire_period
ORDER BY
    CASE hire_period
        WHEN 'Q4 2024 (Late Hire)' THEN 1
        WHEN 'Earlier 2024' THEN 2
        WHEN 'Pre-2024' THEN 3
    END
