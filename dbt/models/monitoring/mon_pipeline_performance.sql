{{ config(materialized='table') }}

-- Pipeline Performance Monitoring: Track simulation runtime and resource utilization
-- Monitors model execution times, memory usage, success rates, and throughput metrics

WITH simulation_runs AS (
    -- Track simulation execution metrics by year and configuration
    SELECT
        simulation_year,
        COUNT(DISTINCT employee_id) AS total_employees_processed,
        COUNT(DISTINCT CASE WHEN employment_status = 'active' THEN employee_id END) AS active_employees,
        COUNT(DISTINCT CASE WHEN employment_status = 'terminated' THEN employee_id END) AS terminated_employees,
        MIN(snapshot_created_at) AS run_start_time,
        MAX(snapshot_created_at) AS run_end_time,
        EXTRACT(EPOCH FROM (MAX(snapshot_created_at) - MIN(snapshot_created_at))) AS run_duration_seconds,
        EXTRACT(EPOCH FROM (MAX(snapshot_created_at) - MIN(snapshot_created_at))) / 60 AS run_duration_minutes
    FROM {{ ref('fct_workforce_snapshot') }}
    GROUP BY simulation_year
),

event_processing_metrics AS (
    -- Track event processing performance
    SELECT
        simulation_year,
        event_type,
        COUNT(*) AS events_processed,
        MIN(created_at) AS first_event_time,
        MAX(created_at) AS last_event_time,
        EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) AS event_processing_duration_seconds,
        -- Calculate events per second processing rate
        CASE
            WHEN EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) > 0 THEN
                COUNT(*) / EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at)))
            ELSE NULL
        END AS events_per_second
    FROM {{ ref('fct_yearly_events') }}
    GROUP BY simulation_year, event_type
),

throughput_metrics AS (
    -- Calculate overall throughput metrics
    SELECT
        sr.simulation_year,
        sr.total_employees_processed,
        sr.run_duration_seconds,
        sr.run_duration_minutes,

        -- Throughput calculations
        CASE
            WHEN sr.run_duration_seconds > 0 THEN
                sr.total_employees_processed / sr.run_duration_seconds
            ELSE NULL
        END AS employees_per_second,

        CASE
            WHEN sr.run_duration_minutes > 0 THEN
                sr.total_employees_processed / sr.run_duration_minutes
            ELSE NULL
        END AS employees_per_minute,

        -- Event processing efficiency
        SUM(epm.events_processed) AS total_events_processed,
        CASE
            WHEN sr.run_duration_seconds > 0 THEN
                SUM(epm.events_processed) / sr.run_duration_seconds
            ELSE NULL
        END AS events_per_second_overall,

        -- Resource utilization estimates (based on processing complexity)
        sr.total_employees_processed * 0.001 AS estimated_cpu_hours,
        sr.total_employees_processed * 0.01 AS estimated_memory_mb

    FROM simulation_runs sr
    LEFT JOIN event_processing_metrics epm ON sr.simulation_year = epm.simulation_year
    GROUP BY sr.simulation_year, sr.total_employees_processed, sr.run_duration_seconds, sr.run_duration_minutes
),

model_execution_metrics AS (
    -- Simulate dbt model execution timing (in real implementation, this would come from dbt metadata)
    SELECT
        simulation_year,
        'fct_workforce_snapshot' AS model_name,
        'fact' AS model_type,
        run_duration_seconds AS estimated_execution_time_seconds,
        total_employees_processed AS records_processed,
        CASE
            WHEN run_duration_seconds > 0 THEN
                total_employees_processed / run_duration_seconds
            ELSE NULL
        END AS records_per_second,
        CASE
            WHEN run_duration_seconds > 60 THEN 'SLOW'
            WHEN run_duration_seconds > 30 THEN 'MEDIUM'
            ELSE 'FAST'
        END AS performance_category
    FROM simulation_runs

    UNION ALL

    SELECT
        simulation_year,
        'fct_yearly_events' AS model_name,
        'fact' AS model_type,
        event_processing_duration_seconds AS estimated_execution_time_seconds,
        events_processed AS records_processed,
        events_per_second AS records_per_second,
        CASE
            WHEN event_processing_duration_seconds > 30 THEN 'SLOW'
            WHEN event_processing_duration_seconds > 10 THEN 'MEDIUM'
            ELSE 'FAST'
        END AS performance_category
    FROM event_processing_metrics
),

