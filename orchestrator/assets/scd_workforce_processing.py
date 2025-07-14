from dagster import asset, AssetExecutionContext, AssetIn
from orchestrator.resources import DuckDBResource, DbtResource
from orchestrator.utils.scd_performance_monitor import SCDPerformanceMonitor
import pandas as pd
from typing import Dict, Any

@asset(
    ins={"workforce_data": AssetIn("int_partitioned_workforce_data")},
    description="Process SCD workforce state using optimized dbt snapshot"
)
def scd_workforce_state_processed(
    context: AssetExecutionContext,
    duckdb: DuckDBResource,
    dbt: DbtResource,
    workforce_data: pd.DataFrame
) -> Dict[str, Any]:
    """Process SCD workforce state using dbt snapshot for optimal performance"""

    # Initialize performance monitoring
    monitor = SCDPerformanceMonitor(context, duckdb)
    monitor.start_monitoring()

    try:
        # Phase 1: Optimize DuckDB settings for SCD processing
        context.log.info("Optimizing DuckDB settings for SCD processing")
        monitor.start_phase("optimize_database")

        with duckdb.get_connection() as conn:
            # Apply performance optimizations
            optimization_queries = [
                "SET threads = 16",  # Use all available cores
                "SET memory_limit = '32GB'",  # Increase memory limit
                "SET enable_parallel_join = true",
                "SET enable_parallel_sort = true",
                "SET enable_parallel_aggregate = true",
                "SET enable_optimizer = true",
                "SET preserve_insertion_order = false",  # Allow reordering for performance
                "SET checkpoint_threshold = '1GB'",  # Reduce checkpoint frequency
                "SET wal_autocheckpoint = 10000",  # Optimize WAL checkpointing
                "SET enable_object_cache = true"  # Enable object caching
            ]

            for query in optimization_queries:
                try:
                    conn.execute(query)
                except Exception as e:
                    context.log.warning(f"Failed to set optimization: {query}, Error: {e}")

        monitor.record_phase_completion("optimize_database", 1)

        # Phase 2: Run change detection
        context.log.info("Running change detection analysis")
        monitor.start_phase("change_detection")

        change_results = dbt.run(["int_workforce_changes"], full_refresh=False)
        if not change_results.success:
            raise Exception(f"Change detection failed: {change_results.results}")

        # Get change statistics
        with duckdb.get_connection() as conn:
            change_stats = conn.execute("""
                SELECT
                    change_type,
                    COUNT(*) as count
                FROM int_workforce_changes
                GROUP BY change_type
            """).df()

            total_changes = change_stats['count'].sum()

            context.log.info(f"Change detection completed: {total_changes} records to process")
            for _, row in change_stats.iterrows():
                context.log.info(f"  - {row['change_type']}: {row['count']} records")

        monitor.record_phase_completion("change_detection", total_changes)

        # Phase 3: Run optimized snapshot (only if changes detected)
        if total_changes > 0:
            context.log.info("Running optimized SCD snapshot processing")
            monitor.start_phase("scd_snapshot")

            snapshot_results = dbt.run(["snapshot:scd_workforce_state_optimized"], full_refresh=False)
            if not snapshot_results.success:
                raise Exception(f"SCD snapshot failed: {snapshot_results.results}")

            monitor.record_phase_completion("scd_snapshot", total_changes)
        else:
            context.log.info("No changes detected, skipping snapshot processing")

        # Phase 4: Data quality validation
        context.log.info("Performing data quality validation")
        monitor.start_phase("data_quality_validation")

        with duckdb.get_connection() as conn:
            # Check for SCD integrity violations
            integrity_check = conn.execute("""
                SELECT
                    employee_id,
                    COUNT(*) as current_record_count
                FROM scd_workforce_state_optimized
                WHERE dbt_valid_to IS NULL
                GROUP BY employee_id
                HAVING COUNT(*) > 1
            """).df()

            if len(integrity_check) > 0:
                context.log.error(f"SCD integrity violation: {len(integrity_check)} employees have multiple current records")
                raise Exception("SCD integrity check failed")

            # Get processing metrics
            processing_metrics = conn.execute("""
                SELECT
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN dbt_valid_to IS NULL THEN 1 END) as current_records,
                    COUNT(DISTINCT employee_id) as unique_employees,
                    MAX(dbt_updated_at) as last_updated
                FROM scd_workforce_state_optimized
            """).fetchone()

        monitor.record_phase_completion("data_quality_validation", processing_metrics[0])

        # Phase 5: Create optimized indexes
        context.log.info("Creating optimized indexes")
        monitor.start_phase("index_creation")

        with duckdb.get_connection() as conn:
            index_queries = [
                "CREATE INDEX IF NOT EXISTS idx_scd_employee_id ON scd_workforce_state_optimized (employee_id)",
                "CREATE INDEX IF NOT EXISTS idx_scd_valid_from ON scd_workforce_state_optimized (dbt_valid_from)",
                "CREATE INDEX IF NOT EXISTS idx_scd_valid_to ON scd_workforce_state_optimized (dbt_valid_to)",
                "CREATE INDEX IF NOT EXISTS idx_scd_current_records ON scd_workforce_state_optimized (employee_id, dbt_valid_to) WHERE dbt_valid_to IS NULL",
                "CREATE INDEX IF NOT EXISTS idx_scd_composite ON scd_workforce_state_optimized (employee_id, dbt_valid_from, dbt_valid_to)",
                "CREATE INDEX IF NOT EXISTS idx_scd_hash ON scd_workforce_state_optimized (change_hash)",
                "ANALYZE scd_workforce_state_optimized"
            ]

            for query in index_queries:
                try:
                    conn.execute(query)
                except Exception as e:
                    context.log.warning(f"Index creation failed: {query}, Error: {e}")

        monitor.record_phase_completion("index_creation", 1)

        # Check SLA compliance
        monitor.check_sla_compliance(sla_threshold_seconds=120)

        performance_summary = monitor.get_performance_summary()

        context.log.info(
            f"SCD processing completed successfully: {processing_metrics[0]} total records, "
            f"{processing_metrics[1]} current records in {performance_summary['total_duration']:.2f}s"
        )

        return {
            "total_records": processing_metrics[0],
            "current_records": processing_metrics[1],
            "unique_employees": processing_metrics[2],
            "last_updated": processing_metrics[3],
            "processing_time": performance_summary['total_duration'],
            "sla_compliant": performance_summary['sla_compliant'],
            "records_processed": performance_summary['records_processed'],
            "avg_throughput": performance_summary['avg_throughput'],
            "phase_metrics": performance_summary['phase_metrics']
        }

    except Exception as e:
        monitor.check_sla_compliance(sla_threshold_seconds=120)
        context.log.error(f"SCD processing failed: {e}")
        raise e

