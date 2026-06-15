-- Feature 096: A new hire who voluntarily enrolled in their hire year must show as participating,
-- with their deferral rate, in that hire-year snapshot (US2 / Contract 3 / VR-5).
-- FAILS (returns rows) when a hire-year voluntary enrollee is not_participating or has a zero
-- deferral rate in the snapshot for their hire year.
{{ config(tags=['data_quality']) }}

WITH hire_year_voluntary AS (
    SELECT DISTINCT
        e.employee_id,
        e.simulation_year
    FROM {{ ref('fct_yearly_events') }} e
    INNER JOIN {{ ref('fct_yearly_events') }} h
        ON e.employee_id = h.employee_id
       AND h.event_type = 'hire'
       AND e.simulation_year = h.simulation_year
    WHERE e.event_type = 'enrollment'
      AND e.event_details LIKE 'Voluntary enrollment%'
)

SELECT
    s.employee_id,
    s.simulation_year,
    s.participation_status,
    s.current_deferral_rate
FROM hire_year_voluntary v
INNER JOIN {{ ref('fct_workforce_snapshot') }} s
    ON s.employee_id = v.employee_id
   AND s.simulation_year = v.simulation_year
WHERE s.participation_status <> 'participating'
   OR COALESCE(s.current_deferral_rate, 0) = 0
