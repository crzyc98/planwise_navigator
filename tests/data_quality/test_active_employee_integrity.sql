-- Test to validate that int_workforce_active_for_events correctly excludes terminated employees
-- This prevents the data integrity issue where terminated employees receive events in subsequent years

{{ config(
    tags=['data_quality', 'critical'],
    severity='error'
) }}

-- Test 1: Verify that no employees who had termination events in the previous year 
-- appear in the current year's active employee list
WITH previous_year_terminations AS (
    SELECT DISTINCT
        employee_id,
        simulation_year AS termination_year,
        simulation_year + 1 AS next_year
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'termination'
),

current_year_active_employees AS (
    SELECT 
        employee_id,
        simulation_year
    FROM {{ ref('int_workforce_active_for_events') }}
),

-- Find any employees who were terminated in year N but appear as active in year N+1
integrity_violations AS (
    SELECT 
        pyt.employee_id,
        pyt.termination_year,
        cyae.simulation_year AS active_year,
        'TERMINATED_EMPLOYEE_ACTIVE' AS violation_type
    FROM previous_year_terminations pyt
    INNER JOIN current_year_active_employees cyae 
        ON pyt.employee_id = cyae.employee_id 
        AND pyt.next_year = cyae.simulation_year
)

-- This test should return 0 rows if data integrity is maintained
SELECT *
FROM integrity_violations