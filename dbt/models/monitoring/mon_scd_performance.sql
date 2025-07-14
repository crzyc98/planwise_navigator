{{ config(
    materialized='table',
    indexes=[
        {'columns': ['component_name'], 'type': 'btree'},
        {'columns': ['metric_timestamp'], 'type': 'btree'},
        {'columns': ['component_name', 'metric_timestamp'], 'type': 'btree'}
    ]
) }}

-- SCD Performance Monitoring Tables
-- Creates monitoring infrastructure for SCD performance tracking

-- Performance metrics table
CREATE TABLE IF NOT EXISTS mon_scd_phase_metrics (
    phase_name VARCHAR(100) NOT NULL,
    metric_timestamp TIMESTAMP NOT NULL,
    duration_seconds DOUBLE NOT NULL,
    record_count INTEGER NOT NULL,
    records_per_second DOUBLE NOT NULL,
    simulation_year INTEGER NOT NULL,
    PRIMARY KEY (phase_name, metric_timestamp)
);

-- SLA breach tracking table
CREATE TABLE IF NOT EXISTS mon_sla_breaches (
    component_name VARCHAR(100) NOT NULL,
    breach_timestamp TIMESTAMP NOT NULL,
    actual_duration_seconds DOUBLE NOT NULL,
    sla_threshold_seconds INTEGER NOT NULL,
    breach_severity VARCHAR(20) NOT NULL,
    PRIMARY KEY (component_name, breach_timestamp)
);

-- Overall performance metrics table
CREATE TABLE IF NOT EXISTS mon_performance_metrics (
    component_name VARCHAR(100) NOT NULL,
    metric_timestamp TIMESTAMP NOT NULL,
    execution_time_seconds DOUBLE NOT NULL,
    total_records_processed INTEGER NOT NULL,
    performance_category VARCHAR(20) NOT NULL,
    PRIMARY KEY (component_name, metric_timestamp)
);

-- SCD integrity monitoring table
CREATE TABLE IF NOT EXISTS mon_scd_integrity_checks (
    check_name VARCHAR(100) NOT NULL,
    check_timestamp TIMESTAMP NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    check_result VARCHAR(20) NOT NULL,
    violation_count INTEGER NOT NULL,
    check_details TEXT,
    PRIMARY KEY (check_name, check_timestamp, table_name)
);

-- Create a view for the monitoring tables to be referenced by other models
SELECT
    'mon_scd_phase_metrics' as table_name,
    'SCD Phase Performance Metrics' as description,
    CURRENT_TIMESTAMP as created_at
UNION ALL
SELECT
    'mon_sla_breaches' as table_name,
    'SLA Breach Tracking' as description,
    CURRENT_TIMESTAMP as created_at
UNION ALL
SELECT
    'mon_performance_metrics' as table_name,
    'Overall Performance Metrics' as description,
    CURRENT_TIMESTAMP as created_at
UNION ALL
SELECT
    'mon_scd_integrity_checks' as table_name,
    'SCD Integrity Check Results' as description,
    CURRENT_TIMESTAMP as created_at
