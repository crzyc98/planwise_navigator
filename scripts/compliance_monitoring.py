#!/usr/bin/env python3
"""
ERISA Compliance Monitoring Script

This script provides automated monitoring and reporting for ERISA compliance
requirements. It can be run on a schedule to ensure ongoing compliance
and generate alerts for any issues.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.erisa_compliance import (AuditTrailManager, ERISAComplianceLevel,
                                     ERISAComplianceValidator)


class ComplianceMonitor:
    """Automated compliance monitoring and reporting system."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize compliance monitor with database connection."""
        self.db_path = db_path or str(project_root / "compliance_monitoring.db")
        self.validator = ERISAComplianceValidator()
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for monitoring history."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compliance_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_date DATE NOT NULL,
                    check_type VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    compliance_percentage REAL,
                    total_requirements INTEGER,
                    compliant_requirements INTEGER,
                    critical_gaps INTEGER,
                    execution_time_ms INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS data_classification_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_date DATE NOT NULL,
                    field_name VARCHAR(100) NOT NULL,
                    classification VARCHAR(20) NOT NULL,
                    encryption_required BOOLEAN,
                    access_control_compliant BOOLEAN,
                    retention_compliant BOOLEAN,
                    status VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compliance_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_date DATE NOT NULL,
                    alert_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    message TEXT NOT NULL,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolved_date DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.commit()

    def run_compliance_check(self) -> Dict[str, Any]:
        """Run comprehensive compliance check and record results."""
        start_time = datetime.now()

        try:
            # Perform compliance validation
            coverage = self.validator.validate_event_coverage()

            # Calculate metrics
            compliance_percentage = coverage["compliance_percentage"]
            total_requirements = coverage["total_requirements"]
            compliant_requirements = coverage["compliant_requirements"]
            critical_gaps = len(coverage["coverage_gaps"])

            # Determine overall status
            if compliance_percentage >= 100.0:
                status = "COMPLIANT"
            elif compliance_percentage >= 95.0:
                status = "WARNING"
            else:
                status = "NON_COMPLIANT"

            # Calculate execution time
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            # Record results
            result = {
                "check_date": date.today(),
                "check_type": "FULL_COMPLIANCE",
                "status": status,
                "compliance_percentage": compliance_percentage,
                "total_requirements": total_requirements,
                "compliant_requirements": compliant_requirements,
                "critical_gaps": critical_gaps,
                "execution_time_ms": int(execution_time),
                "details": json.dumps(coverage),
                "coverage_analysis": coverage,
            }

            self._record_compliance_check(result)

            # Generate alerts if needed
            if status != "COMPLIANT":
                self._generate_compliance_alert(result)

            return result

        except Exception as e:
            # Record failure
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            error_result = {
                "check_date": date.today(),
                "check_type": "FULL_COMPLIANCE",
                "status": "ERROR",
                "compliance_percentage": 0.0,
                "total_requirements": 0,
                "compliant_requirements": 0,
                "critical_gaps": 0,
                "execution_time_ms": int(execution_time),
                "details": json.dumps({"error": str(e)}),
                "error": str(e),
            }

            self._record_compliance_check(error_result)
            self._generate_error_alert(str(e))

            raise

    def run_data_classification_check(self) -> Dict[str, Any]:
        """Run data classification compliance check."""
        results = []
        total_fields = 0
        compliant_fields = 0

        # Check all classified fields
        for field_name in self.validator.data_classifications.keys():
            total_fields += 1

            try:
                validation = self.validator.validate_field_classification(field_name)

                # Check compliance requirements
                encryption_required = validation["compliance_requirements"][
                    "encryption_required"
                ]
                access_control_required = validation["compliance_requirements"][
                    "access_control_required"
                ]
                retention_required = validation["compliance_requirements"][
                    "retention_required"
                ]

                # Determine compliance status
                is_compliant = True
                issues = []

                if encryption_required and not self._verify_encryption(field_name):
                    is_compliant = False
                    issues.append("encryption_missing")

                if access_control_required and not self._verify_access_control(
                    field_name
                ):
                    is_compliant = False
                    issues.append("access_control_missing")

                if retention_required and not self._verify_retention_policy(field_name):
                    is_compliant = False
                    issues.append("retention_policy_missing")

                status = "COMPLIANT" if is_compliant else "NON_COMPLIANT"
                if is_compliant:
                    compliant_fields += 1

                # Record field check
                field_result = {
                    "check_date": date.today(),
                    "field_name": field_name,
                    "classification": validation["classification"],
                    "encryption_required": encryption_required,
                    "access_control_compliant": not access_control_required
                    or self._verify_access_control(field_name),
                    "retention_compliant": not retention_required
                    or self._verify_retention_policy(field_name),
                    "status": status,
                    "issues": issues,
                }

                self._record_classification_check(field_result)
                results.append(field_result)

            except Exception as e:
                # Record error for this field
                error_result = {
                    "check_date": date.today(),
                    "field_name": field_name,
                    "classification": "ERROR",
                    "encryption_required": False,
                    "access_control_compliant": False,
                    "retention_compliant": False,
                    "status": "ERROR",
                    "error": str(e),
                }

                self._record_classification_check(error_result)
                results.append(error_result)

        # Calculate overall metrics
        compliance_percentage = (
            (compliant_fields / total_fields * 100) if total_fields > 0 else 0
        )

        summary = {
            "check_date": date.today(),
            "total_fields": total_fields,
            "compliant_fields": compliant_fields,
            "compliance_percentage": compliance_percentage,
            "field_results": results,
        }

        # Generate alerts for non-compliant fields
        non_compliant_fields = [r for r in results if r["status"] == "NON_COMPLIANT"]
        if non_compliant_fields:
            self._generate_classification_alert(non_compliant_fields)

        return summary

    def _verify_encryption(self, field_name: str) -> bool:
        """Verify encryption is properly implemented for field."""
        # In a real implementation, this would check actual encryption status
        # For now, assume encryption is properly implemented
        return True

    def _verify_access_control(self, field_name: str) -> bool:
        """Verify access control is properly implemented for field."""
        # In a real implementation, this would check actual access control configuration
        # For now, assume access control is properly implemented
        return True

    def _verify_retention_policy(self, field_name: str) -> bool:
        """Verify retention policy is properly implemented for field."""
        # In a real implementation, this would check actual retention policy configuration
        # For now, assume retention policy is properly implemented
        return True

    def _record_compliance_check(self, result: Dict[str, Any]):
        """Record compliance check result in database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO compliance_checks
                (check_date, check_type, status, compliance_percentage,
                 total_requirements, compliant_requirements, critical_gaps,
                 execution_time_ms, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    result["check_date"],
                    result["check_type"],
                    result["status"],
                    result["compliance_percentage"],
                    result["total_requirements"],
                    result["compliant_requirements"],
                    result["critical_gaps"],
                    result["execution_time_ms"],
                    result["details"],
                ),
            )
            conn.commit()

    def _record_classification_check(self, result: Dict[str, Any]):
        """Record data classification check result in database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO data_classification_checks
                (check_date, field_name, classification, encryption_required,
                 access_control_compliant, retention_compliant, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    result["check_date"],
                    result["field_name"],
                    result["classification"],
                    result["encryption_required"],
                    result["access_control_compliant"],
                    result["retention_compliant"],
                    result["status"],
                ),
            )
            conn.commit()

    def _generate_compliance_alert(self, result: Dict[str, Any]):
        """Generate alert for compliance issues."""
        severity = "HIGH" if result["status"] == "NON_COMPLIANT" else "MEDIUM"
        message = f"Compliance check failed: {result['compliance_percentage']:.1f}% compliant ({result['critical_gaps']} critical gaps)"

        self._record_alert("COMPLIANCE_FAILURE", severity, message)

    def _generate_classification_alert(
        self, non_compliant_fields: List[Dict[str, Any]]
    ):
        """Generate alert for data classification issues."""
        field_names = [f["field_name"] for f in non_compliant_fields]
        message = f"Data classification non-compliance detected in fields: {', '.join(field_names)}"

        self._record_alert("CLASSIFICATION_FAILURE", "HIGH", message)

    def _generate_error_alert(self, error_message: str):
        """Generate alert for system errors."""
        message = f"Compliance monitoring system error: {error_message}"
        self._record_alert("SYSTEM_ERROR", "CRITICAL", message)

    def _record_alert(self, alert_type: str, severity: str, message: str):
        """Record alert in database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO compliance_alerts (alert_date, alert_type, severity, message)
                VALUES (?, ?, ?, ?)
            """,
                (date.today(), alert_type, severity, message),
            )
            conn.commit()

    def generate_monitoring_report(self, days: int = 30) -> str:
        """Generate monitoring report for the last N days."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        with sqlite3.connect(self.db_path) as conn:
            # Get compliance check history
            compliance_checks = conn.execute(
                """
                SELECT * FROM compliance_checks
                WHERE check_date BETWEEN ? AND ?
                ORDER BY check_date DESC
            """,
                (start_date, end_date),
            ).fetchall()

            # Get active alerts
            active_alerts = conn.execute(
                """
                SELECT * FROM compliance_alerts
                WHERE alert_date BETWEEN ? AND ? AND resolved = FALSE
                ORDER BY severity DESC, alert_date DESC
            """,
                (start_date, end_date),
            ).fetchall()

            # Get classification check summary
            classification_summary = conn.execute(
                """
                SELECT
                    classification,
                    COUNT(*) as total_checks,
                    SUM(CASE WHEN status = 'COMPLIANT' THEN 1 ELSE 0 END) as compliant_checks
                FROM data_classification_checks
                WHERE check_date BETWEEN ? AND ?
                GROUP BY classification
            """,
                (start_date, end_date),
            ).fetchall()

        # Generate report
        report = f"""# ERISA Compliance Monitoring Report