-- Performance trend analysis
performance_trends AS (
    SELECT
        simulation_year,
        total_employees_processed,
        run_duration_minutes,
        employees_per_minute,

        -- Calculate trends compared to previous year
        LAG(run_duration_minutes) OVER (ORDER BY simulation_year) AS prev_year_duration,
        LAG(total_employees_processed) OVER (ORDER BY simulation_year) AS prev_year_employees,
        LAG(employees_per_minute) OVER (ORDER BY simulation_year) AS prev_year_throughput,

        -- Performance change calculations
        CASE
            WHEN LAG(run_duration_minutes) OVER (ORDER BY simulation_year) > 0 THEN
                (run_duration_minutes - LAG(run_duration_minutes) OVER (ORDER BY simulation_year)) * 100.0 /
                LAG(run_duration_minutes) OVER (ORDER BY simulation_year)
            ELSE NULL
        END AS duration_change_percent,

        CASE
            WHEN LAG(employees_per_minute) OVER (ORDER BY simulation_year) > 0 THEN
                (employees_per_minute - LAG(employees_per_minute) OVER (ORDER BY simulation_year)) * 100.0 /
                LAG(employees_per_minute) OVER (ORDER BY simulation_year)
            ELSE NULL
        END AS throughput_change_percent,

        -- Scale efficiency (how well performance scales with data size)
        CASE
            WHEN LAG(total_employees_processed) OVER (ORDER BY simulation_year) > 0 AND
                 LAG(run_duration_minutes) OVER (ORDER BY simulation_year) > 0 THEN
                (employees_per_minute / LAG(employees_per_minute) OVER (ORDER BY simulation_year)) /
                (total_employees_processed / LAG(total_employees_processed) OVER (ORDER BY simulation_year))
            ELSE NULL
        END AS scale_efficiency_ratio

    FROM throughput_metrics
),

-- Resource utilization estimates
resource_utilization AS (
    SELECT
        simulation_year,
        total_employees_processed,
        estimated_cpu_hours,
        estimated_memory_mb,

        -- Resource efficiency metrics
        estimated_cpu_hours / total_employees_processed AS cpu_hours_per_employee,
        estimated_memory_mb / total_employees_processed AS memory_mb_per_employee,

        -- Resource utilization categories
        CASE
            WHEN estimated_cpu_hours > 1.0 THEN 'HIGH'
            WHEN estimated_cpu_hours > 0.1 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS cpu_utilization_category,

        CASE
            WHEN estimated_memory_mb > 1000 THEN 'HIGH'
            WHEN estimated_memory_mb > 100 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS memory_utilization_category

    FROM throughput_metrics
),

-- Success rate and error tracking
execution_quality AS (
    SELECT
        simulation_year,
        'fct_workforce_snapshot' AS model_name,

        -- Data quality indicators as proxy for execution success
        COUNT(*) AS total_records,
        COUNT(CASE WHEN current_compensation IS NOT NULL THEN 1 END) AS valid_compensation_records,
        COUNT(CASE WHEN current_age BETWEEN 18 AND 70 THEN 1 END) AS valid_age_records,
        COUNT(CASE WHEN current_tenure >= 0 THEN 1 END) AS valid_tenure_records,

        -- Success rate calculations
        COUNT(CASE WHEN current_compensation IS NOT NULL THEN 1 END) * 100.0 / COUNT(*) AS compensation_success_rate,
        COUNT(CASE WHEN current_age BETWEEN 18 AND 70 THEN 1 END) * 100.0 / COUNT(*) AS age_validation_success_rate,
        COUNT(CASE WHEN current_tenure >= 0 THEN 1 END) * 100.0 / COUNT(*) AS tenure_validation_success_rate,

        -- Overall quality score
        (COUNT(CASE WHEN current_compensation IS NOT NULL THEN 1 END) * 100.0 / COUNT(*) +
         COUNT(CASE WHEN current_age BETWEEN 18 AND 70 THEN 1 END) * 100.0 / COUNT(*) +
         COUNT(CASE WHEN current_tenure >= 0 THEN 1 END) * 100.0 / COUNT(*)) / 3 AS overall_quality_score

    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employment_status = 'active'
    GROUP BY simulation_year
)

