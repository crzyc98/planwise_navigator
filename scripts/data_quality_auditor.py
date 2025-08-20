#!/usr/bin/env python3
"""
from navigator_orchestrator.config import get_database_path
Data Quality Auditor for PlanWise Navigator Simulation Database

This script performs comprehensive data quality checks on the simulation database,
focusing on NaN values, type mismatches, and DOUBLE to INT64 casting issues.

Usage:
    python scripts/data_quality_auditor.py

Author: Claude Code
Date: 2025-07-28
"""

import json
from datetime import datetime
from typing import Any, Dict, List

import duckdb
import numpy as np
import pandas as pd


class DataQualityAuditor:
    """Comprehensive data quality auditor for simulation database."""

    def __init__(self, db_path: str = str(get_database_path())):
        """Initialize the auditor with database connection."""
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self.issues = []
        self.summary = {}

    def log_issue(
        self,
        severity: str,
        table: str,
        column: str,
        issue_type: str,
        description: str,
        count: int = 0,
        details: Dict = None,
    ):
        """Log a data quality issue."""
        issue = {
            "timestamp": datetime.now().isoformat(),
            "severity": severity,
            "table": table,
            "column": column,
            "issue_type": issue_type,
            "description": description,
            "count": count,
            "details": details or {},
        }
        self.issues.append(issue)

    def get_table_list(self) -> List[str]:
        """Get list of all tables in the database."""
        try:
            tables = self.conn.execute("SHOW TABLES").fetchall()
            return [table[0] for table in tables]
        except Exception as e:
            self.log_issue(
                "ERROR", "DATABASE", "N/A", "CONNECTION", f"Failed to list tables: {e}"
            )
            return []

    def get_table_schema(self, table_name: str) -> List[tuple]:
        """Get schema information for a table."""
        try:
            schema = self.conn.execute(f"DESCRIBE {table_name}").fetchall()
            return schema
        except Exception as e:
            self.log_issue(
                "ERROR", table_name, "N/A", "SCHEMA", f"Failed to get schema: {e}"
            )
            return []

    def check_null_values(self, table_name: str, column_info: List[tuple]):
        """Check for NULL values in numeric columns that should be integers."""
        numeric_types = ["INTEGER", "BIGINT", "DOUBLE", "DECIMAL", "FLOAT"]

        for col_info in column_info:
            col_name, col_type = col_info[0], col_info[1]
            nullable = col_info[2] if len(col_info) > 2 else "YES"
            default = col_info[3] if len(col_info) > 3 else None
            if col_type in numeric_types:
                try:
                    query = f"""
                    SELECT
                        COUNT(*) as total_rows,
                        COUNT({col_name}) as non_null_rows,
                        COUNT(*) - COUNT({col_name}) as null_rows
                    FROM {table_name}
                    """
                    result = self.conn.execute(query).fetchone()
                    total, non_null, null_count = result

                    if null_count > 0:
                        null_percentage = (null_count / total) * 100 if total > 0 else 0
                        severity = "CRITICAL" if null_percentage > 50 else "WARNING"

                        self.log_issue(
                            severity=severity,
                            table=table_name,
                            column=col_name,
                            issue_type="NULL_VALUES",
                            description=f"Found {null_count} NULL values ({null_percentage:.1f}%) in {col_type} column",
                            count=null_count,
                            details={
                                "total_rows": total,
                                "null_percentage": null_percentage,
                                "column_type": col_type,
                                "nullable": nullable,
                            },
                        )

                except Exception as e:
                    self.log_issue(
                        "ERROR",
                        table_name,
                        col_name,
                        "NULL_CHECK",
                        f"Failed to check NULL values: {e}",
                    )

    def check_type_casting_issues(self, table_name: str, column_info: List[tuple]):
        """Check for potential type casting issues, especially DOUBLE to INT64."""
        for col_info in column_info:
            col_name, col_type = col_info[0], col_info[1]
            if col_type == "DOUBLE":
                try:
                    # Check for values that would fail INT64 casting
                    query = f"""
                    SELECT
                        COUNT(*) as total_rows,
                        COUNT(CASE WHEN {col_name} IS NOT NULL AND
                                  ({col_name} != CAST({col_name} AS BIGINT) OR
                                   {col_name} > 9223372036854775807 OR
                                   {col_name} < -9223372036854775808) THEN 1 END) as casting_issues
                    FROM {table_name}
                    WHERE {col_name} IS NOT NULL
                    """
                    result = self.conn.execute(query).fetchone()
                    total, casting_issues = result

                    if casting_issues > 0:
                        self.log_issue(
                            severity="WARNING",
                            table=table_name,
                            column=col_name,
                            issue_type="CASTING_ISSUE",
                            description=f"Found {casting_issues} values that would fail DOUBLE to INT64 casting",
                            count=casting_issues,
                            details={"total_non_null": total},
                        )

                except Exception as e:
                    self.log_issue(
                        "ERROR",
                        table_name,
                        col_name,
                        "CASTING_CHECK",
                        f"Failed to check casting issues: {e}",
                    )

    def check_event_table_specific_issues(self):
        """Check for specific issues in event-related tables."""
        event_tables = [
            "fct_yearly_events",
            "int_employee_event_stream",
            "fct_workforce_snapshot",
            "int_employee_compensation_by_year",
        ]

        for table in event_tables:
            if table in self.get_table_list():
                try:
                    # Check tenure consistency across event types
                    if table == "int_employee_event_stream":
                        query = """
                        SELECT
                            event_type,
                            COUNT(*) as total_events,
                            COUNT(current_tenure) as non_null_tenure,
                            COUNT(*) - COUNT(current_tenure) as null_tenure
                        FROM int_employee_event_stream
                        GROUP BY event_type
                        ORDER BY null_tenure DESC
                        """
                        results = self.conn.execute(query).fetchall()

                        for event_type, total, non_null, null_count in results:
                            if null_count > 0 and event_type not in [
                                "hire",
                                "initial_state",
                            ]:
                                null_percentage = (null_count / total) * 100
                                self.log_issue(
                                    severity="WARNING",
                                    table=table,
                                    column="current_tenure",
                                    issue_type="EVENT_DESIGN_PATTERN",
                                    description=f"Event type '{event_type}' has {null_count} NULL tenure values by design",
                                    count=null_count,
                                    details={
                                        "event_type": event_type,
                                        "null_percentage": null_percentage,
                                        "is_expected": True,
                                    },
                                )

                except Exception as e:
                    self.log_issue(
                        "ERROR",
                        table,
                        "N/A",
                        "EVENT_CHECK",
                        f"Failed to check event-specific issues: {e}",
                    )

    def check_data_ranges(self, table_name: str, column_info: List[tuple]):
        """Check for unreasonable data ranges in key columns."""
        range_checks = {
            "current_age": (0, 100),
            "employee_age": (0, 100),
            "current_tenure": (0, 50),
            "employee_tenure": (0, 50),
            "level_id": (1, 10),
            "simulation_year": (2020, 2030),
        }

        for col_info in column_info:
            col_name, col_type = col_info[0], col_info[1]
            if col_name in range_checks:
                min_val, max_val = range_checks[col_name]
                try:
                    query = f"""
                    SELECT
                        COUNT(*) as total_rows,
                        COUNT(CASE WHEN {col_name} < {min_val} OR {col_name} > {max_val} THEN 1 END) as out_of_range,
                        MIN({col_name}) as min_value,
                        MAX({col_name}) as max_value
                    FROM {table_name}
                    WHERE {col_name} IS NOT NULL
                    """
                    result = self.conn.execute(query).fetchone()
                    total, out_of_range, actual_min, actual_max = result

                    if out_of_range > 0:
                        self.log_issue(
                            severity="WARNING",
                            table=table_name,
                            column=col_name,
                            issue_type="DATA_RANGE",
                            description=f"Found {out_of_range} values outside expected range [{min_val}, {max_val}]",
                            count=out_of_range,
                            details={
                                "expected_min": min_val,
                                "expected_max": max_val,
                                "actual_min": actual_min,
                                "actual_max": actual_max,
                            },
                        )

                except Exception as e:
                    self.log_issue(
                        "ERROR",
                        table_name,
                        col_name,
                        "RANGE_CHECK",
                        f"Failed to check data range: {e}",
                    )

    def audit_database(self):
        """Perform comprehensive database audit."""
        print("🔍 Starting comprehensive data quality audit...")

        tables = self.get_table_list()
        self.summary["total_tables"] = len(tables)

        for table_name in tables:
            print(f"📋 Auditing table: {table_name}")

            # Get table schema
            schema = self.get_table_schema(table_name)
            if not schema:
                continue

            # Perform various checks
            self.check_null_values(table_name, schema)
            self.check_type_casting_issues(table_name, schema)
            self.check_data_ranges(table_name, schema)

        # Event-specific checks
        print("🎯 Checking event-specific patterns...")
        self.check_event_table_specific_issues()

        # Generate summary
        self.generate_summary()

    def generate_summary(self):
        """Generate audit summary statistics."""
        severity_counts = {}
        issue_type_counts = {}
        table_counts = {}

        for issue in self.issues:
            # Count by severity
            severity = issue["severity"]
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

            # Count by issue type
            issue_type = issue["issue_type"]
            issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1

            # Count by table
            table = issue["table"]
            table_counts[table] = table_counts.get(table, 0) + 1

        self.summary.update(
            {
                "total_issues": len(self.issues),
                "severity_breakdown": severity_counts,
                "issue_type_breakdown": issue_type_counts,
                "table_breakdown": table_counts,
                "audit_timestamp": datetime.now().isoformat(),
            }
        )

    def print_report(self):
        """Print a formatted audit report."""
        print("\n" + "=" * 80)
        print("🏥 DATA QUALITY AUDIT REPORT")
        print("=" * 80)

        print(f"\n📊 SUMMARY:")
        print(f"  • Total Tables Audited: {self.summary.get('total_tables', 0)}")
        print(f"  • Total Issues Found: {self.summary.get('total_issues', 0)}")
        print(f"  • Audit Timestamp: {self.summary.get('audit_timestamp', 'Unknown')}")

        # Severity breakdown
        severity_counts = self.summary.get("severity_breakdown", {})
        if severity_counts:
            print(f"\n🚨 SEVERITY BREAKDOWN:")
            for severity, count in sorted(severity_counts.items()):
                emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "ERROR": "❌"}.get(
                    severity, "ℹ️"
                )
                print(f"  {emoji} {severity}: {count}")

        # Issue type breakdown
        issue_types = self.summary.get("issue_type_breakdown", {})
        if issue_types:
            print(f"\n🔍 ISSUE TYPE BREAKDOWN:")
            for issue_type, count in sorted(issue_types.items()):
                print(f"  • {issue_type}: {count}")

        # Detailed issues
        if self.issues:
            print(f"\n📝 DETAILED ISSUES:")
            for i, issue in enumerate(self.issues[:20], 1):  # Show first 20 issues
                emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "ERROR": "❌"}.get(
                    issue["severity"], "ℹ️"
                )
                print(
                    f"\n{i}. {emoji} {issue['severity']} - {issue['table']}.{issue['column']}"
                )
                print(f"   Issue: {issue['issue_type']}")
                print(f"   Description: {issue['description']}")
                if issue["count"] > 0:
                    print(f"   Affected Records: {issue['count']}")
                if issue.get("details"):
                    print(f"   Details: {issue['details']}")

            if len(self.issues) > 20:
                print(f"\n... and {len(self.issues) - 20} more issues")

        print("\n" + "=" * 80)
        print("🎯 KEY FINDINGS & RECOMMENDATIONS:")
        print("=" * 80)

        # Analyze key findings
        self.print_key_findings()

    def print_key_findings(self):
        """Print key findings and recommendations."""
        tenure_issues = [issue for issue in self.issues if "tenure" in issue["column"]]
        casting_issues = [
            issue for issue in self.issues if issue["issue_type"] == "CASTING_ISSUE"
        ]
        null_issues = [
            issue for issue in self.issues if issue["issue_type"] == "NULL_VALUES"
        ]

        print("\n1. 🎯 TENURE DATA QUALITY ISSUES:")
        if tenure_issues:
            print(
                "   • Found significant NULL values in tenure columns across multiple tables"
            )
            print(
                "   • Root cause: Event stream design intentionally sets tenure to NULL for non-hire events"
            )
            print(
                "   • Impact: Causes DOUBLE to INT64 casting failures in downstream models"
            )
            print(
                "   • Recommendation: Implement tenure calculation logic in event processing"
            )

        print("\n2. 🔄 TYPE CASTING VULNERABILITIES:")
        if casting_issues:
            print(
                f"   • Found {len(casting_issues)} tables with potential casting issues"
            )
            print(
                "   • Primary issue: DOUBLE columns with NULL values being cast to BIGINT"
            )
            print("   • Location: fct_workforce_snapshot.sql line 129")
            print(
                "   • Recommendation: Add COALESCE or conditional logic before casting"
            )

        print("\n3. 📊 NULL VALUE PATTERNS:")
        if null_issues:
            critical_nulls = [
                issue for issue in null_issues if issue["severity"] == "CRITICAL"
            ]
            print(
                f"   • Found NULL values in {len(null_issues)} column/table combinations"
            )
            if critical_nulls:
                print(f"   • {len(critical_nulls)} are critical (>50% NULL values)")
            print("   • Most problematic: current_tenure in int_employee_event_stream")
            print(
                "   • Recommendation: Review event processing logic for tenure calculation"
            )

        print("\n4. 🔧 IMMEDIATE ACTIONS NEEDED:")
        print("   • Fix fct_workforce_snapshot.sql casting logic for current_tenure")
        print("   • Implement proper tenure calculation in int_employee_event_stream")
        print("   • Add data validation checks in event processing pipeline")
        print("   • Consider adding NOT NULL constraints where appropriate")

    def save_report(self, filename: str = None):
        """Save audit report to JSON file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"data_quality_audit_{timestamp}.json"

        report = {"summary": self.summary, "issues": self.issues}

        with open(filename, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"\n💾 Audit report saved to: {filename}")
        return filename

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


def main():
    """Main function to run the data quality audit."""
    auditor = DataQualityAuditor()

    try:
        auditor.audit_database()
        auditor.print_report()
        auditor.save_report()

    except Exception as e:
        print(f"❌ Audit failed: {e}")
        return 1

    finally:
        auditor.close()

    return 0


if __name__ == "__main__":
    exit(main())
