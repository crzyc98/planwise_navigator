{{
  config(
    materialized='view',
    tags=['monitoring', 'compensation', 'inflation', 'executive_dashboard']
  )
}}

/*
Compensation Inflation Monitoring Dashboard
Surfaces per-employee inflation ratios, year-over-year changes, distribution statistics, and outlier detection.

Purpose:
- Monitor compensation inflation across simulation years
- Track year-over-year compensation changes
- Identify outliers and distribution anomalies
- Provide executive dashboard for compensation management
- Enable proactive detection of simulation issues

Author: Claude Code - DuckDB/dbt Performance Optimizer
Created: {{ run_started_at }}
*/

WITH baseline_stats AS (
  -- Calculate baseline compensation statistics
  SELECT
    {{ var('simulation_year') }} as baseline_year,
    COUNT(*) as baseline_employee_count,
    MIN(current_compensation) as baseline_min_comp,
    MAX(current_compensation) as baseline_max_comp,
    AVG(current_compensation) as baseline_avg_comp,
    MEDIAN(current_compensation) as baseline_median_comp,
    STDDEV(current_compensation) as baseline_stddev_comp,

    -- Distribution percentiles
    PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY current_compensation) as baseline_p10,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY current_compensation) as baseline_p25,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY current_compensation) as baseline_p75,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY current_compensation) as baseline_p90,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY current_compensation) as baseline_p95,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY current_compensation) as baseline_p99

  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

current_stats AS (
  -- Calculate current workforce compensation statistics
  SELECT
    {{ var('simulation_year') }} as current_year,
    employment_status,
    COUNT(*) as current_employee_count,
    MIN(current_compensation) as current_min_comp,
    MAX(current_compensation) as current_max_comp,
    AVG(current_compensation) as current_avg_comp,
    MEDIAN(current_compensation) as current_median_comp,
    STDDEV(current_compensation) as current_stddev_comp,

    -- Distribution percentiles
    PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY current_compensation) as current_p10,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY current_compensation) as current_p25,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY current_compensation) as current_p75,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY current_compensation) as current_p90,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY current_compensation) as current_p95,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY current_compensation) as current_p99,

    -- High compensation flags
    COUNT(CASE WHEN current_compensation > 10000000 THEN 1 END) as employees_over_10m,
    COUNT(CASE WHEN current_compensation > 5000000 THEN 1 END) as employees_over_5m,
    COUNT(CASE WHEN current_compensation > 1000000 THEN 1 END) as employees_over_1m,
    COUNT(CASE WHEN current_compensation < 10000 THEN 1 END) as employees_under_10k

  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ var('simulation_year') }}
  GROUP BY simulation_year, employment_status
),

employee_level_inflation AS (
  -- Calculate per-employee inflation metrics
  SELECT
    w.employee_id,
    w.simulation_year,
    w.current_compensation,
    w.employment_status,
    w.level_id,
    w.age_band,
    w.tenure_band,

    b.current_compensation as baseline_compensation,

    -- Inflation calculations
    CASE
      WHEN b.current_compensation > 0
      THEN w.current_compensation / b.current_compensation
      ELSE NULL
    END as inflation_factor,

    w.current_compensation - COALESCE(b.current_compensation, 0) as absolute_increase,

    CASE
      WHEN b.current_compensation > 0
      THEN ((w.current_compensation - b.current_compensation) / b.current_compensation) * 100
      ELSE NULL
    END as percentage_increase,

    -- Outlier flags
    CASE
      WHEN w.current_compensation > 10000000 THEN 'EXTREME_HIGH'
      WHEN w.current_compensation > 5000000 THEN 'VERY_HIGH'
      WHEN w.current_compensation > 1000000 THEN 'HIGH'
      WHEN w.current_compensation < 10000 AND w.employment_status = 'active' THEN 'VERY_LOW'
      ELSE 'NORMAL'
    END as compensation_level_flag,

    CASE
      WHEN b.current_compensation > 0 AND (w.current_compensation / b.current_compensation) > 10.0 THEN 'EXTREME_INFLATION'
      WHEN b.current_compensation > 0 AND (w.current_compensation / b.current_compensation) > 5.0 THEN 'SEVERE_INFLATION'
      WHEN b.current_compensation > 0 AND (w.current_compensation / b.current_compensation) > 2.0 THEN 'HIGH_INFLATION'
      WHEN b.current_compensation > 0 AND (w.current_compensation / b.current_compensation) < 0.8 THEN 'DEFLATION'
      ELSE 'NORMAL_INFLATION'
    END as inflation_flag

  FROM {{ ref('fct_workforce_snapshot') }} w
  LEFT JOIN {{ ref('int_baseline_workforce') }} b
    ON w.employee_id = b.employee_id
    AND b.simulation_year = {{ var('simulation_year') }}
  WHERE w.simulation_year = {{ var('simulation_year') }}
    AND w.employment_status = 'active'
),

