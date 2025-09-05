{% macro events_enrollment_sql(cohort_table, simulation_year) %}
  {#-
    Generate enrollment events for E068A fused event generation

    This macro extracts enrollment event logic from int_enrollment_events.sql
    and optimizes it for in-memory CTE processing within the fused
    fct_yearly_events model.

    Parameters:
    - cohort_table: CTE name containing cohort data with RNG values
    - simulation_year: Current simulation year

    Returns: SQL for enrollment events CTE
  #}

  WITH enrollment_events_base AS (
    SELECT
      ee.employee_id,
      ee.employee_ssn,
      ee.event_type,
      ee.simulation_year,
      ee.effective_date,
      ee.event_details,
      -- Apply bounds checking to enrollment event compensation
      -- This prevents multi-year inflation from incorrect compensation calculation
      CASE
        WHEN ee.compensation_amount IS NULL OR ee.compensation_amount <= 0 THEN
          COALESCE(bw.current_compensation, ey.employee_compensation, 50000)  -- Use baseline or employee_compensation_by_year as fallback
        WHEN ee.compensation_amount > 10000000 THEN
          COALESCE(bw.current_compensation, ey.employee_compensation, 500000)  -- Cap at baseline if >$10M
        WHEN bw.current_compensation IS NOT NULL AND ee.compensation_amount / bw.current_compensation > 100 THEN
          bw.current_compensation  -- If more than 100x difference, use baseline
        WHEN ey.employee_compensation IS NOT NULL AND ee.compensation_amount / ey.employee_compensation > 100 THEN
          ey.employee_compensation  -- If more than 100x difference, use employee_compensation_by_year
        ELSE ee.compensation_amount
      END AS compensation_amount,
      ee.previous_compensation,
      ee.employee_deferral_rate,
      ee.prev_employee_deferral_rate,
      ee.employee_age,
      ee.employee_tenure,
      ee.level_id,
      ee.age_band,
      ee.tenure_band,
      ee.event_probability,
      ee.event_category
    FROM {{ ref('int_enrollment_events') }} ee
    -- Add joins to get baseline compensation for validation
    LEFT JOIN {{ ref('int_baseline_workforce') }} bw
      ON ee.employee_id = bw.employee_id
      AND ee.simulation_year = bw.simulation_year
    LEFT JOIN {{ ref('int_employee_compensation_by_year') }} ey
      ON ee.employee_id = ey.employee_id
      AND ee.simulation_year = ey.simulation_year
    WHERE ee.simulation_year = {{ simulation_year }}
  ),

  -- S051-02: Synthetic Baseline Enrollment Events Integration
  -- Map synthetic enrollment events from census data to yearly events schema
  synthetic_enrollment_events AS (
    SELECT
      se.employee_id,
      -- Handle missing employee_ssn gracefully
      COALESCE(bw.employee_ssn, 'UNKNOWN') AS employee_ssn,
      se.event_type,
      se.simulation_year,
      se.effective_date,
      se.event_details,
      -- Use baseline workforce compensation with bounds checking
      -- This fixes the multi-year inflation issue where enrollment events had inflated compensation
      CASE
        WHEN se.current_compensation IS NULL OR se.current_compensation <= 0 THEN bw.current_compensation
        WHEN se.current_compensation > 10000000 THEN bw.current_compensation  -- Cap at $10M, use baseline
        WHEN bw.current_compensation IS NOT NULL AND se.current_compensation / bw.current_compensation > 100 THEN bw.current_compensation  -- If more than 100x difference, use baseline
        ELSE se.current_compensation
      END AS compensation_amount,
      CAST(NULL AS DECIMAL(18,2)) AS previous_compensation,
      se.employee_deferral_rate::DECIMAL(5,4) AS employee_deferral_rate,
      CAST(NULL AS DECIMAL(5,4)) AS prev_employee_deferral_rate,
      se.current_age AS employee_age,
      se.current_tenure AS employee_tenure,
      se.level_id,
      -- Calculate age_band from current_age for consistency
      CASE
        WHEN se.current_age < 25 THEN '< 25'
        WHEN se.current_age < 35 THEN '25-34'
        WHEN se.current_age < 45 THEN '35-44'
        WHEN se.current_age < 55 THEN '45-54'
        WHEN se.current_age < 65 THEN '55-64'
        ELSE '65+'
      END AS age_band,
      -- Calculate tenure_band from current_tenure for consistency
      CASE
        WHEN se.current_tenure < 2 THEN '< 2'
        WHEN se.current_tenure < 5 THEN '2-4'
        WHEN se.current_tenure < 10 THEN '5-9'
        WHEN se.current_tenure < 15 THEN '10-14'
        WHEN se.current_tenure < 20 THEN '15-19'
        ELSE '20+'
      END AS tenure_band,
      CAST(NULL AS DECIMAL(10,4)) AS event_probability,
      'census_baseline' AS event_category
    FROM {{ ref('int_synthetic_baseline_enrollment_events') }} se
    LEFT JOIN {{ ref('int_baseline_workforce') }} bw
      ON se.employee_id = bw.employee_id
      AND se.simulation_year = bw.simulation_year
    WHERE se.simulation_year = {{ simulation_year }}
      -- Only include synthetic events for the start year to avoid duplicates
      AND se.simulation_year = {{ var('start_year', 2025) }}
  )

  -- Union both types of enrollment events
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM enrollment_events_base

  UNION ALL

  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM synthetic_enrollment_events

{% endmacro %}
