{{ config(materialized='table') }}

/*
  Pre-Enrollment Workforce Model (Circular Dependency Resolution)

  This helper model provides workforce state data WITHOUT enrollment events,
  breaking the circular dependency chain that was preventing E023 enrollment
  engine from functioning.

  Purpose:
  - Serves as clean workforce data source for eligibility determination
  - Excludes enrollment events to prevent circular dependencies
  - Maintains all other workforce event processing (hire, termination, promotion, merit)

  Circular Dependency Resolution:
  OLD: fct_yearly_events → fct_workforce_snapshot → int_eligibility_determination → enrollment models → fct_yearly_events
  NEW: int_workforce_pre_enrollment → int_eligibility_determination → enrollment models → fct_yearly_events

  Usage:
  - Used by int_eligibility_determination instead of fct_workforce_snapshot
  - Provides same schema as workforce snapshot but without enrollment events
  - Enables enrollment processing in separate phase
*/

-- Use existing workforce model that doesn't participate in circular dependency
SELECT
  employee_id,
  employee_ssn,
  -- Calculate birth date from current age and simulation year
  CAST((simulation_year - current_age) || '-01-01' AS DATE) as employee_birth_date,
  hire_date as employee_hire_date,
  employee_gross_compensation as current_compensation,
  current_age,
  current_tenure,
  job_level as level_id,
  'active' as employment_status,
  NULL as termination_date,
  NULL as termination_reason,
  simulation_year,
  current_timestamp as snapshot_created_at,
  CASE WHEN simulation_year = {{ var('simulation_start_year', 2025) }} THEN true ELSE false END as is_from_census,
  age_band,
  tenure_band,
  'active' as detailed_status_code,
  'pending' as current_eligibility_status, -- Will be determined separately
  'pre_enrollment_workforce' as data_source,
  valid_age AND valid_tenure AND valid_compensation as data_quality_valid
FROM {{ ref('int_workforce_active_for_events') }}
WHERE simulation_year = {{ var('simulation_year') }}
ORDER BY employee_id
