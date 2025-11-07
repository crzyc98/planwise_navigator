{{
  config(
    severity='error',
    tags=['data_quality', 'validation', 'new_hire_termination', 'employer_match', 'epic_e061']
  )
}}

/*
  Data Quality Test: New Hire Termination Employer Match Validation (Epic E061)

  Identifies new hire terminations incorrectly receiving employer match contributions
  despite configuration that should exclude them.

  The Problem (Epic E061):
  - New hire terminations receiving incorrect match payments
  - Root cause: apply_eligibility=false bypassed configured eligibility rules

  The Solution:
  - Enable apply_eligibility=true in simulation_config.yaml
  - Configure eligibility rules to exclude new hire terminations:
    * require_active_at_year_end=true (excludes year-of-hire terminations)
    * allow_terminated_new_hires=false (explicit exclusion)

  Returns rows where new hire terminations incorrectly receive employer match.
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH new_hire_termination_employees AS (
    SELECT DISTINCT
        nht.employee_id,
        nht.effective_date AS termination_date,
        'new_hire_termination' AS employee_category
    FROM {{ ref('int_new_hire_termination_events') }} nht
    WHERE nht.simulation_year = {{ simulation_year }}
),

employer_eligibility_status AS (
    SELECT
        employee_id,
        simulation_year,
        eligible_for_match,
        match_eligibility_reason,
        match_apply_eligibility,
        employment_status,
        annual_hours_worked,
        current_tenure,
        match_allow_terminated_new_hires,
        match_requires_active_eoy
    FROM {{ ref('int_employer_eligibility') }}
    WHERE simulation_year = {{ simulation_year }}
),

employee_match_calculations AS (
    SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        employer_match_amount,
        match_status,
        is_eligible_for_match,
        match_eligibility_reason AS match_calc_reason
    FROM {{ ref('int_employee_match_calculations') }}
    WHERE simulation_year = {{ simulation_year }}
),

workforce_snapshot_data AS (
    SELECT
        employee_id,
        simulation_year,
        employment_status AS final_employment_status,
        employer_match_amount AS final_match_amount,
        prorated_annual_compensation
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

employee_analysis AS (
    SELECT
        COALESCE(nht.employee_id, ees.employee_id, emc.employee_id, ws.employee_id) AS employee_id,
        {{ simulation_year }} AS simulation_year,
        CASE
            WHEN nht.employee_id IS NOT NULL THEN 'new_hire_termination'
            ELSE 'other'
        END AS employee_category,
        nht.termination_date,
        ees.eligible_for_match,
        ees.match_eligibility_reason,
        ees.match_apply_eligibility,
        ees.employment_status,
        emc.eligible_compensation,
        emc.deferral_rate,
        emc.annual_deferrals,
        emc.employer_match_amount,
        emc.match_status,
        ws.final_employment_status,
        ws.final_match_amount,
        ees.match_allow_terminated_new_hires,
        ees.match_requires_active_eoy
    FROM new_hire_termination_employees nht
    FULL OUTER JOIN employer_eligibility_status ees ON nht.employee_id = ees.employee_id
    FULL OUTER JOIN employee_match_calculations emc ON COALESCE(nht.employee_id) = emc.employee_id
    FULL OUTER JOIN workforce_snapshot_data ws ON COALESCE(nht.employee_id) = ws.employee_id
)

SELECT
    employee_id,
    simulation_year,
    employee_category,
    termination_date,
    eligible_for_match,
    match_eligibility_reason,
    match_apply_eligibility,
    employment_status,
    eligible_compensation,
    deferral_rate,
    annual_deferrals,
    employer_match_amount,
    final_match_amount,
    match_status,
    CASE
        WHEN employee_category = 'new_hire_termination'
             AND match_apply_eligibility = true
             AND COALESCE(employer_match_amount, 0) > 0 THEN 'FAIL'
        WHEN employee_category = 'new_hire_termination'
             AND match_apply_eligibility = false
             AND COALESCE(employer_match_amount, 0) > 0 THEN 'EXPECTED_ISSUE'
        ELSE 'N/A'
    END AS validation_status,
    CASE
        WHEN match_apply_eligibility = true AND match_allow_terminated_new_hires = false THEN 'CORRECT_CONFIG'
        WHEN match_apply_eligibility = false THEN 'BACKWARD_COMPATIBILITY'
        WHEN match_apply_eligibility = true AND match_allow_terminated_new_hires = true THEN 'INCORRECT_CONFIG'
        ELSE 'UNKNOWN_CONFIG'
    END AS configuration_status,
    CONCAT(
        'New hire termination receiving match: $', ROUND(COALESCE(employer_match_amount, 0), 2),
        ' - Config: apply_eligibility=', match_apply_eligibility,
        ', allow_terminated_new_hires=', COALESCE(match_allow_terminated_new_hires, false)
    ) AS issue_description
FROM employee_analysis
WHERE employee_category = 'new_hire_termination'
  AND (
      (match_apply_eligibility = true AND COALESCE(employer_match_amount, 0) > 0)
      OR (match_apply_eligibility = false AND COALESCE(employer_match_amount, 0) > 0)
  )
ORDER BY
    employer_match_amount DESC,
    employee_id
