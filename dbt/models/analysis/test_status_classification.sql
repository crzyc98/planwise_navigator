{{ config(materialized='view') }}

WITH employee_analysis AS (
    SELECT
        e.employee_id,
        e.employee_source,
        e.employee_hire_date,
        e.initial_state_date,
        ws.detailed_status_code,
        ws.employment_status,
        -- Check if employee was hired during simulation year
        CASE
            WHEN DATE_PART('year', e.employee_hire_date) = {{ var('simulation_year', 2025) }} THEN 'hired_this_year'
            ELSE 'existing_employee'
        END as hire_timing_classification,
        -- Check the difference between hire date and simulation start
        DATE_DIFF('day',
            CAST('{{ var("simulation_year", 2025) }}-01-01' AS DATE),
            e.employee_hire_date
        ) as days_from_sim_start_to_hire
    FROM {{ ref('int_employees_with_initial_state') }} e
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws
        ON e.employee_id = ws.employee_id
        AND e.simulation_year = ws.simulation_year
    WHERE e.simulation_year = {{ var('simulation_year', 2025) }}
)

SELECT
    employee_source,
    employment_status,
    detailed_status_code,
    hire_timing_classification,
    COUNT(*) as employee_count,
    -- Show sample days from sim start to hire for new hires
    CASE
        WHEN hire_timing_classification = 'hired_this_year' THEN
            'Days from sim start: ' || MIN(days_from_sim_start_to_hire) || ' to ' || MAX(days_from_sim_start_to_hire)
        ELSE NULL
    END as hire_timing_range
FROM employee_analysis
GROUP BY 1, 2, 3, 4
ORDER BY employee_source, employment_status, detailed_status_code
