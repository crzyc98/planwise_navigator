-- =====================================================================
-- PlanWise Navigator: Snapshot Behavior Comparison and Optimization
-- =====================================================================
-- Purpose: Compare and optimize snapshot strategies for large datasets
-- Target: DuckDB 1.0.0+ with dbt-duckdb adapter
-- Created: 2025-07-26
-- =====================================================================

-- Configuration parameters (parameterized for flexibility)
-- Use dbt variables or DuckDB variables for dynamic configuration
SET start_year = ${start_year:-2020};
SET end_year = ${end_year:-2025};
SET comparison_mode = ${comparison_mode:-'full'};  -- 'full', 'incremental', 'performance'
SET batch_size = ${batch_size:-10000};
SET enable_indexes = ${enable_indexes:-true};

-- =====================================================================
-- SECTION 1: Performance Indexes for Large Dataset Optimization
-- =====================================================================

-- Create performance indexes for DuckDB optimization
-- These are optimized for the workforce simulation event sourcing pattern

CREATE INDEX IF NOT EXISTS idx_fct_workforce_snapshot_composite
ON fct_workforce_snapshot (simulation_year, employee_id, employment_status);

CREATE INDEX IF NOT EXISTS idx_fct_workforce_snapshot_dates
ON fct_workforce_snapshot (employee_hire_date, termination_date);

CREATE INDEX IF NOT EXISTS idx_fct_yearly_events_composite
ON fct_yearly_events (simulation_year, event_type, employee_id, effective_date);

CREATE INDEX IF NOT EXISTS idx_scd_workforce_state_lookup
ON scd_workforce_state (employee_id, simulation_year, dbt_valid_from, dbt_valid_to);

CREATE INDEX IF NOT EXISTS idx_scd_workforce_state_optimized_hash
ON scd_workforce_state_optimized (employee_id, change_hash, dbt_valid_from);

-- Covering index for common snapshot queries
CREATE INDEX IF NOT EXISTS idx_workforce_snapshot_covering
ON fct_workforce_snapshot (simulation_year, employment_status)
INCLUDE (employee_id, current_compensation, level_id, age_band, tenure_band);

-- =====================================================================
-- SECTION 2: Parameterized Comparison Queries with Year Range Flexibility
-- =====================================================================

-- 2A: Parameterized workforce state comparison across years
WITH parameterized_comparison AS (
  SELECT 
    'fct_workforce_snapshot' AS source_table,
    simulation_year,
    employment_status,
    COUNT(*) AS record_count,
    COUNT(DISTINCT employee_id) AS unique_employees,
    AVG(current_compensation) AS avg_compensation,
    SUM(current_compensation) AS total_compensation,
    MIN(employee_hire_date) AS earliest_hire,
    MAX(employee_hire_date) AS latest_hire
  FROM fct_workforce_snapshot
  WHERE simulation_year BETWEEN getvariable('start_year')::INTEGER 
                           AND getvariable('end_year')::INTEGER
  GROUP BY simulation_year, employment_status
  
  UNION ALL
  
  SELECT 
    'scd_workforce_state' AS source_table,
    simulation_year,
    employment_status,
    COUNT(*) AS record_count,
    COUNT(DISTINCT employee_id) AS unique_employees,
    AVG(employee_gross_compensation) AS avg_compensation,
    SUM(employee_gross_compensation) AS total_compensation,
    MIN(employee_hire_date) AS earliest_hire,
    MAX(employee_hire_date) AS latest_hire
  FROM scd_workforce_state
  WHERE simulation_year BETWEEN getvariable('start_year')::INTEGER 
                           AND getvariable('end_year')::INTEGER
    AND dbt_valid_to IS NULL  -- Current records only
  GROUP BY simulation_year, employment_status
),

-- 2B: Delta analysis between snapshot methods (incremental comparison)
snapshot_deltas AS (
  SELECT 
    fs.simulation_year,
    fs.employee_id,
    fs.employment_status AS fct_status,
    scd.employment_status AS scd_status,
    fs.current_compensation AS fct_compensation,
    scd.employee_gross_compensation AS scd_compensation,
    ABS(fs.current_compensation - scd.employee_gross_compensation) AS compensation_diff,
    CASE 
      WHEN fs.employment_status != scd.employment_status THEN 'status_mismatch'
      WHEN ABS(fs.current_compensation - scd.employee_gross_compensation) > 1000 THEN 'compensation_mismatch'
      ELSE 'match'
    END AS comparison_result
  FROM fct_workforce_snapshot fs
  JOIN scd_workforce_state scd 
    ON fs.employee_id = scd.employee_id 
   AND fs.simulation_year = scd.simulation_year
   AND scd.dbt_valid_to IS NULL
  WHERE fs.simulation_year BETWEEN getvariable('start_year')::INTEGER 
                              AND getvariable('end_year')::INTEGER
)