level_analysis AS (
  -- Analyze inflation by job level
  SELECT
    level_id,
    COUNT(*) as employees_at_level,
    AVG(inflation_factor) as avg_inflation_factor,
    MEDIAN(inflation_factor) as median_inflation_factor,
    MIN(inflation_factor) as min_inflation_factor,
    MAX(inflation_factor) as max_inflation_factor,
    STDDEV(inflation_factor) as stddev_inflation_factor,

    AVG(current_compensation) as avg_current_comp,
    AVG(baseline_compensation) as avg_baseline_comp,

    COUNT(CASE WHEN inflation_flag = 'EXTREME_INFLATION' THEN 1 END) as extreme_inflation_count,
    COUNT(CASE WHEN inflation_flag = 'SEVERE_INFLATION' THEN 1 END) as severe_inflation_count,
    COUNT(CASE WHEN inflation_flag = 'HIGH_INFLATION' THEN 1 END) as high_inflation_count,
    COUNT(CASE WHEN compensation_level_flag = 'EXTREME_HIGH' THEN 1 END) as extreme_high_comp_count

  FROM employee_level_inflation
  WHERE inflation_factor IS NOT NULL
  GROUP BY level_id
),

demographic_analysis AS (
  -- Analyze inflation by demographics
  SELECT
    age_band,
    tenure_band,
    COUNT(*) as employees_in_segment,
    AVG(inflation_factor) as avg_inflation_factor,
    MAX(inflation_factor) as max_inflation_factor,
    COUNT(CASE WHEN inflation_flag IN ('EXTREME_INFLATION', 'SEVERE_INFLATION') THEN 1 END) as high_risk_count

  FROM employee_level_inflation
  WHERE inflation_factor IS NOT NULL
  GROUP BY age_band, tenure_band
),

outlier_detection AS (
  -- Statistical outlier detection using IQR method
  SELECT
    employee_id,
    current_compensation,
    inflation_factor,
    percentage_increase,
    inflation_flag,
    compensation_level_flag,

    -- Calculate z-score for compensation
    (current_compensation - (SELECT AVG(current_compensation) FROM employee_level_inflation)) /
    NULLIF((SELECT STDDEV(current_compensation) FROM employee_level_inflation), 0) as compensation_z_score,

    -- Calculate z-score for inflation factor
    (inflation_factor - (SELECT AVG(inflation_factor) FROM employee_level_inflation WHERE inflation_factor IS NOT NULL)) /
    NULLIF((SELECT STDDEV(inflation_factor) FROM employee_level_inflation WHERE inflation_factor IS NOT NULL), 0) as inflation_z_score,

    -- IQR-based outlier detection
    CASE
      WHEN inflation_factor > (SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY inflation_factor) FROM employee_level_inflation WHERE inflation_factor IS NOT NULL) +
                              1.5 * ((SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY inflation_factor) FROM employee_level_inflation WHERE inflation_factor IS NOT NULL) -
                                     (SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY inflation_factor) FROM employee_level_inflation WHERE inflation_factor IS NOT NULL))
      THEN 'STATISTICAL_OUTLIER_HIGH'
      WHEN inflation_factor < (SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY inflation_factor) FROM employee_level_inflation WHERE inflation_factor IS NOT NULL) -
                              1.5 * ((SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY inflation_factor) FROM employee_level_inflation WHERE inflation_factor IS NOT NULL) -
                                     (SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY inflation_factor) FROM employee_level_inflation WHERE inflation_factor IS NOT NULL))
      THEN 'STATISTICAL_OUTLIER_LOW'
      ELSE 'NOT_OUTLIER'
    END as statistical_outlier_flag

  FROM employee_level_inflation
  WHERE inflation_factor IS NOT NULL
)

