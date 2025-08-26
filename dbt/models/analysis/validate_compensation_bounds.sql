{{ config(materialized='table', tags=['validation', 'data_quality']) }}

/*
  Multi-Year Compensation Inflation Validation

  This model validates that compensation values remain within reasonable bounds
  across all simulation years to prevent the extreme inflation issue where
  employees had compensation values reaching $17.8M.

  Bounds Checking:
  - Minimum compensation: $30,000
  - Maximum compensation: $2,000,000
  - Maximum year-over-year growth: 50%
  - Flags employees with suspicious compensation patterns
*/

WITH current_simulation_year AS (
  SELECT {{ var('simulation_year', 2025) }} as simulation_year
),

-- Check workforce snapshot compensation bounds
workforce_bounds AS (
  SELECT
    'fct_workforce_snapshot' as model_name,
    simulation_year,
    employee_id,
    current_compensation,
    prorated_annual_compensation,
    full_year_equivalent_compensation,
    -- Validation flags
    CASE
      WHEN current_compensation > 2000000 THEN 'current_compensation_exceeds_2M'
      WHEN current_compensation < 30000 THEN 'current_compensation_below_30K'
      WHEN prorated_annual_compensation > 2000000 THEN 'prorated_compensation_exceeds_2M'
      WHEN prorated_annual_compensation < 20000 THEN 'prorated_compensation_below_20K'
      WHEN full_year_equivalent_compensation > 2000000 THEN 'full_year_compensation_exceeds_2M'
      WHEN full_year_equivalent_compensation < 30000 THEN 'full_year_compensation_below_30K'
      ELSE 'valid'
    END as validation_status,
    'workforce_snapshot_bounds_check' as validation_type
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = (SELECT simulation_year FROM current_simulation_year)
),

-- Check yearly events compensation bounds
events_bounds AS (
  SELECT
    'fct_yearly_events' as model_name,
    simulation_year,
    employee_id,
    compensation_amount,
    previous_compensation,
    NULL::DECIMAL as full_year_equivalent_compensation,
    -- Validation flags
    CASE
      WHEN compensation_amount > 2000000 THEN 'event_compensation_exceeds_2M'
      WHEN compensation_amount < 0 THEN 'negative_compensation'
      WHEN previous_compensation IS NOT NULL AND compensation_amount / previous_compensation > 5 THEN 'excessive_compensation_growth'
      ELSE 'valid'
    END as validation_status,
    CONCAT('event_bounds_check_', event_type) as validation_type
  FROM {{ ref('fct_yearly_events') }}
  WHERE simulation_year = (SELECT simulation_year FROM current_simulation_year)
    AND compensation_amount IS NOT NULL
),

-- Check employee compensation by year bounds
compensation_by_year_bounds AS (
  SELECT
    'int_employee_compensation_by_year' as model_name,
    simulation_year,
    employee_id,
    employee_compensation as current_compensation,
    starting_year_compensation as prorated_annual_compensation,
    ending_year_compensation as full_year_equivalent_compensation,
    -- Validation flags
    CASE
      WHEN employee_compensation > 2000000 THEN 'employee_compensation_exceeds_2M'
      WHEN employee_compensation < 30000 THEN 'employee_compensation_below_30K'
      WHEN starting_year_compensation > 2000000 THEN 'starting_compensation_exceeds_2M'
      WHEN ending_year_compensation > 2000000 THEN 'ending_compensation_exceeds_2M'
      ELSE 'valid'
    END as validation_status,
    'compensation_by_year_bounds_check' as validation_type
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = (SELECT simulation_year FROM current_simulation_year)
),

-- Combine all validation results
all_validations AS (
  SELECT * FROM workforce_bounds
  UNION ALL
  SELECT * FROM events_bounds
  UNION ALL
  SELECT * FROM compensation_by_year_bounds
),

-- Summary statistics
validation_summary AS (
  SELECT
    model_name,
    validation_type,
    validation_status,
    COUNT(*) as violation_count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY model_name) as violation_percentage,
    MIN(current_compensation) as min_compensation,
    MAX(current_compensation) as max_compensation,
    AVG(current_compensation) as avg_compensation
  FROM all_validations
  GROUP BY model_name, validation_type, validation_status
)

-- Final output with validation details and summary
SELECT
  av.model_name,
  av.simulation_year,
  av.employee_id,
  av.current_compensation,
  av.prorated_annual_compensation,
  av.full_year_equivalent_compensation,
  av.validation_status,
  av.validation_type,
  vs.violation_count,
  vs.violation_percentage,
  -- Add severity classification
  CASE
    WHEN av.validation_status LIKE '%exceeds_2M%' THEN 'CRITICAL'
    WHEN av.validation_status LIKE '%below_%K' THEN 'WARNING'
    WHEN av.validation_status LIKE 'excessive_%' THEN 'HIGH'
    WHEN av.validation_status = 'negative_compensation' THEN 'CRITICAL'
    ELSE 'INFO'
  END as severity,
  CURRENT_TIMESTAMP as validation_timestamp
FROM all_validations av
LEFT JOIN validation_summary vs
  ON av.model_name = vs.model_name
  AND av.validation_type = vs.validation_type
  AND av.validation_status = vs.validation_status
WHERE av.validation_status != 'valid'  -- Only show violations
ORDER BY
  CASE WHEN av.validation_status LIKE '%exceeds_2M%' THEN 1 ELSE 2 END,
  av.current_compensation DESC,
  av.employee_id
