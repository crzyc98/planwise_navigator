"""
Validation Reporting and Alerting System

Provides comprehensive reporting and alerting capabilities for data quality
validation results across multi-year simulations. Integrates with the
MultiYearValidationFramework to provide clear visibility into data lineage
and quality metrics.

Key Features:
- Real-time validation reporting with severity-based alerting
- Comprehensive validation dashboards and summaries
- Data quality trend analysis and anomaly detection
- Integration with existing logging and monitoring infrastructure
- Configurable alerting thresholds and notification channels
- Export capabilities for audit and compliance reporting

Usage:
    # Initialize validation reporter
    reporter = ValidationReporter(config, database_manager)

    # Generate comprehensive report
    report = reporter.generate_comprehensive_report(validation_summary)

    # Send alerts for critical issues
    reporter.send_validation_alerts(validation_results)
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from .validation_framework import ValidationResult, ValidationSummary, ValidationSeverity, ValidationStatus
from .multi_year_validation_framework import (
    MultiYearValidationSummary, CrossYearValidationResult,
    EventSourcingValidationResult, BusinessLogicValidationResult
)
from .config import OrchestrationConfig
from .database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class AlertChannel(Enum):
    """Alert notification channels."""
    LOG = "log"
    EMAIL = "email"
    SLACK = "slack"
    DATABASE = "database"
    FILE = "file"


class ReportFormat(Enum):
    """Report output formats."""
    JSON = "json"
    HTML = "html"
    CSV = "csv"
    MARKDOWN = "markdown"


@dataclass
class ValidationAlert:
    """Validation alert data structure."""
    alert_id: str
    timestamp: datetime
    severity: ValidationSeverity
    check_name: str
    message: str
    details: Dict[str, Any]
    scenario_id: Optional[str] = None
    year: Optional[int] = None
    resolved: bool = False
    resolution_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary format."""
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "check_name": self.check_name,
            "message": self.message,
            "details": self.details,
            "scenario_id": self.scenario_id,
            "year": self.year,
            "resolved": self.resolved,
            "resolution_notes": self.resolution_notes
        }


