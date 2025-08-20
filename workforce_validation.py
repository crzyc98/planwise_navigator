#!/usr/bin/env python3
"""
Workforce Calculation Validation Framework

Provides bounds checking and anomaly detection for workforce simulation calculations
to prevent future inflation issues like the 6.7x multiplication that was just fixed.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    metric_name: str
    actual_value: float
    expected_range: Tuple[float, float]
    message: str
    severity: str = "INFO"  # INFO, WARNING, ERROR, CRITICAL


@dataclass
class WorkforceValidationSummary:
    """Summary of all workforce validation checks."""

    total_checks: int
    passed_checks: int
    failed_checks: int
    critical_failures: List[ValidationResult]
    warnings: List[ValidationResult]

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        return (
            (self.passed_checks / self.total_checks * 100)
            if self.total_checks > 0
            else 0
        )

    @property
    def has_critical_failures(self) -> bool:
        """Check if there are any critical failures."""
        return len(self.critical_failures) > 0


class WorkforceCalculationValidator:
    """Validator for workforce simulation calculations."""

    def __init__(self, database_path: str = "simulation.duckdb"):
        """
        Initialize validator.

        Args:
            database_path: Path to the DuckDB database file
        """
        self.database_path = database_path

        # Define expected ranges for key metrics
        self.validation_rules = {
            "total_hires_needed": {
                "min_ratio": 0.05,  # Minimum 5% of current workforce
                "max_ratio": 0.50,  # Maximum 50% of current workforce
                "description": "Total hires needed should be reasonable vs current workforce",
            },
            "target_growth_rate": {
                "min_value": -0.10,  # Maximum 10% shrinkage
                "max_value": 0.25,  # Maximum 25% growth
                "description": "Growth rate should be within realistic business bounds",
            },
            "new_hire_salary_adjustment": {
                "min_value": 0.80,  # Minimum 80% of current (market downturn)
                "max_value": 1.50,  # Maximum 150% of current (hot market)
                "description": "New hire salary adjustment should be reasonable",
            },
            "total_turnover_rate": {
                "min_value": 0.05,  # Minimum 5% turnover
                "max_value": 0.40,  # Maximum 40% turnover
                "description": "Turnover rate should be within industry norms",
            },
        }

    def validate_workforce_needs(
        self, simulation_year: int, scenario_id: str = "default"
    ) -> WorkforceValidationSummary:
        """
        Validate workforce needs calculations for a given year.

        Args:
            simulation_year: Year to validate
            scenario_id: Scenario identifier

        Returns:
            WorkforceValidationSummary with validation results
        """
        results = []

        try:
            conn = duckdb.connect(self.database_path)

            # Get workforce needs data
            query = """
            SELECT
                starting_workforce_count,
                total_hires_needed,
                target_growth_rate,
                total_turnover_rate,
                avg_new_hire_compensation,
                avg_current_compensation,
                balance_status
            FROM int_workforce_needs
            WHERE simulation_year = ? AND scenario_id = ?
            """

            result = conn.execute(query, [simulation_year, scenario_id]).fetchone()

            if not result:
                return WorkforceValidationSummary(
                    total_checks=0,
                    passed_checks=0,
                    failed_checks=1,
                    critical_failures=[
                        ValidationResult(
                            passed=False,
                            metric_name="data_availability",
                            actual_value=0,
                            expected_range=(1, 1),
                            message=f"No workforce needs data found for year {simulation_year}, scenario {scenario_id}",
                            severity="CRITICAL",
                        )
                    ],
                    warnings=[],
                )

            (
                starting_workforce,
                total_hires,
                growth_rate,
                turnover_rate,
                new_hire_comp,
                current_comp,
                balance_status,
            ) = result

            # Validate hire count vs workforce size
            hire_ratio = (
                total_hires / starting_workforce if starting_workforce > 0 else 0
            )
            results.append(
                self._validate_metric(
                    "hiring_ratio",
                    hire_ratio,
                    self.validation_rules["total_hires_needed"]["min_ratio"],
                    self.validation_rules["total_hires_needed"]["max_ratio"],
                    f"Hiring ratio ({hire_ratio:.1%}) vs workforce size",
                    "CRITICAL" if hire_ratio > 0.5 else "WARNING",
                )
            )

            # Validate growth rate
            results.append(
                self._validate_metric(
                    "target_growth_rate",
                    growth_rate,
                    self.validation_rules["target_growth_rate"]["min_value"],
                    self.validation_rules["target_growth_rate"]["max_value"],
                    f"Growth rate ({growth_rate:.1%})",
                    "ERROR",
                )
            )

            # Validate turnover rate
            results.append(
                self._validate_metric(
                    "total_turnover_rate",
                    turnover_rate,
                    self.validation_rules["total_turnover_rate"]["min_value"],
                    self.validation_rules["total_turnover_rate"]["max_value"],
                    f"Turnover rate ({turnover_rate:.1%})",
                    "ERROR",
                )
            )

            # Validate new hire salary adjustment
            salary_adjustment = (
                new_hire_comp / current_comp if current_comp > 0 else 1.0
            )
            results.append(
                self._validate_metric(
                    "new_hire_salary_adjustment",
                    salary_adjustment,
                    self.validation_rules["new_hire_salary_adjustment"]["min_value"],
                    self.validation_rules["new_hire_salary_adjustment"]["max_value"],
                    f"New hire salary adjustment ({salary_adjustment:.2f}x)",
                    "WARNING",
                )
            )

            # Validate balance status
            if balance_status != "BALANCED":
                results.append(
                    ValidationResult(
                        passed=False,
                        metric_name="workforce_balance",
                        actual_value=0
                        if balance_status == "SIGNIFICANT_VARIANCE"
                        else 1,
                        expected_range=(1, 1),
                        message=f"Workforce balance status: {balance_status}",
                        severity="WARNING"
                        if balance_status == "MINOR_VARIANCE"
                        else "ERROR",
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        passed=True,
                        metric_name="workforce_balance",
                        actual_value=1,
                        expected_range=(1, 1),
                        message="Workforce balance status: BALANCED",
                        severity="INFO",
                    )
                )

            # Historical anomaly detection (if previous years exist)
            historical_check = self._validate_historical_consistency(
                simulation_year, total_hires
            )
            if historical_check:
                results.append(historical_check)

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            results.append(
                ValidationResult(
                    passed=False,
                    metric_name="validation_execution",
                    actual_value=0,
                    expected_range=(1, 1),
                    message=f"Validation execution failed: {str(e)}",
                    severity="CRITICAL",
                )
            )
        finally:
            if "conn" in locals():
                conn.close()

        return self._summarize_results(results)

    def _validate_metric(
        self,
        metric_name: str,
        actual_value: float,
        min_value: float,
        max_value: float,
        description: str,
        severity: str = "ERROR",
    ) -> ValidationResult:
        """Validate a single metric against bounds."""
        passed = min_value <= actual_value <= max_value

        return ValidationResult(
            passed=passed,
            metric_name=metric_name,
            actual_value=actual_value,
            expected_range=(min_value, max_value),
            message=f"{description} - {'✅ PASS' if passed else '❌ FAIL'}",
            severity="INFO" if passed else severity,
        )

    def _validate_historical_consistency(
        self, simulation_year: int, current_hires: float
    ) -> Optional[ValidationResult]:
        """Check for dramatic changes vs historical data."""
        try:
            conn = duckdb.connect(self.database_path)

            # Get previous year's hire count if available
            prev_query = """
            SELECT total_hires_needed
            FROM int_workforce_needs
            WHERE simulation_year = ?
            """

            prev_result = conn.execute(prev_query, [simulation_year - 1]).fetchone()

            if prev_result:
                prev_hires = prev_result[0]
                change_ratio = (
                    current_hires / prev_hires if prev_hires > 0 else float("inf")
                )

                # Flag dramatic changes (>3x or <0.3x)
                if change_ratio > 3.0 or change_ratio < 0.3:
                    return ValidationResult(
                        passed=False,
                        metric_name="historical_consistency",
                        actual_value=change_ratio,
                        expected_range=(0.3, 3.0),
                        message=f"Dramatic change vs previous year: {change_ratio:.1f}x ({current_hires:.0f} vs {prev_hires:.0f})",
                        severity="WARNING",
                    )
                else:
                    return ValidationResult(
                        passed=True,
                        metric_name="historical_consistency",
                        actual_value=change_ratio,
                        expected_range=(0.3, 3.0),
                        message=f"Historical consistency check passed: {change_ratio:.1f}x change",
                        severity="INFO",
                    )

        except Exception as e:
            logger.debug(f"Historical validation skipped: {e}")
        finally:
            if "conn" in locals():
                conn.close()

        return None

    def _summarize_results(
        self, results: List[ValidationResult]
    ) -> WorkforceValidationSummary:
        """Summarize validation results."""
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        critical_failures = [
            r for r in results if not r.passed and r.severity == "CRITICAL"
        ]
        warnings = [
            r for r in results if not r.passed and r.severity in ["WARNING", "ERROR"]
        ]

        return WorkforceValidationSummary(
            total_checks=len(results),
            passed_checks=passed,
            failed_checks=failed,
            critical_failures=critical_failures,
            warnings=warnings,
        )

    def print_validation_report(self, summary: WorkforceValidationSummary) -> None:
        """Print a formatted validation report."""
        print("\n🔍 WORKFORCE CALCULATION VALIDATION REPORT")
        print("=" * 50)

        print(f"📊 Summary:")
        print(f"   Total checks: {summary.total_checks}")
        print(f"   Passed: {summary.passed_checks}")
        print(f"   Failed: {summary.failed_checks}")
        print(f"   Success rate: {summary.success_rate:.1f}%")

        if summary.critical_failures:
            print(f"\n🚨 CRITICAL FAILURES ({len(summary.critical_failures)}):")
            for failure in summary.critical_failures:
                print(f"   ❌ {failure.metric_name}: {failure.message}")

        if summary.warnings:
            print(f"\n⚠️  WARNINGS ({len(summary.warnings)}):")
            for warning in summary.warnings:
                print(f"   ⚠️  {warning.metric_name}: {warning.message}")

        if not summary.has_critical_failures and summary.success_rate > 80:
            print(f"\n✅ Overall validation: PASSED")
        else:
            print(f"\n❌ Overall validation: FAILED")


def validate_current_simulation(year: int = 2025) -> bool:
    """
    Quick validation function for current simulation.

    Args:
        year: Simulation year to validate

    Returns:
        True if validation passes, False otherwise
    """
    validator = WorkforceCalculationValidator()
    summary = validator.validate_workforce_needs(year)
    validator.print_validation_report(summary)

    return not summary.has_critical_failures and summary.success_rate > 80


if __name__ == "__main__":
    # Run validation for current year
    success = validate_current_simulation(2025)
    exit(0 if success else 1)