-- =====================================================================
-- SECTION 3: Incremental Comparison Strategies for Large Datasets
-- =====================================================================

-- 3A: Batch-wise comparison for memory efficiency
, batched_comparison AS (
  SELECT 
    batch_id,
    comparison_result,
    COUNT(*) AS batch_count,
    AVG(compensation_diff) AS avg_compensation_diff,
    MAX(compensation_diff) AS max_compensation_diff
  FROM (
    SELECT 
      *,
      NTILE(CEIL(COUNT(*) OVER() / getvariable('batch_size')::INTEGER)) OVER (ORDER BY employee_id) AS batch_id
    FROM snapshot_deltas
  ) batched
  GROUP BY batch_id, comparison_result
),

-- 3B: Incremental change detection using hash-based comparison
incremental_changes AS (
  SELECT 
    current_snapshot.simulation_year,
    current_snapshot.employee_id,
    current_snapshot.change_hash AS current_hash,
    previous_snapshot.change_hash AS previous_hash,
    CASE 
      WHEN previous_snapshot.change_hash IS NULL THEN 'new_record'
      WHEN current_snapshot.change_hash != previous_snapshot.change_hash THEN 'changed'
      ELSE 'unchanged'
    END AS change_type,
    current_snapshot.current_compensation,
    current_snapshot.employment_status
  FROM (
    SELECT 
      simulation_year,
      employee_id,
      current_compensation,
      employment_status,
      -- Generate consistent hash for change detection
      hash(
        current_compensation::VARCHAR || '|' ||
        COALESCE(employment_status, 'NULL') || '|' ||
        COALESCE(level_id::VARCHAR, 'NULL') || '|' ||
        COALESCE(termination_date::VARCHAR, 'NULL')
      ) AS change_hash
    FROM fct_workforce_snapshot
    WHERE simulation_year BETWEEN getvariable('start_year')::INTEGER 
                             AND getvariable('end_year')::INTEGER
  ) current_snapshot
  LEFT JOIN (
    SELECT 
      simulation_year + 1 AS next_year,  -- Join to next year
      employee_id,
      hash(
        current_compensation::VARCHAR || '|' ||
        COALESCE(employment_status, 'NULL') || '|' ||
        COALESCE(level_id::VARCHAR, 'NULL') || '|' ||
        COALESCE(termination_date::VARCHAR, 'NULL')
      ) AS change_hash
    FROM fct_workforce_snapshot
    WHERE simulation_year BETWEEN getvariable('start_year')::INTEGER - 1
                             AND getvariable('end_year')::INTEGER - 1
  ) previous_snapshot
    ON current_snapshot.simulation_year = previous_snapshot.next_year
   AND current_snapshot.employee_id = previous_snapshot.employee_id
),

-- =====================================================================
-- SECTION 4: Performance Benchmarking and Statistics
-- =====================================================================

-- 4A: Query performance comparison with timing
performance_metrics AS (
  SELECT 
    'Standard Snapshot Query' AS query_type,
    COUNT(*) AS record_count,
    NOW() AS start_time
  FROM fct_workforce_snapshot
  WHERE simulation_year BETWEEN getvariable('start_year')::INTEGER 
                           AND getvariable('end_year')::INTEGER
  
  UNION ALL
  
  SELECT 
    'Optimized SCD Query' AS query_type,
    COUNT(*) AS record_count,
    NOW() AS start_time
  FROM scd_workforce_state_optimized
  WHERE simulation_year BETWEEN getvariable('start_year')::INTEGER 
                           AND getvariable('end_year')::INTEGER
    AND dbt_valid_to IS NULL
),

-- 4B: Data quality validation across snapshot methods
data_quality_check AS (
  SELECT 
    simulation_year,
    'Data Consistency Check' AS check_type,
    COUNT(CASE WHEN comparison_result != 'match' THEN 1 END) AS inconsistencies,
    COUNT(*) AS total_records,
    ROUND(
      100.0 * COUNT(CASE WHEN comparison_result = 'match' THEN 1 END) / COUNT(*), 
      2
    ) AS consistency_percentage
  FROM snapshot_deltas
  GROUP BY simulation_year
),

-- =====================================================================
-- SECTION 5: Optimized Aggregation Queries for Large Datasets
-- =====================================================================