-- Final consolidated monitoring report
SELECT
  -- METADATA
  {{ var('simulation_year') }} as simulation_year,
  CURRENT_TIMESTAMP as report_generated_at,
  'compensation_inflation_monitoring' as report_type,

  -- OVERALL STATISTICS
  (SELECT baseline_employee_count FROM baseline_stats) as baseline_employee_count,
  (SELECT current_employee_count FROM current_stats WHERE employment_status = 'active') as current_active_employees,

  -- BASELINE VS CURRENT COMPARISON
  (SELECT baseline_avg_comp FROM baseline_stats) as baseline_avg_compensation,
  (SELECT current_avg_comp FROM current_stats WHERE employment_status = 'active') as current_avg_compensation,
  (SELECT current_avg_comp FROM current_stats WHERE employment_status = 'active') /
    NULLIF((SELECT baseline_avg_comp FROM baseline_stats), 0) as overall_inflation_factor,

  (SELECT baseline_median_comp FROM baseline_stats) as baseline_median_compensation,
  (SELECT current_median_comp FROM current_stats WHERE employment_status = 'active') as current_median_compensation,
  (SELECT current_median_comp FROM current_stats WHERE employment_status = 'active') /
    NULLIF((SELECT baseline_median_comp FROM baseline_stats), 0) as median_inflation_factor,

  (SELECT baseline_max_comp FROM baseline_stats) as baseline_max_compensation,
  (SELECT current_max_comp FROM current_stats WHERE employment_status = 'active') as current_max_compensation,

  -- HIGH COMPENSATION FLAGS
  (SELECT employees_over_10m FROM current_stats WHERE employment_status = 'active') as employees_over_10m,
  (SELECT employees_over_5m FROM current_stats WHERE employment_status = 'active') as employees_over_5m,
  (SELECT employees_over_1m FROM current_stats WHERE employment_status = 'active') as employees_over_1m,
  (SELECT employees_under_10k FROM current_stats WHERE employment_status = 'active') as employees_under_10k,

  -- INFLATION RISK SUMMARY
  (SELECT COUNT(*) FROM employee_level_inflation WHERE inflation_flag = 'EXTREME_INFLATION') as extreme_inflation_employees,
  (SELECT COUNT(*) FROM employee_level_inflation WHERE inflation_flag = 'SEVERE_INFLATION') as severe_inflation_employees,
  (SELECT COUNT(*) FROM employee_level_inflation WHERE inflation_flag = 'HIGH_INFLATION') as high_inflation_employees,

  -- STATISTICAL OUTLIERS
  (SELECT COUNT(*) FROM outlier_detection WHERE statistical_outlier_flag = 'STATISTICAL_OUTLIER_HIGH') as statistical_outliers_high,
  (SELECT COUNT(*) FROM outlier_detection WHERE statistical_outlier_flag = 'STATISTICAL_OUTLIER_LOW') as statistical_outliers_low,

  -- LEVEL ANALYSIS SUMMARY (TOP LEVEL WITH HIGHEST INFLATION)
  (SELECT level_id FROM level_analysis ORDER BY avg_inflation_factor DESC LIMIT 1) as highest_inflation_level,
  (SELECT avg_inflation_factor FROM level_analysis ORDER BY avg_inflation_factor DESC LIMIT 1) as highest_level_avg_inflation,
  (SELECT extreme_inflation_count FROM level_analysis ORDER BY extreme_inflation_count DESC LIMIT 1) as max_extreme_inflation_by_level,

  -- DISTRIBUTION HEALTH METRICS
  (SELECT current_p95 FROM current_stats WHERE employment_status = 'active') as p95_compensation,
  (SELECT current_p99 FROM current_stats WHERE employment_status = 'active') as p99_compensation,
  (SELECT current_stddev_comp FROM current_stats WHERE employment_status = 'active') as compensation_std_deviation,

  -- OVERALL HEALTH ASSESSMENT
  CASE
    WHEN (SELECT employees_over_10m FROM current_stats WHERE employment_status = 'active') > 0 THEN 'CRITICAL'
    WHEN (SELECT COUNT(*) FROM employee_level_inflation WHERE inflation_flag = 'EXTREME_INFLATION') > 5 THEN 'SEVERE'
    WHEN (SELECT employees_over_5m FROM current_stats WHERE employment_status = 'active') >
         (SELECT current_employee_count FROM current_stats WHERE employment_status = 'active') * 0.01 THEN 'WARNING'
    WHEN (SELECT COUNT(*) FROM employee_level_inflation WHERE inflation_flag IN ('SEVERE_INFLATION', 'HIGH_INFLATION')) >
         (SELECT current_employee_count FROM current_stats WHERE employment_status = 'active') * 0.05 THEN 'WARNING'
    ELSE 'HEALTHY'
  END as overall_compensation_health,

  -- RECOMMENDATIONS
  CONCAT_WS('; ',
    CASE WHEN (SELECT employees_over_10m FROM current_stats WHERE employment_status = 'active') > 0
         THEN 'IMMEDIATE ACTION: ' || (SELECT employees_over_10m FROM current_stats WHERE employment_status = 'active') || ' employees exceed $10M compensation' END,
    CASE WHEN (SELECT COUNT(*) FROM employee_level_inflation WHERE inflation_flag = 'EXTREME_INFLATION') > 0
         THEN 'REVIEW REQUIRED: ' || (SELECT COUNT(*) FROM employee_level_inflation WHERE inflation_flag = 'EXTREME_INFLATION') || ' employees have extreme compensation inflation' END,
    CASE WHEN (SELECT employees_over_5m FROM current_stats WHERE employment_status = 'active') > 10
         THEN 'MONITOR: ' || (SELECT employees_over_5m FROM current_stats WHERE employment_status = 'active') || ' employees exceed $5M compensation' END,
    CASE WHEN (SELECT COUNT(*) FROM outlier_detection WHERE statistical_outlier_flag = 'STATISTICAL_OUTLIER_HIGH') > 20
         THEN 'INVESTIGATE: ' || (SELECT COUNT(*) FROM outlier_detection WHERE statistical_outlier_flag = 'STATISTICAL_OUTLIER_HIGH') || ' statistical outliers detected' END
  ) as recommendations
