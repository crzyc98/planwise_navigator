"""
Run Summary and Reporting System for PlanWise Navigator

Provides comprehensive run summaries with error tracking, performance analysis,
and audit trail generation for production observability.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logger import ProductionLogger
from .performance_monitor import PerformanceMonitor


@dataclass
class RunIssue:
    """Container for run issues (errors and warnings)"""

    level: str  # 'error' or 'warning'
    message: str
    context: Dict[str, Any]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "context": self.context,
            "timestamp": self.timestamp,
        }


@dataclass
class RunMetadata:
    """Container for run metadata"""

    run_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    status: str = "running"
    backup_path: Optional[str] = None
    configuration: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": round(self.duration_seconds, 2)
            if self.duration_seconds
            else None,
            "status": self.status,
            "backup_path": self.backup_path,
            "configuration": self.configuration,
            "environment": self.environment,
        }


class RunSummaryGenerator:
    """
    Comprehensive run summary generator that tracks execution metadata,
    performance metrics, and issues for audit trail and debugging.

    Features:
    - Complete run metadata tracking
    - Error and warning cataloging
    - Performance metrics integration
    - Automated summary generation
    - Human-readable console output
    - JSON artifact creation for audit trails
    """

    def __init__(
        self,
        run_id: str,
        logger: ProductionLogger,
        performance_monitor: Optional[PerformanceMonitor] = None,
    ):
        """
        Initialize run summary generator

        Args:
            run_id: Unique identifier for this simulation run
            logger: ProductionLogger instance for logging
            performance_monitor: Optional PerformanceMonitor for metrics
        """
        self.run_id = run_id
        self.logger = logger
        self.performance_monitor = performance_monitor
        self.metadata = RunMetadata(run_id=run_id, start_time=datetime.now())
        self.errors: List[RunIssue] = []
        self.warnings: List[RunIssue] = []
        self.custom_metrics: Dict[str, Any] = {}

        # Record environment information
        self._capture_environment()

        # Log run start
        self.logger.info("Simulation run started", run_id=run_id)

    def _capture_environment(self) -> None:
        """Capture environment information for audit trail"""
        import os
        import platform
        import sys

        self.metadata.environment = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "hostname": platform.node(),
            "working_directory": os.getcwd(),
            "user": os.getenv("USER", "unknown"),
            "timestamp": datetime.now().isoformat(),
        }

    def set_configuration(self, config: Dict[str, Any]) -> None:
        """Set run configuration for audit trail"""
        self.metadata.configuration = config
        self.logger.info("Run configuration set", configuration=config)

    def add_error(self, error: str, context: Dict[str, Any] = None) -> None:
        """
        Add error to summary

        Args:
            error: Error message
            context: Additional context about the error
        """
        issue = RunIssue(
            level="error",
            message=error,
            context=context or {},
            timestamp=datetime.now().isoformat(),
        )
        self.errors.append(issue)
        # Filter out reserved keywords to avoid conflicts
        safe_context = {
            k: v for k, v in issue.context.items() if k not in ["level", "message"]
        }
        self.logger.error(f"Run error: {error}", **safe_context)

    def add_warning(self, warning: str, context: Dict[str, Any] = None) -> None:
        """
        Add warning to summary

        Args:
            warning: Warning message
            context: Additional context about the warning
        """
        issue = RunIssue(
            level="warning",
            message=warning,
            context=context or {},
            timestamp=datetime.now().isoformat(),
        )
        self.warnings.append(issue)
        # Filter out reserved keywords to avoid conflicts
        safe_context = {
            k: v for k, v in issue.context.items() if k not in ["level", "message"]
        }
        self.logger.log_event("WARNING", f"Run warning: {warning}", **safe_context)

    def add_metric(self, name: str, value: Any, description: str = None) -> None:
        """
        Add custom metric to summary

        Args:
            name: Metric name
            value: Metric value
            description: Optional description of the metric
        """
        self.custom_metrics[name] = {
            "value": value,
            "description": description,
            "timestamp": datetime.now().isoformat(),
        }
        self.logger.info(f"Custom metric: {name}", metric=name, value=value)

    def set_backup_path(self, backup_path: str) -> None:
        """Set backup path for audit trail"""
        self.metadata.backup_path = backup_path
        self.logger.info("Backup created", backup_path=backup_path)

    def generate_summary(self, final_status: str = "success") -> Dict[str, Any]:
        """
        Generate comprehensive run summary

        Args:
            final_status: Final status of the run ('success', 'failed', 'partial')

        Returns:
            Complete run summary dictionary
        """
        # Finalize metadata
        self.metadata.end_time = datetime.now()
        self.metadata.status = final_status
        self.metadata.duration_seconds = (
            self.metadata.end_time - self.metadata.start_time
        ).total_seconds()

        # Get performance metrics if available
        performance_summary = {}
        if self.performance_monitor:
            performance_summary = self.performance_monitor.get_summary()

        # Build complete summary
        summary = {
            "run_metadata": self.metadata.to_dict(),
            "execution_summary": {
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings),
                "has_backup": self.metadata.backup_path is not None,
                "custom_metrics_count": len(self.custom_metrics),
            },
            "performance_metrics": performance_summary,
            "custom_metrics": self.custom_metrics,
            "issues": {
                "errors": [issue.to_dict() for issue in self.errors],
                "warnings": [issue.to_dict() for issue in self.warnings],
            },
        }

        # Add top contributors by duration (operations) for quick insight
        try:
            top_contributors = []
            if self.performance_monitor:
                metrics = self.performance_monitor.get_metrics()
                # Build sortable list: (name, duration, context)
                items = []
                for name, data in metrics.items():
                    duration = data.get("duration_seconds") or 0
                    items.append(
                        {
                            "name": name,
                            "duration_seconds": duration,
                            # capture common context fields if present
                            "stage": data.get("stage"),
                            "year": data.get("year"),
                        }
                    )
                # Sort by duration descending and take top 5
                items.sort(key=lambda x: (x["duration_seconds"] or 0), reverse=True)
                top_contributors = items[:5]
            summary["performance_top_contributors"] = top_contributors
        except Exception:
            # Do not fail summary generation if we cannot compute contributors
            summary["performance_top_contributors"] = []

        # Add compact per-year, per-stage breakdown table
        try:
            breakdown_rows = []
            if self.performance_monitor:
                metrics = self.performance_monitor.get_metrics()

                # Collect stage durations per year
                per_year: dict[int, dict[str, float]] = {}
                totals: dict[int, float] = {}

                for name, data in metrics.items():
                    year = data.get("year")
                    stage = data.get("stage")
                    duration = data.get("duration_seconds") or 0.0
                    if year is None:
                        # Try to extract year from operation name (e.g., year_simulation_2025)
                        if isinstance(name, str) and name.startswith("year_simulation_"):
                            try:
                                y = int(name.rsplit("_", 1)[-1])
                                totals[y] = duration
                            except Exception:
                                pass
                        continue

                    # Normalize year to int
                    try:
                        year_int = int(year)
                    except Exception:
                        continue

                    if stage:
                        per_year.setdefault(year_int, {})[stage] = duration

                # Build compact rows ordered by year
                STAGE_ORDER = [
                    "INITIALIZATION",
                    "FOUNDATION",
                    "EVENT_GENERATION",
                    "STATE_ACCUMULATION",
                    "VALIDATION",
                    "REPORTING",
                ]

                for year in sorted(set(list(per_year.keys()) + list(totals.keys()))):
                    row: dict[str, object] = {"year": year}
                    for st in STAGE_ORDER:
                        val = per_year.get(year, {}).get(st)
                        if val is not None:
                            # Round to 3 decimals for compactness
                            row[st] = round(val, 3)
                    # Add total if we have it
                    if year in totals:
                        row["total"] = round(totals[year], 3)
                    breakdown_rows.append(row)

            summary["performance_breakdown"] = {"by_year": breakdown_rows}
        except Exception:
            summary["performance_breakdown"] = {"by_year": []}

        # Save summary artifacts
        self._save_summary_artifacts(summary)

        # Log final summary
        self.logger.info("Run completed", **summary["run_metadata"])

        # Print human-readable summary to console
        self._print_console_summary(summary)

        return summary

    def _save_summary_artifacts(self, summary: Dict[str, Any]) -> None:
        """Save summary artifacts to disk"""
        # Create run-specific artifact directory
        artifacts_dir = Path(f"artifacts/runs/{self.run_id}")
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Save complete summary as JSON
        with open(artifacts_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        # Save errors separately if any exist
        if self.errors:
            with open(artifacts_dir / "errors.json", "w") as f:
                json.dump([error.to_dict() for error in self.errors], f, indent=2)

        # Save warnings separately if any exist
        if self.warnings:
            with open(artifacts_dir / "warnings.json", "w") as f:
                json.dump([warning.to_dict() for warning in self.warnings], f, indent=2)

        # Save performance metrics if available
        if self.performance_monitor:
            with open(artifacts_dir / "performance.json", "w") as f:
                json.dump(self.performance_monitor.get_metrics(), f, indent=2)

        self.logger.info(
            "Summary artifacts saved", artifacts_directory=str(artifacts_dir)
        )

    def _print_console_summary(self, summary: Dict[str, Any]) -> None:
        """Print human-readable summary to console"""
        metadata = summary["run_metadata"]
        exec_summary = summary["execution_summary"]
        perf_summary = summary["performance_metrics"]

        print(f"\n{'='*60}")
        print(f"  Run {self.run_id} Complete")
        print(f"{'='*60}")

        # Basic run info
        print(f"Status: {metadata['status'].upper()}")
        if metadata["duration_seconds"]:
            duration = timedelta(seconds=metadata["duration_seconds"])
            print(f"Duration: {duration}")

        # Issue summary
        if exec_summary["total_errors"] > 0:
            print(f"❌ Errors: {exec_summary['total_errors']}")
        if exec_summary["total_warnings"] > 0:
            print(f"⚠️  Warnings: {exec_summary['total_warnings']}")
        if exec_summary["total_errors"] == 0 and exec_summary["total_warnings"] == 0:
            print("✅ No issues detected")

        # Performance summary
        if perf_summary.get("total_operations", 0) > 0:
            print(f"\nPerformance:")
            print(f"  Operations: {perf_summary['total_operations']}")
            print(f"  Total Duration: {perf_summary['total_duration_seconds']}s")
            if perf_summary.get("slowest_operation"):
                slowest = perf_summary["slowest_operation"]
                print(f"  Slowest: {slowest['name']} ({slowest['duration']}s)")

        # Compact per-year breakdown (if available)
        breakdown = summary.get("performance_breakdown", {}).get("by_year", [])
        if breakdown:
            print("\nPerformance Breakdown (seconds):")
            # Header (short labels)
            print("  Year  Found  Events  State  Valid  Report  Total")
            for row in breakdown:
                year = row.get("year")
                # Use get with default of None; print blanks if missing
                found = row.get("FOUNDATION")
                events = row.get("EVENT_GENERATION")
                state = row.get("STATE_ACCUMULATION")
                valid = row.get("VALIDATION")
                report = row.get("REPORTING")
                total = row.get("total")
                def fmt(v):
                    return f"{v:.3f}" if isinstance(v, (int, float)) else "   -  "
                print(
                    f"  {year}  {fmt(found):>6} {fmt(events):>7} {fmt(state):>6} {fmt(valid):>6} {fmt(report):>7} {fmt(total):>7}"
                )

        # Top contributors (if available)
        top = summary.get("performance_top_contributors", [])
        if top:
            print("\nTop Contributors:")
            for item in top:
                name = item.get("name", "unknown")
                duration = item.get("duration_seconds", 0)
                stage = item.get("stage")
                year = item.get("year")
                label = name
                if stage and year:
                    label = f"{stage} {year}"
                print(f"  • {label}: {duration:.3f}s")

        # Backup info
        if metadata["backup_path"]:
            print(f"\n💾 Backup: {metadata['backup_path']}")

        # Artifacts location
        print(f"\n📁 Artifacts: artifacts/runs/{self.run_id}/")
        print(f"{'='*60}\n")

    def get_issue_summary(self) -> Dict[str, Any]:
        """Get summary of issues for quick status check"""
        return {
            "total_errors": len(self.errors),
            "total_warnings": len(self.warnings),
            "has_issues": len(self.errors) > 0 or len(self.warnings) > 0,
            "latest_error": self.errors[-1].to_dict() if self.errors else None,
            "latest_warning": self.warnings[-1].to_dict() if self.warnings else None,
        }

    def export_for_monitoring(self) -> Dict[str, Any]:
        """Export summary in format suitable for monitoring systems"""
        metadata = self.metadata.to_dict()

        return {
            "run_id": self.run_id,
            "status": metadata["status"],
            "duration_seconds": metadata["duration_seconds"],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "has_backup": metadata["backup_path"] is not None,
            "start_time": metadata["start_time"],
            "end_time": metadata["end_time"],
            "environment": metadata["environment"]["hostname"],
            "user": metadata["environment"]["user"],
        }
