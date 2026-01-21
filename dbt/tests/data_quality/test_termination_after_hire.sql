/*
    Test: Termination Date After Hire Date

    FR-005: System MUST include a data quality test that validates no termination_date < hire_date exists

    This test validates that all termination events have effective_date >= employee_hire_date.
    The test returns rows that violate this constraint - the result should be 0 rows.

    Bug Fix (E022): Ensures termination dates are always on or after the employee's hire date.

    Success Criteria:
    - SC-001: Zero employees in fct_workforce_snapshot have termination_date < employee_hire_date
    - SC-002: Zero termination events in fct_yearly_events have effective_date < the employee's hire_date
    - SC-003: Data quality test for termination-after-hire passes with zero violations
*/

-- Check fct_workforce_snapshot for termination_date < hire_date
SELECT
    employee_id,
    employee_hire_date,
    termination_date,
    'fct_workforce_snapshot' AS source_table,
    'termination_date < employee_hire_date' AS violation_type
FROM {{ ref('fct_workforce_snapshot') }}
WHERE termination_date IS NOT NULL
  AND employee_hire_date IS NOT NULL
  AND termination_date < employee_hire_date
  AND simulation_year = {{ var('simulation_year') }}

UNION ALL

-- Check fct_yearly_events for termination events with effective_date < hire_date
-- Join to get hire_date from workforce snapshot
SELECT
    e.employee_id,
    s.employee_hire_date,
    e.effective_date AS termination_date,
    'fct_yearly_events' AS source_table,
    'effective_date < employee_hire_date' AS violation_type
FROM {{ ref('fct_yearly_events') }} e
INNER JOIN {{ ref('fct_workforce_snapshot') }} s
    ON e.employee_id = s.employee_id
    AND e.simulation_year = s.simulation_year
WHERE UPPER(e.event_type) = 'TERMINATION'
  AND e.simulation_year = {{ var('simulation_year') }}
  AND s.employee_hire_date IS NOT NULL
  AND e.effective_date < s.employee_hire_date
