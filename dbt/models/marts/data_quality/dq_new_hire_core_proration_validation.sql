{{ config(
    materialized='table',
    tags=['data_quality', 'validation', 'new_hire_core_proration', 'epic_s065', 'critical']
) }}

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

  Returns both detailed validation results and summary statistics.
  Empty FAIL results indicate the fix is working correctly.
  Critical for ensuring core contribution accuracy and compliance.
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
),

-- Summary statistics for monitoring and reporting
summary_stats AS (
    SELECT
        {{ simulation_year }} AS simulation_year,

        -- New hire proration validation statistics
        COUNT(CASE WHEN employee_category IN ('new_hire_active', 'new_hire_termination') THEN 1 END) AS total_new_hires,
        COUNT(CASE WHEN new_hire_proration_validation = 'FAIL' THEN 1 END) AS new_hires_proration_failures,
        COUNT(CASE WHEN new_hire_proration_validation = 'PASS' THEN 1 END) AS new_hires_proration_passes,

        -- Low hours validation statistics
        COUNT(CASE WHEN annual_hours_worked < 1000 THEN 1 END) AS total_low_hours_employees,
        COUNT(CASE WHEN low_hours_validation = 'FAIL' THEN 1 END) AS low_hours_validation_failures,

        -- Rate consistency statistics
        COUNT(CASE WHEN rate_consistency_validation = 'FAIL' THEN 1 END) AS rate_consistency_failures,
        COUNT(CASE WHEN rate_consistency_validation = 'PASS' THEN 1 END) AS rate_consistency_passes,

        -- Compensation basis validation
        COUNT(CASE WHEN compensation_basis_validation = 'LIKELY_USING_ANNUAL_COMPENSATION' THEN 1 END) AS likely_using_annual_compensation,
        COUNT(CASE WHEN compensation_basis_validation = 'CORRECTLY_USING_PRORATED_COMPENSATION' THEN 1 END) AS correctly_using_prorated_compensation,

        -- Financial impact analysis
        SUM(ABS(core_amount_variance)) AS total_absolute_variance,
        AVG(CASE WHEN core_amount_variance != 0 THEN ABS(core_amount_variance) END) AS avg_absolute_variance,
        MAX(ABS(core_amount_variance)) AS max_absolute_variance,

        -- Overall validation status
        CASE
            WHEN COUNT(CASE WHEN new_hire_proration_validation = 'FAIL' THEN 1 END) = 0
                 AND COUNT(CASE WHEN low_hours_validation = 'FAIL' THEN 1 END) = 0
                 AND COUNT(CASE WHEN rate_consistency_validation = 'FAIL' THEN 1 END) = 0
            THEN 'ALL_PASS'
            WHEN COUNT(CASE WHEN new_hire_proration_validation = 'FAIL' THEN 1 END) > 0
            THEN 'NEW_HIRE_PRORATION_ISSUES'
            WHEN COUNT(CASE WHEN low_hours_validation = 'FAIL' THEN 1 END) > 0
            THEN 'LOW_HOURS_VALIDATION_ISSUES'
            WHEN COUNT(CASE WHEN rate_consistency_validation = 'FAIL' THEN 1 END) > 0
            THEN 'RATE_CONSISTENCY_ISSUES'
            ELSE 'MIXED_ISSUES'
        END AS overall_validation_status

    FROM validation_results
)

-- Return both detailed results (for investigation) and summary (for monitoring)
SELECT
    'DETAIL' AS record_type,
    employee_id,
    simulation_year,
    employee_category,
    hire_date,
    termination_date,
    annual_compensation,
    prorated_annual_compensation,
    annual_hours_worked::INTEGER AS annual_hours_worked,
    employment_status,
    eligible_for_core,
    final_core_amount,
    expected_core_amount_prorated,
    actual_core_rate,
    core_amount_variance,
    new_hire_proration_validation,
    low_hours_validation,
    rate_consistency_validation,
    compensation_basis_validation,

    -- Summary fields (NULL for detail records)
    NULL::BIGINT AS total_new_hires,
    NULL::BIGINT AS new_hires_proration_failures,
    NULL::BIGINT AS total_low_hours_employees,
    NULL::BIGINT AS low_hours_validation_failures,
    NULL::BIGINT AS rate_consistency_failures,
    NULL::BIGINT AS likely_using_annual_compensation,
    NULL::DECIMAL AS total_absolute_variance,
    NULL::VARCHAR AS overall_validation_status

FROM validation_results
WHERE employee_id IS NOT NULL

UNION ALL

SELECT
    'SUMMARY' AS record_type,
    NULL AS employee_id,
    simulation_year,
    NULL AS employee_category,
    NULL AS hire_date,
    NULL AS termination_date,
    NULL AS annual_compensation,
    NULL AS prorated_annual_compensation,
    NULL AS annual_hours_worked,
    NULL AS employment_status,
    NULL AS eligible_for_core,
    NULL AS final_core_amount,
    NULL AS expected_core_amount_prorated,
    NULL AS actual_core_rate,
    NULL AS core_amount_variance,
    NULL AS new_hire_proration_validation,
    NULL AS low_hours_validation,
    NULL AS rate_consistency_validation,
    NULL AS compensation_basis_validation,

    -- Summary data
    total_new_hires,
    new_hires_proration_failures,
    total_low_hours_employees,
    low_hours_validation_failures,
    rate_consistency_failures,
    likely_using_annual_compensation,
    total_absolute_variance,
    overall_validation_status

FROM summary_stats

ORDER BY record_type, employee_id
