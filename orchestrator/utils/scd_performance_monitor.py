from typing import Dict, Any, Optional
import time
from datetime import datetime, timedelta
from dagster import AssetExecutionContext
from orchestrator.resources import DuckDBResource

class SCDPerformanceMonitor:
    """Monitor SCD processing performance with SLA tracking and integrity checks"""

    def __init__(self, context: AssetExecutionContext, duckdb: DuckDBResource):
        self.context = context
        self.duckdb = duckdb
        self.start_time = None
        self.metrics = {}
        self.phase_start_times = {}

    def start_monitoring(self):
        """Start performance monitoring"""
        self.start_time = time.time()
        self.context.log.info("Starting SCD performance monitoring")

    def record_phase_completion(self, phase_name: str, record_count: int):
        """Record completion of SCD processing phase with enhanced metrics"""
        if self.start_time is None:
            return

        current_time = time.time()
        phase_duration = current_time - self.phase_start_times.get(phase_name, current_time)
        total_duration = current_time - self.start_time

        self.metrics[phase_name] = {
            "duration_seconds": phase_duration,
            "record_count": record_count,
            "records_per_second": record_count / phase_duration if phase_duration > 0 else 0,
            "total_duration_seconds": total_duration
        }

        self.context.log.info(
            f"SCD Phase '{phase_name}' completed: "
            f"{record_count} records in {phase_duration:.2f}s "
            f"({self.metrics[phase_name]['records_per_second']:.0f} records/sec)"
        )

        # Record detailed metrics
        self._record_detailed_metrics(phase_name, record_count, phase_duration)

    def start_phase(self, phase_name: str):
        """Start timing a specific phase"""
        self.phase_start_times[phase_name] = time.time()

    def get_total_duration(self) -> float:
        """Get total processing duration"""
        if self.start_time is None:
            return 0
        return time.time() - self.start_time

    def check_scd_integrity(self) -> Dict[str, Any]:
        """Check SCD Type 2 integrity and data quality"""
        integrity_results = {
            "multiple_current_records": 0,
            "orphaned_records": 0,
            "overlapping_periods": 0,
            "null_key_violations": 0,
            "change_data_capture_anomalies": 0
        }

        try:
            with self.duckdb.get_connection() as conn:
                # Check for multiple current records per employee
                multiple_current = conn.execute("""
                    SELECT COUNT(*)
                    FROM (
                        SELECT employee_id
                        FROM scd_workforce_state_optimized
                        WHERE dbt_valid_to IS NULL
                        GROUP BY employee_id
                        HAVING COUNT(*) > 1
                    )
                """).fetchone()[0]
                integrity_results["multiple_current_records"] = multiple_current

                # Check for NULL key violations
                null_keys = conn.execute("""
                    SELECT COUNT(*)
                    FROM scd_workforce_state_optimized
                    WHERE employee_id IS NULL OR dbt_valid_from IS NULL
                """).fetchone()[0]
                integrity_results["null_key_violations"] = null_keys

                # Check for overlapping periods
                overlapping = conn.execute("""
                    SELECT COUNT(*)
                    FROM scd_workforce_state_optimized s1
                    JOIN scd_workforce_state_optimized s2 ON s1.employee_id = s2.employee_id
                    WHERE s1.dbt_scd_id != s2.dbt_scd_id
                      AND s1.dbt_valid_from < COALESCE(s2.dbt_valid_to, '9999-12-31')
                      AND COALESCE(s1.dbt_valid_to, '9999-12-31') > s2.dbt_valid_from
                """).fetchone()[0]
                integrity_results["overlapping_periods"] = overlapping

                # Check for change data capture anomalies
                change_anomalies = conn.execute("""
                    SELECT COUNT(*)
                    FROM (
                        SELECT employee_id, COUNT(*) as change_count
                        FROM scd_workforce_state_optimized
                        WHERE dbt_valid_from >= CURRENT_DATE - INTERVAL '1 day'
                        GROUP BY employee_id
                        HAVING COUNT(*) > 10  -- More than 10 changes in one day is suspicious
                    )
                """).fetchone()[0]
                integrity_results["change_data_capture_anomalies"] = change_anomalies

        except Exception as e:
            self.context.log.warning(f"Integrity check failed: {e}")
            return integrity_results

        # Log integrity check results
        total_violations = sum(integrity_results.values())
        if total_violations > 0:
            self.context.log.warning(f"SCD integrity violations found: {integrity_results}")
        else:
            self.context.log.info("SCD integrity check passed")

        return integrity_results

    def check_sla_compliance(self, sla_threshold_seconds: int = 120):
        """Check SLA compliance and alert if exceeded"""
        if self.start_time is None:
            return

        total_duration = time.time() - self.start_time

        if total_duration > sla_threshold_seconds:
            self.context.log.warning(
                f"SCD processing exceeded SLA: {total_duration:.2f}s > {sla_threshold_seconds}s"
            )

            # Record SLA breach
            self._record_sla_breach(total_duration, sla_threshold_seconds)

        # Record performance metrics
        self._record_performance_metrics(total_duration)

        # Check integrity
        integrity_results = self.check_scd_integrity()

        # Alert on integrity violations
        if sum(integrity_results.values()) > 0:
            self.context.log.error("SCD integrity violations detected - review required")

    def _record_detailed_metrics(self, phase_name: str, record_count: int, duration: float):
        """Record detailed phase metrics"""
        try:
            with self.duckdb.get_connection() as conn:
                # Create monitoring table if it doesn't exist
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS mon_scd_phase_metrics (
                        phase_name VARCHAR,
                        metric_timestamp TIMESTAMP,
                        duration_seconds DOUBLE,
                        record_count INTEGER,
                        records_per_second DOUBLE,
                        simulation_year INTEGER
                    )
                """)

                conn.execute("""
                    INSERT INTO mon_scd_phase_metrics (
                        phase_name,
                        metric_timestamp,
                        duration_seconds,
                        record_count,
                        records_per_second,
                        simulation_year
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, [
                    phase_name,
                    datetime.now(),
                    duration,
                    record_count,
                    record_count / duration if duration > 0 else 0,
                    self.context.run.run_config.get("simulation_year", 2025)
                ])
        except Exception as e:
            self.context.log.warning(f"Failed to record detailed metrics: {e}")

    def _record_sla_breach(self, actual_duration: float, sla_threshold: int):
        """Record SLA breach in monitoring table"""
        try:
            with self.duckdb.get_connection() as conn:
                # Create monitoring table if it doesn't exist
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS mon_sla_breaches (
                        component_name VARCHAR,
                        breach_timestamp TIMESTAMP,
                        actual_duration_seconds DOUBLE,
                        sla_threshold_seconds INTEGER,
                        breach_severity VARCHAR
                    )
                """)

                conn.execute("""
                    INSERT INTO mon_sla_breaches (
                        component_name,
                        breach_timestamp,
                        actual_duration_seconds,
                        sla_threshold_seconds,
                        breach_severity
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, [
                    "scd_workforce_state",
                    datetime.now(),
                    actual_duration,
                    sla_threshold,
                    "HIGH" if actual_duration > sla_threshold * 2 else "MEDIUM"
                ])
        except Exception as e:
            self.context.log.warning(f"Failed to record SLA breach: {e}")

    def _record_performance_metrics(self, total_duration: float):
        """Record performance metrics for trending"""
        try:
            with self.duckdb.get_connection() as conn:
                # Create monitoring table if it doesn't exist
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS mon_performance_metrics (
                        component_name VARCHAR,
                        metric_timestamp TIMESTAMP,
                        execution_time_seconds DOUBLE,
                        total_records_processed INTEGER,
                        performance_category VARCHAR
                    )
                """)

                conn.execute("""
                    INSERT INTO mon_performance_metrics (
                        component_name,
                        metric_timestamp,
                        execution_time_seconds,
                        total_records_processed,
                        performance_category
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, [
                    "scd_workforce_state",
                    datetime.now(),
                    total_duration,
                    sum(m["record_count"] for m in self.metrics.values()),
                    "EXCELLENT" if total_duration < 60 else "GOOD" if total_duration < 120 else "POOR"
                ])
        except Exception as e:
            self.context.log.warning(f"Failed to record performance metrics: {e}")

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        return {
            "total_duration": self.get_total_duration(),
            "phase_metrics": self.metrics,
            "sla_compliant": self.get_total_duration() < 120,
            "records_processed": sum(m["record_count"] for m in self.metrics.values()),
            "avg_throughput": sum(m["records_per_second"] for m in self.metrics.values()) / len(self.metrics) if self.metrics else 0
        }
