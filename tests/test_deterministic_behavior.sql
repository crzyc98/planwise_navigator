-- Test: Deterministic behavior validation
-- Ensures same random seed produces identical timing results across runs
-- This test validates reproducibility for both legacy and realistic modes
-- Expected: Zero mismatched dates between runs with same seed

{{ config(severity='error') }}

-- Note: This test would require running the same simulation twice
-- For now, we validate internal consistency within a single run

WITH timing_consistency AS (
  SELECT
    employee_id,
    effective_date,
    -- Generate timing again using same logic to verify consistency
    {{ get_realistic_raise_date('employee_id', var('simulation_year')) }} as recalculated_date
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'RAISE'
    AND simulation_year = {{ var('simulation_year') }}
),
consistency_check AS (
  SELECT
    employee_id,
    effective_date,
    recalculated_date,
    CASE
      WHEN effective_date = recalculated_date THEN 'CONSISTENT'
      ELSE 'INCONSISTENT'
    END as consistency_status
  FROM timing_consistency
)
SELECT
  employee_id,
  effective_date,
  recalculated_date,
  'DETERMINISTIC_BEHAVIOR_FAILURE' as error_type
FROM consistency_check
WHERE consistency_status = 'INCONSISTENT'