-- 5A: Columnar-optimized aggregations using DuckDB's strengths
columnar_aggregations AS (
  SELECT 
    simulation_year,
    employment_status,
    level_id,
    age_band,
    tenure_band,
    -- Use DuckDB's efficient aggregation functions
    COUNT(*) AS employee_count,
    -- Approximate aggregations for performance on large datasets
    APPROX_COUNT_DISTINCT(employee_id) AS approx_unique_employees,
    -- Statistical aggregations
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY current_compensation) AS median_compensation,
    STDDEV_SAMP(current_compensation) AS compensation_std_dev,
    -- Memory-efficient window functions
    SUM(current_compensation) OVER (PARTITION BY simulation_year) AS year_total_compensation
  FROM fct_workforce_snapshot
  WHERE simulation_year BETWEEN getvariable('start_year')::INTEGER 
                           AND getvariable('end_year')::INTEGER
  GROUP BY simulation_year, employment_status, level_id, age_band, tenure_band
),

-- 5B: Incremental window calculations for trend analysis
trend_analysis AS (
  SELECT 
    simulation_year,
    employment_status,
    employee_count,
    -- Efficient window functions for trend calculation
    employee_count - LAG(employee_count, 1, 0) OVER (
      PARTITION BY employment_status 
      ORDER BY simulation_year
    ) AS year_over_year_change,
    -- Moving averages using DuckDB's optimized window functions
    AVG(employee_count) OVER (
      PARTITION BY employment_status 
      ORDER BY simulation_year 
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS three_year_moving_avg
  FROM (
    SELECT 
      simulation_year,
      employment_status,
      COUNT(*) AS employee_count
    FROM fct_workforce_snapshot
    WHERE simulation_year BETWEEN getvariable('start_year')::INTEGER 
                             AND getvariable('end_year')::INTEGER
    GROUP BY simulation_year, employment_status
  ) base_counts
)

-- =====================================================================
-- FINAL OUTPUT: Comprehensive Comparison Results
-- =====================================================================

-- Main comparison output based on comparison_mode parameter
SELECT 
  CASE getvariable('comparison_mode')
    WHEN 'full' THEN 'Full Comparison Report'
    WHEN 'incremental' THEN 'Incremental Changes Report'
    WHEN 'performance' THEN 'Performance Metrics Report'
    ELSE 'Standard Report'
  END AS report_type,
  
  -- Summary statistics
  (SELECT COUNT(*) FROM parameterized_comparison) AS total_comparison_rows,
  (SELECT COUNT(*) FROM snapshot_deltas WHERE comparison_result != 'match') AS data_inconsistencies,
  (SELECT AVG(consistency_percentage) FROM data_quality_check) AS avg_consistency_percentage,
  
  -- Performance indicators
  (SELECT COUNT(*) FROM incremental_changes WHERE change_type = 'changed') AS incremental_changes_detected,
  (SELECT MAX(record_count) FROM performance_metrics) AS max_query_record_count,
  
  -- Optimization recommendations
  CASE 
    WHEN (SELECT AVG(consistency_percentage) FROM data_quality_check) < 95 
    THEN 'Review data consistency issues'
    WHEN (SELECT COUNT(*) FROM incremental_changes WHERE change_type = 'changed') > 1000 
    THEN 'Consider incremental processing'
    ELSE 'Performance optimization recommended'
  END AS optimization_recommendation,
  
  -- Timestamp for reproducibility
  NOW() AS analysis_timestamp,
  getvariable('start_year') AS analysis_start_year,
  getvariable('end_year') AS analysis_end_year

-- Conditional result sets based on comparison mode
UNION ALL

-- Detailed results for full comparison mode
SELECT 
  'Detail: ' || source_table AS report_type,
  simulation_year AS total_comparison_rows,
  record_count AS data_inconsistencies,
  avg_compensation AS avg_consistency_percentage,
  unique_employees AS incremental_changes_detected,
  total_compensation AS max_query_record_count,
  employment_status AS optimization_recommendation,
  NOW() AS analysis_timestamp,
  getvariable('start_year') AS analysis_start_year,
  getvariable('end_year') AS analysis_end_year
FROM parameterized_comparison
WHERE getvariable('comparison_mode') = 'full'

ORDER BY report_type, total_comparison_rows;

-- =====================================================================
-- Additional Performance Optimization Notes:
-- =====================================================================
-- 
-- 1. Index Strategy: 
--    - Composite indexes on (simulation_year, employee_id, employment_status)
--    - Covering indexes for frequently accessed columns
--    - Hash-based indexes for SCD change detection
--
-- 2. Query Optimization:
--    - Use CTEs for complex logic readability and potential optimization
--    - Leverage DuckDB's columnar storage with selective column access
--    - Batch processing for memory-constrained environments
--
-- 3. Incremental Processing:
--    - Hash-based change detection for minimal data scanning
--    - Parameterized year ranges for targeted analysis
--    - Approximate aggregations for performance on large datasets
--
-- 4. Memory Management:
--    - NTILE-based batching for controlled memory usage
--    - Window functions optimized for DuckDB's execution engine
--    - Efficient JOIN strategies using indexed columns
--
-- =====================================================================