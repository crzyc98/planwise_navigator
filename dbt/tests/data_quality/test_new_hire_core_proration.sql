-- Converted from validation model to test
-- Added simulation_year filter for performance

/*
  New Hire Core Contribution Proration Validation (Story S065-02)

  Validates the comprehensive fix for new hire core contribution proration implemented in Epic S065-02.
  Ensures that new hire core contributions are properly calculated based on prorated compensation,
  not full annual compensation, maintaining the ~1% contribution rate accuracy.

  The Problem (Story S065-02):
  - New hires were receiving core contributions based on full annual compensation
  - Should receive contributions based on prorated compensation from hire date to year-end
  - Employees with <1000 hours should receive $0 core contributions
  - Core contribution rate should be approximately 1% of prorated compensation

  The Solution:
  - Fixed proration logic in int_employer_core_contributions.sql
  - Proper calculation: prorated_compensation * core_contribution_rate
  - Enforcement of <1000 hour rule for core contributions
  - Validation of rate consistency across the workforce

  Key Validations:
  - Verifies proper proration for new hires (rate ~1% of prorated, not annual compensation)
  - Validates <1000 hour employees receive $0 core contributions
  - Checks for rate consistency violations (deviation > 0.1% from expected rate)
  - Ensures no regression in existing functionality
  - Validates data integrity and event sourcing guarantees

  Returns only failing records for dbt test.
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set expected_core_rate = var('employer_core_contribution_rate', 0.01) %}
{% set rate_tolerance = 0.001 %}  -- 0.1% tolerance for rate validation

WITH new_hire_employees AS (
    -- Identify employees who were hired in the current simulation year
    -- These are the primary focus of the proration validation
    SELECT DISTINCT
        h.employee_id,
        h.effective_date AS hire_date,
        'new_hire' AS employee_category
    FROM {{ ref('fct_yearly_events') }} h
    WHERE h.simulation_year = {{ simulation_year }}
      AND h.event_type = 'hire'
),

workforce_snapshot_data AS (
    -- Get workforce snapshot data with all relevant fields for validation
    SELECT
        employee_id,
        simulation_year,
        employee_hire_date,
        employment_status,
        annual_hours_worked,
        current_compensation,  -- Full annual compensation
        prorated_annual_compensation,  -- Prorated compensation (what should be used for core)
        employer_core_amount,
        total_employer_contributions
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

employer_core_data AS (
    -- Get detailed core contribution calculation data
    SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        employment_status,
        eligible_for_core,
        annual_hours_worked,
        employer_core_amount
    FROM {{ ref('int_employer_core_contributions') }}
    WHERE simulation_year = {{ simulation_year }}
),

termination_events AS (
    -- Identify employees who were terminated in the current year
    SELECT DISTINCT
        t.employee_id,
        t.effective_date AS termination_date
    FROM {{ ref('fct_yearly_events') }} t
    WHERE t.simulation_year = {{ simulation_year }}
      AND t.event_type = 'termination'
),

-- Combine all employee data for comprehensive analysis
employee_analysis AS (
    SELECT
        COALESCE(nh.employee_id, ws.employee_id, ecd.employee_id) AS employee_id,
        {{ simulation_year }} AS simulation_year,

        -- Employee categorization
        CASE
            WHEN nh.employee_id IS NOT NULL AND te.employee_id IS NOT NULL THEN 'new_hire_termination'
            WHEN nh.employee_id IS NOT NULL THEN 'new_hire_active'
            ELSE 'continuing_employee'
        END AS employee_category,

        nh.hire_date,
        te.termination_date,

        -- Compensation data
        ws.current_compensation AS annual_compensation,
        ws.prorated_annual_compensation,
        ws.annual_hours_worked,
        ws.employment_status,

        -- Core contribution data
        ws.employer_core_amount AS final_core_amount,
        ecd.employer_core_amount AS calculated_core_amount,
        ecd.eligible_for_core,
        ecd.eligible_compensation,

        -- Calculate expected core amount based on prorated compensation
        CASE
            WHEN ws.prorated_annual_compensation IS NOT NULL
                 AND ws.prorated_annual_compensation > 0
                 AND COALESCE(ws.annual_hours_worked, 0) >= 1000
            THEN ROUND(ws.prorated_annual_compensation * {{ expected_core_rate }}, 2)
            ELSE 0.00
        END AS expected_core_amount_prorated,

        -- Calculate what core would be if incorrectly based on annual compensation
        CASE
            WHEN ws.current_compensation IS NOT NULL
                 AND ws.current_compensation > 0
                 AND COALESCE(ws.annual_hours_worked, 0) >= 1000
            THEN ROUND(ws.current_compensation * {{ expected_core_rate }}, 2)
            ELSE 0.00
        END AS incorrect_core_amount_annual

    FROM new_hire_employees nh
    FULL OUTER JOIN workforce_snapshot_data ws ON nh.employee_id = ws.employee_id
    FULL OUTER JOIN employer_core_data ecd ON COALESCE(nh.employee_id, ws.employee_id) = ecd.employee_id
    LEFT JOIN termination_events te ON COALESCE(nh.employee_id, ws.employee_id) = te.employee_id

    WHERE COALESCE(nh.employee_id, ws.employee_id, ecd.employee_id) IS NOT NULL
),

-- Core validation logic
validation_results AS (
    SELECT
        employee_id,
        simulation_year,
        employee_category,
        hire_date,
        termination_date,
        annual_compensation,
        prorated_annual_compensation,
        annual_hours_worked,
        employment_status,
        final_core_amount,
        calculated_core_amount,
        expected_core_amount_prorated,
        incorrect_core_amount_annual,
        eligible_for_core,

        -- S065-02: Core validation - New hires should receive core based on prorated compensation
        CASE
            WHEN employee_category IN ('new_hire_active', 'new_hire_termination')
                 AND eligible_for_core = true
                 AND COALESCE(annual_hours_worked, 0) >= 1000
                 AND ABS(COALESCE(final_core_amount, 0) - expected_core_amount_prorated) <= {{ rate_tolerance }} * prorated_annual_compensation
            THEN 'PASS'
            WHEN employee_category IN ('new_hire_active', 'new_hire_termination')
                 AND eligible_for_core = true
                 AND COALESCE(annual_hours_worked, 0) >= 1000
                 AND ABS(COALESCE(final_core_amount, 0) - expected_core_amount_prorated) > {{ rate_tolerance }} * prorated_annual_compensation
            THEN 'FAIL'
            WHEN employee_category IN ('new_hire_active', 'new_hire_termination')
                 AND (eligible_for_core = false OR COALESCE(annual_hours_worked, 0) < 1000)
                 AND COALESCE(final_core_amount, 0) = 0
            THEN 'PASS'
            WHEN employee_category IN ('new_hire_active', 'new_hire_termination')
                 AND (eligible_for_core = false OR COALESCE(annual_hours_worked, 0) < 1000)
                 AND COALESCE(final_core_amount, 0) > 0
            THEN 'FAIL'
            ELSE 'N/A'
        END AS new_hire_proration_validation,

        -- Validation for <1000 hour employees receiving $0 core
        CASE
            WHEN COALESCE(annual_hours_worked, 0) < 1000
                 AND COALESCE(final_core_amount, 0) = 0
            THEN 'PASS'
            WHEN COALESCE(annual_hours_worked, 0) < 1000
                 AND COALESCE(final_core_amount, 0) > 0
            THEN 'FAIL'
            ELSE 'N/A'
        END AS low_hours_validation,

        -- Rate consistency validation (for eligible employees with >1000 hours)
        CASE
            WHEN eligible_for_core = true
                 AND COALESCE(annual_hours_worked, 0) >= 1000
                 AND prorated_annual_compensation > 0
                 AND ABS((COALESCE(final_core_amount, 0) / prorated_annual_compensation) - {{ expected_core_rate }}) <= {{ rate_tolerance }}
            THEN 'PASS'
            WHEN eligible_for_core = true
                 AND COALESCE(annual_hours_worked, 0) >= 1000
                 AND prorated_annual_compensation > 0
                 AND ABS((COALESCE(final_core_amount, 0) / prorated_annual_compensation) - {{ expected_core_rate }}) > {{ rate_tolerance }}
            THEN 'FAIL'
            ELSE 'N/A'
        END AS rate_consistency_validation,

        -- Calculate actual rate for analysis
        CASE
            WHEN prorated_annual_compensation > 0
            THEN ROUND(COALESCE(final_core_amount, 0) / prorated_annual_compensation, 4)
            ELSE 0
        END AS actual_core_rate,

        -- Identify potential issues with annual vs prorated calculation
        CASE
            WHEN employee_category IN ('new_hire_active', 'new_hire_termination')
                 AND eligible_for_core = true
                 AND COALESCE(annual_hours_worked, 0) >= 1000
                 AND ABS(COALESCE(final_core_amount, 0) - incorrect_core_amount_annual) < ABS(COALESCE(final_core_amount, 0) - expected_core_amount_prorated)
            THEN 'LIKELY_USING_ANNUAL_COMPENSATION'
            WHEN employee_category IN ('new_hire_active', 'new_hire_termination')
                 AND eligible_for_core = true
                 AND COALESCE(annual_hours_worked, 0) >= 1000
                 AND ABS(COALESCE(final_core_amount, 0) - expected_core_amount_prorated) < ABS(COALESCE(final_core_amount, 0) - incorrect_core_amount_annual)
            THEN 'CORRECTLY_USING_PRORATED_COMPENSATION'
            ELSE 'N/A'
        END AS compensation_basis_validation,

        -- Calculate variance from expected
        expected_core_amount_prorated - COALESCE(final_core_amount, 0) AS core_amount_variance

    FROM employee_analysis
)

-- Return only failing records for dbt test
SELECT *
FROM validation_results
WHERE employee_id IS NOT NULL
  AND (new_hire_proration_validation = 'FAIL'
       OR low_hours_validation = 'FAIL'
       OR rate_consistency_validation = 'FAIL')
