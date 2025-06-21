# Monitoring Models - Pipeline & Data Quality Monitoring

## Purpose

The monitoring models (`dbt/models/monitoring/mon_data_quality.sql` and `dbt/models/monitoring/mon_pipeline_performance.sql`) provide continuous oversight of the PlanWise Navigator simulation pipeline, tracking data quality metrics, pipeline performance, and business rule compliance in real-time.

## Architecture

The monitoring system implements a comprehensive observability framework:
- **Data Quality Monitoring**: Statistical validation and drift detection
- **Pipeline Performance**: Execution timing and resource utilization
- **Business Rule Compliance**: Automated validation of simulation constraints
- **Alert Generation**: Proactive notification of issues and anomalies

## Key Monitoring Models

### 1. mon_data_quality.sql - Data Quality Dashboard

**Purpose**: Track data quality metrics across all simulation models and detect anomalies or drift in workforce data patterns.

```sql
{{ config(
    materialized='table',
    indexes=[
      {'columns': ['check_date', 'model_name'], 'type': 'btree'},
      {'columns': ['quality_score'], 'type': 'btree'}
    ]
) }}

WITH quality_checks AS (
  -- Row count validation
  SELECT
    CURRENT_DATE AS check_date,
    'fct_workforce_snapshot' AS model_name,
    'row_count' AS check_type,
    COUNT(*) AS current_value,
    {{ var('expected_workforce_size') }} AS expected_value,
    ABS(COUNT(*) - {{ var('expected_workforce_size') }}) * 100.0 / {{ var('expected_workforce_size') }} AS variance_percent,
    CASE 
      WHEN ABS(COUNT(*) - {{ var('expected_workforce_size') }}) * 100.0 / {{ var('expected_workforce_size') }} < 5 
      THEN 'PASS' 
      ELSE 'FAIL' 
    END AS status
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ var('current_simulation_year') }}
  
  UNION ALL
  
  -- Null value checks
  SELECT
    CURRENT_DATE AS check_date,
    'fct_workforce_snapshot' AS model_name,
    'null_check_employee_id' AS check_type,
    COUNT(*) FILTER (WHERE employee_id IS NULL) AS current_value,
    0 AS expected_value,
    CASE WHEN COUNT(*) FILTER (WHERE employee_id IS NULL) = 0 THEN 0 ELSE 100 END AS variance_percent,
    CASE WHEN COUNT(*) FILTER (WHERE employee_id IS NULL) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
  FROM {{ ref('fct_workforce_snapshot') }}
  
  UNION ALL
  
  -- Distribution checks for compensation
  SELECT
    CURRENT_DATE AS check_date,
    'fct_workforce_snapshot' AS model_name,
    'compensation_distribution' AS check_type,
    ROUND(AVG(current_compensation), 0) AS current_value,
    {{ var('expected_avg_compensation', 75000) }} AS expected_value,
    ABS(AVG(current_compensation) - {{ var('expected_avg_compensation', 75000) }}) * 100.0 / {{ var('expected_avg_compensation', 75000) }} AS variance_percent,
    CASE 
      WHEN ABS(AVG(current_compensation) - {{ var('expected_avg_compensation', 75000) }}) * 100.0 / {{ var('expected_avg_compensation', 75000) }} < 10 
      THEN 'PASS' 
      ELSE 'WARN' 
    END AS status
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE employment_status = 'active'
  
  UNION ALL
  
  -- Event volume validation
  SELECT
    CURRENT_DATE AS check_date,
    'fct_yearly_events' AS model_name,
    'event_volume_' || event_type AS check_type,
    COUNT(*) AS current_value,
    CASE event_type
      WHEN 'hire' THEN ROUND({{ var('baseline_workforce_count') }} * {{ var('target_growth_rate') }} * 1.2)  -- Growth + replacement
      WHEN 'termination' THEN ROUND({{ var('baseline_workforce_count') }} * {{ var('total_termination_rate') }})
      WHEN 'promotion' THEN ROUND({{ var('baseline_workforce_count') }} * {{ var('promotion_base_rate', 0.15) }})
      ELSE NULL
    END AS expected_value,
    CASE event_type
      WHEN 'hire' THEN ABS(COUNT(*) - ROUND({{ var('baseline_workforce_count') }} * {{ var('target_growth_rate') }} * 1.2)) * 100.0 / ROUND({{ var('baseline_workforce_count') }} * {{ var('target_growth_rate') }} * 1.2)
      WHEN 'termination' THEN ABS(COUNT(*) - ROUND({{ var('baseline_workforce_count') }} * {{ var('total_termination_rate') }})) * 100.0 / ROUND({{ var('baseline_workforce_count') }} * {{ var('total_termination_rate') }})
      WHEN 'promotion' THEN ABS(COUNT(*) - ROUND({{ var('baseline_workforce_count') }} * {{ var('promotion_base_rate', 0.15) }})) * 100.0 / ROUND({{ var('baseline_workforce_count') }} * {{ var('promotion_base_rate', 0.15) }})
      ELSE 0
    END AS variance_percent,
    CASE 
      WHEN event_type IN ('hire', 'termination', 'promotion') 
        AND ABS(COUNT(*) - expected_value) * 100.0 / expected_value < 15 
      THEN 'PASS'
      WHEN event_type IN ('hire', 'termination', 'promotion')
        AND ABS(COUNT(*) - expected_value) * 100.0 / expected_value < 25
      THEN 'WARN'
      ELSE 'FAIL'
    END AS status
  FROM {{ ref('fct_yearly_events') }}
  WHERE simulation_year = {{ var('current_simulation_year') }}
  GROUP BY event_type
),

quality_summary AS (
  SELECT
    check_date,
    model_name,
    COUNT(*) AS total_checks,
    COUNT(*) FILTER (WHERE status = 'PASS') AS passed_checks,
    COUNT(*) FILTER (WHERE status = 'WARN') AS warning_checks,
    COUNT(*) FILTER (WHERE status = 'FAIL') AS failed_checks,
    ROUND(COUNT(*) FILTER (WHERE status = 'PASS') * 100.0 / COUNT(*), 1) AS quality_score,
    CASE
      WHEN COUNT(*) FILTER (WHERE status = 'FAIL') > 0 THEN 'CRITICAL'
      WHEN COUNT(*) FILTER (WHERE status = 'WARN') > 2 THEN 'WARNING'
      WHEN ROUND(COUNT(*) FILTER (WHERE status = 'PASS') * 100.0 / COUNT(*), 1) >= 95 THEN 'HEALTHY'
      ELSE 'DEGRADED'
    END AS overall_status
  FROM quality_checks
  GROUP BY check_date, model_name
)

SELECT
  q.check_date,
  q.model_name,
  q.check_type,
  q.current_value,
  q.expected_value,
  q.variance_percent,
  q.status,
  s.quality_score,
  s.overall_status,
  -- Trend analysis
  LAG(q.current_value) OVER (
    PARTITION BY q.model_name, q.check_type 
    ORDER BY q.check_date
  ) AS previous_value,
  CASE 
    WHEN LAG(q.current_value) OVER (PARTITION BY q.model_name, q.check_type ORDER BY q.check_date) IS NOT NULL
    THEN ROUND((q.current_value - LAG(q.current_value) OVER (PARTITION BY q.model_name, q.check_type ORDER BY q.check_date)) * 100.0 / LAG(q.current_value) OVER (PARTITION BY q.model_name, q.check_type ORDER BY q.check_date), 2)
    ELSE NULL
  END AS trend_percent
FROM quality_checks q
JOIN quality_summary s ON q.check_date = s.check_date AND q.model_name = s.model_name
ORDER BY q.check_date DESC, q.model_name, q.check_type
```

