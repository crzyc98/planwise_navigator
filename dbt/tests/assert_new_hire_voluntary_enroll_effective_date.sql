-- Feature 096: A hire-year voluntary enrollment for a new hire must be effective on the
-- employee's eligibility date (hire date + eligibility waiting period), per spec clarification.
-- FAILS (returns rows) for any hire-year voluntary enrollment whose effective date != eligibility date.
{{ config(tags=['data_quality']) }}

WITH hires AS (
    SELECT
        employee_id,
        effective_date::DATE AS hire_date,
        simulation_year AS hire_year
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'hire'
),

hire_year_voluntary AS (
    SELECT
        employee_id,
        effective_date::DATE AS enroll_date,
        simulation_year AS enroll_year
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'enrollment'
      AND event_details LIKE 'Voluntary enrollment%'
)

SELECT
    v.employee_id,
    v.enroll_date,
    h.hire_date,
    (h.hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY)::DATE AS expected_eligibility_date
FROM hire_year_voluntary v
INNER JOIN hires h
    ON v.employee_id = h.employee_id
   AND v.enroll_year = h.hire_year
WHERE v.enroll_date <> (h.hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY)::DATE
