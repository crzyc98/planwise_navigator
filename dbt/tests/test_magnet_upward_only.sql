-- Test: magnet never lowers a deferral rate (upward-only constraint, voluntary model)
-- Returns rows only when a violation exists (rate lowered below 10% ceiling).
-- The < 0.10 filter excludes ceiling-capped rows to avoid false positives.
SELECT employee_id, raw_deferral_rate, selected_deferral_rate
FROM {{ ref('int_voluntary_enrollment_decision') }}
WHERE raw_deferral_rate > selected_deferral_rate
  AND selected_deferral_rate < 0.10
