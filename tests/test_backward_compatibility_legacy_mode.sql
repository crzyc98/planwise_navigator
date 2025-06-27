-- Test: Backward compatibility validation for legacy mode
-- Ensures legacy mode produces identical results to original hard-coded logic
-- Expected: Zero differences between legacy macro and original calculation

{{ config(severity='error') }}

WITH legacy_macro_results AS (
  SELECT
    employee_id,
    {{ legacy_timing_calculation('employee_id', var('simulation_year')) }} as legacy_macro_date
  FROM {{ ref('int_workforce_previous_year') }}
  WHERE employment_status = 'active'
    AND {{ var('raise_timing_methodology', 'legacy') }} = 'legacy'
  LIMIT 1000  -- Test sample for performance
),
original_logic_results AS (
  SELECT
    employee_id,
    -- Original hard-coded logic from int_merit_events.sql
    CASE
      WHEN (LENGTH(employee_id) % 2) = 0
      THEN CAST({{ var('simulation_year') }} || '-01-01' AS DATE)
      ELSE CAST({{ var('simulation_year') }} || '-07-01' AS DATE)
    END as original_logic_date
  FROM {{ ref('int_workforce_previous_year') }}
  WHERE employment_status = 'active'
    AND {{ var('raise_timing_methodology', 'legacy') }} = 'legacy'
  LIMIT 1000  -- Same sample size
),
compatibility_check AS (
  SELECT
    l.employee_id,
    l.legacy_macro_date,
    o.original_logic_date,
    CASE
      WHEN l.legacy_macro_date = o.original_logic_date THEN 'COMPATIBLE'
      ELSE 'INCOMPATIBLE'
    END as compatibility_status
  FROM legacy_macro_results l
  JOIN original_logic_results o ON l.employee_id = o.employee_id
)
SELECT
  employee_id,
  legacy_macro_date,
  original_logic_date,
  'BACKWARD_COMPATIBILITY_FAILURE' as error_type
FROM compatibility_check
WHERE compatibility_status = 'INCOMPATIBLE'
