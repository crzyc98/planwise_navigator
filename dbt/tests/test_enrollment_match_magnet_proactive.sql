-- Test: match magnet fires in proactive enrollment model (Constitution III pre-fix failure)
-- Passes when at least one proactive enrollee has proactive_deferral_rate > raw_deferral_rate
-- (i.e., was snapped upward to the match threshold).
-- Fails (returns 1 row) pre-fix because the proactive model had zero match awareness.
SELECT 1
WHERE (
  SELECT COUNT(*)
  FROM {{ ref('int_proactive_voluntary_enrollment') }}
  WHERE will_enroll_proactively = true
    AND proactive_deferral_rate > raw_deferral_rate
) = 0
