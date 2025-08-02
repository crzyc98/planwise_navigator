{{ config(
    materialized='table',
    indexes=[
        {'columns': ['table_name'], 'type': 'btree'},
        {'columns': ['created_at'], 'type': 'btree'}
    ]
) }}

-- SCD Performance Monitoring Metadata
-- Provides metadata about monitoring infrastructure for SCD performance tracking
-- Replaced CREATE TABLE statements with SELECT-based metadata model

SELECT
    'mon_scd_phase_metrics' as table_name,
    'SCD Phase Performance Metrics' as description,
    'Tracks phase-level performance metrics for SCD operations' as details,
    'phase_name, metric_timestamp, duration_seconds, record_count, records_per_second, simulation_year' as expected_columns,
    CURRENT_TIMESTAMP as created_at
UNION ALL
SELECT
    'mon_sla_breaches' as table_name,
    'SLA Breach Tracking' as description,
    'Monitors SLA breaches in SCD processing' as details,
    'component_name, breach_timestamp, actual_duration_seconds, sla_threshold_seconds, breach_severity' as expected_columns,
    CURRENT_TIMESTAMP as created_at
UNION ALL
SELECT
    'mon_performance_metrics' as table_name,
    'Overall Performance Metrics' as description,
    'Overall performance metrics for SCD components' as details,
    'component_name, metric_timestamp, execution_time_seconds, total_records_processed, performance_category' as expected_columns,
    CURRENT_TIMESTAMP as created_at
UNION ALL
SELECT
    'mon_scd_integrity_checks' as table_name,
    'SCD Integrity Check Results' as description,
    'Data integrity checks for SCD operations' as details,
    'check_name, check_timestamp, table_name, check_result, violation_count, check_details' as expected_columns,
    CURRENT_TIMESTAMP as created_at
