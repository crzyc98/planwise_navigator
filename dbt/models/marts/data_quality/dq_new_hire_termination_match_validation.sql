{{ config(
    materialized='table',
    tags=['data_quality', 'validation', 'new_hire_termination', 'employer_match', 'epic_e061']
) }}

/*
  New Hire Termination Employer Match Validation (Epic E061)

  Identifies and validates the fix for new hire terminations incorrectly receiving
  employer match contributions despite configuration that should exclude them.

  The Problem (Epic E061):
  - 126 out of 218 new hire terminations receiving incorrect match payments
  - Total $110,713 in incorrect match payments in 2025
  - Root cause: apply_eligibility=false bypassed configured eligibility rules

  The Solution:
  - Enable apply_eligibility=true in simulation_config.yaml
  - Configure eligibility rules to exclude new hire terminations:
    * require_active_at_year_end=true (excludes year-of-hire terminations)
    * allow_terminated_new_hires=false (explicit exclusion)

  Key Validations:
  - Identifies new hire terminations receiving match when they shouldn't
  - Calculates financial impact of the issue
  - Validates that the fix eliminates incorrect payments
  - Ensures legitimate employees still receive proper match
  - Tracks eligibility enforcement status and reasons

  Performance: Optimized for large datasets using efficient joins and filtering
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH new_hire_termination_employees AS (
    -- Identify employees who were both hired and terminated in the same simulation year
    -- These are the employees who should NOT receive employer match under the new rules
    SELECT DISTINCT
        nht.employee_id,
        nht.effective_date AS termination_date,
        'new_hire_termination' AS employee_category
    FROM {{ ref('int_new_hire_termination_events') }} nht
    WHERE nht.simulation_year = {{ simulation_year }}
),

new_hire_employees AS (
    -- Get all new hires for the simulation year (including those who stayed active)
    SELECT DISTINCT
        h.employee_id,
        h.effective_date AS hire_date,
        'new_hire_active' AS employee_category
    FROM {{ ref('int_hiring_events') }} h
    WHERE h.simulation_year = {{ simulation_year }}
      AND h.employee_id NOT IN (
          SELECT employee_id FROM new_hire_termination_employees
      )
),

employer_eligibility_status AS (
    -- Get employer eligibility determinations for all employees
    SELECT
        employee_id,
        simulation_year,
        eligible_for_match,
        match_eligibility_reason,
        match_apply_eligibility,
        employment_status,
        annual_hours_worked,
        current_tenure,
        -- Metadata for audit trail
        match_allow_new_hires,
        match_allow_terminated_new_hires,
        match_allow_experienced_terminations,
        match_requires_active_eoy
    FROM {{ ref('int_employer_eligibility') }}
    WHERE simulation_year = {{ simulation_year }}
),

employee_match_calculations AS (
    -- Get match calculations for all employees
    SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        employer_match_amount,
        uncapped_match_amount,
        match_status,
        is_eligible_for_match,
        match_eligibility_reason AS match_calc_reason,
        eligibility_config_applied
    FROM {{ ref('int_employee_match_calculations') }}
    WHERE simulation_year = {{ simulation_year }}
),

workforce_snapshot_data AS (
    -- Get final workforce snapshot data for cross-validation
    SELECT
        employee_id,
        simulation_year,
        employment_status AS final_employment_status,
        employer_match_amount AS final_match_amount,
        total_employer_contributions,
        prorated_annual_compensation
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- Combine all employee data for comprehensive analysis
employee_analysis AS (
    SELECT
        COALESCE(
            nht.employee_id,
            nh.employee_id,
            ees.employee_id,
            emc.employee_id,
            ws.employee_id
        ) AS employee_id,
        {{ simulation_year }} AS simulation_year,

        -- Employee categorization
        CASE
            WHEN nht.employee_id IS NOT NULL THEN 'new_hire_termination'
            WHEN nh.employee_id IS NOT NULL THEN 'new_hire_active'
            ELSE 'continuing_employee'
        END AS employee_category,

        nht.termination_date,
        nh.hire_date,

        -- Eligibility data
        ees.eligible_for_match,
        ees.match_eligibility_reason,
        ees.match_apply_eligibility,
        ees.employment_status,
        ees.annual_hours_worked,
        ees.current_tenure,

        -- Match calculation data
        emc.eligible_compensation,
        emc.deferral_rate,
        emc.annual_deferrals,
        emc.employer_match_amount,
        emc.uncapped_match_amount,
        emc.match_status,
        emc.is_eligible_for_match AS calc_eligible_for_match,
        emc.match_calc_reason,
        emc.eligibility_config_applied,

        -- Final snapshot data
        ws.final_employment_status,
        ws.final_match_amount,
        ws.total_employer_contributions,
        ws.prorated_annual_compensation,

        -- Configuration metadata
        ees.match_allow_new_hires,
        ees.match_allow_terminated_new_hires,
        ees.match_allow_experienced_terminations,
        ees.match_requires_active_eoy

    FROM new_hire_termination_employees nht
    FULL OUTER JOIN new_hire_employees nh ON nht.employee_id = nh.employee_id
    FULL OUTER JOIN employer_eligibility_status ees ON COALESCE(nht.employee_id, nh.employee_id) = ees.employee_id
    FULL OUTER JOIN employee_match_calculations emc ON COALESCE(nht.employee_id, nh.employee_id) = emc.employee_id
    FULL OUTER JOIN workforce_snapshot_data ws ON COALESCE(nht.employee_id, nh.employee_id) = ws.employee_id
),

-- Validation logic
validation_results AS (
    SELECT
        employee_id,
        simulation_year,
        employee_category,
        termination_date,
        hire_date,

        -- Eligibility and match data
        eligible_for_match,
        match_eligibility_reason,
        match_apply_eligibility,
        employment_status,
        annual_hours_worked,
        current_tenure,

        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        employer_match_amount,
        final_match_amount,
        match_status,

        -- Epic E061: Core validation - New hire terminations should NOT receive match
        CASE
            WHEN employee_category = 'new_hire_termination'
                 AND match_apply_eligibility = true
                 AND COALESCE(employer_match_amount, 0) > 0 THEN 'FAIL'
            WHEN employee_category = 'new_hire_termination'
                 AND match_apply_eligibility = true
                 AND COALESCE(employer_match_amount, 0) = 0 THEN 'PASS'
            WHEN employee_category = 'new_hire_termination'
                 AND match_apply_eligibility = false
                 AND COALESCE(employer_match_amount, 0) > 0 THEN 'EXPECTED_ISSUE'  -- Known issue when eligibility disabled
            ELSE 'N/A'
        END AS new_hire_termination_match_validation,

        -- Configuration validation
        CASE
            WHEN match_apply_eligibility = true AND match_allow_terminated_new_hires = false THEN 'CORRECT_CONFIG'
            WHEN match_apply_eligibility = false THEN 'BACKWARD_COMPATIBILITY'
            WHEN match_apply_eligibility = true AND match_allow_terminated_new_hires = true THEN 'INCORRECT_CONFIG'
            ELSE 'UNKNOWN_CONFIG'
        END AS configuration_validation,

        -- Eligibility reason validation for new hire terminations
        CASE
            WHEN employee_category = 'new_hire_termination'
                 AND match_apply_eligibility = true
                 AND eligible_for_match = false
                 AND match_eligibility_reason IN ('inactive_eoy', 'ineligible') THEN 'PASS'
            WHEN employee_category = 'new_hire_termination'
                 AND match_apply_eligibility = true
                 AND eligible_for_match = true THEN 'FAIL'
            WHEN employee_category = 'new_hire_termination'
                 AND match_apply_eligibility = false THEN 'BACKWARD_COMPATIBILITY'
            ELSE 'N/A'
        END AS eligibility_reason_validation,

        -- Financial impact calculation
        CASE
            WHEN employee_category = 'new_hire_termination'
                 AND COALESCE(employer_match_amount, 0) > 0 THEN employer_match_amount
            ELSE 0
        END AS incorrect_match_amount,

        -- Active employee validation (ensure they still get match if eligible)
        CASE
            WHEN employee_category IN ('new_hire_active', 'continuing_employee')
                 AND eligible_for_match = true
                 AND annual_deferrals > 0
                 AND COALESCE(employer_match_amount, 0) = 0 THEN 'FAIL'
            WHEN employee_category IN ('new_hire_active', 'continuing_employee')
                 AND eligible_for_match = true
                 AND annual_deferrals > 0
                 AND COALESCE(employer_match_amount, 0) > 0 THEN 'PASS'
            ELSE 'N/A'
        END AS eligible_employee_match_validation,

        eligibility_config_applied,
        match_allow_terminated_new_hires,
        match_requires_active_eoy

    FROM employee_analysis
),

-- Summary statistics
summary_stats AS (
    SELECT
        {{ simulation_year }} AS simulation_year,

        -- New hire termination statistics
        COUNT(CASE WHEN employee_category = 'new_hire_termination' THEN 1 END) AS total_new_hire_terminations,
        COUNT(CASE WHEN new_hire_termination_match_validation = 'FAIL' THEN 1 END) AS new_hire_terminations_with_incorrect_match,
        COUNT(CASE WHEN new_hire_termination_match_validation = 'PASS' THEN 1 END) AS new_hire_terminations_correctly_excluded,
        COUNT(CASE WHEN new_hire_termination_match_validation = 'EXPECTED_ISSUE' THEN 1 END) AS new_hire_terminations_legacy_issue,

        -- Financial impact
        SUM(incorrect_match_amount) AS total_incorrect_match_payments,
        AVG(CASE WHEN incorrect_match_amount > 0 THEN incorrect_match_amount END) AS avg_incorrect_match_per_employee,
        MAX(incorrect_match_amount) AS max_incorrect_match_per_employee,

        -- Configuration status
        MAX(CASE WHEN match_apply_eligibility = true THEN 1 ELSE 0 END) AS eligibility_enforcement_enabled,
        MAX(CASE WHEN match_allow_terminated_new_hires = false THEN 1 ELSE 0 END) AS terminated_new_hires_excluded,

        -- Active employee validation
        COUNT(CASE WHEN eligible_employee_match_validation = 'FAIL' THEN 1 END) AS eligible_employees_missing_match,
        COUNT(CASE WHEN eligible_employee_match_validation = 'PASS' THEN 1 END) AS eligible_employees_receiving_match,

        -- Overall validation status
        CASE
            WHEN COUNT(CASE WHEN new_hire_termination_match_validation = 'FAIL' THEN 1 END) = 0
                 AND COUNT(CASE WHEN eligible_employee_match_validation = 'FAIL' THEN 1 END) = 0 THEN 'ALL_PASS'
            WHEN COUNT(CASE WHEN new_hire_termination_match_validation = 'FAIL' THEN 1 END) > 0 THEN 'NEW_HIRE_TERMINATION_ISSUES'
            WHEN COUNT(CASE WHEN eligible_employee_match_validation = 'FAIL' THEN 1 END) > 0 THEN 'ELIGIBLE_EMPLOYEE_ISSUES'
            ELSE 'MIXED_ISSUES'
        END AS overall_validation_status

    FROM validation_results
)

-- Return both detailed results and summary
SELECT
    'DETAIL' AS record_type,
    employee_id,
    simulation_year,
    employee_category,
    termination_date,
    hire_date,
    eligible_for_match,
    match_eligibility_reason,
    match_apply_eligibility,
    employment_status,
    annual_hours_worked::INTEGER AS annual_hours_worked,
    current_tenure,
    eligible_compensation,
    deferral_rate,
    annual_deferrals,
    employer_match_amount,
    final_match_amount,
    match_status,
    new_hire_termination_match_validation,
    configuration_validation,
    eligibility_reason_validation,
    incorrect_match_amount,
    eligible_employee_match_validation,
    match_allow_terminated_new_hires,
    match_requires_active_eoy,

    -- Summary fields (NULL for detail records)
    NULL::BIGINT AS total_new_hire_terminations,
    NULL::BIGINT AS new_hire_terminations_with_incorrect_match,
    NULL::DECIMAL AS total_incorrect_match_payments,
    NULL::VARCHAR AS overall_validation_status

FROM validation_results
WHERE employee_id IS NOT NULL

UNION ALL

SELECT
    'SUMMARY' AS record_type,
    NULL AS employee_id,
    simulation_year,
    NULL AS employee_category,
    NULL AS termination_date,
    NULL AS hire_date,
    NULL AS eligible_for_match,
    NULL AS match_eligibility_reason,
    NULL AS match_apply_eligibility,
    NULL AS employment_status,
    NULL AS annual_hours_worked,
    NULL AS current_tenure,
    NULL AS eligible_compensation,
    NULL AS deferral_rate,
    NULL AS annual_deferrals,
    NULL AS employer_match_amount,
    NULL AS final_match_amount,
    NULL AS match_status,
    NULL AS new_hire_termination_match_validation,
    NULL AS configuration_validation,
    NULL AS eligibility_reason_validation,
    NULL AS incorrect_match_amount,
    NULL AS eligible_employee_match_validation,
    NULL AS match_allow_terminated_new_hires,
    NULL AS match_requires_active_eoy,

    -- Summary data
    total_new_hire_terminations,
    new_hire_terminations_with_incorrect_match,
    total_incorrect_match_payments,
    overall_validation_status

FROM summary_stats

ORDER BY record_type, employee_id