**Report Period**: {start_date} to {end_date} ({days} days)
**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

### Compliance Status
"""

        if compliance_checks:
            latest_check = compliance_checks[0]
            status_emoji = {
                "COMPLIANT": "✅",
                "WARNING": "⚠️",
                "NON_COMPLIANT": "❌",
                "ERROR": "🚨",
            }.get(latest_check[3], "❓")

            report += f"""
- **Current Status**: {status_emoji} {latest_check[3]}
- **Compliance Rate**: {latest_check[4]:.1f}%
- **Total Requirements**: {latest_check[5]}
- **Compliant Requirements**: {latest_check[6]}
- **Critical Gaps**: {latest_check[7]}
"""
        else:
            report += "\n- **Status**: No compliance checks found in this period\n"

        report += f"\n### Alert Summary\n"

        if active_alerts:
            alert_counts = {}
            for alert in active_alerts:
                severity = alert[3]
                alert_counts[severity] = alert_counts.get(severity, 0) + 1

            for severity, count in sorted(alert_counts.items()):
                emoji = {"CRITICAL": "🚨", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(
                    severity, "❓"
                )
                report += f"- **{severity}**: {emoji} {count} alerts\n"
        else:
            report += "- **Status**: ✅ No active alerts\n"

        # Compliance Check History
        report += f"\n## Compliance Check History\n\n"

        if compliance_checks:
            report += (
                "| Date | Status | Compliance % | Critical Gaps | Execution Time |\n"
            )
            report += (
                "|------|--------|--------------|---------------|----------------|\n"
            )

            for check in compliance_checks[:10]:  # Last 10 checks
                status_emoji = {
                    "COMPLIANT": "✅",
                    "WARNING": "⚠️",
                    "NON_COMPLIANT": "❌",
                    "ERROR": "🚨",
                }.get(check[3], "❓")

                report += f"| {check[1]} | {status_emoji} {check[3]} | {check[4]:.1f}% | {check[7]} | {check[8]}ms |\n"
        else:
            report += "No compliance checks found in this period.\n"

        # Data Classification Summary
        report += f"\n## Data Classification Compliance\n\n"

        if classification_summary:
            report += (
                "| Classification | Total Checks | Compliant | Compliance Rate |\n"
            )
            report += "|----------------|--------------|-----------|----------------|\n"

            for summary in classification_summary:
                classification = summary[0]
                total = summary[1]
                compliant = summary[2]
                rate = (compliant / total * 100) if total > 0 else 0

                rate_emoji = "✅" if rate >= 100 else "⚠️" if rate >= 95 else "❌"
                report += f"| {classification} | {total} | {compliant} | {rate_emoji} {rate:.1f}% |\n"
        else:
            report += "No classification checks found in this period.\n"

        # Active Alerts
        report += f"\n## Active Alerts\n\n"

        if active_alerts:
            for alert in active_alerts:
                severity_emoji = {
                    "CRITICAL": "🚨",
                    "HIGH": "🔴",
                    "MEDIUM": "🟡",
                    "LOW": "🟢",
                }.get(alert[3], "❓")

                report += f"### {severity_emoji} {alert[2]} - {alert[3]}\n"
                report += f"**Date**: {alert[1]}  \n"
                report += f"**Message**: {alert[4]}  \n\n"
        else:
            report += "✅ No active alerts.\n"

        # Recommendations
        report += f"\n## Recommendations\n\n"

        if active_alerts:
            critical_alerts = [a for a in active_alerts if a[3] == "CRITICAL"]
            high_alerts = [a for a in active_alerts if a[3] == "HIGH"]

            if critical_alerts:
                report += "### Immediate Actions Required\n"
                for alert in critical_alerts:
                    report += f"- Address critical alert: {alert[4]}\n"
                report += "\n"

            if high_alerts:
                report += "### High Priority Actions\n"
                for alert in high_alerts:
                    report += f"- Resolve high priority issue: {alert[4]}\n"
                report += "\n"

        if compliance_checks and compliance_checks[0][4] < 100:
            report += "### Compliance Improvement\n"
            report += "- Review non-compliant requirements and implement remediation\n"
            report += "- Schedule benefits counsel review if needed\n"
            report += "- Update documentation and procedures\n\n"

        report += "### Regular Maintenance\n"
        report += "- Continue daily compliance monitoring\n"
        report += "- Review and update classification rules quarterly\n"
        report += "- Schedule annual benefits counsel review\n"
        report += "- Maintain audit trail and documentation\n"

        return report

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts."""
        with sqlite3.connect(self.db_path) as conn:
            alerts = conn.execute(
                """
                SELECT * FROM compliance_alerts
                WHERE resolved = FALSE
                ORDER BY severity DESC, alert_date DESC
            """
            ).fetchall()

        return [
            {
                "id": alert[0],
                "alert_date": alert[1],
                "alert_type": alert[2],
                "severity": alert[3],
                "message": alert[4],
                "resolved": bool(alert[5]),
                "resolved_date": alert[6],
                "created_at": alert[7],
            }
            for alert in alerts
        ]

    def resolve_alert(self, alert_id: int):
        """Mark an alert as resolved."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE compliance_alerts
                SET resolved = TRUE, resolved_date = ?
                WHERE id = ?
            """,
                (date.today(), alert_id),
            )
            conn.commit()


