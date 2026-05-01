-- Test: magnet never lowers a deferral rate (upward-only constraint, proactive model)
-- Returns rows only when a violation exists (rate lowered below 10% ceiling).
-- The < 0.10 filter excludes ceiling-capped rows to avoid false positives.
SELECT employee_id, raw_deferral_rate, proactive_deferral_rate
FROM {{ ref('int_proactive_voluntary_enrollment') }}
WHERE raw_deferral_rate > proactive_deferral_rate
  AND will_enroll_proactively = true
  AND proactive_deferral_rate < 0.10