-- Final consolidated performance monitoring view
SELECT
    tm.simulation_year,

    -- Basic execution metrics
    tm.total_employees_processed,
    tm.total_events_processed,
    tm.run_duration_minutes,
    tm.run_duration_seconds,

    -- Throughput metrics
    tm.employees_per_minute,
    tm.employees_per_second,
    tm.events_per_second_overall,

    -- Resource utilization
    ru.estimated_cpu_hours,
    ru.estimated_memory_mb,
    ru.cpu_hours_per_employee,
    ru.memory_mb_per_employee,
    ru.cpu_utilization_category,
    ru.memory_utilization_category,

    -- Performance trends
    pt.prev_year_duration,
    pt.prev_year_employees,
    pt.prev_year_throughput,
    pt.duration_change_percent,
    pt.throughput_change_percent,
    pt.scale_efficiency_ratio,

    -- Performance categorization
    CASE
        WHEN tm.run_duration_minutes > 60 THEN 'SLOW'
        WHEN tm.run_duration_minutes > 30 THEN 'MEDIUM'
        ELSE 'FAST'
    END AS overall_performance_category,

    CASE
        WHEN tm.employees_per_minute > 1000 THEN 'HIGH'
        WHEN tm.employees_per_minute > 100 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS throughput_category,

    -- Execution quality metrics
    eq.overall_quality_score,
    eq.compensation_success_rate,
    eq.age_validation_success_rate,
    eq.tenure_validation_success_rate,

    CASE
        WHEN eq.overall_quality_score >= 95 THEN 'EXCELLENT'
        WHEN eq.overall_quality_score >= 90 THEN 'GOOD'
        WHEN eq.overall_quality_score >= 80 THEN 'FAIR'
        ELSE 'POOR'
    END AS quality_category,

    -- Performance alerts
    CASE
        WHEN tm.run_duration_minutes > 120 THEN 'SLOW_EXECUTION'
        WHEN tm.employees_per_minute < 10 THEN 'LOW_THROUGHPUT'
        WHEN ru.estimated_cpu_hours > 2.0 THEN 'HIGH_CPU_USAGE'
        WHEN ru.estimated_memory_mb > 2000 THEN 'HIGH_MEMORY_USAGE'
        WHEN eq.overall_quality_score < 90 THEN 'QUALITY_ISSUE'
        WHEN pt.throughput_change_percent < -20 THEN 'PERFORMANCE_DEGRADATION'
        ELSE 'OK'
    END AS performance_alert,

    -- SLA compliance (assuming 30 minutes is the SLA)
    CASE
        WHEN tm.run_duration_minutes <= 30 THEN 'WITHIN_SLA'
        WHEN tm.run_duration_minutes <= 60 THEN 'SLA_WARNING'
        ELSE 'SLA_BREACH'
    END AS sla_status,

    -- Metadata
    CURRENT_TIMESTAMP AS performance_check_timestamp

FROM throughput_metrics tm
LEFT JOIN performance_trends pt ON tm.simulation_year = pt.simulation_year
LEFT JOIN resource_utilization ru ON tm.simulation_year = ru.simulation_year
LEFT JOIN execution_quality eq ON tm.simulation_year = eq.simulation_year

ORDER BY tm.simulation_year DESC
