-- Feature 096: Each new hire's voluntary enrollment decision must produce exactly ONE enrollment
-- event across all simulation years — no duplicate/delayed second enrollment (US3 / VR-1 / SC-005).
-- FAILS (returns rows) for any new hire with more than one voluntary enrollment event.
{{ config(tags=['data_quality']) }}

SELECT
    employee_id,
    COUNT(*) AS voluntary_enrollment_event_count
FROM {{ ref('fct_yearly_events') }}
WHERE event_type = 'enrollment'
  AND event_details LIKE 'Voluntary enrollment%'
GROUP BY employee_id
HAVING COUNT(*) > 1
