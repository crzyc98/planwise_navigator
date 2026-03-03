{{ config(
    materialized='table',
    tags=['eligibility', 'erisa', 'STATE_ACCUMULATION']
) }}

/*
  ERISA Eligibility Computation Period Model (E063)

  Implements ERISA-compliant Initial Eligibility Computation Period (IECP)
  and plan-year computation periods with 1,000-hour threshold classification.

  Key features:
  - IECP boundary calculation from hire date (12-month window)
  - Plan-year switching after IECP completion
  - Overlap/double-credit rule per ERISA
  - IRC 410(a)(4) plan entry date computation
  - Prorated hours from 2,080 annual basis

  Sources:
  - int_baseline_workforce: Census employees with hire dates
  - int_hiring_events: Simulated new hires
  - int_new_hire_termination_events: Employment status (terminated flag)
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- Plan year boundaries (configurable via erisa_eligibility config)
{% set plan_year_start_month = var('erisa_eligibility', {}).get('plan_year_start_month', 1) | int %}
{% set plan_year_start_day = var('erisa_eligibility', {}).get('plan_year_start_day', 1) | int %}

WITH
-- Census employees (baseline workforce)
census_employees AS (
  SELECT
    employee_id,
    employee_hire_date AS hire_date,
    'active' AS employment_status,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("plan_design_id", "default") }}' AS plan_design_id
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employment_status = 'active'
    AND employee_id IS NOT NULL
),

-- Simulated new hires
new_hires AS (
  SELECT
    employee_id,
    effective_date AS hire_date,
    'active' AS employment_status,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("plan_design_id", "default") }}' AS plan_design_id
  FROM {{ ref('int_hiring_events') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employee_id IS NOT NULL
),

-- Combine all employees
all_employees AS (
  SELECT * FROM census_employees
  UNION ALL
  SELECT * FROM new_hires
),

-- Flag terminated new hires
terminated_new_hires AS (
  SELECT DISTINCT employee_id
  FROM {{ ref('int_new_hire_termination_events') }}
  WHERE simulation_year = {{ simulation_year }}
),

-- Enriched employee data with termination status and date boundaries
employee_base AS (
  SELECT
    ae.employee_id,
    ae.hire_date,
    ae.scenario_id,
    ae.plan_design_id,
    CASE
      WHEN tnr.employee_id IS NOT NULL THEN 'terminated'
      ELSE 'active'
    END AS employment_status,

    -- IECP boundary: hire_date + 12 months
    ae.hire_date + INTERVAL '1 year' AS hire_date_anniversary,

    -- Plan year boundaries for current simulation year
    MAKE_DATE({{ simulation_year }}, {{ plan_year_start_month }}, {{ plan_year_start_day }}) AS plan_year_start,
    MAKE_DATE({{ simulation_year }}, 12, 31) AS year_end,
    MAKE_DATE({{ simulation_year }}, 1, 1) AS year_start,

    -- Next plan year start (for entry date calculation)
    MAKE_DATE({{ simulation_year }} + 1, {{ plan_year_start_month }}, {{ plan_year_start_day }}) AS next_plan_year_start,

    -- Is this the employee's hire year?
    CASE
      WHEN EXTRACT(YEAR FROM ae.hire_date) = {{ simulation_year }} THEN TRUE
      ELSE FALSE
    END AS is_hire_year,

    -- Is the IECP complete by end of this year?
    CASE
      WHEN (ae.hire_date + INTERVAL '1 year') <= MAKE_DATE({{ simulation_year }}, 12, 31) THEN TRUE
      ELSE FALSE
    END AS is_iecp_complete_this_year

  FROM all_employees ae
  LEFT JOIN terminated_new_hires tnr ON ae.employee_id = tnr.employee_id
),

-- Compute IECP records
-- Year of hire: always IECP
-- Year after hire (IECP completes): IECP evaluation + potential plan year overlap
-- All other years: plan year only
computation_periods AS (
  SELECT
    eb.employee_id,
    {{ simulation_year }} AS simulation_year,
    eb.hire_date,
    eb.hire_date_anniversary AS iecp_end_date,
    eb.scenario_id,
    eb.plan_design_id,
    eb.employment_status,
    eb.plan_year_start,
    eb.year_end,
    eb.year_start,
    eb.next_plan_year_start,
    eb.is_hire_year,
    eb.is_iecp_complete_this_year,

    -- Determine period type
    CASE
      -- Hire year: always IECP
      WHEN eb.is_hire_year THEN 'iecp'
      -- Year after hire when IECP completes this year: still evaluating IECP
      WHEN NOT eb.is_hire_year
           AND eb.hire_date_anniversary > eb.year_start
           AND eb.hire_date_anniversary <= eb.year_end
        THEN 'iecp'
      -- All other years: plan year
      ELSE 'plan_year'
    END AS period_type,

    -- Period start/end dates
    CASE
      WHEN eb.is_hire_year THEN eb.hire_date
      WHEN NOT eb.is_hire_year
           AND eb.hire_date_anniversary > eb.year_start
           AND eb.hire_date_anniversary <= eb.year_end
        THEN eb.year_start
      ELSE eb.plan_year_start
    END AS period_start_date,

    CASE
      WHEN eb.is_hire_year THEN eb.year_end
      WHEN NOT eb.is_hire_year
           AND eb.hire_date_anniversary > eb.year_start
           AND eb.hire_date_anniversary <= eb.year_end
        THEN eb.hire_date_anniversary
      ELSE eb.year_end
    END AS period_end_date,

    -- IECP Year 1 hours: hire_date to year_end in hire year
    CASE
      WHEN eb.is_hire_year THEN
        GREATEST(0.0,
          DATEDIFF('day', eb.hire_date, MAKE_DATE({{ simulation_year }}, 12, 31))
          / 365.0 * 2080.0
        )
      ELSE 0.0
    END AS iecp_year1_hours,

    -- IECP Year 2 hours: year_start to hire_date_anniversary in the year IECP completes
    CASE
      WHEN NOT eb.is_hire_year
           AND eb.hire_date_anniversary > eb.year_start
           AND eb.hire_date_anniversary <= eb.year_end
        THEN
          GREATEST(0.0,
            DATEDIFF('day', MAKE_DATE({{ simulation_year }}, 1, 1), eb.hire_date_anniversary)
            / 365.0 * 2080.0
          )
      ELSE 0.0
    END AS iecp_year2_hours,

    -- Plan year hours: full year for plan-year periods, or post-IECP portion for overlap year
    CASE
      -- Full plan year
      WHEN NOT eb.is_hire_year
           AND eb.hire_date_anniversary <= eb.year_start
        THEN 2080.0
      -- Plan year portion after IECP completes (for overlap evaluation)
      WHEN NOT eb.is_hire_year
           AND eb.hire_date_anniversary > eb.year_start
           AND eb.hire_date_anniversary <= eb.year_end
        THEN
          GREATEST(0.0,
            DATEDIFF('day', eb.hire_date_anniversary, MAKE_DATE({{ simulation_year }}, 12, 31))
            / 365.0 * 2080.0
          )
      ELSE 0.0
    END AS plan_year_hours

  FROM employee_base eb
),

-- Calculate total IECP hours and apply threshold classification
classified_periods AS (
  SELECT
    cp.*,

    -- Total IECP hours (sum of year 1 + year 2 if this is the IECP completion year)
    CASE
      WHEN cp.period_type = 'iecp' AND cp.is_hire_year THEN cp.iecp_year1_hours
      WHEN cp.period_type = 'iecp' AND NOT cp.is_hire_year THEN cp.iecp_year1_hours + cp.iecp_year2_hours
      ELSE 0.0
    END AS iecp_total_hours,

    -- Annual hours prorated for this period
    CASE
      WHEN cp.period_type = 'iecp' AND cp.is_hire_year THEN cp.iecp_year1_hours
      WHEN cp.period_type = 'iecp' AND NOT cp.is_hire_year THEN cp.iecp_year1_hours + cp.iecp_year2_hours
      ELSE cp.plan_year_hours
    END AS annual_hours_prorated,

    -- IECP threshold met?
    CASE
      WHEN cp.period_type = 'iecp' AND cp.is_hire_year
        THEN cp.iecp_year1_hours >= 1000
      WHEN cp.period_type = 'iecp' AND NOT cp.is_hire_year
        THEN (cp.iecp_year1_hours + cp.iecp_year2_hours) >= 1000
      ELSE FALSE
    END AS iecp_eligible,

    -- Plan year threshold met? (only relevant when IECP is complete or plan_year period)
    CASE
      WHEN cp.period_type = 'plan_year' THEN cp.plan_year_hours >= 1000
      -- In IECP completion year, also check the plan year portion for overlap
      WHEN cp.period_type = 'iecp' AND NOT cp.is_hire_year
           AND cp.is_iecp_complete_this_year
        THEN cp.plan_year_hours >= 1000
      ELSE FALSE
    END AS is_plan_year_eligible,

    -- Overlap/double-credit: both IECP and plan year meet threshold
    CASE
      WHEN cp.period_type = 'iecp' AND NOT cp.is_hire_year
           AND cp.is_iecp_complete_this_year
           AND (cp.iecp_year1_hours + cp.iecp_year2_hours) >= 1000
           AND cp.plan_year_hours >= 1000
        THEN TRUE
      -- Jan 1 hires: IECP = plan year, no double credit
      WHEN cp.period_type = 'iecp' AND cp.is_hire_year
           AND EXTRACT(MONTH FROM cp.hire_date) = {{ plan_year_start_month }}
           AND EXTRACT(DAY FROM cp.hire_date) = {{ plan_year_start_day }}
        THEN FALSE
      ELSE FALSE
    END AS overlap_double_credit

  FROM computation_periods cp
),

-- Final output with eligibility years and reason codes
final AS (
  SELECT
    cp.employee_id,
    cp.simulation_year,
    cp.period_type,
    cp.period_start_date,
    cp.period_end_date,
    cp.hire_date,
    cp.iecp_end_date,
    ROUND(cp.annual_hours_prorated, 2)::DECIMAL(8,2) AS annual_hours_prorated,
    ROUND(cp.iecp_year1_hours, 2)::DECIMAL(8,2) AS iecp_year1_hours,
    ROUND(cp.iecp_year2_hours, 2)::DECIMAL(8,2) AS iecp_year2_hours,
    ROUND(cp.iecp_total_hours, 2)::DECIMAL(8,2) AS iecp_total_hours,

    -- Hours classification using reusable macro
    {{ classify_service_hours('cp.annual_hours_prorated') }} AS hours_classification,

    cp.is_iecp_complete_this_year AS is_iecp_complete,
    cp.is_plan_year_eligible,
    cp.iecp_eligible,
    cp.overlap_double_credit,

    -- Eligibility years this period
    CASE
      WHEN cp.overlap_double_credit THEN 2
      WHEN cp.iecp_eligible THEN 1
      WHEN cp.is_plan_year_eligible THEN 1
      ELSE 0
    END AS eligibility_years_this_period,

    -- Plan entry date per IRC 410(a)(4)
    -- Entry date = LEAST(next plan year start, eligibility_met_date + 6 months)
    CASE
      WHEN cp.iecp_eligible OR cp.is_plan_year_eligible OR cp.overlap_double_credit THEN
        LEAST(
          cp.next_plan_year_start,
          CASE
            WHEN cp.iecp_eligible AND cp.is_hire_year THEN cp.period_end_date + INTERVAL '6 months'
            WHEN cp.iecp_eligible AND NOT cp.is_hire_year THEN cp.iecp_end_date + INTERVAL '6 months'
            WHEN cp.is_plan_year_eligible THEN cp.period_end_date + INTERVAL '6 months'
            ELSE cp.next_plan_year_start
          END
        )::DATE
      ELSE NULL
    END AS plan_entry_date,

    -- Eligibility reason codes
    CASE
      WHEN cp.overlap_double_credit THEN 'eligible_double_credit'
      WHEN cp.iecp_eligible AND cp.period_type = 'iecp' THEN 'eligible_iecp'
      WHEN cp.is_plan_year_eligible AND cp.period_type = 'plan_year' THEN 'eligible_plan_year'
      -- IECP completion year: IECP failed but plan year passed
      WHEN cp.is_plan_year_eligible AND cp.period_type = 'iecp'
           AND cp.is_iecp_complete_this_year AND NOT cp.iecp_eligible THEN 'eligible_plan_year'
      WHEN cp.period_type = 'iecp' AND NOT cp.is_iecp_complete_this_year THEN 'pending_iecp'
      WHEN cp.period_type = 'iecp' AND cp.is_iecp_complete_this_year
           AND NOT cp.iecp_eligible AND NOT cp.is_plan_year_eligible THEN 'insufficient_hours_iecp'
      WHEN cp.period_type = 'plan_year' AND NOT cp.is_plan_year_eligible THEN 'insufficient_hours_plan_year'
      ELSE 'pending_iecp'
    END AS eligibility_reason,

    cp.scenario_id,
    cp.plan_design_id

  FROM classified_periods cp
)

SELECT * FROM final
ORDER BY employee_id, simulation_year, period_type