### 2. mon_pipeline_performance.sql - Pipeline Performance Metrics

**Purpose**: Monitor pipeline execution performance, resource utilization, and identify optimization opportunities.

```sql
{{ config(
    materialized='incremental',
    unique_key='execution_id',
    on_schema_change='append_new_columns'
) }}

WITH execution_metrics AS (
  SELECT
    {{ dbt_utils.generate_surrogate_key(['invocation_id', 'node_id']) }} AS execution_id,
    invocation_id,
    node_id,
    run_started_at,
    run_completed_at,
    EXTRACT(EPOCH FROM (run_completed_at - run_started_at)) AS execution_time_seconds,
    status,
    rows_affected,
    bytes_processed,
    -- Resource utilization (if available)
    thread_id,
    CURRENT_TIMESTAMP AS recorded_at
  FROM {{ ref('dbt_run_results') }}  -- Assuming dbt run results are captured
  
  {% if is_incremental() %}
    WHERE run_started_at > (SELECT MAX(run_started_at) FROM {{ this }})
  {% endif %}
),

performance_analysis AS (
  SELECT
    execution_id,
    invocation_id,
    node_id,
    run_started_at::date AS execution_date,
    execution_time_seconds,
    rows_affected,
    status,
    -- Performance categorization
    CASE
      WHEN execution_time_seconds < 30 THEN 'FAST'
      WHEN execution_time_seconds < 120 THEN 'NORMAL'
      WHEN execution_time_seconds < 300 THEN 'SLOW'
      ELSE 'VERY_SLOW'
    END AS performance_category,
    -- Efficiency metrics
    CASE 
      WHEN rows_affected > 0 THEN ROUND(execution_time_seconds / rows_affected * 1000, 2)
      ELSE NULL
    END AS seconds_per_1k_rows,
    -- Historical comparison
    AVG(execution_time_seconds) OVER (
      PARTITION BY node_id 
      ORDER BY run_started_at 
      ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING
    ) AS avg_historical_time,
    recorded_at
  FROM execution_metrics
),

alerts AS (
  SELECT
    execution_id,
    node_id,
    execution_date,
    execution_time_seconds,
    avg_historical_time,
    performance_category,
    -- Performance degradation alerts
    CASE
      WHEN avg_historical_time IS NOT NULL 
        AND execution_time_seconds > avg_historical_time * 2 
      THEN 'PERFORMANCE_DEGRADATION'
      WHEN status != 'success' 
      THEN 'EXECUTION_FAILURE'
      WHEN performance_category = 'VERY_SLOW' 
      THEN 'SLOW_EXECUTION'
      ELSE NULL
    END AS alert_type,
    CASE
      WHEN avg_historical_time IS NOT NULL 
        AND execution_time_seconds > avg_historical_time * 2 
      THEN ROUND((execution_time_seconds - avg_historical_time) * 100.0 / avg_historical_time, 1)
      ELSE NULL
    END AS performance_degradation_percent
  FROM performance_analysis
)

SELECT
  a.execution_id,
  a.node_id,
  a.execution_date,
  a.execution_time_seconds,
  a.avg_historical_time,
  a.performance_category,
  a.alert_type,
  a.performance_degradation_percent,
  p.rows_affected,
  p.seconds_per_1k_rows,
  p.status,
  p.recorded_at,
  -- Summary statistics
  COUNT(*) OVER (PARTITION BY a.node_id, a.execution_date) AS daily_executions,
  AVG(a.execution_time_seconds) OVER (PARTITION BY a.node_id, a.execution_date) AS avg_daily_time,
  MAX(a.execution_time_seconds) OVER (PARTITION BY a.node_id, a.execution_date) AS max_daily_time
FROM alerts a
JOIN performance_analysis p ON a.execution_id = p.execution_id
ORDER BY a.execution_date DESC, a.execution_time_seconds DESC
```