@asset(
    deps=["scd_workforce_state_processed"],
    description="Export optimized SCD data to Parquet"
)
def scd_workforce_state_exported(
    context: AssetExecutionContext,
    duckdb: DuckDBResource
) -> str:
    """Export SCD data to partitioned Parquet for downstream consumption"""

    output_path = context.run.run_config.get("scd_output_path", "data/scd_workforce_state")

    with duckdb.get_connection() as conn:
        # Export to partitioned Parquet using COPY
        export_query = f"""
            COPY (
                SELECT
                    employee_id,
                    employee_ssn,
                    employee_birth_date,
                    employee_hire_date,
                    current_compensation,
                    prorated_annual_compensation,
                    full_year_equivalent_compensation,
                    current_age,
                    current_tenure,
                    level_id,
                    age_band,
                    tenure_band,
                    employment_status,
                    termination_date,
                    termination_reason,
                    detailed_status_code,
                    simulation_year,
                    dbt_valid_from,
                    dbt_valid_to,
                    dbt_scd_id,
                    dbt_updated_at,
                    change_hash
                FROM scd_workforce_state_optimized
                WHERE dbt_valid_to IS NULL OR dbt_valid_to > CURRENT_DATE - INTERVAL '2 years'
            ) TO '{output_path}'
            (FORMAT PARQUET, PARTITION_BY simulation_year, COMPRESSION GZIP, OVERWRITE_OR_IGNORE true)
        """

        try:
            conn.execute(export_query)
        except Exception as e:
            context.log.warning(f"Export failed, trying alternative method: {e}")
            # Alternative export method without partitioning
            conn.execute(f"""
                COPY (
                    SELECT * FROM scd_workforce_state_optimized
                    WHERE dbt_valid_to IS NULL OR dbt_valid_to > CURRENT_DATE - INTERVAL '2 years'
                ) TO '{output_path}/scd_workforce_state.parquet'
                (FORMAT PARQUET, COMPRESSION GZIP, OVERWRITE_OR_IGNORE true)
            """)

        # Verify export
        try:
            file_count = conn.execute(f"""
                SELECT COUNT(*) FROM glob('{output_path}/**/*.parquet')
            """).fetchone()[0]
        except:
            file_count = 1  # Fallback for single file export

        context.log.info(f"Exported SCD data to {output_path}: {file_count} Parquet files")

        return output_path

