"""
Data quality and validation framework for orchestrator_dbt.

Provides comprehensive validation checks for setup operations including
seed data integrity, staging model validation, and business logic checks.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .config import OrchestrationConfig
from .database_manager import DatabaseManager


logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Validation check severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationStatus(Enum):
    """Validation check status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    check_name: str
    status: ValidationStatus
    severity: ValidationSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    execution_time_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        """Check if validation passed."""
        return self.status == ValidationStatus.PASSED

    @property
    def failed(self) -> bool:
        """Check if validation failed."""
        return self.status == ValidationStatus.FAILED

    def __repr__(self) -> str:
        return (
            f"ValidationResult("
            f"check='{self.check_name}', "
            f"status={self.status.value}, "
            f"severity={self.severity.value}"
            f")"
        )


@dataclass
class ValidationSummary:
    """Summary of all validation results."""
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    skipped_checks: int = 0
    error_checks: int = 0
    critical_failures: int = 0
    warnings: int = 0
    total_execution_time: float = 0.0
    results: List[ValidationResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_checks == 0:
            return 100.0
        return (self.passed_checks / self.total_checks) * 100.0

    @property
    def is_valid(self) -> bool:
        """Check if overall validation is successful."""
        return self.critical_failures == 0 and self.failed_checks == 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return self.warnings > 0

    def get_failed_checks(self) -> List[ValidationResult]:
        """Get list of failed validation checks."""
        return [r for r in self.results if r.failed]

    def get_critical_failures(self) -> List[ValidationResult]:
        """Get list of critical failures."""
        return [r for r in self.results if r.severity == ValidationSeverity.CRITICAL and r.failed]

    def __repr__(self) -> str:
        return (
            f"ValidationSummary("
            f"total={self.total_checks}, "
            f"passed={self.passed_checks}, "
            f"failed={self.failed_checks}, "
            f"success_rate={self.success_rate:.1f}%"
            f")"
        )


class ValidationFramework:
    """
    Comprehensive validation framework for setup operations.

    Provides validation checks for database state, seed data integrity,
    staging model results, and business logic compliance.
    """

    def __init__(self, config: OrchestrationConfig, database_manager: DatabaseManager):
        """
        Initialize validation framework.

        Args:
            config: Orchestration configuration
            database_manager: Database manager for executing queries
        """
        self.config = config
        self.db_manager = database_manager

    def validate_seed_data_integrity(self) -> ValidationResult:
        """
        Validate integrity of loaded seed data.

        Returns:
            ValidationResult for seed data integrity
        """
        try:
            logger.info("Validating seed data integrity...")

            required_tables = self.config.validation.required_seed_tables
            missing_tables = []
            empty_tables = []
            table_stats = {}

            with self.db_manager.get_connection(read_only=True) as conn:
                for table in required_tables:
                    # Check if table exists
                    if not self.db_manager.table_exists(table):
                        missing_tables.append(table)
                        continue

                    # Check row count
                    row_count = self.db_manager.get_table_row_count(table)
                    table_stats[table] = row_count

                    if row_count == 0:
                        empty_tables.append(table)

            # Determine result
            if missing_tables:
                return ValidationResult(
                    check_name="seed_data_integrity",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Missing required seed tables: {missing_tables}",
                    details={
                        "missing_tables": missing_tables,
                        "empty_tables": empty_tables,
                        "table_stats": table_stats
                    }
                )

            if empty_tables:
                return ValidationResult(
                    check_name="seed_data_integrity",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"Empty required seed tables: {empty_tables}",
                    details={
                        "missing_tables": missing_tables,
                        "empty_tables": empty_tables,
                        "table_stats": table_stats
                    }
                )

            return ValidationResult(
                check_name="seed_data_integrity",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.INFO,
                message=f"All {len(required_tables)} required seed tables loaded successfully",
                details={
                    "required_tables": required_tables,
                    "table_stats": table_stats
                }
            )

        except Exception as e:
            logger.error(f"Error validating seed data integrity: {e}")
            return ValidationResult(
                check_name="seed_data_integrity",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Validation error: {e}",
                details={"error": str(e)}
            )

    def validate_staging_models(self) -> ValidationResult:
        """
        Validate staging models are properly materialized.

        Returns:
            ValidationResult for staging models
        """
        try:
            logger.info("Validating staging models...")

            required_models = self.config.validation.required_staging_models
            missing_models = []
            empty_models = []
            model_stats = {}

            for model in required_models:
                # Check if model table exists
                if not self.db_manager.table_exists(model):
                    missing_models.append(model)
                    continue

                # Check row count
                row_count = self.db_manager.get_table_row_count(model)
                model_stats[model] = row_count

                if row_count == 0:
                    empty_models.append(model)

            # Determine result
            if missing_models:
                return ValidationResult(
                    check_name="staging_models_validation",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Missing required staging models: {missing_models}",
                    details={
                        "missing_models": missing_models,
                        "empty_models": empty_models,
                        "model_stats": model_stats
                    }
                )

            if empty_models:
                return ValidationResult(
                    check_name="staging_models_validation",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"Empty required staging models: {empty_models}",
                    details={
                        "missing_models": missing_models,
                        "empty_models": empty_models,
                        "model_stats": model_stats
                    }
                )

            return ValidationResult(
                check_name="staging_models_validation",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.INFO,
                message=f"All {len(required_models)} required staging models validated successfully",
                details={
                    "required_models": required_models,
                    "model_stats": model_stats
                }
            )

        except Exception as e:
            logger.error(f"Error validating staging models: {e}")
            return ValidationResult(
                check_name="staging_models_validation",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Validation error: {e}",
                details={"error": str(e)}
            )

    def validate_baseline_workforce(self) -> ValidationResult:
        """
        Validate baseline workforce data quality.

        Returns:
            ValidationResult for baseline workforce
        """
        try:
            logger.info("Validating baseline workforce...")

            if not self.db_manager.table_exists("int_baseline_workforce"):
                return ValidationResult(
                    check_name="baseline_workforce_validation",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message="Baseline workforce table not found",
                    details={"missing_table": "int_baseline_workforce"}
                )

            with self.db_manager.get_connection(read_only=True) as conn:
                # Get workforce statistics
                workforce_query = """
                    SELECT
                        COUNT(*) as total_employees,
                        COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
                        COUNT(CASE WHEN compensation IS NULL OR compensation <= 0 THEN 1 END) as invalid_compensation,
                        AVG(compensation) as avg_compensation,
                        MIN(compensation) as min_compensation,
                        MAX(compensation) as max_compensation
                    FROM int_baseline_workforce
                """

                result = conn.execute(workforce_query).fetchone()

                if not result or result[0] == 0:
                    return ValidationResult(
                        check_name="baseline_workforce_validation",
                        status=ValidationStatus.FAILED,
                        severity=ValidationSeverity.CRITICAL,
                        message="No employees found in baseline workforce",
                        details={"total_employees": 0}
                    )

                total, active, invalid_comp, avg_comp, min_comp, max_comp = result

                # Check minimum workforce size
                min_workforce = self.config.validation.min_baseline_workforce_count
                if active < min_workforce:
                    return ValidationResult(
                        check_name="baseline_workforce_validation",
                        status=ValidationStatus.FAILED,
                        severity=ValidationSeverity.ERROR,
                        message=f"Insufficient active workforce: {active} < {min_workforce}",
                        details={
                            "total_employees": total,
                            "active_employees": active,
                            "min_required": min_workforce,
                            "invalid_compensation": invalid_comp
                        }
                    )

                # Check for data quality issues
                warnings = []
                if invalid_comp > 0:
                    warnings.append(f"{invalid_comp} employees with invalid compensation")

                if min_comp and min_comp < 20000:  # Suspiciously low compensation
                    warnings.append(f"Minimum compensation suspiciously low: ${min_comp:,.2f}")

                severity = ValidationSeverity.WARNING if warnings else ValidationSeverity.INFO
                message = f"Baseline workforce validated: {active:,} active employees"
                if warnings:
                    message += f" (Warnings: {'; '.join(warnings)})"

                return ValidationResult(
                    check_name="baseline_workforce_validation",
                    status=ValidationStatus.PASSED,
                    severity=severity,
                    message=message,
                    details={
                        "total_employees": total,
                        "active_employees": active,
                        "invalid_compensation": invalid_comp,
                        "avg_compensation": round(avg_comp or 0, 2),
                        "min_compensation": round(min_comp or 0, 2),
                        "max_compensation": round(max_comp or 0, 2),
                        "warnings": warnings
                    }
                )

        except Exception as e:
            logger.error(f"Error validating baseline workforce: {e}")
            return ValidationResult(
                check_name="baseline_workforce_validation",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Validation error: {e}",
                details={"error": str(e)}
            )

    def validate_census_data_quality(self) -> ValidationResult:
        """
        Validate census data quality and consistency.

        Returns:
            ValidationResult for census data quality
        """
        try:
            logger.info("Validating census data quality...")

            if not self.db_manager.table_exists("stg_census_data"):
                return ValidationResult(
                    check_name="census_data_quality",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message="Census data table not found",
                    details={"missing_table": "stg_census_data"}
                )

            with self.db_manager.get_connection(read_only=True) as conn:
                # Check for data quality issues
                quality_query = """
                    SELECT
                        COUNT(*) as total_records,
                        COUNT(DISTINCT employee_id) as unique_employees,
                        COUNT(CASE WHEN employee_id IS NULL THEN 1 END) as null_employee_ids,
                        COUNT(CASE WHEN employee_hire_date IS NULL THEN 1 END) as null_hire_dates,
                        COUNT(CASE WHEN employee_gross_compensation IS NULL OR employee_gross_compensation <= 0 THEN 1 END) as invalid_compensation
                    FROM stg_census_data
                """

                result = conn.execute(quality_query).fetchone()

                if not result or result[0] == 0:
                    return ValidationResult(
                        check_name="census_data_quality",
                        status=ValidationStatus.FAILED,
                        severity=ValidationSeverity.CRITICAL,
                        message="No records found in census data",
                        details={"total_records": 0}
                    )

                (total_records, unique_employees, null_ids, null_hire_dates,
                 invalid_comp) = result

                # Check for duplicates
                if total_records != unique_employees:
                    return ValidationResult(
                        check_name="census_data_quality",
                        status=ValidationStatus.FAILED,
                        severity=ValidationSeverity.ERROR,
                        message=f"Duplicate employee IDs found: {total_records} records vs {unique_employees} unique",
                        details={
                            "total_records": total_records,
                            "unique_employees": unique_employees,
                            "duplicate_count": total_records - unique_employees
                        }
                    )

                # Check for critical data quality issues
                critical_issues = []
                if null_ids > 0:
                    critical_issues.append(f"{null_ids} null employee IDs")
                if null_hire_dates > 0:
                    critical_issues.append(f"{null_hire_dates} null hire dates")

                if critical_issues:
                    return ValidationResult(
                        check_name="census_data_quality",
                        status=ValidationStatus.FAILED,
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Critical data quality issues: {'; '.join(critical_issues)}",
                        details={
                            "total_records": total_records,
                            "null_employee_ids": null_ids,
                            "null_hire_dates": null_hire_dates,
                            "invalid_compensation": invalid_comp
                        }
                    )

                # Check for warnings
                warnings = []
                if invalid_comp > 0:
                    warnings.append(f"{invalid_comp} invalid compensation values")

                severity = ValidationSeverity.WARNING if warnings else ValidationSeverity.INFO
                message = f"Census data quality validated: {unique_employees:,} unique employees"
                if warnings:
                    message += f" (Warnings: {'; '.join(warnings)})"

                return ValidationResult(
                    check_name="census_data_quality",
                    status=ValidationStatus.PASSED,
                    severity=severity,
                    message=message,
                    details={
                        "total_records": total_records,
                        "unique_employees": unique_employees,
                        "invalid_compensation": invalid_comp,
                        "warnings": warnings
                    }
                )

        except Exception as e:
            logger.error(f"Error validating census data quality: {e}")
            return ValidationResult(
                check_name="census_data_quality",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Validation error: {e}",
                details={"error": str(e)}
            )

    def validate_configuration_consistency(self) -> ValidationResult:
        """
        Validate configuration data consistency across tables.

        Returns:
            ValidationResult for configuration consistency
        """
        try:
            logger.info("Validating configuration consistency...")

            issues = []

            with self.db_manager.get_connection(read_only=True) as conn:
                # Check job levels consistency
                if (self.db_manager.table_exists("stg_config_job_levels") and
                    self.db_manager.table_exists("int_baseline_workforce")):

                    orphan_query = """
                        SELECT COUNT(*) as orphan_count
                        FROM int_baseline_workforce w
                        LEFT JOIN stg_config_job_levels jl ON w.job_level_id = jl.job_level_id
                        WHERE jl.job_level_id IS NULL
                    """

                    orphan_result = conn.execute(orphan_query).fetchone()
                    if orphan_result and orphan_result[0] > 0:
                        issues.append(f"{orphan_result[0]} employees with undefined job levels")

                # Check compensation parameters
                if self.db_manager.table_exists("stg_comp_levers"):
                    comp_query = """
                        SELECT COUNT(*) as param_count
                        FROM stg_comp_levers
                        WHERE parameter_value IS NULL
                    """

                    comp_result = conn.execute(comp_query).fetchone()
                    if comp_result and comp_result[0] > 0:
                        issues.append(f"{comp_result[0]} compensation parameters with null/empty values")

                # Check COLA configuration
                if self.db_manager.table_exists("stg_config_cola_by_year"):
                    cola_query = """
                        SELECT COUNT(*) as missing_years
                        FROM (
                            SELECT generate_series(2020, 2030) as year
                        ) years
                        LEFT JOIN stg_config_cola_by_year cola ON years.year = cola.year
                        WHERE cola.year IS NULL
                    """

                    try:
                        cola_result = conn.execute(cola_query).fetchone()
                        if cola_result and cola_result[0] > 5:  # More than 5 missing years
                            issues.append(f"{cola_result[0]} years missing COLA configuration")
                    except Exception:
                        # Ignore if generate_series not available
                        pass

            if issues:
                return ValidationResult(
                    check_name="configuration_consistency",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.WARNING,
                    message=f"Configuration consistency issues: {'; '.join(issues)}",
                    details={"issues": issues}
                )

            return ValidationResult(
                check_name="configuration_consistency",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.INFO,
                message="Configuration consistency validated successfully",
                details={"issues_found": 0}
            )

        except Exception as e:
            logger.error(f"Error validating configuration consistency: {e}")
            return ValidationResult(
                check_name="configuration_consistency",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.WARNING,
                message=f"Validation error: {e}",
                details={"error": str(e)}
            )

    def run_comprehensive_validation(self) -> ValidationSummary:
        """
        Run all validation checks and return comprehensive summary.

        Returns:
            ValidationSummary with results from all checks
        """
        logger.info("Starting comprehensive validation...")

        validation_checks = [
            self.validate_seed_data_integrity,
            self.validate_staging_models,
            self.validate_baseline_workforce,
            self.validate_census_data_quality,
            self.validate_configuration_consistency
        ]

        summary = ValidationSummary()

        for check_func in validation_checks:
            try:
                result = check_func()
                summary.results.append(result)

                summary.total_checks += 1

                if result.status == ValidationStatus.PASSED:
                    summary.passed_checks += 1
                elif result.status == ValidationStatus.FAILED:
                    summary.failed_checks += 1
                elif result.status == ValidationStatus.SKIPPED:
                    summary.skipped_checks += 1
                else:  # ERROR
                    summary.error_checks += 1

                if result.severity == ValidationSeverity.CRITICAL and result.failed:
                    summary.critical_failures += 1
                elif result.severity == ValidationSeverity.WARNING:
                    summary.warnings += 1

                summary.total_execution_time += result.execution_time_seconds

            except Exception as e:
                logger.error(f"Error running validation check {check_func.__name__}: {e}")
                error_result = ValidationResult(
                    check_name=check_func.__name__,
                    status=ValidationStatus.ERROR,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Check execution error: {e}",
                    details={"error": str(e)}
                )
                summary.results.append(error_result)
                summary.total_checks += 1
                summary.error_checks += 1
                summary.critical_failures += 1

        logger.info(f"Validation completed: {summary}")
        return summary