@dataclass
class ValidationReport:
    """Comprehensive validation report."""
    report_id: str
    timestamp: datetime
    summary: Dict[str, Any]
    validation_results: List[ValidationResult]
    alerts: List[ValidationAlert]
    performance_metrics: Dict[str, Any]
    recommendations: List[str]
    trends: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary format."""
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp.isoformat(),
            "summary": self.summary,
            "validation_results": [result.__dict__ for result in self.validation_results],
            "alerts": [alert.to_dict() for alert in self.alerts],
            "performance_metrics": self.performance_metrics,
            "recommendations": self.recommendations,
            "trends": self.trends,
            "metadata": self.metadata
        }


class ValidationReporter:
    """
    Comprehensive validation reporting and alerting system.

    Provides real-time validation reporting with severity-based alerting,
    comprehensive dashboards, trend analysis, and export capabilities
    for audit and compliance requirements.
    """

    def __init__(self, config: OrchestrationConfig, database_manager: DatabaseManager):
        """
        Initialize validation reporter.

        Args:
            config: Orchestration configuration
            database_manager: Database manager for data access
        """
        self.config = config
        self.db_manager = database_manager

        # Reporting configuration
        self.alert_channels = self._get_alert_channels()
        self.alert_thresholds = self._get_alert_thresholds()
        self.report_output_dir = self._get_report_output_dir()

        # Alert tracking
        self._active_alerts: List[ValidationAlert] = []
        self._alert_history: List[ValidationAlert] = []
        self._report_history: List[ValidationReport] = []

        logger.info(f"ValidationReporter initialized with channels: {[c.value for c in self.alert_channels]}")

    def _get_alert_channels(self) -> List[AlertChannel]:
        """Get configured alert channels."""
        # Default to log channel, can be extended with configuration
        return [AlertChannel.LOG, AlertChannel.DATABASE]

    def _get_alert_thresholds(self) -> Dict[str, Any]:
        """Get alert threshold configuration."""
        return {
            "critical_failure_threshold": 1,  # Alert on any critical failure
            "warning_threshold": 5,  # Alert on 5+ warnings
            "performance_degradation_threshold": 2.0,  # Alert if validation takes 2x longer
            "circuit_breaker_threshold": 1  # Alert when circuit breaker opens
        }

    def _get_report_output_dir(self) -> Path:
        """Get report output directory."""
        output_dir = self.config.project_root / "validation_reports"
        output_dir.mkdir(exist_ok=True)
        return output_dir

    def generate_comprehensive_report(
        self,
        validation_summary: Union[ValidationSummary, MultiYearValidationSummary],
        include_trends: bool = True,
        include_recommendations: bool = True
    ) -> ValidationReport:
        """
        Generate comprehensive validation report.

        Args:
            validation_summary: Validation summary to report on
            include_trends: Whether to include trend analysis
            include_recommendations: Whether to include recommendations

        Returns:
            Comprehensive validation report
        """
        logger.info("Generating comprehensive validation report")

        report_id = f"validation_report_{int(datetime.utcnow().timestamp())}"
        timestamp = datetime.utcnow()

        # Generate summary
        summary = self._generate_report_summary(validation_summary)

        # Extract validation results
        validation_results = validation_summary.results

        # Generate alerts
        alerts = self._generate_alerts_from_results(validation_results)

        # Extract performance metrics
        performance_metrics = self._extract_performance_metrics(validation_summary)

        # Generate recommendations
        recommendations = []
        if include_recommendations:
            recommendations = self._generate_recommendations(validation_summary)

        # Generate trends
        trends = {}
        if include_trends:
            trends = self._generate_trend_analysis(validation_summary)

        # Create metadata
        metadata = {
            "config_version": "1.0.0",
            "generator": "ValidationReporter",
            "total_validation_time": getattr(validation_summary, 'total_execution_time', 0),
            "validation_mode": getattr(validation_summary, 'validation_mode', 'unknown')
        }

        # Create report
        report = ValidationReport(
            report_id=report_id,
            timestamp=timestamp,
            summary=summary,
            validation_results=validation_results,
            alerts=alerts,
            performance_metrics=performance_metrics,
            recommendations=recommendations,
            trends=trends,
            metadata=metadata
        )

        # Store report in history
        self._report_history.append(report)

        logger.info(f"Comprehensive validation report generated: {report_id}")
        return report

    def _generate_report_summary(
        self,
        validation_summary: Union[ValidationSummary, MultiYearValidationSummary]
    ) -> Dict[str, Any]:
        """Generate report summary section."""
        summary = {
            "overall_status": "PASSED" if validation_summary.is_valid else "FAILED",
            "total_checks": validation_summary.total_checks,
            "passed_checks": validation_summary.passed_checks,
            "failed_checks": validation_summary.failed_checks,
            "critical_failures": validation_summary.critical_failures,
            "warnings": validation_summary.warnings,
            "success_rate": validation_summary.success_rate,
            "execution_time": validation_summary.total_execution_time
        }

        # Add multi-year specific metrics if available
        if isinstance(validation_summary, MultiYearValidationSummary):
            summary.update({
                "years_validated": validation_summary.years_validated,
                "cross_year_checks": validation_summary.cross_year_checks,
                "event_sourcing_checks": validation_summary.event_sourcing_checks,
                "business_logic_checks": validation_summary.business_logic_checks,
                "total_records_validated": validation_summary.total_records_validated,
                "total_events_validated": validation_summary.total_events_validated,
                "performance_impact_ms": validation_summary.performance_impact_ms
            })

        return summary

    def _generate_alerts_from_results(self, validation_results: List[ValidationResult]) -> List[ValidationAlert]:
        """Generate alerts from validation results."""
        alerts = []

        for result in validation_results:
            # Generate alert for critical failures
            if result.severity == ValidationSeverity.CRITICAL and result.failed:
                alert = ValidationAlert(
                    alert_id=f"critical_{result.check_name}_{int(datetime.utcnow().timestamp())}",
                    timestamp=datetime.utcnow(),
                    severity=result.severity,
                    check_name=result.check_name,
                    message=f"Critical validation failure: {result.message}",
                    details=result.details,
                    scenario_id=result.details.get("scenario_id"),
                    year=result.details.get("year")
                )
                alerts.append(alert)

            # Generate alert for error conditions
            elif result.status == ValidationStatus.ERROR:
                alert = ValidationAlert(
                    alert_id=f"error_{result.check_name}_{int(datetime.utcnow().timestamp())}",
                    timestamp=datetime.utcnow(),
                    severity=ValidationSeverity.ERROR,
                    check_name=result.check_name,
                    message=f"Validation error: {result.message}",
                    details=result.details,
                    scenario_id=result.details.get("scenario_id"),
                    year=result.details.get("year")
                )
                alerts.append(alert)

        return alerts

    def _extract_performance_metrics(
        self,
        validation_summary: Union[ValidationSummary, MultiYearValidationSummary]
    ) -> Dict[str, Any]:
        """Extract performance metrics from validation summary."""
        base_metrics = {
            "total_execution_time": validation_summary.total_execution_time,
            "average_check_time": (
                validation_summary.total_execution_time / validation_summary.total_checks
                if validation_summary.total_checks > 0 else 0
            ),
            "checks_per_second": (
                validation_summary.total_checks / validation_summary.total_execution_time
                if validation_summary.total_execution_time > 0 else 0
            )
        }

        # Add multi-year specific performance metrics
        if isinstance(validation_summary, MultiYearValidationSummary):
            base_metrics.update({
                "performance_impact_ms": validation_summary.performance_impact_ms,
                "records_per_second": (
                    validation_summary.total_records_validated / validation_summary.total_execution_time
                    if validation_summary.total_execution_time > 0 else 0
                ),
                "events_per_second": (
                    validation_summary.total_events_validated / validation_summary.total_execution_time
                    if validation_summary.total_execution_time > 0 else 0
                )
            })

        return base_metrics

    def _generate_recommendations(
        self,
        validation_summary: Union[ValidationSummary, MultiYearValidationSummary]
    ) -> List[str]:
        """Generate actionable recommendations based on validation results."""
        recommendations = []

        # Performance recommendations
        if validation_summary.total_execution_time > 300:  # More than 5 minutes
            recommendations.append(
                "Consider enabling performance optimization to reduce validation execution time"
            )

        # Data quality recommendations
        if validation_summary.warnings > 10:
            recommendations.append(
                f"Address {validation_summary.warnings} validation warnings to improve data quality"
            )

        # Critical failure recommendations
        if validation_summary.critical_failures > 0:
            recommendations.append(
                f"Investigate and resolve {validation_summary.critical_failures} critical validation failures immediately"
            )

        # Success rate recommendations
        if validation_summary.success_rate < 90:
            recommendations.append(
                f"Improve validation success rate from {validation_summary.success_rate:.1f}% to >95%"
            )

        # Multi-year specific recommendations
        if isinstance(validation_summary, MultiYearValidationSummary):
            # Cross-year integrity
            cross_year_failures = len(validation_summary.get_cross_year_failures())
            if cross_year_failures > 0:
                recommendations.append(
                    f"Review {cross_year_failures} cross-year integrity issues for workforce consistency"
                )

            # Event sourcing
            event_sourcing_failures = len(validation_summary.get_event_sourcing_failures())
            if event_sourcing_failures > 0:
                recommendations.append(
                    f"Fix {event_sourcing_failures} event sourcing integrity issues for audit trail completeness"
                )

            # Business logic
            business_logic_failures = len(validation_summary.get_business_logic_failures())
            if business_logic_failures > 0:
                recommendations.append(
                    f"Address {business_logic_failures} business logic compliance issues"
                )

        return recommendations

    def _generate_trend_analysis(
        self,
        validation_summary: Union[ValidationSummary, MultiYearValidationSummary]
    ) -> Dict[str, Any]:
        """Generate trend analysis from historical validation data."""
        trends = {}

        # Analyze recent report history for trends
        if len(self._report_history) >= 3:
            recent_reports = self._report_history[-3:]

            # Success rate trend
            success_rates = [r.summary.get("success_rate", 0) for r in recent_reports]
            trends["success_rate_trend"] = {
                "current": success_rates[-1],
                "previous": success_rates[-2],
                "change": success_rates[-1] - success_rates[-2],
                "direction": "improving" if success_rates[-1] > success_rates[-2] else "declining"
            }

            # Execution time trend
            exec_times = [r.summary.get("execution_time", 0) for r in recent_reports]
            trends["execution_time_trend"] = {
                "current": exec_times[-1],
                "previous": exec_times[-2],
                "change": exec_times[-1] - exec_times[-2],
                "direction": "improving" if exec_times[-1] < exec_times[-2] else "declining"
            }

            # Alert frequency trend
            alert_counts = [len(r.alerts) for r in recent_reports]
            trends["alert_frequency_trend"] = {
                "current": alert_counts[-1],
                "previous": alert_counts[-2],
                "change": alert_counts[-1] - alert_counts[-2],
                "direction": "improving" if alert_counts[-1] < alert_counts[-2] else "declining"
            }

        return trends

    def send_validation_alerts(
        self,
        alerts: List[ValidationAlert],
        channels: Optional[List[AlertChannel]] = None
    ) -> Dict[str, Any]:
        """
        Send validation alerts through configured channels.

        Args:
            alerts: List of alerts to send
            channels: Optional list of specific channels to use

        Returns:
            Alert sending results
        """
        if not alerts:
            return {"status": "no_alerts", "alerts_sent": 0}

        if channels is None:
            channels = self.alert_channels

        logger.info(f"Sending {len(alerts)} validation alerts through {len(channels)} channels")

        results = {
            "alerts_sent": len(alerts),
            "channels_used": [c.value for c in channels],
            "channel_results": {}
        }

        for channel in channels:
            try:
                if channel == AlertChannel.LOG:
                    self._send_log_alerts(alerts)
                elif channel == AlertChannel.DATABASE:
                    self._send_database_alerts(alerts)
                elif channel == AlertChannel.FILE:
                    self._send_file_alerts(alerts)

                results["channel_results"][channel.value] = {"status": "success"}

            except Exception as e:
                logger.error(f"Failed to send alerts through {channel.value}: {e}")
                results["channel_results"][channel.value] = {"status": "error", "error": str(e)}

        # Update active alerts
        self._active_alerts.extend(alerts)
        self._alert_history.extend(alerts)

        return results

    def _send_log_alerts(self, alerts: List[ValidationAlert]) -> None:
        """Send alerts to logging system."""
        for alert in alerts:
            if alert.severity == ValidationSeverity.CRITICAL:
                logger.critical(f"VALIDATION ALERT: {alert.message} (Check: {alert.check_name})")
            elif alert.severity == ValidationSeverity.ERROR:
                logger.error(f"VALIDATION ALERT: {alert.message} (Check: {alert.check_name})")
            elif alert.severity == ValidationSeverity.WARNING:
                logger.warning(f"VALIDATION ALERT: {alert.message} (Check: {alert.check_name})")
            else:
                logger.info(f"VALIDATION ALERT: {alert.message} (Check: {alert.check_name})")

    def _send_database_alerts(self, alerts: List[ValidationAlert]) -> None:
        """Send alerts to database for persistence."""
        try:
            with self.db_manager.get_connection() as conn:
                # Create alerts table if it doesn't exist
                create_table_sql = """
                    CREATE TABLE IF NOT EXISTS validation_alerts (
                        alert_id VARCHAR PRIMARY KEY,
                        timestamp TIMESTAMP,
                        severity VARCHAR,
                        check_name VARCHAR,
                        message TEXT,
                        details JSON,
                        scenario_id VARCHAR,
                        year INTEGER,
                        resolved BOOLEAN DEFAULT FALSE,
                        resolution_notes TEXT
                    )
                """
                conn.execute(create_table_sql)

                # Insert alerts
                for alert in alerts:
                    insert_sql = """
                        INSERT OR REPLACE INTO validation_alerts
                        (alert_id, timestamp, severity, check_name, message, details, scenario_id, year, resolved, resolution_notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    conn.execute(insert_sql, (
                        alert.alert_id,
                        alert.timestamp,
                        alert.severity.value,
                        alert.check_name,
                        alert.message,
                        json.dumps(alert.details),
                        alert.scenario_id,
                        alert.year,
                        alert.resolved,
                        alert.resolution_notes
                    ))

                conn.commit()
                logger.debug(f"Stored {len(alerts)} alerts in database")

        except Exception as e:
            logger.error(f"Failed to store alerts in database: {e}")
            raise

    def _send_file_alerts(self, alerts: List[ValidationAlert]) -> None:
        """Send alerts to file system."""
        try:
            alerts_file = self.report_output_dir / f"alerts_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

            alerts_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "alert_count": len(alerts),
                "alerts": [alert.to_dict() for alert in alerts]
            }

            with open(alerts_file, 'w') as f:
                json.dump(alerts_data, f, indent=2, default=str)

            logger.debug(f"Saved {len(alerts)} alerts to {alerts_file}")

        except Exception as e:
            logger.error(f"Failed to save alerts to file: {e}")
            raise

    def export_report(
        self,
        report: ValidationReport,
        format: ReportFormat = ReportFormat.JSON,
        filename: Optional[str] = None
    ) -> Path:
        """
        Export validation report to file.

        Args:
            report: Validation report to export
            format: Export format
            filename: Optional custom filename

        Returns:
            Path to exported file
        """
        if filename is None:
            timestamp = report.timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"validation_report_{timestamp}.{format.value}"

        export_path = self.report_output_dir / filename

        try:
            if format == ReportFormat.JSON:
                with open(export_path, 'w') as f:
                    json.dump(report.to_dict(), f, indent=2, default=str)

            elif format == ReportFormat.MARKDOWN:
                self._export_markdown_report(report, export_path)

            elif format == ReportFormat.HTML:
                self._export_html_report(report, export_path)

            elif format == ReportFormat.CSV:
                self._export_csv_report(report, export_path)

            logger.info(f"Exported validation report to {export_path}")
            return export_path

        except Exception as e:
            logger.error(f"Failed to export report: {e}")
            raise

    def _export_markdown_report(self, report: ValidationReport, export_path: Path) -> None:
        """Export report in Markdown format."""
        with open(export_path, 'w') as f:
            f.write(f"# Validation Report: {report.report_id}\n\n")
            f.write(f"**Generated:** {report.timestamp.isoformat()}\n\n")

            # Summary section
            f.write("## Summary\n\n")
            f.write(f"- **Overall Status:** {report.summary.get('overall_status', 'UNKNOWN')}\n")
            f.write(f"- **Success Rate:** {report.summary.get('success_rate', 0):.1f}%\n")
            f.write(f"- **Total Checks:** {report.summary.get('total_checks', 0)}\n")
            f.write(f"- **Critical Failures:** {report.summary.get('critical_failures', 0)}\n")
            f.write(f"- **Warnings:** {report.summary.get('warnings', 0)}\n")
            f.write(f"- **Execution Time:** {report.summary.get('execution_time', 0):.2f}s\n\n")

            # Alerts section
            if report.alerts:
                f.write("## Alerts\n\n")
                for alert in report.alerts:
                    f.write(f"### {alert.severity.value.upper()}: {alert.check_name}\n")
                    f.write(f"**Message:** {alert.message}\n\n")
                    f.write(f"**Timestamp:** {alert.timestamp.isoformat()}\n\n")

            # Recommendations section
            if report.recommendations:
                f.write("## Recommendations\n\n")
                for i, rec in enumerate(report.recommendations, 1):
                    f.write(f"{i}. {rec}\n")
                f.write("\n")

    def _export_html_report(self, report: ValidationReport, export_path: Path) -> None:
        """Export report in HTML format."""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Validation Report: {report.report_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .status-passed {{ color: green; }}
                .status-failed {{ color: red; }}
                .severity-critical {{ background-color: #ffebee; color: #c62828; }}
                .severity-error {{ background-color: #fff3e0; color: #ef6c00; }}
                .severity-warning {{ background-color: #fffde7; color: #f57f17; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>Validation Report: {report.report_id}</h1>
            <p><strong>Generated:</strong> {report.timestamp.isoformat()}</p>

            <h2>Summary</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Overall Status</td><td class="status-{report.summary.get('overall_status', 'unknown').lower()}">{report.summary.get('overall_status', 'UNKNOWN')}</td></tr>
                <tr><td>Success Rate</td><td>{report.summary.get('success_rate', 0):.1f}%</td></tr>
                <tr><td>Total Checks</td><td>{report.summary.get('total_checks', 0)}</td></tr>
                <tr><td>Critical Failures</td><td>{report.summary.get('critical_failures', 0)}</td></tr>
                <tr><td>Warnings</td><td>{report.summary.get('warnings', 0)}</td></tr>
                <tr><td>Execution Time</td><td>{report.summary.get('execution_time', 0):.2f}s</td></tr>
            </table>
        """

        if report.alerts:
            html_content += "<h2>Alerts</h2><table><tr><th>Severity</th><th>Check</th><th>Message</th><th>Timestamp</th></tr>"
            for alert in report.alerts:
                html_content += f"""
                <tr class="severity-{alert.severity.value}">
                    <td>{alert.severity.value.upper()}</td>
                    <td>{alert.check_name}</td>
                    <td>{alert.message}</td>
                    <td>{alert.timestamp.isoformat()}</td>
                </tr>
                """
            html_content += "</table>"

        html_content += "</body></html>"

        with open(export_path, 'w') as f:
            f.write(html_content)

    def _export_csv_report(self, report: ValidationReport, export_path: Path) -> None:
        """Export report in CSV format."""
        import csv

        with open(export_path, 'w', newline='') as f:
            writer = csv.writer(f)

            # Write summary
            writer.writerow(["Section", "Metric", "Value"])
            writer.writerow(["Summary", "Report ID", report.report_id])
            writer.writerow(["Summary", "Timestamp", report.timestamp.isoformat()])
            writer.writerow(["Summary", "Overall Status", report.summary.get('overall_status', 'UNKNOWN')])
            writer.writerow(["Summary", "Success Rate", f"{report.summary.get('success_rate', 0):.1f}%"])
            writer.writerow(["Summary", "Total Checks", report.summary.get('total_checks', 0)])
            writer.writerow(["Summary", "Critical Failures", report.summary.get('critical_failures', 0)])
            writer.writerow(["Summary", "Warnings", report.summary.get('warnings', 0)])
            writer.writerow(["Summary", "Execution Time", f"{report.summary.get('execution_time', 0):.2f}s"])

            # Write alerts
            if report.alerts:
                writer.writerow([])  # Empty row
                writer.writerow(["Alerts", "Severity", "Check Name", "Message", "Timestamp"])
                for alert in report.alerts:
                    writer.writerow([
                        "Alert",
                        alert.severity.value.upper(),
                        alert.check_name,
                        alert.message,
                        alert.timestamp.isoformat()
                    ])

    def get_active_alerts(self) -> List[ValidationAlert]:
        """Get list of currently active alerts."""
        return [alert for alert in self._active_alerts if not alert.resolved]

    def resolve_alert(self, alert_id: str, resolution_notes: str) -> bool:
        """
        Resolve an active alert.

        Args:
            alert_id: ID of alert to resolve
            resolution_notes: Notes about the resolution

        Returns:
            True if alert was found and resolved
        """
        for alert in self._active_alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolution_notes = resolution_notes
                logger.info(f"Resolved alert {alert_id}: {resolution_notes}")
                return True

        logger.warning(f"Alert {alert_id} not found in active alerts")
        return False

    def get_validation_dashboard_data(self) -> Dict[str, Any]:
        """Get data for validation dashboard display."""
        active_alerts = self.get_active_alerts()
        recent_reports = self._report_history[-10:] if self._report_history else []

        return {
            "active_alerts_count": len(active_alerts),
            "critical_alerts_count": len([a for a in active_alerts if a.severity == ValidationSeverity.CRITICAL]),
            "recent_reports_count": len(recent_reports),
            "latest_report": recent_reports[-1].to_dict() if recent_reports else None,
            "alert_summary": {
                "critical": len([a for a in active_alerts if a.severity == ValidationSeverity.CRITICAL]),
                "error": len([a for a in active_alerts if a.severity == ValidationSeverity.ERROR]),
                "warning": len([a for a in active_alerts if a.severity == ValidationSeverity.WARNING])
            },
            "performance_trends": self._get_performance_trends(),
            "data_quality_score": self._calculate_data_quality_score(),
            "last_updated": datetime.utcnow().isoformat()
        }

    def _get_performance_trends(self) -> Dict[str, Any]:
        """Get performance trends from recent reports."""
        if len(self._report_history) < 2:
            return {"insufficient_data": True}

        recent_reports = self._report_history[-5:]  # Last 5 reports

        execution_times = [r.summary.get("execution_time", 0) for r in recent_reports]
        success_rates = [r.summary.get("success_rate", 0) for r in recent_reports]

        return {
            "execution_time_trend": {
                "values": execution_times,
                "current": execution_times[-1],
                "average": sum(execution_times) / len(execution_times),
                "improving": execution_times[-1] < execution_times[-2] if len(execution_times) > 1 else None
            },
            "success_rate_trend": {
                "values": success_rates,
                "current": success_rates[-1],
                "average": sum(success_rates) / len(success_rates),
                "improving": success_rates[-1] > success_rates[-2] if len(success_rates) > 1 else None
            }
        }

    def _calculate_data_quality_score(self) -> Dict[str, Any]:
        """Calculate overall data quality score."""
        if not self._report_history:
            return {"score": 0, "grade": "N/A", "message": "No validation history available"}

        latest_report = self._report_history[-1]
        summary = latest_report.summary

        # Base score from success rate
        base_score = summary.get("success_rate", 0)

        # Penalties
        critical_penalty = summary.get("critical_failures", 0) * 20  # 20 points per critical failure
        warning_penalty = summary.get("warnings", 0) * 2  # 2 points per warning

        # Final score
        final_score = max(0, base_score - critical_penalty - warning_penalty)

        # Grade assignment
        if final_score >= 95:
            grade = "A+"
        elif final_score >= 90:
            grade = "A"
        elif final_score >= 85:
            grade = "B+"
        elif final_score >= 80:
            grade = "B"
        elif final_score >= 70:
            grade = "C"
        elif final_score >= 60:
            grade = "D"
        else:
            grade = "F"

        return {
            "score": final_score,
            "grade": grade,
            "base_score": base_score,
            "penalties": {
                "critical_failures": critical_penalty,
                "warnings": warning_penalty
            },
            "message": f"Data quality grade: {grade} ({final_score:.1f}/100)"
        }
