-- Test: match magnet fires in voluntary enrollment model (Constitution III pre-fix failure)
-- Passes when at least one enrollee has match_optimized_rate > raw_deferral_rate
-- (i.e., was snapped upward to the match threshold).
-- Fails (returns 1 row) pre-fix because the column does not exist or no rows are snapped.
SELECT 1
WHERE (
  SELECT COUNT(*)
  FROM {{ ref('int_voluntary_enrollment_decision') }}
  WHERE will_enroll = true
    AND match_optimized_rate > raw_deferral_rate
) = 0