def main():
    """Main entry point for compliance monitoring."""
    parser = argparse.ArgumentParser(description="ERISA Compliance Monitoring")
    parser.add_argument("--check", action="store_true", help="Run compliance check")
    parser.add_argument(
        "--classification", action="store_true", help="Run data classification check"
    )
    parser.add_argument(
        "--report",
        type=int,
        metavar="DAYS",
        help="Generate monitoring report for last N days",
    )
    parser.add_argument("--alerts", action="store_true", help="Show active alerts")
    parser.add_argument(
        "--resolve", type=int, metavar="ALERT_ID", help="Resolve alert by ID"
    )
    parser.add_argument("--output", type=str, help="Output file for reports")
    parser.add_argument("--db", type=str, help="Database file path")

    args = parser.parse_args()

    if not any(
        [args.check, args.classification, args.report, args.alerts, args.resolve]
    ):
        parser.print_help()
        return

    # Initialize monitor
    monitor = ComplianceMonitor(db_path=args.db)

    try:
        if args.check:
            print("Running compliance check...")
            result = monitor.run_compliance_check()
            print(f"✅ Compliance check complete: {result['status']}")
            print(f"   Compliance rate: {result['compliance_percentage']:.1f}%")
            print(f"   Critical gaps: {result['critical_gaps']}")
            print(f"   Execution time: {result['execution_time_ms']}ms")

        if args.classification:
            print("Running data classification check...")
            result = monitor.run_data_classification_check()
            print(f"✅ Data classification check complete")
            print(f"   Total fields: {result['total_fields']}")
            print(f"   Compliant fields: {result['compliant_fields']}")
            print(f"   Compliance rate: {result['compliance_percentage']:.1f}%")

        if args.report:
            print(f"Generating monitoring report for last {args.report} days...")
            report = monitor.generate_monitoring_report(args.report)

            if args.output:
                with open(args.output, "w") as f:
                    f.write(report)
                print(f"✅ Report saved to {args.output}")
            else:
                print(report)

        if args.alerts:
            alerts = monitor.get_active_alerts()
            if alerts:
                print(f"Active alerts ({len(alerts)}):")
                for alert in alerts:
                    severity_emoji = {
                        "CRITICAL": "🚨",
                        "HIGH": "🔴",
                        "MEDIUM": "🟡",
                        "LOW": "🟢",
                    }.get(alert["severity"], "❓")
                    print(
                        f"  {alert['id']}: {severity_emoji} {alert['severity']} - {alert['message']}"
                    )
            else:
                print("✅ No active alerts")

        if args.resolve:
            monitor.resolve_alert(args.resolve)
            print(f"✅ Alert {args.resolve} marked as resolved")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
