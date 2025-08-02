{{ config(materialized='table') }}

/*
  Simplified Enrollment Events Model (Epic E023: Auto-Enrollment Integration)

  Generates enrollment events directly from baseline workforce using simplified logic.
  This provides immediate enrollment events functionality while the complex pipeline
  can be developed separately.

  Event Types Generated:
  - 'enrollment': Auto-enrollment and voluntary enrollment events
  - 'enrollment_change': Opt-out events based on demographics

  Simplified Integration:
  - Consumes: int_baseline_workforce (active workforce)
  - Produces: Events for fct_yearly_events integration
  - Uses demographic-based enrollment logic
  - Ready for immediate use, can be enhanced later with complex pipeline
*/

WITH active_workforce AS (
  -- Use consistent data source with other event models (terminations, hiring)
  SELECT DISTINCT
    employee_id,
    employee_ssn,
    employee_hire_date,
    {{ var('simulation_year') }} as simulation_year,
    current_age,
    current_tenure,
    level_id,
    employee_compensation AS current_compensation,
    -- Calculate age and tenure bands consistently with other models
    CASE
      WHEN current_age < 25 THEN '< 25'
      WHEN current_age < 35 THEN '25-34'
      WHEN current_age < 45 THEN '35-44'
      WHEN current_age < 55 THEN '45-54'
      WHEN current_age < 65 THEN '55-64'
      ELSE '65+'
    END AS age_band,
    CASE
      WHEN current_tenure < 2 THEN '< 2'
      WHEN current_tenure < 5 THEN '2-4'
      WHEN current_tenure < 10 THEN '5-9'
      WHEN current_tenure < 20 THEN '10-19'
      ELSE '20+'
    END AS tenure_band,
    employment_status,
    -- Include enrollment status from compensation table
    employee_enrollment_date
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
),

eligible_for_enrollment AS (
  -- Simple eligibility and enrollment logic based on demographics
  SELECT
    *,
    -- Age-based enrollment segments
    CASE
      WHEN current_age < 30 THEN 'young'
      WHEN current_age < 45 THEN 'mid_career'
      WHEN current_age < 60 THEN 'mature'
      ELSE 'senior'
    END as age_segment,

    -- Income-based segments
    CASE
      WHEN current_compensation < 50000 THEN 'low_income'
      WHEN current_compensation < 100000 THEN 'moderate'
      WHEN current_compensation < 200000 THEN 'high'
      ELSE 'executive'
    END as income_segment,

    -- Enhanced eligibility check: tenure >= 1 year AND not already enrolled AND hire date cutoff AND scope check
    CASE
      WHEN current_tenure >= 1
        AND employee_enrollment_date IS NULL
        AND (
          -- Hire date cutoff filter (if specified)
          {% if var("auto_enrollment_hire_date_cutoff", null) %}
            employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff") }}'::DATE
          {% else %}
            true
          {% endif %}
        )
        AND (
          -- Scope check: new_hires_only vs all_eligible_employees (default to all_eligible_employees)
          CASE
            WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'new_hires_only'
              THEN employee_hire_date >= CAST(simulation_year || '-01-01' AS DATE)
            WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'all_eligible_employees'
              THEN true
            ELSE true  -- Default to eligible if unrecognized scope
          END
        )
        THEN true
      ELSE false
    END as is_eligible,

    -- Check if already enrolled (for audit/tracking purposes)
    CASE
      WHEN employee_enrollment_date IS NOT NULL THEN true
      ELSE false
    END as is_already_enrolled,

    -- Generate deterministic "random" values for enrollment decisions
    (ABS(HASH(employee_id || '-enroll-' || CAST(simulation_year AS VARCHAR))) % 1000) / 1000.0 as enrollment_random,
    (ABS(HASH(employee_id || '-optout-' || CAST(simulation_year AS VARCHAR))) % 1000) / 1000.0 as optout_random
  FROM active_workforce
),

