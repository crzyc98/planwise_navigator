/*
    Test: Tenure At Termination Accuracy

    FR-008: System MUST include a data quality test that validates terminated employees
    have tenure = floor((termination_date - hire_date) / 365.25)

    This test validates that terminated employees have their tenure calculated to
    their termination date (not year-end). The test returns rows where the
    calculated tenure doesn't match the expected formula - the result should be 0 rows.

    Bug Fix (E022): Ensures terminated employees show tenure calculated to their
    termination date using the Anniversary Year Method.

    Success Criteria:
    - SC-005: Tenure calculations for terminated employees produce non-negative values (tenure >= 0)
    - SC-006: Tenure is calculated using the Anniversary Year Method
    - SC-007: For employee hired 2024-08-01 and terminated 2026-01-10, current_tenure = 1
    - SC-008: Data quality test for tenure-at-termination accuracy passes with zero violations

    Tolerance: Allows for 0 difference (exact match required)
*/

SELECT
    employee_id,
    employee_hire_date,
    termination_date,
    current_tenure AS actual_tenure,
    FLOOR(DATEDIFF('day', employee_hire_date, termination_date) / 365.25)::INTEGER AS expected_tenure,
    current_tenure - FLOOR(DATEDIFF('day', employee_hire_date, termination_date) / 365.25)::INTEGER AS tenure_difference,
    'tenure_mismatch' AS violation_type
FROM {{ ref('fct_workforce_snapshot') }}
WHERE employment_status = 'terminated'
  AND termination_date IS NOT NULL
  AND employee_hire_date IS NOT NULL
  AND simulation_year = {{ var('simulation_year') }}
  -- Violation: actual tenure doesn't match expected formula
  AND current_tenure != FLOOR(DATEDIFF('day', employee_hire_date, termination_date) / 365.25)::INTEGER
