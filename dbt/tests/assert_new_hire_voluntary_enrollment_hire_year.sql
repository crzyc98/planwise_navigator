-- Feature 096: New hires must be able to voluntarily enroll in their HIRE year.
-- Defect signature (pre-fix): voluntary enrollments exist, but ZERO of them occur in any
-- enrollee's hire year because the decision engine never saw current-year new hires.
-- This test FAILS (returns a row) when voluntary enrollments exist in the simulation but none
-- of them land in a new hire's hire year. Passes vacuously when voluntary enrollment is disabled.
{{ config(tags=['data_quality']) }}

WITH voluntary_enrollments AS (
    SELECT
        employee_id,
        simulation_year AS enroll_year
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'enrollment'
      AND event_details LIKE 'Voluntary enrollment%'
),

hires AS (
    SELECT
        employee_id,
        simulation_year AS hire_year
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'hire'
),

hire_year_voluntary AS (
    SELECT v.employee_id
    FROM voluntary_enrollments v
    INNER JOIN hires h
        ON v.employee_id = h.employee_id
       AND v.enroll_year = h.hire_year
)

SELECT 'no_new_hire_hire_year_voluntary_enrollment' AS failure_reason
WHERE (SELECT COUNT(*) FROM voluntary_enrollments) > 0
  AND (SELECT COUNT(*) FROM hire_year_voluntary) = 0
