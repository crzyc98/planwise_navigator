#!/usr/bin/env python3
"""
from navigator_orchestrator.config import get_database_path
Standalone validation script for the promotion events fix.

This script executes the validation plan outlined in the session document,
running the MVP orchestrator pipeline, analyzing the results, and generating
a comprehensive validation report.

References:
- orchestrator_mvp/run_mvp.py
- orchestrator_mvp/core/event_emitter.py
- docs/sessions/2025/session_2025_07_18_promotion_events_fix.md
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class PromotionEventsValidator:
    """Validates the promotion events fix implementation."""

    def __init__(self, db_path: str = str(get_database_path())):
        """Initialize the validator with database connection."""
        self.db_path = db_path
        self.conn = None
        self.validation_results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "summary": {},
        }

    def connect_db(self):
        """Establish database connection."""
        self.conn = duckdb.connect(self.db_path)

    def close_db(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def run_mvp_orchestrator(self) -> Dict[str, any]:
        """Run the MVP orchestrator pipeline to generate promotion events."""
        print("Running MVP orchestrator pipeline...")
        start_time = time.time()

        try:
            # Run the MVP orchestrator
            result = subprocess.run(
                [sys.executable, "orchestrator_mvp/run_mvp.py"],
                capture_output=True,
                text=True,
                cwd=project_root,
            )

            elapsed_time = time.time() - start_time

            output_data = {
                "success": result.returncode == 0,
                "elapsed_time": elapsed_time,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

            # Parse debug output for promotion event counts
            if "Promotion Events Debug:" in result.stdout:
                debug_lines = result.stdout.split("\n")
                for i, line in enumerate(debug_lines):
                    if "Promotion Events Debug:" in line:
                        # Extract debug information
                        output_data["debug_info"] = self._parse_debug_output(
                            debug_lines[i : i + 10]
                        )
                        break

            return output_data

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "elapsed_time": time.time() - start_time,
            }

    def _parse_debug_output(self, debug_lines: List[str]) -> Dict[str, any]:
        """Parse debug output from promotion event generation."""
        debug_info = {}

        for line in debug_lines:
            if "Total eligible employees:" in line:
                debug_info["eligible_employees"] = int(line.split(":")[-1].strip())
            elif "Generated promotion events:" in line:
                debug_info["promotion_events"] = int(line.split(":")[-1].strip())
            elif "Level" in line and "eligible:" in line:
                # Parse level-specific info
                parts = line.split(",")
                for part in parts:
                    if "Level" in part and "eligible:" in part:
                        level = int(part.split()[1].strip(":"))
                        count = int(part.split()[-1])
                        debug_info[f"level_{level}_eligible"] = count

        return debug_info

    def validate_event_counts(self) -> Dict[str, any]:
        """Validate that promotion events are generated (not 0)."""
        print("Validating promotion event counts...")

        query = """
        SELECT
            COUNT(*) as total_events,
            SUM(CASE WHEN event_type = 'promotion' THEN 1 ELSE 0 END) as promotion_events
        FROM fct_yearly_events
        WHERE simulation_year = 2023
        """

        result = self.conn.execute(query).fetchone()
        total_events, promotion_events = result

        validation = {
            "test_name": "Event Count Validation",
            "passed": promotion_events > 0,
            "total_events": total_events,
            "promotion_events": promotion_events,
            "message": f"Generated {promotion_events} promotion events (expected > 0)",
        }

        if promotion_events == 0:
            validation[
                "error"
            ] = "CRITICAL: No promotion events generated (same as before fix)"

        return validation

    def check_promotion_rates(self) -> Dict[str, any]:
        """Compare actual promotion rates with expected hazard-based calculations."""
        print("Checking promotion rates by level...")

        # Query promotion events and workforce by level
        query = """
        WITH workforce_counts AS (
            SELECT
                level,
                COUNT(*) as employee_count
            FROM int_workforce_previous_year
            WHERE simulation_year = 2023
            GROUP BY level
        ),
        promotion_counts AS (
            SELECT
                JSON_EXTRACT(event_data, '$.old_level')::INTEGER as level,
                COUNT(*) as promotion_count
            FROM fct_yearly_events
            WHERE event_type = 'promotion'
            AND simulation_year = 2023
            GROUP BY JSON_EXTRACT(event_data, '$.old_level')::INTEGER
        )
        SELECT
            w.level,
            w.employee_count,
            COALESCE(p.promotion_count, 0) as promotion_count,
            COALESCE(p.promotion_count, 0) * 100.0 / w.employee_count as promotion_rate
        FROM workforce_counts w
        LEFT JOIN promotion_counts p ON w.level = p.level
        ORDER BY w.level
        """

        results = self.conn.execute(query).fetchall()

        # Expected rates from session document
        expected_rates = {
            1: (6, 8),  # Level 1: ~6-8%
            2: (5, 7),  # Level 2: ~5-7%
            3: (4, 6),  # Level 3: ~4-6%
            4: (3, 4),  # Level 4: ~3-4%
        }

        rate_validation = {
            "test_name": "Promotion Rate Validation",
            "passed": True,
            "levels": {},
        }

        for level, employee_count, promotion_count, actual_rate in results:
            expected_min, expected_max = expected_rates.get(level, (0, 100))

            level_passed = expected_min <= actual_rate <= expected_max

            rate_validation["levels"][level] = {
                "employee_count": employee_count,
                "promotion_count": promotion_count,
                "actual_rate": f"{actual_rate:.2f}%",
                "expected_range": f"{expected_min}-{expected_max}%",
                "passed": level_passed,
            }

            if not level_passed:
                rate_validation["passed"] = False

        return rate_validation

    def analyze_random_distribution(self) -> Dict[str, any]:
        """Verify that random values are properly distributed."""
        print("Analyzing random value distribution...")

        # Query a sample of random values from debug output (if available)
        # For now, we'll analyze the distribution of promotions across employees
        query = """
        WITH employee_promotions AS (
            SELECT
                JSON_EXTRACT(event_data, '$.employee_id') as employee_id,
                COUNT(*) as promotion_count
            FROM fct_yearly_events
            WHERE event_type = 'promotion'
            AND simulation_year = 2023
            GROUP BY JSON_EXTRACT(event_data, '$.employee_id')
        )
        SELECT
            COUNT(DISTINCT employee_id) as unique_promoted_employees,
            MAX(promotion_count) as max_promotions_per_employee,
            AVG(promotion_count) as avg_promotions_per_employee
        FROM employee_promotions
        """

        result = self.conn.execute(query).fetchone()
        unique_promoted, max_promotions, avg_promotions = result

        distribution_validation = {
            "test_name": "Random Distribution Analysis",
            "passed": True,
            "unique_promoted_employees": unique_promoted,
            "max_promotions_per_employee": max_promotions,
            "avg_promotions_per_employee": f"{avg_promotions:.2f}",
        }

        # Validate that no employee gets promoted multiple times in same year
        if max_promotions > 1:
            distribution_validation["passed"] = False
            distribution_validation[
                "error"
            ] = f"Employee promoted {max_promotions} times in same year"

        return distribution_validation

    def validate_database_storage(self) -> Dict[str, any]:
        """Query the database to confirm promotion events are stored with proper structure."""
        print("Validating database storage...")

        # Check event structure
        query = """
        SELECT
            event_id,
            employee_id,
            event_type,
            event_date,
            simulation_year,
            scenario_id,
            event_data
        FROM fct_yearly_events
        WHERE event_type = 'promotion'
        AND simulation_year = 2023
        LIMIT 5
        """

        sample_events = self.conn.execute(query).fetchall()

        storage_validation = {
            "test_name": "Database Storage Validation",
            "passed": True,
            "sample_count": len(sample_events),
            "issues": [],
        }

        # Validate each sample event
        for event in sample_events:
            (
                event_id,
                employee_id,
                event_type,
                event_date,
                sim_year,
                scenario_id,
                event_data,
            ) = event

            # Parse event_data JSON
            try:
                data = json.loads(event_data)

                # Check required fields
                required_fields = [
                    "old_level",
                    "new_level",
                    "old_salary",
                    "new_salary",
                    "promotion_percentage",
                ]
                for field in required_fields:
                    if field not in data:
                        storage_validation["issues"].append(
                            f"Missing field '{field}' in event {event_id}"
                        )
                        storage_validation["passed"] = False

                # Validate data integrity
                if "old_level" in data and "new_level" in data:
                    if data["new_level"] != data["old_level"] + 1:
                        storage_validation["issues"].append(
                            f"Invalid level progression in event {event_id}"
                        )
                        storage_validation["passed"] = False

                if "old_salary" in data and "new_salary" in data:
                    if data["new_salary"] <= data["old_salary"]:
                        storage_validation["issues"].append(
                            f"Invalid salary change in event {event_id}"
                        )
                        storage_validation["passed"] = False

            except json.JSONDecodeError:
                storage_validation["issues"].append(f"Invalid JSON in event {event_id}")
                storage_validation["passed"] = False

        return storage_validation

    def generate_validation_report(self, output_path: Optional[str] = None) -> str:
        """Generate a comprehensive validation report."""
        print("Generating validation report...")

        # Build report content
        report_lines = [
            "# Promotion Events Fix Validation Report",
            f"\nGenerated: {self.validation_results['timestamp']}",
            "\n## Executive Summary",
            "",
        ]

        # Calculate overall pass/fail
        all_passed = all(
            test.get("passed", False)
            for test in self.validation_results["tests"].values()
        )

        if all_passed:
            report_lines.append("✅ **ALL VALIDATION TESTS PASSED**")
            report_lines.append("\nThe promotion events fix is working correctly.")
        else:
            report_lines.append("❌ **VALIDATION FAILED**")
            failed_tests = [
                name
                for name, test in self.validation_results["tests"].items()
                if not test.get("passed", False)
            ]
            report_lines.append(f"\nFailed tests: {', '.join(failed_tests)}")

        # Add test results
        report_lines.extend(["\n## Test Results", ""])

        for test_name, test_result in self.validation_results["tests"].items():
            status = "✅ PASSED" if test_result.get("passed", False) else "❌ FAILED"
            report_lines.append(
                f"### {test_result.get('test_name', test_name)}: {status}"
            )

            # Add test-specific details
            if test_name == "orchestrator_run":
                if test_result.get("success"):
                    report_lines.append(
                        f"- Execution time: {test_result.get('elapsed_time', 0):.2f} seconds"
                    )
                    if "debug_info" in test_result:
                        debug = test_result["debug_info"]
                        report_lines.append(
                            f"- Eligible employees: {debug.get('eligible_employees', 'N/A')}"
                        )
                        report_lines.append(
                            f"- Generated promotions: {debug.get('promotion_events', 'N/A')}"
                        )
                else:
                    report_lines.append(
                        f"- Error: {test_result.get('error', 'Unknown error')}"
                    )

            elif test_name == "event_counts":
                report_lines.append(
                    f"- Total events: {test_result.get('total_events', 0):,}"
                )
                report_lines.append(
                    f"- Promotion events: {test_result.get('promotion_events', 0):,}"
                )
                if "error" in test_result:
                    report_lines.append(f"- ⚠️ {test_result['error']}")

            elif test_name == "promotion_rates":
                report_lines.append(
                    "\n| Level | Employees | Promotions | Actual Rate | Expected Range | Status |"
                )
                report_lines.append(
                    "|-------|-----------|------------|-------------|----------------|--------|"
                )

                for level, data in sorted(test_result.get("levels", {}).items()):
                    status = "✅" if data["passed"] else "❌"
                    report_lines.append(
                        f"| {level} | {data['employee_count']:,} | {data['promotion_count']:,} | "
                        f"{data['actual_rate']} | {data['expected_range']} | {status} |"
                    )

            elif test_name == "random_distribution":
                report_lines.append(
                    f"- Unique promoted employees: {test_result.get('unique_promoted_employees', 0):,}"
                )
                report_lines.append(
                    f"- Max promotions per employee: {test_result.get('max_promotions_per_employee', 0)}"
                )
                if "error" in test_result:
                    report_lines.append(f"- ⚠️ {test_result['error']}")

            elif test_name == "database_storage":
                report_lines.append(
                    f"- Sample events checked: {test_result.get('sample_count', 0)}"
                )
                if test_result.get("issues"):
                    report_lines.append("- Issues found:")
                    for issue in test_result["issues"]:
                        report_lines.append(f"  - {issue}")
                else:
                    report_lines.append("- No issues found")

            report_lines.append("")

        # Add recommendations
        report_lines.extend(["\n## Recommendations", ""])

        if all_passed:
            report_lines.extend(
                [
                    "1. The promotion events fix is working correctly and can be deployed.",
                    "2. Continue monitoring promotion rates to ensure they remain within expected ranges.",
                    "3. Consider implementing automated alerts for significant deviations from expected rates.",
                ]
            )
        else:
            report_lines.extend(
                [
                    "1. Review the failed tests and debug the specific issues identified.",
                    "2. Check the session document for the original implementation details.",
                    "3. Verify that all seed data (promotion hazard configuration) is loaded correctly.",
                    "4. Ensure the correct workforce source (int_workforce_previous_year) is being used.",
                ]
            )

        # Build final report
        report_content = "\n".join(report_lines)

        # Save report if output path provided
        if output_path:
            with open(output_path, "w") as f:
                f.write(report_content)
            print(f"Report saved to: {output_path}")

        return report_content

    def run_validation(self) -> bool:
        """Run the complete validation process."""
        print("=" * 80)
        print("Promotion Events Fix Validation")
        print("=" * 80)

        try:
            # Connect to database
            self.connect_db()

            # Run MVP orchestrator
            orchestrator_result = self.run_mvp_orchestrator()
            self.validation_results["tests"]["orchestrator_run"] = orchestrator_result

            if not orchestrator_result.get("success"):
                print("❌ MVP orchestrator failed to run")
                return False

            # Run validation tests
            self.validation_results["tests"][
                "event_counts"
            ] = self.validate_event_counts()
            self.validation_results["tests"][
                "promotion_rates"
            ] = self.check_promotion_rates()
            self.validation_results["tests"][
                "random_distribution"
            ] = self.analyze_random_distribution()
            self.validation_results["tests"][
                "database_storage"
            ] = self.validate_database_storage()

            # Generate report
            report_path = (
                project_root
                / "docs"
                / "validation"
                / "promotion_events_fix_validation_results.md"
            )
            report_path.parent.mkdir(parents=True, exist_ok=True)

            report_content = self.generate_validation_report(str(report_path))

            # Print summary
            print("\n" + "=" * 80)
            print("VALIDATION SUMMARY")
            print("=" * 80)

            all_passed = all(
                test.get("passed", False)
                for test in self.validation_results["tests"].values()
            )

            if all_passed:
                print("✅ ALL TESTS PASSED - Promotion events fix is working correctly!")
            else:
                print("❌ VALIDATION FAILED - See report for details")
                failed_tests = [
                    test["test_name"]
                    for test in self.validation_results["tests"].values()
                    if not test.get("passed", False)
                ]
                print(f"Failed tests: {', '.join(failed_tests)}")

            print(f"\nDetailed report saved to: {report_path}")

            return all_passed

        except Exception as e:
            print(f"❌ Validation error: {str(e)}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            self.close_db()


def main():
    """Main entry point for the validation script."""
    validator = PromotionEventsValidator()
    success = validator.run_validation()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
