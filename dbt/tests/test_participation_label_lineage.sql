{{ config(severity='error', tags=['enrollment', 'data_quality']) }}

-- Feature 108 (issue #419): the snapshot may claim census enrollment only
-- when the enrollment state accumulator records a baseline-source enrollment.
-- Any row returned is a participation label without supporting lineage.
SELECT
  s.employee_id,
  s.simulation_year,
  s.participation_status_detail,
  esa.enrollment_source
FROM {{ ref('fct_workforce_snapshot') }} s
LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} esa
  ON esa.employee_id = s.employee_id
  AND esa.simulation_year = s.simulation_year
WHERE s.participation_status_detail = 'participating - census enrollment'
  AND COALESCE(esa.enrollment_source, 'none') <> 'baseline'
