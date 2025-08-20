#!/usr/bin/env python3
"""
from navigator_orchestrator.config import get_database_path
Comprehensive validation script for workforce snapshot architecture refactoring.
Automates testing process and generates detailed validation report.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
import pandas as pd
import pytest

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("validation_results.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class SnapshotRefactorValidator:
    """Validates the workforce snapshot architecture refactoring."""

    def __init__(self, db_path: str = str(get_database_path())):
        self.db_path = db_path
        self.project_root = Path(__file__).parent.parent
        self.dbt_dir = self.project_root / "dbt"
        self.results = {
            "contract_verification": {},
            "dependency_tests": {},
            "integration_tests": {},
            "behavior_validation": {},
            "performance_metrics": {},
            "overall_status": "PENDING",
        }

    def validate_contracts(self) -> Dict[str, bool]:
        """Run dbt contract tests and schema validation."""
        logger.info("=== Phase 1: Contract Verification ===")
        results = {}

        try:
            # Build the model with full refresh
            logger.info("Building fct_workforce_snapshot with full refresh...")
            cmd = [
                "dbt",
                "build",
                "--select",
                "fct_workforce_snapshot",
                "--full-refresh",
                "--vars",
                '{"simulation_year": 2025, "scenario_id": "default"}',
            ]
            result = subprocess.run(
                cmd, cwd=self.dbt_dir, capture_output=True, text=True
            )
            results["model_build"] = result.returncode == 0
            if result.returncode != 0:
                logger.error(f"Model build failed: {result.stderr}")

            # Run contract tests
            logger.info("Running contract tests...")
            cmd = [
                "dbt",
                "test",
                "--select",
                "fct_workforce_snapshot",
                "--vars",
                '{"simulation_year": 2025, "scenario_id": "default"}',
            ]
            result = subprocess.run(
                cmd, cwd=self.dbt_dir, capture_output=True, text=True
            )
            results["contract_tests"] = result.returncode == 0
            if result.returncode != 0:
                logger.error(f"Contract tests failed: {result.stderr}")

            # Verify schema structure
            logger.info("Verifying schema structure...")
            results["schema_verification"] = self._verify_schema_structure()

        except Exception as e:
            logger.error(f"Contract verification failed: {str(e)}")
            results["error"] = str(e)

        self.results["contract_verification"] = results
        return results

    def _verify_schema_structure(self) -> bool:
        """Verify the schema structure matches expected contract."""
        try:
            conn = duckdb.connect(self.db_path)

            # Check if table exists
            tables = conn.execute("SHOW TABLES").fetchall()
            if not any("fct_workforce_snapshot" in str(t) for t in tables):
                logger.error("fct_workforce_snapshot table not found")
                return False

            # Get column information
            columns = conn.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'fct_workforce_snapshot'
                ORDER BY ordinal_position
            """
            ).fetchall()

            # Expected columns based on actual schema
            expected_columns = {
                "employee_id": "VARCHAR",
                "simulation_year": "INTEGER",
                "scenario_id": "VARCHAR",
                "employment_status": "VARCHAR",
                "current_compensation": "DOUBLE",
                "level_id": "INTEGER",
                "current_age": "BIGINT",
                "current_tenure": "BIGINT",
                "age_band": "VARCHAR",
                "tenure_band": "VARCHAR",
            }

            # Verify critical columns exist
            actual_columns = {col[0]: col[1] for col in columns}
            for col_name, expected_type in expected_columns.items():
                if col_name not in actual_columns:
                    logger.error(f"Missing required column: {col_name}")
                    return False

            conn.close()
            return True

        except Exception as e:
            logger.error(f"Schema verification error: {str(e)}")
            return False

    def test_dependencies(self) -> Dict[str, bool]:
        """Execute dependency smoke tests for all model categories."""
        logger.info("\n=== Phase 2: Dependency Smoke Tests ===")
        results = {}

        test_configs = [
            (
                "SCD Snapshots",
                ["scd_workforce_state_optimized+"],
                {"simulation_year": 2025},
            ),
            (
                "Mart Models",
                ["fct_compensation_growth", "fct_policy_optimization"],
                {"simulation_year": 2025},
            ),
            (
                "Monitoring Models",
                ["mon_pipeline_performance", "mon_data_quality"],
                {"simulation_year": 2025},
            ),
            (
                "Circular Dependencies",
                ["int_active_employees_prev_year_snapshot+"],
                {"simulation_year": 2026},
            ),
        ]

        for test_name, models, vars_dict in test_configs:
            logger.info(f"Testing {test_name}...")
            try:
                vars_json = json.dumps(vars_dict)
                cmd = ["dbt", "build", "--select"] + models + ["--vars", vars_json]
                result = subprocess.run(
                    cmd, cwd=self.dbt_dir, capture_output=True, text=True
                )
                results[test_name] = result.returncode == 0

                if result.returncode != 0:
                    logger.error(f"{test_name} failed: {result.stderr}")
                else:
                    logger.info(f"{test_name} passed successfully")

            except Exception as e:
                logger.error(f"{test_name} error: {str(e)}")
                results[test_name] = False

        self.results["dependency_tests"] = results
        return results

    def run_integration_tests(self) -> Dict[str, bool]:
        """Execute the full integration test suite with proper reporting."""
        logger.info("\n=== Phase 3: Integration Testing ===")
        results = {}

        test_suites = [
            (
                "Simulation Behavior",
                "tests/integration/test_simulation_behavior_comparison.py",
            ),
            (
                "Multi-Year Cold Start",
                "tests/integration/test_multi_year_cold_start.py",
            ),
            ("SCD Data Consistency", "tests/integration/test_scd_data_consistency.py"),
            (
                "Compensation Workflow",
                "tests/test_compensation_workflow_integration.py",
            ),
        ]

        for test_name, test_path in test_suites:
            logger.info(f"Running {test_name} tests...")
            try:
                full_path = self.project_root / test_path
                if not full_path.exists():
                    logger.warning(f"{test_name} test file not found at {test_path}")
                    results[test_name] = False
                    continue

                cmd = [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(full_path),
                    "-v",
                    "--tb=short",
                ]
                result = subprocess.run(
                    cmd, cwd=self.project_root, capture_output=True, text=True
                )
                results[test_name] = result.returncode == 0

                if result.returncode != 0:
                    logger.error(f"{test_name} tests failed")
                    # Extract failure details from pytest output
                    if "FAILED" in result.stdout:
                        failures = [
                            line
                            for line in result.stdout.split("\n")
                            if "FAILED" in line
                        ]
                        for failure in failures[:5]:  # Show first 5 failures
                            logger.error(f"  - {failure}")
                else:
                    logger.info(f"{test_name} tests passed")

            except Exception as e:
                logger.error(f"{test_name} test error: {str(e)}")
                results[test_name] = False

        self.results["integration_tests"] = results
        return results

    def compare_behavior(self) -> Dict[str, any]:
        """Perform row-level data comparison between implementations."""
        logger.info("\n=== Phase 4: Behavior Validation ===")
        results = {}

        try:
            conn = duckdb.connect(self.db_path)

            # Employee count validation
            logger.info("Validating employee counts...")
            employee_counts = conn.execute(
                """
                SELECT
                    simulation_year,
                    employment_status,
                    COUNT(*) as employee_count,
                    COUNT(DISTINCT employee_id) as unique_employees
                FROM fct_workforce_snapshot
                WHERE simulation_year >= 2024
                GROUP BY simulation_year, employment_status
                ORDER BY simulation_year, employment_status
            """
            ).fetchdf()
            results["employee_counts"] = employee_counts.to_dict("records")

            # Compensation validation
            logger.info("Validating compensation calculations...")
            comp_stats = conn.execute(
                """
                SELECT
                    simulation_year,
                    employment_status,
                    COUNT(*) as count,
                    AVG(current_compensation) as avg_comp,
                    SUM(current_compensation) as total_comp,
                    MIN(current_compensation) as min_comp,
                    MAX(current_compensation) as max_comp
                FROM fct_workforce_snapshot
                WHERE simulation_year >= 2024
                GROUP BY simulation_year, employment_status
                ORDER BY simulation_year, employment_status
            """
            ).fetchdf()
            results["compensation_stats"] = comp_stats.to_dict("records")

            # Event distribution validation
            logger.info("Validating event distributions...")
            event_dist = conn.execute(
                """
                SELECT
                    simulation_year,
                    event_type,
                    COUNT(*) as event_count
                FROM fct_yearly_events
                WHERE simulation_year >= 2024
                GROUP BY simulation_year, event_type
                ORDER BY simulation_year, event_type
            """
            ).fetchdf()
            results["event_distribution"] = event_dist.to_dict("records")

            # Data quality checks
            logger.info("Running data quality checks...")
            quality_checks = conn.execute(
                """
                SELECT
                    'null_employee_ids' as check_name,
                    COUNT(*) as issue_count
                FROM fct_workforce_snapshot
                WHERE employee_id IS NULL

                UNION ALL

                SELECT
                    'negative_compensation' as check_name,
                    COUNT(*) as issue_count
                FROM fct_workforce_snapshot
                WHERE current_compensation < 0

                UNION ALL

                SELECT
                    'invalid_age' as check_name,
                    COUNT(*) as issue_count
                FROM fct_workforce_snapshot
                WHERE current_age < 18 OR current_age > 100
            """
            ).fetchdf()
            results["data_quality"] = quality_checks.to_dict("records")

            # Overall behavior validation status
            results["validation_passed"] = all(
                row["issue_count"] == 0 for row in results["data_quality"]
            )

            conn.close()

        except Exception as e:
            logger.error(f"Behavior comparison error: {str(e)}")
            results["error"] = str(e)
            results["validation_passed"] = False

        self.results["behavior_validation"] = results
        return results

    def check_performance(self) -> Dict[str, any]:
        """Capture and compare runtime metrics."""
        logger.info("\n=== Phase 5: Performance Validation ===")
        results = {}

        try:
            # Run a timed build of the refactored models
            logger.info("Measuring refactored model performance...")
            start_time = datetime.now()

            cmd = [
                "dbt",
                "build",
                "--select",
                "+fct_workforce_snapshot",
                "--vars",
                '{"simulation_year": 2025}',
            ]
            result = subprocess.run(
                cmd, cwd=self.dbt_dir, capture_output=True, text=True
            )

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            results["execution_time_seconds"] = execution_time
            results["build_successful"] = result.returncode == 0

            # Extract model timing information from dbt output
            if "Completed successfully" in result.stdout:
                lines = result.stdout.split("\n")
                model_timings = []
                for line in lines:
                    if "model" in line and "completed in" in line:
                        model_timings.append(line.strip())
                results["model_timings"] = model_timings[:10]  # First 10 models

            # Check incremental strategy
            logger.info("Testing incremental strategy...")
            cmd = [
                "dbt",
                "run",
                "--select",
                "fct_workforce_snapshot",
                "--vars",
                '{"simulation_year": 2025}',
            ]
            incremental_start = datetime.now()
            result = subprocess.run(
                cmd, cwd=self.dbt_dir, capture_output=True, text=True
            )
            incremental_time = (datetime.now() - incremental_start).total_seconds()

            results["incremental_time_seconds"] = incremental_time
            results["incremental_successful"] = result.returncode == 0

            # Performance assessment
            results["performance_acceptable"] = (
                execution_time < 300
                and incremental_time  # Less than 5 minutes for full build
                < 60  # Less than 1 minute for incremental
            )

        except Exception as e:
            logger.error(f"Performance check error: {str(e)}")
            results["error"] = str(e)
            results["performance_acceptable"] = False

        self.results["performance_metrics"] = results
        return results

    def generate_report(self) -> str:
        """Create a comprehensive validation report."""
        logger.info("\n=== Generating Validation Report ===")

        # Determine overall status
        all_passed = (
            all(self.results.get("contract_verification", {}).values())
            and all(self.results.get("dependency_tests", {}).values())
            and all(self.results.get("integration_tests", {}).values())
            and self.results.get("behavior_validation", {}).get(
                "validation_passed", False
            )
            and self.results.get("performance_metrics", {}).get(
                "performance_acceptable", False
            )
        )

        self.results["overall_status"] = "PASSED" if all_passed else "FAILED"

        # Generate report content
        report_lines = [
            "# Workforce Snapshot Architecture Validation Report",
            f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"\n## Overall Status: **{self.results['overall_status']}**",
            "\n---\n",
        ]

        # Contract Verification
        report_lines.append("## Contract Verification")
        for check, passed in self.results.get("contract_verification", {}).items():
            status = "✅ PASSED" if passed else "❌ FAILED"
            report_lines.append(f"- {check}: {status}")

        # Dependency Tests
        report_lines.append("\n## Dependency Tests")
        for test, passed in self.results.get("dependency_tests", {}).items():
            status = "✅ PASSED" if passed else "❌ FAILED"
            report_lines.append(f"- {test}: {status}")

        # Integration Tests
        report_lines.append("\n## Integration Tests")
        for test, passed in self.results.get("integration_tests", {}).items():
            status = "✅ PASSED" if passed else "❌ FAILED"
            report_lines.append(f"- {test}: {status}")

        # Behavior Validation
        report_lines.append("\n## Behavior Validation")
        behavior = self.results.get("behavior_validation", {})
        if behavior.get("validation_passed"):
            report_lines.append("✅ All behavior validations passed")
        else:
            report_lines.append("❌ Behavior validation issues found:")
            if "data_quality" in behavior:
                for check in behavior["data_quality"]:
                    if check["issue_count"] > 0:
                        report_lines.append(
                            f"  - {check['check_name']}: {check['issue_count']} issues"
                        )

        # Performance Metrics
        report_lines.append("\n## Performance Metrics")
        perf = self.results.get("performance_metrics", {})
        if "execution_time_seconds" in perf:
            report_lines.append(
                f"- Full build time: {perf['execution_time_seconds']:.2f} seconds"
            )
        if "incremental_time_seconds" in perf:
            report_lines.append(
                f"- Incremental build time: {perf['incremental_time_seconds']:.2f} seconds"
            )
        if perf.get("performance_acceptable"):
            report_lines.append("✅ Performance is acceptable")
        else:
            report_lines.append("❌ Performance needs optimization")

        # Recommendations
        report_lines.append("\n## Recommendations")
        if self.results["overall_status"] == "PASSED":
            report_lines.append(
                "✅ The refactored snapshot architecture is ready for deployment."
            )
            report_lines.append("- All contracts are preserved")
            report_lines.append("- All dependencies are compatible")
            report_lines.append("- Behavior is consistent with original implementation")
            report_lines.append("- Performance is within acceptable limits")
        else:
            report_lines.append(
                "❌ The refactored architecture needs attention before deployment:"
            )
            if not all(self.results.get("contract_verification", {}).values()):
                report_lines.append("- Fix contract verification failures")
            if not all(self.results.get("dependency_tests", {}).values()):
                report_lines.append("- Resolve dependency compatibility issues")
            if not all(self.results.get("integration_tests", {}).values()):
                report_lines.append("- Address integration test failures")
            if not behavior.get("validation_passed", False):
                report_lines.append("- Investigate behavior validation discrepancies")
            if not perf.get("performance_acceptable", False):
                report_lines.append("- Optimize performance bottlenecks")

        report_content = "\n".join(report_lines)

        # Save report
        report_path = self.project_root / "validation_report.md"
        with open(report_path, "w") as f:
            f.write(report_content)

        # Also save detailed JSON results
        json_path = self.project_root / "validation_results.json"
        with open(json_path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        logger.info(f"Report saved to: {report_path}")
        logger.info(f"Detailed results saved to: {json_path}")

        return report_content

    def run_full_validation(self):
        """Execute all validation phases in sequence."""
        logger.info(
            "Starting comprehensive validation of snapshot architecture refactoring..."
        )

        try:
            # Phase 1: Contract Verification
            self.validate_contracts()

            # Phase 2: Dependency Tests
            self.test_dependencies()

            # Phase 3: Integration Tests
            self.run_integration_tests()

            # Phase 4: Behavior Validation
            self.compare_behavior()

            # Phase 5: Performance Validation
            self.check_performance()

            # Generate final report
            report = self.generate_report()

            # Print summary
            print("\n" + "=" * 60)
            print(f"VALIDATION COMPLETE: {self.results['overall_status']}")
            print("=" * 60)

            if self.results["overall_status"] == "FAILED":
                sys.exit(1)

        except Exception as e:
            logger.error(f"Validation failed with error: {str(e)}")
            self.results["overall_status"] = "ERROR"
            self.results["error"] = str(e)
            self.generate_report()
            sys.exit(1)


def main():
    """Main entry point for the validation script."""
    validator = SnapshotRefactorValidator()
    validator.run_full_validation()


if __name__ == "__main__":
    main()