@asset(
    deps=["scd_workforce_state_exported"],
    description="Generate SCD performance report"
)
def scd_performance_report(
    context: AssetExecutionContext,
    duckdb: DuckDBResource
) -> Dict[str, Any]:
    """Generate comprehensive SCD performance report"""

    with duckdb.get_connection() as conn:
        # Get latest performance metrics
        try:
            performance_data = conn.execute("""
                SELECT
                    component_name,
                    execution_time_seconds,
                    total_records_processed,
                    performance_category,
                    metric_timestamp
                FROM mon_performance_metrics
                WHERE component_name = 'scd_workforce_state'
                ORDER BY metric_timestamp DESC
                LIMIT 1
            """).fetchone()
        except:
            performance_data = None

        # Get SLA breach history
        try:
            sla_breaches = conn.execute("""
                SELECT
                    COUNT(*) as breach_count,
                    AVG(actual_duration_seconds) as avg_breach_duration,
                    MAX(actual_duration_seconds) as max_breach_duration
                FROM mon_sla_breaches
                WHERE component_name = 'scd_workforce_state'
                    AND breach_timestamp >= CURRENT_DATE - INTERVAL '30 days'
            """).fetchone()
        except:
            sla_breaches = (0, 0, 0)

        # Get phase performance breakdown
        try:
            phase_performance = conn.execute("""
                SELECT
                    phase_name,
                    AVG(duration_seconds) as avg_duration,
                    AVG(records_per_second) as avg_throughput,
                    COUNT(*) as execution_count
                FROM mon_scd_phase_metrics
                WHERE metric_timestamp >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY phase_name
                ORDER BY avg_duration DESC
            """).df()
        except:
            phase_performance = pd.DataFrame()

        report = {
            "report_timestamp": datetime.now().isoformat(),
            "latest_performance": {
                "execution_time": performance_data[1] if performance_data else 0,
                "records_processed": performance_data[2] if performance_data else 0,
                "performance_category": performance_data[3] if performance_data else "UNKNOWN",
                "last_run": performance_data[4] if performance_data else None
            },
            "sla_compliance": {
                "breach_count_30_days": sla_breaches[0],
                "avg_breach_duration": sla_breaches[1],
                "max_breach_duration": sla_breaches[2],
                "sla_target": 120
            },
            "phase_performance": phase_performance.to_dict('records') if not phase_performance.empty else [],
            "recommendations": []
        }

        # Add performance recommendations
        if performance_data and performance_data[1] > 120:
            report["recommendations"].append("Consider increasing DuckDB memory limit or thread count")

        if sla_breaches[0] > 5:
            report["recommendations"].append("Frequent SLA breaches detected - review indexing strategy")

        if not phase_performance.empty:
            slowest_phase = phase_performance.iloc[0]
            if slowest_phase['avg_duration'] > 60:
                report["recommendations"].append(f"Phase '{slowest_phase['phase_name']}' is the bottleneck - investigate further")

        context.log.info(f"SCD performance report generated: {report['latest_performance']['performance_category']} performance")

        return report
