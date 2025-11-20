-- Converted from validation model to test
-- Added simulation_year filter for performance

/*
  Validation for Story S042-01: Enrollment-Deferral Rate Consistency

  This test ensures the key requirement from Epic S042-01:
  "Add data quality test: every enrolled employee has enrollment event OR registry entry"

  VALIDATION RULES:
  1. Every employee in deferral rate accumulator v2 must have enrollment events
  2. No employees should have deferral rates without corresponding enrollment events
  3. Deferral rates must match between enrollment events and state accumulator

  Returns only failing records (0 rows = all validations pass)
*/

WITH enrolled_employees_from_accumulator AS (
    SELECT DISTINCT
        employee_id,
        current_deferral_rate,
        original_deferral_rate,
        is_enrolled_flag,
        employee_enrollment_date
    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),

enrolled_employees_from_events AS (
    SELECT DISTINCT
        employee_id,
        employee_deferral_rate,
        effective_date as enrollment_date
    FROM {{ ref('int_enrollment_events') }}
    WHERE LOWER(event_type) = 'enrollment'
      AND simulation_year <= {{ var('simulation_year') }}
),

validation_results AS (
    SELECT
        COALESCE(acc.employee_id, evt.employee_id) as employee_id,

        -- Validation flags
        CASE
            WHEN acc.employee_id IS NOT NULL AND evt.employee_id IS NULL
            THEN 'FAIL_NO_ENROLLMENT_EVENT'
            WHEN acc.employee_id IS NULL AND evt.employee_id IS NOT NULL
            THEN 'FAIL_NO_ACCUMULATOR_RECORD'
            WHEN ABS(COALESCE(acc.current_deferral_rate, acc.original_deferral_rate, 0) - COALESCE(evt.employee_deferral_rate, 0)) > 0.001
            THEN 'FAIL_DEFERRAL_RATE_MISMATCH'
            ELSE 'PASS'
        END as validation_result,

        -- Details for debugging
        acc.current_deferral_rate,
        acc.original_deferral_rate,
        evt.employee_deferral_rate,
        acc.employee_enrollment_date,
        evt.enrollment_date,

        -- Summary fields
        CASE
            WHEN acc.employee_id IS NOT NULL AND evt.employee_id IS NULL THEN 'Missing enrollment event'
            WHEN acc.employee_id IS NULL AND evt.employee_id IS NOT NULL THEN 'Missing accumulator record'
            WHEN ABS(COALESCE(acc.current_deferral_rate, acc.original_deferral_rate, 0) - COALESCE(evt.employee_deferral_rate, 0)) > 0.001
            THEN 'Deferral rate mismatch: Accumulator=' || COALESCE(acc.current_deferral_rate, acc.original_deferral_rate, 0) || ', Event=' || COALESCE(evt.employee_deferral_rate, 0)
            ELSE 'Consistent enrollment and deferral data'
        END as validation_details

    FROM enrolled_employees_from_accumulator acc
    FULL OUTER JOIN enrolled_employees_from_events evt
        ON acc.employee_id = evt.employee_id
)

-- Return only failing records (0 rows = all validations pass)
SELECT
    employee_id,
    validation_result,
    validation_details,
    current_deferral_rate,
    original_deferral_rate,
    employee_deferral_rate,
    employee_enrollment_date,
    enrollment_date,

    -- Summary flags
    0 as is_valid,
    1 as is_failed,

    -- Metadata
    {{ var('simulation_year') }} as simulation_year,
    CURRENT_TIMESTAMP as validation_timestamp

FROM validation_results
WHERE validation_result LIKE 'FAIL%'
ORDER BY
    validation_result DESC,
    employee_id

/*
  EXPECTED RESULTS for Story S042-01:
  - 0 rows returned means all validations pass
  - No 'FAIL_NO_ENROLLMENT_EVENT' records (every enrolled employee has enrollment event)
  - No 'FAIL_DEFERRAL_RATE_MISMATCH' records (rates are consistent)

  KEY VALIDATION:
  Employee NH_2025_000007 should show:
  - validation_result = 'PASS' (not in failing records)
  - current_deferral_rate = 0.06 (6%)
  - employee_deferral_rate = 0.06 (6%)
  - validation_details = 'Consistent enrollment and deferral data'
*/
