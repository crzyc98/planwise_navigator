-- E066 Compensation Annualization Fix Validation
-- This query shows the before/after impact of preferring annualized vs gross compensation

WITH compensation_comparison AS (
    SELECT
        employee_id,
        employee_hire_date,
        employee_gross_compensation,
        employee_annualized_compensation,

        -- OLD LOGIC (what we had before)
        COALESCE(employee_gross_compensation, employee_annualized_compensation) AS old_current_compensation,

        -- NEW LOGIC (our fix)
        COALESCE(employee_annualized_compensation, employee_gross_compensation) AS new_current_compensation,

        -- Calculate the difference
        COALESCE(employee_annualized_compensation, employee_gross_compensation) -
        COALESCE(employee_gross_compensation, employee_annualized_compensation) AS compensation_difference,

        -- Calculate percentage change
        CASE
            WHEN COALESCE(employee_gross_compensation, employee_annualized_compensation) > 0
            THEN (COALESCE(employee_annualized_compensation, employee_gross_compensation) -
                  COALESCE(employee_gross_compensation, employee_annualized_compensation)) * 100.0 /
                  COALESCE(employee_gross_compensation, employee_annualized_compensation)
            ELSE 0
        END AS percentage_change,

        -- Days worked in 2024 for late hires
        CASE
            WHEN employee_hire_date >= '2024-01-01'
            THEN DATE_DIFF('day', employee_hire_date, '2024-12-31') + 1
            ELSE 365
        END AS days_worked_2024

    FROM {{ ref('stg_census_data') }}
    WHERE employee_termination_date IS NULL
),

late_hires_analysis AS (
    SELECT *,
        CASE
            WHEN employee_hire_date >= '2024-10-01' THEN 'Q4 2024 (Late Hire)'
            WHEN employee_hire_date >= '2024-07-01' THEN 'Q3 2024'
            WHEN employee_hire_date >= '2024-01-01' THEN 'Q1-Q2 2024'
            ELSE 'Pre-2024'
        END AS hire_period
    FROM compensation_comparison
)

SELECT
    -- Focus on the example employee first
    employee_id,
    employee_hire_date,
    hire_period,
    days_worked_2024,
    old_current_compensation,
    new_current_compensation,
    compensation_difference,
    ROUND(percentage_change, 1) AS percentage_change

FROM late_hires_analysis
WHERE employee_id = 'EMP_2024_003851'
   OR hire_period = 'Q4 2024 (Late Hire)'  -- Show all late hires
ORDER BY
    CASE WHEN employee_id = 'EMP_2024_003851' THEN 0 ELSE 1 END,  -- Put example employee first
    employee_hire_date DESC