-- Generate enrollment events using simplified demographics-based logic
enrollment_events AS (
  SELECT
    efo.employee_id,
    efo.employee_ssn,
    'enrollment' as event_type,
    efo.simulation_year,
    CAST((efo.simulation_year || '-01-15 08:00:00') AS TIMESTAMP) as effective_date, -- Fixed enrollment date

    -- Event details based on demographics
    CASE efo.age_segment
      WHEN 'young' THEN 'Young employee auto-enrollment - 3% default deferral'
      WHEN 'mid_career' THEN 'Mid-career voluntary enrollment - 6% deferral'
      WHEN 'mature' THEN 'Mature employee enrollment - 8% deferral'
      ELSE 'Senior employee enrollment - 10% deferral'
    END as event_details,

    -- Compensation amount (current compensation at time of enrollment)
    efo.current_compensation as compensation_amount,
    NULL as previous_compensation,

    -- Employee demographics at time of enrollment
    efo.current_age as employee_age,
    efo.current_tenure as employee_tenure,
    efo.level_id,
    efo.age_band,
    efo.tenure_band,

    -- Event probability based on simplified demographics
    CASE efo.age_segment
      WHEN 'young' THEN 0.30        -- 30% enrollment rate for young employees
      WHEN 'mid_career' THEN 0.55   -- 55% enrollment rate for mid-career
      WHEN 'mature' THEN 0.70       -- 70% enrollment rate for mature employees
      ELSE 0.80                     -- 80% enrollment rate for senior employees
    END *
    CASE efo.income_segment
      WHEN 'low_income' THEN 0.70   -- Lower enrollment for low income
      WHEN 'moderate' THEN 1.0      -- Base rate for moderate income
      WHEN 'high' THEN 1.15         -- Higher enrollment for high income
      ELSE 1.25                     -- Highest enrollment for executives
    END as event_probability,

    -- Event category for grouping
    CASE efo.age_segment
      WHEN 'young' THEN 'auto_enrollment'
      WHEN 'mid_career' THEN 'voluntary_enrollment'
      WHEN 'mature' THEN 'proactive_enrollment'
      ELSE 'executive_enrollment'
    END as event_category
  FROM eligible_for_enrollment efo
  WHERE efo.is_eligible = true
    AND efo.enrollment_random < (
      CASE efo.age_segment
        WHEN 'young' THEN 0.30
        WHEN 'mid_career' THEN 0.55
        WHEN 'mature' THEN 0.70
        ELSE 0.80
      END *
      CASE efo.income_segment
        WHEN 'low_income' THEN 0.70
        WHEN 'moderate' THEN 1.0
        WHEN 'high' THEN 1.15
        ELSE 1.25
      END
    )
),

-- Generate opt-out events using simplified logic
opt_out_events AS (
  SELECT
    efo.employee_id,
    efo.employee_ssn,
    'enrollment_change' as event_type,
    efo.simulation_year,
    CAST((efo.simulation_year || '-06-15 14:00:00') AS TIMESTAMP) as effective_date, -- Mid-year opt-out

    -- Opt-out event details
    'Auto-enrollment opt-out - reduced deferral from default to 0%' as event_details,

    -- Compensation remains the same, but showing the change impact
    efo.current_compensation as compensation_amount,
    efo.current_compensation as previous_compensation,

    -- Employee demographics
    efo.current_age as employee_age,
    efo.current_tenure as employee_tenure,
    efo.level_id,
    efo.age_band,
    efo.tenure_band,

    -- Opt-out probability based on demographics (simplified)
    CASE efo.age_segment
      WHEN 'young' THEN 0.35  -- Higher opt-out rate for young employees
      WHEN 'mid_career' THEN 0.20
      WHEN 'mature' THEN 0.15
      ELSE 0.10               -- Lower opt-out rate for seniors
    END *
    CASE efo.income_segment
      WHEN 'low_income' THEN 1.60  -- Much higher opt-out for low income
      WHEN 'moderate' THEN 1.0     -- Base rate
      WHEN 'high' THEN 0.60        -- Lower opt-out for high income
      ELSE 0.20                    -- Very low opt-out for executives
    END as event_probability,

    'enrollment_opt_out' as event_category
  FROM eligible_for_enrollment efo
  WHERE efo.is_eligible = true
    AND efo.age_segment = 'young'  -- Only young employees get auto-enrolled
    AND efo.optout_random < (
      0.35 *  -- Base young opt-out rate
      CASE efo.income_segment
        WHEN 'low_income' THEN 1.60
        WHEN 'moderate' THEN 1.0
        WHEN 'high' THEN 0.60
        ELSE 0.20
      END
    )
),

-- Combine all enrollment-related events
all_enrollment_events AS (
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM enrollment_events

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
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM opt_out_events
)

-- Final selection compatible with fct_yearly_events schema with event sourcing metadata
SELECT
  employee_id,
  employee_ssn,
  event_type,
  simulation_year,
  effective_date,
  event_details,
  compensation_amount,
  previous_compensation,
  employee_age,
  employee_tenure,
  level_id,
  age_band,
  tenure_band,
  event_probability,
  event_category,
  -- Event sourcing metadata for audit trail
  ROW_NUMBER() OVER (PARTITION BY employee_id, simulation_year ORDER BY effective_date, event_type) as event_sequence,
  CURRENT_TIMESTAMP as created_at,
  '{{ var("scenario_id", "default") }}' as parameter_scenario_id,
  'enrollment_pipeline' as parameter_source,
  CASE
    WHEN employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
    WHEN simulation_year IS NULL THEN 'INVALID_SIMULATION_YEAR'
    WHEN effective_date IS NULL THEN 'INVALID_EFFECTIVE_DATE'
    WHEN compensation_amount IS NULL THEN 'INVALID_COMPENSATION'
    ELSE 'VALID'
  END as data_quality_flag
FROM all_enrollment_events
WHERE employee_id IS NOT NULL
  AND simulation_year IS NOT NULL
  AND effective_date IS NOT NULL
  AND event_type IS NOT NULL
ORDER BY employee_id, effective_date,
  CASE event_type
    WHEN 'enrollment' THEN 1
    WHEN 'enrollment_change' THEN 2
    ELSE 3
  END