## Alert and Notification System

### Quality Alerts Configuration
```sql
-- Alert generation for critical issues
CREATE OR REPLACE VIEW quality_alerts AS
SELECT
  check_date,
  model_name,
  check_type,
  status,
  variance_percent,
  'CRITICAL: ' || model_name || ' ' || check_type || ' check failed with ' || 
  ROUND(variance_percent, 1) || '% variance' AS alert_message,
  CASE
    WHEN status = 'FAIL' AND check_type LIKE '%row_count%' THEN 'HIGH'
    WHEN status = 'FAIL' AND check_type LIKE '%null_check%' THEN 'CRITICAL'
    WHEN status = 'WARN' THEN 'MEDIUM'
    ELSE 'LOW'
  END AS severity
FROM {{ ref('mon_data_quality') }}
WHERE status IN ('FAIL', 'WARN')
  AND check_date = CURRENT_DATE;
```

### Performance Alerts
```sql
-- Performance degradation alerts
CREATE OR REPLACE VIEW performance_alerts AS
SELECT
  execution_date,
  node_id,
  alert_type,
  execution_time_seconds,
  performance_degradation_percent,
  'PERFORMANCE: ' || node_id || ' execution time increased by ' ||
  performance_degradation_percent || '% (' || execution_time_seconds || 's)' AS alert_message,
  CASE
    WHEN alert_type = 'EXECUTION_FAILURE' THEN 'CRITICAL'
    WHEN performance_degradation_percent > 100 THEN 'HIGH'
    WHEN performance_degradation_percent > 50 THEN 'MEDIUM'
    ELSE 'LOW'
  END AS severity
FROM {{ ref('mon_pipeline_performance') }}
WHERE alert_type IS NOT NULL
  AND execution_date = CURRENT_DATE;
```

## Monitoring Dashboards

