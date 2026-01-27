"""
DuckDB-specific performance monitoring for PlanAlign Engine.

Provides comprehensive performance monitoring for DuckDB operations
with stage-by-stage checkpoints and optimization recommendations.

Epic E068E: Engine & I/O Tuning - DuckDB Performance Monitoring
Target: 15-25% performance improvement through monitoring and optimization.
"""

import json
import logging
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from .data_models import (
    PerformanceCheckpoint,
    PerformanceLevel,
    PerformanceOptimization,
)
from .recommendations import generate_optimization_recommendations


class DuckDBPerformanceMonitor:
    """
    Comprehensive performance monitoring for DuckDB operations in Navigator Orchestrator.

    Epic E068E: Engine & I/O Tuning implementation

    Features:
    - Real-time memory, CPU, and I/O tracking during pipeline execution
    - Stage-by-stage performance checkpoints with detailed metrics
    - Performance optimization recommendations based on collected data
    - Comprehensive performance reports with trend analysis
    - Integration hooks for PipelineOrchestrator workflow stages
    - Target: 15-25% performance improvement through monitoring insights
    """

    def __init__(
        self,
        database_path: Path,
        logger: Optional[logging.Logger] = None,
        reports_dir: Path = Path("reports/performance"),
    ):
        """
        Initialize DuckDB performance monitor

        Args:
            database_path: Path to DuckDB simulation database
            logger: Optional logger instance
            reports_dir: Directory for performance reports
        """
        self.database_path = Path(database_path)
        self.logger = logger or logging.getLogger(__name__)
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Performance tracking state
        self.monitoring_active = False
        self.start_time: Optional[float] = None
        self.checkpoints: List[PerformanceCheckpoint] = []
        self.initial_metrics: Optional[Dict[str, Any]] = None

        # Performance thresholds (E068E targets)
        self.thresholds = {
            "memory_warning_gb": 32.0,  # Warn above 32GB memory usage
            "memory_critical_gb": 48.0,  # Critical above 48GB (target: stable <10GB, peak <40GB)
            "cpu_warning_percent": 85.0,  # Warn above 85% CPU usage
            "cpu_critical_percent": 95.0,  # Critical above 95% CPU
            "cpu_target_percent": 80.0,  # Target: >80% utilization during compute stages
            "io_warning_rate_mbps": 500,  # Warn above 500MB/s sustained I/O
            "execution_time_warning_s": 300,  # Warn if stage >5 minutes
            "stage_time_target_s": 30,  # Target: complex joins <30s per stage
            "database_growth_warning_gb": 5.0,  # Warn if DB grows >5GB per stage
            "database_growth_target_gb": 1.0,  # Target: <1GB growth per simulation year
        }

    def start_monitoring(self) -> None:
        """Initialize performance monitoring and capture baseline metrics"""
        try:
            self.start_time = time.time()
            self.monitoring_active = True
            self.checkpoints.clear()

            # Capture initial system state
            self.initial_metrics = self._capture_system_metrics()

            self.logger.info("DuckDB performance monitoring started (E068E)")
            self.logger.info(
                f"Initial memory: {self.initial_metrics['memory_gb']:.1f}GB "
                f"({self.initial_metrics['memory_percent']:.1f}%)"
            )
            self.logger.info(
                f"Initial database size: {self.initial_metrics['database_gb']:.2f}GB"
            )
            self.logger.info(
                f"CPU cores: {self.initial_metrics['cpu_count']}, "
                f"System RAM: {psutil.virtual_memory().total / (1024**3):.1f}GB"
            )

        except Exception as e:
            self.logger.error(f"Failed to start DuckDB performance monitoring: {e}")
            self.monitoring_active = False

    def record_checkpoint(self, stage_name: str) -> PerformanceCheckpoint:
        """Record performance metrics at a workflow stage checkpoint"""
        if not self.monitoring_active:
            self.logger.warning(
                "Performance monitoring not active. Starting monitoring now."
            )
            self.start_monitoring()

        try:
            current_time = time.time()
            elapsed_time = current_time - self.start_time if self.start_time else 0

            # Capture current system metrics
            metrics = self._capture_system_metrics()

            # Create checkpoint
            checkpoint = PerformanceCheckpoint(
                stage_name=stage_name,
                timestamp=current_time,
                elapsed_time=elapsed_time,
                memory_usage_gb=metrics["memory_gb"],
                memory_percent=metrics["memory_percent"],
                memory_available_gb=metrics["memory_available_gb"],
                disk_usage_gb=metrics["disk_gb"],
                database_size_gb=metrics["database_gb"],
                cpu_percent=metrics["cpu_percent"],
                cpu_count=metrics["cpu_count"],
                io_read_bytes=metrics["io_read_bytes"],
                io_write_bytes=metrics["io_write_bytes"],
                io_read_count=metrics["io_read_count"],
                io_write_count=metrics["io_write_count"],
                thread_count=metrics["thread_count"],
            )

            self.checkpoints.append(checkpoint)

            # Log checkpoint with key metrics
            self.logger.info(f"Performance checkpoint - {stage_name}:")
            self.logger.info(f"  Time: {elapsed_time:.1f}s elapsed")
            self.logger.info(
                f"  Memory: {checkpoint.memory_usage_gb:.1f}GB "
                f"({checkpoint.memory_percent:.1f}%)"
            )
            self.logger.info(f"  Database: {checkpoint.database_size_gb:.2f}GB")
            self.logger.info(f"  CPU: {checkpoint.cpu_percent:.1f}%")

            # Calculate stage duration for performance assessment
            if len(self.checkpoints) > 1:
                prev_checkpoint = self.checkpoints[-2]
                stage_duration = checkpoint.elapsed_time - prev_checkpoint.elapsed_time
                self.logger.info(f"  Stage duration: {stage_duration:.1f}s")

            # Check for immediate performance issues
            self._check_performance_alerts(checkpoint)

            return checkpoint

        except Exception as e:
            self.logger.error(f"Failed to record checkpoint for {stage_name}: {e}")
            # Return minimal checkpoint to prevent pipeline failures
            return PerformanceCheckpoint(
                stage_name=stage_name,
                timestamp=time.time(),
                elapsed_time=0,
                memory_usage_gb=0,
                memory_percent=0,
                memory_available_gb=0,
                disk_usage_gb=0,
                database_size_gb=0,
                cpu_percent=0,
                cpu_count=1,
                io_read_bytes=0,
                io_write_bytes=0,
                io_read_count=0,
                io_write_count=0,
                thread_count=1,
            )

    def stop_monitoring(self) -> None:
        """Stop performance monitoring and finalize metrics collection"""
        if self.monitoring_active:
            self.monitoring_active = False
            total_time = time.time() - self.start_time if self.start_time else 0
            self.logger.info(
                f"DuckDB performance monitoring stopped after {total_time:.1f}s"
            )

    def get_performance_statistics(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics from all checkpoints"""
        if not self.checkpoints:
            return {"error": "No performance checkpoints recorded"}

        # Calculate comprehensive statistics
        memory_values = [c.memory_usage_gb for c in self.checkpoints]
        cpu_values = [c.cpu_percent for c in self.checkpoints]
        db_sizes = [c.database_size_gb for c in self.checkpoints]

        stats = {
            "summary": {
                "total_checkpoints": len(self.checkpoints),
                "total_execution_time": self.checkpoints[-1].elapsed_time,
                "peak_memory_gb": max(memory_values),
                "avg_memory_gb": sum(memory_values) / len(memory_values),
                "min_memory_gb": min(memory_values),
                "peak_cpu_percent": max(cpu_values),
                "avg_cpu_percent": sum(cpu_values) / len(cpu_values),
                "min_cpu_percent": min(cpu_values),
                "final_database_size_gb": db_sizes[-1],
                "database_growth_gb": db_sizes[-1] - db_sizes[0]
                if len(db_sizes) > 1
                else 0,
                "system_memory_gb": psutil.virtual_memory().total / (1024**3),
                "cpu_cores": self.checkpoints[0].cpu_count if self.checkpoints else 0,
            },
            "stages": [
                {
                    "stage": c.stage_name,
                    "elapsed_time": c.elapsed_time,
                    "memory_gb": c.memory_usage_gb,
                    "cpu_percent": c.cpu_percent,
                    "database_size_gb": c.database_size_gb,
                    "io_read_mb": c.io_read_bytes / (1024**2),
                    "io_write_mb": c.io_write_bytes / (1024**2),
                }
                for c in self.checkpoints
            ],
            "performance_level": self._assess_overall_performance(),
            "e068e_targets": self._assess_e068e_targets(),
        }

        return stats

    def generate_report(self) -> str:
        """Generate comprehensive performance optimization report for E068E"""
        if not self.checkpoints:
            return "No performance data available. Run start_monitoring() and record_checkpoint() first."

        stats = self.get_performance_statistics()
        optimizations = self._generate_optimization_recommendations()

        report_lines = [
            "DuckDB Performance Analysis Report (E068E)",
            "=" * 55,
            f"Generated: {datetime.now().isoformat()}",
            f"Database: {self.database_path}",
            f"Target: 15-25% performance improvement",
            "",
            "EXECUTIVE SUMMARY",
            "-" * 20,
            f"Total execution time: {stats['summary']['total_execution_time']:.1f} seconds",
            f"Peak memory usage: {stats['summary']['peak_memory_gb']:.1f}GB "
            f"(Target: <40GB peak, <10GB typical)",
            f"Average CPU utilization: {stats['summary']['avg_cpu_percent']:.1f}% "
            f"(Target: >80% during compute)",
            f"Database growth: {stats['summary']['database_growth_gb']:.2f}GB "
            f"(Target: <1GB per simulation year)",
            f"Overall performance: {stats['performance_level'].value.upper()}",
            "",
            "E068E TARGET ASSESSMENT",
            "-" * 25,
        ]

        # Add E068E target assessment
        report_lines.append(stats["e068e_targets"])

        report_lines.extend(["", "STAGE BREAKDOWN", "-" * 15])

        # Add detailed stage-by-stage analysis
        prev_time = 0
        for i, stage_data in enumerate(stats["stages"]):
            stage_duration = stage_data["elapsed_time"] - prev_time

            # Calculate I/O rate for this stage
            if i > 0:
                prev_stage = stats["stages"][i - 1]
                io_delta_mb = (
                    stage_data["io_read_mb"]
                    + stage_data["io_write_mb"]
                    - prev_stage["io_read_mb"]
                    - prev_stage["io_write_mb"]
                )
                io_rate_mbps = io_delta_mb / stage_duration if stage_duration > 0 else 0
                io_info = f", I/O: {io_rate_mbps:.0f}MB/s"
            else:
                io_info = ""

            # Performance indicators
            perf_indicators = []
            if stage_duration > self.thresholds["stage_time_target_s"]:
                perf_indicators.append("SLOW")
            if stage_data["memory_gb"] > self.thresholds["memory_warning_gb"]:
                perf_indicators.append("HIGH-MEM")
            if stage_data["cpu_percent"] < self.thresholds["cpu_target_percent"]:
                perf_indicators.append("LOW-CPU")

            indicator_str = (
                f" [{', '.join(perf_indicators)}]" if perf_indicators else ""
            )

            report_lines.append(
                f"{stage_data['stage']}: {stage_duration:.1f}s "
                f"(Memory: {stage_data['memory_gb']:.1f}GB, "
                f"CPU: {stage_data['cpu_percent']:.1f}%, "
                f"DB: {stage_data['database_size_gb']:.2f}GB{io_info}){indicator_str}"
            )
            prev_time = stage_data["elapsed_time"]

        # Add optimization recommendations
        if optimizations:
            report_lines.extend(["", "OPTIMIZATION RECOMMENDATIONS", "-" * 30])

            # Group by priority
            high_priority = [o for o in optimizations if o.priority <= 2]
            medium_priority = [o for o in optimizations if o.priority == 3]
            low_priority = [o for o in optimizations if o.priority >= 4]

            if high_priority:
                report_lines.append("\n🔴 HIGH PRIORITY:")
                for opt in high_priority:
                    report_lines.extend(
                        [
                            f"• {opt.category}: {opt.description}",
                            f"  → {opt.recommendation}",
                            f"  💡 {opt.potential_improvement}",
                            "",
                        ]
                    )

            if medium_priority:
                report_lines.append("🟡 MEDIUM PRIORITY:")
                for opt in medium_priority:
                    report_lines.extend(
                        [
                            f"• {opt.category}: {opt.description}",
                            f"  → {opt.recommendation}",
                            "",
                        ]
                    )

            if low_priority:
                report_lines.append("🟢 LOW PRIORITY:")
                for opt in low_priority:
                    report_lines.append(f"• {opt.category}: {opt.recommendation}")

        # System information
        report_lines.extend(
            [
                "",
                "SYSTEM INFORMATION",
                "-" * 18,
                f"CPU cores: {stats['summary']['cpu_cores']}",
                f"System memory: {stats['summary']['system_memory_gb']:.1f}GB",
                f"Database location: {self.database_path}",
                "",
            ]
        )

        return "\n".join(report_lines)

    def export_performance_data(self, filename: Optional[str] = None) -> Path:
        """Export detailed performance data to JSON for analysis"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"duckdb_performance_{timestamp}.json"

        export_path = self.reports_dir / filename

        # Prepare statistics and ensure JSON-serializable values
        stats = self.get_performance_statistics()
        if isinstance(stats.get("performance_level"), Enum):
            stats["performance_level"] = stats["performance_level"].value

        export_data = {
            "metadata": {
                "epic": "E068E",
                "target": "15-25% performance improvement",
                "database_path": str(self.database_path),
                "monitoring_start": self.start_time,
                "export_timestamp": datetime.now().isoformat(),
                "total_checkpoints": len(self.checkpoints),
            },
            "thresholds": self.thresholds,
            "initial_metrics": self.initial_metrics,
            "checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints],
            "statistics": stats,
            "optimizations": [
                {
                    "category": opt.category,
                    "severity": opt.severity,
                    "description": opt.description,
                    "recommendation": opt.recommendation,
                    "potential_improvement": opt.potential_improvement,
                    "priority": opt.priority,
                }
                for opt in self._generate_optimization_recommendations()
            ],
        }

        with open(export_path, "w") as f:
            json.dump(export_data, f, indent=2)

        self.logger.info(f"DuckDB performance data exported to {export_path}")
        return export_path

    def _capture_system_metrics(self) -> Dict[str, Any]:
        """Capture current system performance metrics"""
        try:
            # Memory metrics
            memory = psutil.virtual_memory()

            # Disk and database metrics
            disk_usage = self._get_disk_usage()
            database_size = self._get_database_size()

            # CPU metrics with 1-second sample for accuracy
            cpu_percent = psutil.cpu_percent(interval=1.0)
            cpu_count = psutil.cpu_count()

            # I/O metrics
            io_stats = psutil.disk_io_counters()

            # Process/thread count
            try:
                thread_count = len(psutil.Process().threads())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                thread_count = 1

            return {
                "memory_gb": memory.used / (1024**3),
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
                "disk_gb": disk_usage / (1024**3),
                "database_gb": database_size / (1024**3),
                "cpu_percent": cpu_percent,
                "cpu_count": cpu_count,
                "io_read_bytes": io_stats.read_bytes if io_stats else 0,
                "io_write_bytes": io_stats.write_bytes if io_stats else 0,
                "io_read_count": io_stats.read_count if io_stats else 0,
                "io_write_count": io_stats.write_count if io_stats else 0,
                "thread_count": thread_count,
            }
        except Exception as e:
            self.logger.error(f"Error capturing system metrics: {e}")
            return {
                "memory_gb": 0,
                "memory_percent": 0,
                "memory_available_gb": 0,
                "disk_gb": 0,
                "database_gb": 0,
                "cpu_percent": 0,
                "cpu_count": 1,
                "io_read_bytes": 0,
                "io_write_bytes": 0,
                "io_read_count": 0,
                "io_write_count": 0,
                "thread_count": 1,
            }

    def _get_disk_usage(self) -> int:
        """Get disk usage for database directory"""
        try:
            return sum(
                f.stat().st_size
                for f in self.database_path.parent.rglob("*")
                if f.is_file()
            )
        except Exception:
            return 0

    def _get_database_size(self) -> int:
        """Get current database file size"""
        try:
            return self.database_path.stat().st_size if self.database_path.exists() else 0
        except Exception:
            return 0

    def _check_performance_alerts(self, checkpoint: PerformanceCheckpoint) -> None:
        """Check checkpoint against thresholds and log performance alerts"""
        alerts = []

        # Memory alerts
        if checkpoint.memory_usage_gb > self.thresholds["memory_critical_gb"]:
            alerts.append(
                f"CRITICAL: Memory usage {checkpoint.memory_usage_gb:.1f}GB exceeds critical threshold ({self.thresholds['memory_critical_gb']}GB)"
            )
        elif checkpoint.memory_usage_gb > self.thresholds["memory_warning_gb"]:
            alerts.append(
                f"WARNING: Memory usage {checkpoint.memory_usage_gb:.1f}GB exceeds warning threshold ({self.thresholds['memory_warning_gb']}GB)"
            )

        # CPU alerts
        if checkpoint.cpu_percent > self.thresholds["cpu_critical_percent"]:
            alerts.append(
                f"CRITICAL: CPU usage {checkpoint.cpu_percent:.1f}% exceeds critical threshold ({self.thresholds['cpu_critical_percent']}%)"
            )
        elif checkpoint.cpu_percent > self.thresholds["cpu_warning_percent"]:
            alerts.append(
                f"WARNING: CPU usage {checkpoint.cpu_percent:.1f}% exceeds warning threshold ({self.thresholds['cpu_warning_percent']}%)"
            )
        elif checkpoint.cpu_percent < (
            self.thresholds["cpu_target_percent"] - 20
        ):  # 60% threshold for underutilization
            alerts.append(
                f"INFO: CPU usage {checkpoint.cpu_percent:.1f}% is low, consider increasing parallelization"
            )

        # Stage duration alerts
        if len(self.checkpoints) > 1:
            prev_checkpoint = self.checkpoints[-2]
            stage_duration = checkpoint.elapsed_time - prev_checkpoint.elapsed_time
            if stage_duration > self.thresholds["execution_time_warning_s"]:
                alerts.append(
                    f"WARNING: Stage {checkpoint.stage_name} took {stage_duration:.1f}s (exceeds {self.thresholds['execution_time_warning_s']}s threshold)"
                )
            elif stage_duration > self.thresholds["stage_time_target_s"]:
                alerts.append(
                    f"INFO: Stage {checkpoint.stage_name} took {stage_duration:.1f}s (target: <{self.thresholds['stage_time_target_s']}s)"
                )

        # Database growth alerts
        if len(self.checkpoints) > 1:
            prev_checkpoint = self.checkpoints[-2]
            db_growth = checkpoint.database_size_gb - prev_checkpoint.database_size_gb
            if db_growth > self.thresholds["database_growth_warning_gb"]:
                alerts.append(
                    f"WARNING: Database grew by {db_growth:.2f}GB in stage {checkpoint.stage_name} (exceeds {self.thresholds['database_growth_warning_gb']}GB threshold)"
                )

        # Log all alerts with appropriate levels
        for alert in alerts:
            if "CRITICAL" in alert:
                self.logger.error(alert)
            elif "WARNING" in alert:
                self.logger.warning(alert)
            else:
                self.logger.info(alert)

    def _assess_overall_performance(self) -> PerformanceLevel:
        """Assess overall performance level based on E068E targets"""
        if not self.checkpoints:
            return PerformanceLevel.CRITICAL

        # Calculate basic statistics directly to avoid circular dependency
        memory_values = [c.memory_usage_gb for c in self.checkpoints]
        cpu_values = [c.cpu_percent for c in self.checkpoints]
        db_sizes = [c.database_size_gb for c in self.checkpoints]

        stats = {
            "total_execution_time": self.checkpoints[-1].elapsed_time,
            "peak_memory_gb": max(memory_values),
            "avg_cpu_percent": sum(cpu_values) / len(cpu_values),
            "database_growth_gb": db_sizes[-1] - db_sizes[0]
            if len(db_sizes) > 1
            else 0,
        }

        # E068E-aligned performance scoring (0-100)
        score = 100

        # Memory efficiency (30 points max) - Target: stable <10GB, peak <40GB
        peak_memory = stats["peak_memory_gb"]
        if peak_memory > 48:
            score -= 30  # Exceeds critical threshold
        elif peak_memory > 40:
            score -= 20  # Exceeds E068E target
        elif peak_memory > 24:
            score -= 10  # Moderate usage
        elif peak_memory > 10:
            score -= 5  # Above typical target
        # 0-10GB is excellent

        # CPU efficiency (25 points max) - Target: >80% during compute stages
        avg_cpu = stats["avg_cpu_percent"]
        if avg_cpu < 20:
            score -= 20  # Severe underutilization
        elif avg_cpu < 50:
            score -= 15  # Underutilization
        elif avg_cpu < 80:
            score -= 10  # Below E068E target
        elif avg_cpu > 95:
            score -= 15  # Over-utilization/contention
        # 80-95% is optimal

        # Execution time efficiency (25 points max) - Target: complex joins <30s per stage
        total_time = stats["total_execution_time"]
        stage_count = len(self.checkpoints)
        avg_stage_time = total_time / stage_count if stage_count > 0 else 0

        if avg_stage_time > 300:  # 5 minutes per stage
            score -= 25
        elif avg_stage_time > 120:  # 2 minutes per stage
            score -= 20
        elif avg_stage_time > 60:  # 1 minute per stage
            score -= 15
        elif avg_stage_time > 30:  # Above E068E target
            score -= 10
        # <30s per stage is excellent

        # Database growth efficiency (20 points max) - Target: <1GB per simulation year
        db_growth = stats["database_growth_gb"]
        if db_growth > 10:
            score -= 20
        elif db_growth > 5:
            score -= 15
        elif db_growth > 2:
            score -= 10
        elif db_growth > 1:  # Above E068E target
            score -= 5
        # <1GB is excellent

        # Convert score to performance level
        if score >= 90:
            return PerformanceLevel.EXCELLENT
        elif score >= 75:
            return PerformanceLevel.GOOD
        elif score >= 60:
            return PerformanceLevel.MODERATE
        elif score >= 40:
            return PerformanceLevel.POOR
        else:
            return PerformanceLevel.CRITICAL

    def _assess_e068e_targets(self) -> str:
        """Assess performance against specific E068E targets"""
        if not self.checkpoints:
            return "No performance data available"

        # Calculate statistics directly to avoid circular dependency
        memory_values = [c.memory_usage_gb for c in self.checkpoints]
        cpu_values = [c.cpu_percent for c in self.checkpoints]
        db_sizes = [c.database_size_gb for c in self.checkpoints]

        peak_memory = max(memory_values)
        avg_memory = sum(memory_values) / len(memory_values)
        avg_cpu = sum(cpu_values) / len(cpu_values)
        db_growth = db_sizes[-1] - db_sizes[0] if len(db_sizes) > 1 else 0
        total_time = self.checkpoints[-1].elapsed_time
        stage_count = len(self.checkpoints)
        avg_stage_time = total_time / stage_count if stage_count > 0 else 0
        target_lines = []

        target_lines.append("E068E Performance Target Assessment:")
        target_lines.append("")

        # Memory targets
        if avg_memory < 10 and peak_memory < 40:
            target_lines.append(
                f"✅ Memory: Peak {peak_memory:.1f}GB, Avg {avg_memory:.1f}GB (EXCELLENT)"
            )
        elif peak_memory < 40:
            target_lines.append(
                f"✅ Memory: Peak {peak_memory:.1f}GB, Avg {avg_memory:.1f}GB (GOOD - below 40GB target)"
            )
        else:
            target_lines.append(
                f"❌ Memory: Peak {peak_memory:.1f}GB, Avg {avg_memory:.1f}GB (EXCEEDS 40GB target)"
            )

        # CPU utilization targets
        if avg_cpu >= 80:
            target_lines.append(
                f"✅ CPU: {avg_cpu:.1f}% average (GOOD - above 80% target)"
            )
        elif avg_cpu >= 60:
            target_lines.append(
                f"⚠️ CPU: {avg_cpu:.1f}% average (MODERATE - below 80% target)"
            )
        else:
            target_lines.append(
                f"❌ CPU: {avg_cpu:.1f}% average (LOW - well below 80% target)"
            )

        # Storage efficiency
        if db_growth <= 1:
            target_lines.append(
                f"✅ Storage: {db_growth:.2f}GB growth (EXCELLENT - meets 1GB target)"
            )
        elif db_growth <= 2:
            target_lines.append(
                f"⚠️ Storage: {db_growth:.2f}GB growth (MODERATE - above 1GB target)"
            )
        else:
            target_lines.append(
                f"❌ Storage: {db_growth:.2f}GB growth (HIGH - well above 1GB target)"
            )

        # Query performance

        if avg_stage_time <= 30:
            target_lines.append(
                f"✅ Query Performance: {avg_stage_time:.1f}s avg per stage (EXCELLENT - meets 30s target)"
            )
        elif avg_stage_time <= 60:
            target_lines.append(
                f"⚠️ Query Performance: {avg_stage_time:.1f}s avg per stage (MODERATE - above 30s target)"
            )
        else:
            target_lines.append(
                f"❌ Query Performance: {avg_stage_time:.1f}s avg per stage (SLOW - well above 30s target)"
            )

        return "\n".join(target_lines)

    def _generate_optimization_recommendations(self) -> List[PerformanceOptimization]:
        """Generate E068E-specific optimization recommendations"""
        return generate_optimization_recommendations(self.checkpoints, self.thresholds)
