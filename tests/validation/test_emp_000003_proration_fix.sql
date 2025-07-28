-- Test for EMP_000003 prorated compensation calculation fix
-- This test validates the specific scenario that was overstated by $471
-- Expected: $62,337.78 (319 employment days with salary change on July 14, 2028)

{% set test_employee = 'EMP_000003' %}
{% set test_year = 2028 %}

WITH expected_calculation AS (
    -- Manual calculation for validation
    SELECT
        '{{ test_employee }}' AS employee_id,
        {{ test_year }} AS simulation_year,

        -- Employment period: Jan 1 - Nov 14, 2028 (319 days)
        319 AS expected_employment_days,

        -- Period 1: Jan 1 - July 13 (195 days) @ $60,853.72
        195 AS period_1_days,
        60853.72 AS period_1_salary,

        -- Period 2: July 14 - Nov 14 (124 days) @ $64,671.59
        124 AS period_2_days,
        64671.59 AS period_2_salary,

        -- Expected prorated calculation
        ROUND(
            (60853.72 * 195 + 64671.59 * 124) / 319,
            2
        ) AS expected_prorated_compensation
),

actual_calculation AS (
    -- Get actual calculation from fct_workforce_snapshot
    SELECT
        employee_id,
        simulation_year,
        prorated_annual_compensation AS actual_prorated_compensation,
        employment_status,
        termination_date,
        employee_hire_date
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employee_id = '{{ test_employee }}'
      AND simulation_year = {{ test_year }}
),

validation_results AS (
    SELECT
        e.employee_id,
        e.simulation_year,
        e.expected_prorated_compensation,
        a.actual_prorated_compensation,
        a.employment_status,
        a.termination_date,
        a.employee_hire_date,

        -- Calculate the difference
        ABS(a.actual_prorated_compensation - e.expected_prorated_compensation) AS calculation_difference,

        -- Validation status
        CASE
            WHEN ABS(a.actual_prorated_compensation - e.expected_prorated_compensation) < 0.01
            THEN 'PASS'
            ELSE 'FAIL'
        END AS validation_status,

        -- Error details if validation fails
        CASE
            WHEN ABS(a.actual_prorated_compensation - e.expected_prorated_compensation) >= 0.01
            THEN CONCAT(
                'Expected: $', CAST(e.expected_prorated_compensation AS VARCHAR),
                ', Actual: $', CAST(a.actual_prorated_compensation AS VARCHAR),
                ', Difference: $', CAST(ABS(a.actual_prorated_compensation - e.expected_prorated_compensation) AS VARCHAR)
            )
            ELSE 'Calculation matches expected result'
        END AS error_details

    FROM expected_calculation e
    LEFT JOIN actual_calculation a ON e.employee_id = a.employee_id
),

-- Additional debugging: Check the actual periods created for this employee
period_debug AS (
    SELECT
        '{{ test_employee }}' AS employee_id,
        'PERIOD_DEBUG' AS validation_status,
        CONCAT(
            'Actual periods would need to be checked in compensation_periods CTE - ',
            'this requires the model to be built to see intermediate results'
        ) AS error_details,
        NULL AS expected_prorated_compensation,
        NULL AS actual_prorated_compensation,
        NULL AS calculation_difference,
        NULL AS employment_status,
        NULL AS termination_date,
        NULL AS employee_hire_date,
        {{ test_year }} AS simulation_year
)

-- Return validation results
SELECT
    employee_id,
    simulation_year,
    validation_status,
    expected_prorated_compensation,
    actual_prorated_compensation,
    calculation_difference,
    employment_status,
    termination_date,
    employee_hire_date,
    error_details
FROM validation_results

UNION ALL

SELECT
    employee_id,
    simulation_year,
    validation_status,
    expected_prorated_compensation,
    actual_prorated_compensation,
    calculation_difference,
    employment_status,
    termination_date,
    employee_hire_date,
    error_details
FROM period_debug

-- Test should return 'PASS' for the main validation
-- If it returns 'FAIL', the error_details will show the discrepancy