### Data Quality Dashboard Queries
```sql
-- Overall system health
SELECT
  model_name,
  quality_score,
  overall_status,
  failed_checks,
  warning_checks
FROM {{ ref('mon_data_quality') }}
WHERE check_date = CURRENT_DATE
ORDER BY quality_score ASC;

-- Trend analysis
SELECT
  check_date,
  model_name,
  quality_score,
  LAG(quality_score) OVER (PARTITION BY model_name ORDER BY check_date) AS prev_score
FROM {{ ref('mon_data_quality') }}
WHERE check_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY check_date DESC, model_name;
```

### Performance Dashboard Queries
```sql
-- Slowest models today
SELECT
  node_id,
  AVG(execution_time_seconds) AS avg_time,
  MAX(execution_time_seconds) AS max_time,
  COUNT(*) AS execution_count
FROM {{ ref('mon_pipeline_performance') }}
WHERE execution_date = CURRENT_DATE
GROUP BY node_id
ORDER BY avg_time DESC
LIMIT 10;

-- Performance trends
SELECT
  execution_date,
  AVG(execution_time_seconds) AS avg_pipeline_time,
  COUNT(DISTINCT node_id) AS models_executed,
  COUNT(*) FILTER (WHERE alert_type IS NOT NULL) AS alert_count
FROM {{ ref('mon_pipeline_performance') }}
WHERE execution_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY execution_date
ORDER BY execution_date DESC;
```

## Custom Monitoring Tests

### Data Drift Detection
```sql
-- Macro for statistical distribution comparison
{% macro test_distribution_drift(model, column_name, baseline_date, drift_threshold=0.1) %}
  WITH current_stats AS (
    SELECT
      AVG({{ column_name }}) AS current_mean,
      STDDEV({{ column_name }}) AS current_stddev,
      COUNT(*) AS current_count
    FROM {{ model }}
    WHERE DATE(created_at) = CURRENT_DATE
  ),
  
  baseline_stats AS (
    SELECT
      AVG({{ column_name }}) AS baseline_mean,
      STDDEV({{ column_name }}) AS baseline_stddev,
      COUNT(*) AS baseline_count
    FROM {{ model }}
    WHERE DATE(created_at) = '{{ baseline_date }}'
  )
  
  SELECT
    ABS(c.current_mean - b.baseline_mean) / b.baseline_mean AS mean_drift,
    ABS(c.current_stddev - b.baseline_stddev) / b.baseline_stddev AS stddev_drift
  FROM current_stats c
  CROSS JOIN baseline_stats b
  WHERE ABS(c.current_mean - b.baseline_mean) / b.baseline_mean > {{ drift_threshold }}
     OR ABS(c.current_stddev - b.baseline_stddev) / b.baseline_stddev > {{ drift_threshold }}
{% endmacro %}
```

## Integration with External Systems

### Slack Notifications
```python
def send_quality_alert(alert_data):
    """Send data quality alerts to Slack channel"""
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    
    message = {
        "text": f"🚨 Data Quality Alert: {alert_data['model_name']}",
        "attachments": [
            {
                "color": "danger" if alert_data['status'] == 'FAIL' else "warning",
                "fields": [
                    {"title": "Check Type", "value": alert_data['check_type'], "short": True},
                    {"title": "Status", "value": alert_data['status'], "short": True},
                    {"title": "Variance", "value": f"{alert_data['variance_percent']}%", "short": True},
                    {"title": "Date", "value": alert_data['check_date'], "short": True}
                ]
            }
        ]
    }
```

## Dependencies

### Required Components
- dbt run results capture mechanism
- Alert notification system
- Dashboard visualization tools
- Historical data storage

### Configuration Dependencies
- Quality thresholds and tolerances
- Performance benchmarks
- Alert routing configuration

## Related Files

### Monitoring Infrastructure
- `orchestrator/assets/validation.py` - Dagster validation assets
- `scripts/validation_checks.py` - Additional monitoring utilities
- Dashboard components for monitoring visualization

### Alert and Response
- Slack/email notification configurations
- Runbook documentation for alert response
- Automated remediation scripts

## Implementation Notes

### Best Practices 
1. **Baseline Establishment**: Set realistic quality and performance baselines
2. **Alert Fatigue Prevention**: Tune thresholds to minimize false positives
3. **Historical Tracking**: Maintain sufficient history for trend analysis
4. **Actionable Alerts**: Ensure alerts provide clear remediation guidance

### Performance Considerations
- Use incremental materialization for monitoring tables
- Implement efficient indexing on frequently queried columns
- Balance monitoring comprehensiveness with system overhead
- Archive old monitoring data to manage storage costs