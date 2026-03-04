{{
  config(
    severity='error',
    tags=['data_quality', 'erisa', 'eligibility']
  )
}}

/*
  Data Quality Test: IECP Computation Period Validation

  Validates:
  (a) IECP spans exactly 12 months from hire date
  (b) iecp_year1_hours + iecp_year2_hours = iecp_total_hours
  (c) Mid-year hires produce correct partial-year proration
  (d) System switches to plan_year period type after first anniversary
  (e) Plan entry dates comply with IRC 410(a)(4) statutory maximum
  (f) Every row has non-null eligibility_reason and traceable audit fields

  Returns failure rows only with descriptive issue_description.
*/

-- Plan year boundaries from same config the model uses
{% set pysd = var('plan_year_start_date', '2025-01-01') | string %}
{% set plan_year_start_month = pysd[5:7] | int %}
{% set plan_year_start_day = pysd[8:10] | int %}

WITH validation_checks AS (
  SELECT
    ecp.employee_id,
    ecp.simulation_year,
    ecp.period_type,
    ecp.hire_date,
    ecp.iecp_end_date,
    ecp.iecp_year1_hours,
    ecp.iecp_year2_hours,
    ecp.iecp_total_hours,
    ecp.annual_hours_prorated,
    ecp.hours_classification,
    ecp.plan_entry_date,
    ecp.eligibility_reason,
    ecp.period_start_date,
    ecp.period_end_date,
    ecp.eligibility_years_this_period,

    -- (a) IECP should span exactly 12 months from hire date
    CASE
      WHEN ecp.period_type = 'iecp'
           AND ecp.iecp_end_date != (ecp.hire_date + INTERVAL '1 year')::DATE
        THEN 'IECP end date does not equal hire_date + 12 months: iecp_end=' || CAST(ecp.iecp_end_date AS VARCHAR) || ', expected=' || CAST((ecp.hire_date + INTERVAL '1 year')::DATE AS VARCHAR)
      ELSE NULL
    END AS check_a,

    -- (b) IECP hour sum consistency
    CASE
      WHEN ecp.period_type = 'iecp'
           AND ABS(ecp.iecp_total_hours - (ecp.iecp_year1_hours + ecp.iecp_year2_hours)) > 0.01
        THEN 'IECP hour sum mismatch: total=' || CAST(ecp.iecp_total_hours AS VARCHAR) || ', year1+year2=' || CAST(ecp.iecp_year1_hours + ecp.iecp_year2_hours AS VARCHAR)
      ELSE NULL
    END AS check_b,

    -- (c) Mid-year hires should have prorated hours < 2080 in hire year
    CASE
      WHEN ecp.period_type = 'iecp'
           AND EXTRACT(YEAR FROM ecp.hire_date) = ecp.simulation_year
           AND EXTRACT(MONTH FROM ecp.hire_date) > 1
           AND ecp.iecp_year1_hours >= 2080.0
        THEN 'Mid-year hire has non-prorated hours: hire_date=' || CAST(ecp.hire_date AS VARCHAR) || ', hours=' || CAST(ecp.iecp_year1_hours AS VARCHAR)
      ELSE NULL
    END AS check_c,

    -- (d) After IECP completion, period_type should be plan_year
    CASE
      WHEN ecp.period_type = 'iecp'
           AND (ecp.hire_date + INTERVAL '1 year')::DATE < MAKE_DATE(ecp.simulation_year, 1, 1)
        THEN 'IECP period_type used after IECP should be complete: hire_date=' || CAST(ecp.hire_date AS VARCHAR) || ', sim_year=' || CAST(ecp.simulation_year AS VARCHAR)
      ELSE NULL
    END AS check_d,

    -- (e) Plan entry date must not exceed statutory maximum per IRC 410(a)(4)
    CASE
      WHEN ecp.plan_entry_date IS NOT NULL
           AND ecp.plan_entry_date > LEAST(
             MAKE_DATE(ecp.simulation_year + 1, {{ plan_year_start_month }}, {{ plan_year_start_day }}),
             CASE
               WHEN ecp.period_type = 'iecp' AND EXTRACT(YEAR FROM ecp.hire_date) = ecp.simulation_year
                 THEN (ecp.period_end_date + INTERVAL '6 months')::DATE
               WHEN ecp.period_type = 'iecp'
                 THEN (ecp.iecp_end_date + INTERVAL '6 months')::DATE
               ELSE (ecp.period_end_date + INTERVAL '6 months')::DATE
             END
           )
        THEN 'Plan entry date exceeds IRC 410(a)(4) maximum: entry=' || CAST(ecp.plan_entry_date AS VARCHAR)
      ELSE NULL
    END AS check_e,

    -- (f) Audit trail: non-null eligibility_reason, period_type, hours
    CASE
      WHEN ecp.eligibility_reason IS NULL THEN 'NULL eligibility_reason'
      WHEN ecp.period_type IS NULL THEN 'NULL period_type'
      WHEN ecp.annual_hours_prorated IS NULL THEN 'NULL annual_hours_prorated'
      ELSE NULL
    END AS check_f

  FROM {{ ref('int_eligibility_computation_period') }} ecp
)

SELECT
  employee_id,
  simulation_year,
  period_type,
  hire_date,
  COALESCE(check_a, check_b, check_c, check_d, check_e, check_f) AS issue_description
FROM validation_checks
WHERE check_a IS NOT NULL
   OR check_b IS NOT NULL
   OR check_c IS NOT NULL
   OR check_d IS NOT NULL
   OR check_e IS NOT NULL
   OR check_f IS NOT NULL
ORDER BY employee_id
