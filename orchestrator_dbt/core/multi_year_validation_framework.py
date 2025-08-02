"""
Multi-Year Validation Framework Extension

Extends the existing ValidationFramework with comprehensive multi-year simulation
validation capabilities including cross-year data integrity, event sourcing
validation, and business logic compliance across simulation years.

Key Features:
- Multi-year workforce state continuity validation
- Event sourcing integrity with immutable audit trails
- Cross-year financial calculation accuracy
- Performance-optimized validation with minimal impact
- UUID-based tracking for complete audit trails
- Business rule compliance across simulation boundaries

Integration:
- Extends existing ValidationFramework patterns
- Integrates with MultiYearOrchestrator workflow
- Provides comprehensive reporting and alerting
- Maintains backward compatibility with existing validation

Usage:
    # Initialize multi-year validation
    multi_year_validator = MultiYearValidationFramework(config, database_manager)

    # Validate across multiple years
    validation_result = multi_year_validator.validate_multi_year_simulation(
        start_year=2025,
        end_year=2029
    )

    # Check specific cross-year integrity
    integrity_result = multi_year_validator.validate_cross_year_integrity(2025, 2026)
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from .validation_framework import (
    ValidationFramework, ValidationResult, ValidationSummary,
    ValidationSeverity, ValidationStatus
)
from .config import OrchestrationConfig
from .database_manager import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class CrossYearValidationResult(ValidationResult):
    """Extended validation result for cross-year checks."""
    from_year: int = 0
    to_year: int = 0
    records_validated: int = 0
    cross_year_issues: List[Dict[str, Any]] = field(default_factory=list)
    employee_lifecycle_violations: List[str] = field(default_factory=list)
    financial_inconsistencies: List[Dict[str, Decimal]] = field(default_factory=list)


@dataclass
class EventSourcingValidationResult(ValidationResult):
    """Validation result specifically for event sourcing integrity."""
    events_validated: int = 0
    missing_events: List[str] = field(default_factory=list)
    duplicate_events: List[str] = field(default_factory=list)
    uuid_violations: List[str] = field(default_factory=list)
    immutability_violations: List[str] = field(default_factory=list)
    audit_trail_gaps: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BusinessLogicValidationResult(ValidationResult):
    """Validation result for business logic compliance across years."""
    business_rules_checked: int = 0
    rule_violations: List[Dict[str, Any]] = field(default_factory=list)
    compensation_violations: List[str] = field(default_factory=list)
    hiring_pattern_anomalies: List[Dict[str, Any]] = field(default_factory=list)
    termination_pattern_anomalies: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MultiYearValidationSummary(ValidationSummary):
    """Extended validation summary for multi-year simulations."""
    years_validated: List[int] = field(default_factory=list)
    cross_year_checks: int = 0
    event_sourcing_checks: int = 0
    business_logic_checks: int = 0
    total_records_validated: int = 0
    total_events_validated: int = 0
    performance_impact_ms: float = 0.0

    def get_cross_year_failures(self) -> List[CrossYearValidationResult]:
        """Get list of cross-year validation failures."""
        return [r for r in self.results if isinstance(r, CrossYearValidationResult) and r.failed]

    def get_event_sourcing_failures(self) -> List[EventSourcingValidationResult]:
        """Get list of event sourcing validation failures."""
        return [r for r in self.results if isinstance(r, EventSourcingValidationResult) and r.failed]

    def get_business_logic_failures(self) -> List[BusinessLogicValidationResult]:
        """Get list of business logic validation failures."""
        return [r for r in self.results if isinstance(r, BusinessLogicValidationResult) and r.failed]


class MultiYearValidationFramework(ValidationFramework):
    """
    Extended validation framework for multi-year simulation validation.

    Provides comprehensive validation capabilities for:
    - Cross-year data consistency and employee lifecycle continuity
    - Event sourcing integrity with immutable audit trails
    - Business logic compliance across simulation boundaries
    - Performance-optimized validation with minimal simulation impact

    The framework extends the existing ValidationFramework to maintain
    compatibility while adding sophisticated multi-year validation capabilities.
    """

    def __init__(self, config: OrchestrationConfig, database_manager: DatabaseManager):
        """
        Initialize multi-year validation framework.

        Args:
            config: Orchestration configuration
            database_manager: Database manager for executing queries
        """
        super().__init__(config, database_manager)

        # Multi-year specific configuration
        validation_config = config.validation.__dict__ if hasattr(config, 'validation') else {}
        self.enable_performance_optimization = validation_config.get(
            "enable_performance_optimization", True
        )
        self.batch_size = validation_config.get("batch_size", 1000)
        self.max_validation_time_seconds = validation_config.get(
            "max_validation_time_seconds", 300
        )

        # Validation mode configuration
        multi_year_config = config.get_multi_year_config()
        self.validation_mode = multi_year_config.error_handling.validation_mode
        self.fail_fast = multi_year_config.error_handling.fail_fast
        self.enable_real_time_validation = getattr(multi_year_config.monitoring, 'enable_real_time_validation', True)

        # Performance tracking
        self._validation_start_time = None
        self._performance_metrics = {}
        self._validation_history = []

        # Circuit breaker for validation performance
        self._validation_failures = 0
        self._max_validation_failures = 5
        self._circuit_breaker_open = False

    def validate_multi_year_simulation(
        self,
        start_year: int,
        end_year: int,
        scenario_id: Optional[str] = None
    ) -> MultiYearValidationSummary:
        """
        Validate complete multi-year simulation with comprehensive checks.

        Args:
            start_year: Starting simulation year
            end_year: Ending simulation year
            scenario_id: Optional scenario ID for filtering

        Returns:
            Comprehensive multi-year validation summary
        """
        logger.info(f"Starting multi-year validation: {start_year}-{end_year}")
        self._validation_start_time = time.time()

        # Initialize summary
        summary = MultiYearValidationSummary()
        summary.years_validated = list(range(start_year, end_year + 1))

        try:
            # 1. Basic foundation validation (reuse existing framework)
            foundation_result = self.run_comprehensive_validation()
            summary.results.extend(foundation_result.results)
            summary.total_checks += foundation_result.total_checks
            summary.passed_checks += foundation_result.passed_checks
            summary.failed_checks += foundation_result.failed_checks
            summary.critical_failures += foundation_result.critical_failures
            summary.warnings += foundation_result.warnings

            # 2. Cross-year integrity validation
            for year in range(start_year, end_year):
                cross_year_result = self.validate_cross_year_integrity(year, year + 1, scenario_id)
                summary.results.append(cross_year_result)
                summary.cross_year_checks += 1
                summary.total_checks += 1

                if cross_year_result.passed:
                    summary.passed_checks += 1
                elif cross_year_result.failed:
                    summary.failed_checks += 1
                    if cross_year_result.severity == ValidationSeverity.CRITICAL:
                        summary.critical_failures += 1
                elif cross_year_result.severity == ValidationSeverity.WARNING:
                    summary.warnings += 1

                summary.total_records_validated += cross_year_result.records_validated

            # 3. Event sourcing validation across all years
            event_sourcing_result = self.validate_event_sourcing_integrity(
                start_year, end_year, scenario_id
            )
            summary.results.append(event_sourcing_result)
            summary.event_sourcing_checks += 1
            summary.total_checks += 1
            summary.total_events_validated += event_sourcing_result.events_validated

            if event_sourcing_result.passed:
                summary.passed_checks += 1
            elif event_sourcing_result.failed:
                summary.failed_checks += 1
                if event_sourcing_result.severity == ValidationSeverity.CRITICAL:
                    summary.critical_failures += 1
            elif event_sourcing_result.severity == ValidationSeverity.WARNING:
                summary.warnings += 1

            # 4. Business logic validation across years
            business_logic_result = self.validate_business_logic_compliance(
                start_year, end_year, scenario_id
            )
            summary.results.append(business_logic_result)
            summary.business_logic_checks += 1
            summary.total_checks += 1

            if business_logic_result.passed:
                summary.passed_checks += 1
            elif business_logic_result.failed:
                summary.failed_checks += 1
                if business_logic_result.severity == ValidationSeverity.CRITICAL:
                    summary.critical_failures += 1
            elif business_logic_result.severity == ValidationSeverity.WARNING:
                summary.warnings += 1

            # 5. Performance impact calculation
            summary.performance_impact_ms = (time.time() - self._validation_start_time) * 1000

            # 6. Calculate total execution time
            summary.total_execution_time = time.time() - self._validation_start_time

            logger.info(f"Multi-year validation completed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Multi-year validation failed: {e}")

            # Create error result
            error_result = ValidationResult(
                check_name="multi_year_validation",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Multi-year validation failed: {e}",
                details={"error": str(e), "years": f"{start_year}-{end_year}"}
            )

            summary.results.append(error_result)
            summary.total_checks += 1
            summary.error_checks += 1
            summary.critical_failures += 1

            if self._validation_start_time:
                summary.total_execution_time = time.time() - self._validation_start_time
                summary.performance_impact_ms = summary.total_execution_time * 1000

            return summary

    def validate_cross_year_integrity(
        self,
        from_year: int,
        to_year: int,
        scenario_id: Optional[str] = None
    ) -> CrossYearValidationResult:
        """
        Validate data integrity and employee lifecycle continuity between years.

        Args:
            from_year: Source year for comparison
            to_year: Target year for comparison
            scenario_id: Optional scenario ID for filtering

        Returns:
            Cross-year validation result with detailed integrity checks
        """
        start_time = time.time()
        logger.info(f"Validating cross-year integrity: {from_year} -> {to_year}")

        try:
            cross_year_issues = []
            employee_lifecycle_violations = []
            financial_inconsistencies = []
            total_records = 0

            with self.db_manager.get_connection(read_only=True) as conn:
                # 1. Validate employee lifecycle continuity
                lifecycle_query = """
                    WITH from_year_workforce AS (
                        SELECT employee_id, employment_status, compensation, job_level_id
                        FROM fct_workforce_snapshot
                        WHERE simulation_year = ?
                        {scenario_filter}
                    ),
                    to_year_workforce AS (
                        SELECT employee_id, employment_status, compensation, job_level_id
                        FROM fct_workforce_snapshot
                        WHERE simulation_year = ?
                        {scenario_filter}
                    ),
                    lifecycle_transitions AS (
                        SELECT
                            f.employee_id,
                            f.employment_status as from_status,
                            t.employment_status as to_status,
                            f.compensation as from_compensation,
                            t.compensation as to_compensation,
                            f.job_level_id as from_level,
                            t.job_level_id as to_level
                        FROM from_year_workforce f
                        FULL OUTER JOIN to_year_workforce t ON f.employee_id = t.employee_id
                    )
                    SELECT
                        COUNT(*) as total_transitions,
                        COUNT(CASE WHEN from_status = 'active' AND to_status IS NULL THEN 1 END) as disappeared_employees,
                        COUNT(CASE WHEN from_status IS NULL AND to_status = 'active' THEN 1 END) as appeared_employees,
                        COUNT(CASE WHEN from_status = 'terminated' AND to_status = 'active' THEN 1 END) as resurrection_violations,
                        COUNT(CASE WHEN from_compensation > to_compensation * 1.5 THEN 1 END) as suspicious_salary_decreases,
                        COUNT(CASE WHEN to_compensation > from_compensation * 2.0 THEN 1 END) as suspicious_salary_increases
                    FROM lifecycle_transitions
                """

                scenario_filter = "AND scenario_id = ?" if scenario_id else ""
                formatted_query = lifecycle_query.format(scenario_filter=scenario_filter)

                params = [from_year, to_year]
                if scenario_id:
                    params.extend([scenario_id, scenario_id])

                lifecycle_result = conn.execute(formatted_query, params).fetchone()

                if lifecycle_result:
                    (total_transitions, disappeared, appeared, resurrections,
                     salary_decreases, salary_increases) = lifecycle_result

                    total_records += total_transitions or 0

                    # Check for violations
                    if disappeared and disappeared > total_transitions * 0.01:  # More than 1% disappeared
                        cross_year_issues.append({
                            "type": "employee_disappearance",
                            "count": disappeared,
                            "threshold_exceeded": True,
                            "severity": "warning"
                        })

                    if resurrections and resurrections > 0:
                        employee_lifecycle_violations.extend([
                            f"Employee resurrection violation: {resurrections} terminated employees became active"
                        ])

                    if salary_decreases and salary_decreases > 0:
                        financial_inconsistencies.append({
                            "type": "suspicious_salary_decrease",
                            "count": salary_decreases,
                            "threshold": Decimal("0.5")  # >50% decrease
                        })

                    if salary_increases and salary_increases > 0:
                        financial_inconsistencies.append({
                            "type": "suspicious_salary_increase",
                            "count": salary_increases,
                            "threshold": Decimal("2.0")  # >100% increase
                        })

                # 2. Validate event sourcing continuity
                event_continuity_query = """
                    SELECT
                        COUNT(*) as total_events,
                        COUNT(CASE WHEN simulation_year = ? THEN 1 END) as from_year_events,
                        COUNT(CASE WHEN simulation_year = ? THEN 1 END) as to_year_events,
                        COUNT(DISTINCT employee_id) as unique_employees
                    FROM fct_yearly_events
                    WHERE simulation_year IN (?, ?)
                    {scenario_filter}
                """

                scenario_filter = "AND scenario_id = ?" if scenario_id else ""
                formatted_query = event_continuity_query.format(scenario_filter=scenario_filter)

                params = [from_year, to_year, from_year, to_year]
                if scenario_id:
                    params.append(scenario_id)

                event_result = conn.execute(formatted_query, params).fetchone()

                if event_result:
                    total_events, from_events, to_events, unique_employees = event_result

                    # Check for event volume anomalies
                    if from_events and to_events:
                        volume_ratio = to_events / from_events if from_events > 0 else float('inf')
                        if volume_ratio > 3.0 or volume_ratio < 0.3:  # More than 3x change
                            cross_year_issues.append({
                                "type": "event_volume_anomaly",
                                "from_year_events": from_events,
                                "to_year_events": to_events,
                                "ratio": float(volume_ratio),
                                "severity": "warning"
                            })

                # 3. Validate compensation progression logic
                compensation_query = """
                    WITH compensation_changes AS (
                        SELECT
                            f.employee_id,
                            f.compensation as from_compensation,
                            t.compensation as to_compensation,
                            (t.compensation - f.compensation) / f.compensation as change_rate
                        FROM (
                            SELECT employee_id, compensation
                            FROM fct_workforce_snapshot
                            WHERE simulation_year = ? AND employment_status = 'active'
                            {scenario_filter}
                        ) f
                        JOIN (
                            SELECT employee_id, compensation
                            FROM fct_workforce_snapshot
                            WHERE simulation_year = ? AND employment_status = 'active'
                            {scenario_filter}
                        ) t ON f.employee_id = t.employee_id
                        WHERE f.compensation > 0
                    )
                    SELECT
                        COUNT(*) as total_comparisons,
                        AVG(change_rate) as avg_change_rate,
                        STDDEV(change_rate) as stddev_change_rate,
                        COUNT(CASE WHEN change_rate < -0.1 THEN 1 END) as salary_cuts,
                        COUNT(CASE WHEN change_rate > 0.3 THEN 1 END) as large_increases
                    FROM compensation_changes
                """

                scenario_filter = "AND scenario_id = ?" if scenario_id else ""
                formatted_query = compensation_query.format(scenario_filter=scenario_filter)

                params = [from_year, to_year]
                if scenario_id:
                    params.extend([scenario_id, scenario_id])

                comp_result = conn.execute(formatted_query, params).fetchone()

                if comp_result:
                    (total_comp, avg_change, stddev_change, salary_cuts, large_increases) = comp_result

                    if salary_cuts and salary_cuts > total_comp * 0.05:  # More than 5% salary cuts
                        financial_inconsistencies.append({
                            "type": "excessive_salary_cuts",
                            "count": salary_cuts,
                            "percentage": float(salary_cuts / total_comp) if total_comp > 0 else 0,
                            "threshold": Decimal("0.05")
                        })

                    if large_increases and large_increases > total_comp * 0.02:  # More than 2% large increases
                        financial_inconsistencies.append({
                            "type": "excessive_large_increases",
                            "count": large_increases,
                            "percentage": float(large_increases / total_comp) if total_comp > 0 else 0,
                            "threshold": Decimal("0.02")
                        })

            # Determine validation result
            execution_time = time.time() - start_time

            # Critical failures
            if employee_lifecycle_violations:
                return CrossYearValidationResult(
                    check_name=f"cross_year_integrity_{from_year}_{to_year}",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Critical employee lifecycle violations found: {len(employee_lifecycle_violations)}",
                    details={
                        "violations": employee_lifecycle_violations,
                        "cross_year_issues": cross_year_issues,
                        "financial_inconsistencies": financial_inconsistencies
                    },
                    execution_time_seconds=execution_time,
                    from_year=from_year,
                    to_year=to_year,
                    records_validated=total_records,
                    cross_year_issues=cross_year_issues,
                    employee_lifecycle_violations=employee_lifecycle_violations,
                    financial_inconsistencies=financial_inconsistencies
                )

            # Warning conditions
            severity = ValidationSeverity.INFO
            message = f"Cross-year integrity validated successfully: {from_year} -> {to_year}"

            if cross_year_issues or financial_inconsistencies:
                severity = ValidationSeverity.WARNING
                warning_count = len(cross_year_issues) + len(financial_inconsistencies)
                message = f"Cross-year integrity validated with {warning_count} warnings: {from_year} -> {to_year}"

            return CrossYearValidationResult(
                check_name=f"cross_year_integrity_{from_year}_{to_year}",
                status=ValidationStatus.PASSED,
                severity=severity,
                message=message,
                details={
                    "records_validated": total_records,
                    "cross_year_issues": cross_year_issues,
                    "financial_inconsistencies": financial_inconsistencies
                },
                execution_time_seconds=execution_time,
                from_year=from_year,
                to_year=to_year,
                records_validated=total_records,
                cross_year_issues=cross_year_issues,
                employee_lifecycle_violations=employee_lifecycle_violations,
                financial_inconsistencies=financial_inconsistencies
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Cross-year integrity validation failed: {e}")

            return CrossYearValidationResult(
                check_name=f"cross_year_integrity_{from_year}_{to_year}",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Cross-year validation error: {e}",
                details={"error": str(e), "from_year": from_year, "to_year": to_year},
                execution_time_seconds=execution_time,
                from_year=from_year,
                to_year=to_year
            )

    def validate_event_sourcing_integrity(
        self,
        start_year: int,
        end_year: int,
        scenario_id: Optional[str] = None
    ) -> EventSourcingValidationResult:
        """
        Validate event sourcing integrity with immutable audit trails.

        Args:
            start_year: Starting year for validation
            end_year: Ending year for validation
            scenario_id: Optional scenario ID for filtering

        Returns:
            Event sourcing validation result with audit trail analysis
        """
        start_time = time.time()
        logger.info(f"Validating event sourcing integrity: {start_year}-{end_year}")

        try:
            missing_events = []
            duplicate_events = []
            uuid_violations = []
            immutability_violations = []
            audit_trail_gaps = []
            total_events = 0

            with self.db_manager.get_connection(read_only=True) as conn:
                # 1. Validate UUID uniqueness and format
                uuid_query = """
                    SELECT
                        COUNT(*) as total_events,
                        COUNT(DISTINCT event_id) as unique_events,
                        COUNT(CASE WHEN event_id IS NULL THEN 1 END) as null_uuids,
                        COUNT(CASE WHEN LENGTH(event_id) != 36 THEN 1 END) as invalid_uuid_format
                    FROM fct_yearly_events
                    WHERE simulation_year BETWEEN ? AND ?
                    {scenario_filter}
                """

                scenario_filter = "AND scenario_id = ?" if scenario_id else ""
                formatted_query = uuid_query.format(scenario_filter=scenario_filter)

                params = [start_year, end_year]
                if scenario_id:
                    params.append(scenario_id)

                uuid_result = conn.execute(formatted_query, params).fetchone()

                if uuid_result:
                    total_events, unique_events, null_uuids, invalid_formats = uuid_result

                    # Check for UUID violations
                    if null_uuids and null_uuids > 0:
                        uuid_violations.append(f"{null_uuids} events with NULL UUIDs")

                    if invalid_formats and invalid_formats > 0:
                        uuid_violations.append(f"{invalid_formats} events with invalid UUID format")

                    if total_events != unique_events:
                        duplicate_count = total_events - unique_events
                        duplicate_events.append(f"{duplicate_count} duplicate event UUIDs found")

                # 2. Validate event immutability (check for event modifications)
                immutability_query = """
                    SELECT
                        event_id,
                        COUNT(*) as occurrence_count,
                        MIN(created_at) as first_created,
                        MAX(created_at) as last_created
                    FROM fct_yearly_events
                    WHERE simulation_year BETWEEN ? AND ?
                    {scenario_filter}
                    GROUP BY event_id
                    HAVING COUNT(*) > 1
                    LIMIT 100
                """

                formatted_query = immutability_query.format(scenario_filter=scenario_filter)

                immutability_results = conn.execute(formatted_query, params).fetchall()

                for result in immutability_results:
                    event_id, count, first_created, last_created = result
                    immutability_violations.append(
                        f"Event {event_id} appears {count} times (potential modification)"
                    )

                # 3. Validate audit trail completeness for employee lifecycles
                audit_trail_query = """
                    WITH employee_events AS (
                        SELECT
                            employee_id,
                            simulation_year,
                            event_type,
                            effective_date,
                            ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY effective_date) as event_sequence
                        FROM fct_yearly_events
                        WHERE simulation_year BETWEEN ? AND ?
                        AND event_type IN ('hire', 'promotion', 'merit', 'termination')
                        {scenario_filter}
                    ),
                    lifecycle_gaps AS (
                        SELECT
                            employee_id,
                            COUNT(*) as total_events,
                            MIN(CASE WHEN event_type = 'hire' THEN event_sequence END) as first_hire_seq,
                            MAX(CASE WHEN event_type = 'termination' THEN event_sequence END) as last_term_seq,
                            COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as hire_count,
                            COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as term_count
                        FROM employee_events
                        GROUP BY employee_id
                    )
                    SELECT
                        COUNT(*) as employees_analyzed,
                        COUNT(CASE WHEN hire_count = 0 THEN 1 END) as missing_hire_events,
                        COUNT(CASE WHEN hire_count > 1 THEN 1 END) as multiple_hire_events,
                        COUNT(CASE
                            WHEN last_term_seq IS NOT NULL AND first_hire_seq IS NOT NULL
                            AND last_term_seq < first_hire_seq THEN 1
                        END) as termination_before_hire
                    FROM lifecycle_gaps
                """

                formatted_query = audit_trail_query.format(scenario_filter=scenario_filter)

                audit_result = conn.execute(formatted_query, params).fetchone()

                if audit_result:
                    (employees_analyzed, missing_hires, multiple_hires,
                     term_before_hire) = audit_result

                    if missing_hires and missing_hires > 0:
                        audit_trail_gaps.append({
                            "type": "missing_hire_events",
                            "count": missing_hires,
                            "description": f"{missing_hires} employees without hire events"
                        })

                    if multiple_hires and multiple_hires > 0:
                        audit_trail_gaps.append({
                            "type": "multiple_hire_events",
                            "count": multiple_hires,
                            "description": f"{multiple_hires} employees with multiple hire events"
                        })

                    if term_before_hire and term_before_hire > 0:
                        audit_trail_gaps.append({
                            "type": "termination_before_hire",
                            "count": term_before_hire,
                            "description": f"{term_before_hire} employees terminated before hired"
                        })

                # 4. Validate event ordering and timestamp consistency
                timestamp_query = """
                    SELECT
                        COUNT(*) as total_events,
                        COUNT(CASE WHEN effective_date > created_at::DATE THEN 1 END) as future_effective_dates,
                        COUNT(CASE WHEN created_at IS NULL THEN 1 END) as null_timestamps
                    FROM fct_yearly_events
                    WHERE simulation_year BETWEEN ? AND ?
                    {scenario_filter}
                """

                formatted_query = timestamp_query.format(scenario_filter=scenario_filter)

                timestamp_result = conn.execute(formatted_query, params).fetchone()

                if timestamp_result:
                    total_ts_events, future_dates, null_timestamps = timestamp_result

                    if future_dates and future_dates > 0:
                        immutability_violations.append(
                            f"{future_dates} events with effective dates in the future"
                        )

                    if null_timestamps and null_timestamps > 0:
                        uuid_violations.append(f"{null_timestamps} events with NULL timestamps")

            # Determine validation result
            execution_time = time.time() - start_time

            # Critical failures
            critical_issues = []
            if uuid_violations:
                critical_issues.extend(uuid_violations)
            if duplicate_events:
                critical_issues.extend(duplicate_events)
            if immutability_violations:
                critical_issues.extend(immutability_violations)

            if critical_issues:
                return EventSourcingValidationResult(
                    check_name=f"event_sourcing_integrity_{start_year}_{end_year}",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Critical event sourcing violations: {len(critical_issues)} issues",
                    details={
                        "critical_issues": critical_issues,
                        "audit_trail_gaps": audit_trail_gaps,
                        "total_events_validated": total_events
                    },
                    execution_time_seconds=execution_time,
                    events_validated=total_events,
                    missing_events=missing_events,
                    duplicate_events=duplicate_events,
                    uuid_violations=uuid_violations,
                    immutability_violations=immutability_violations,
                    audit_trail_gaps=audit_trail_gaps
                )

            # Warning conditions
            severity = ValidationSeverity.INFO
            message = f"Event sourcing integrity validated: {total_events:,} events checked"

            if audit_trail_gaps:
                severity = ValidationSeverity.WARNING
                message = f"Event sourcing validated with {len(audit_trail_gaps)} audit trail gaps"

            return EventSourcingValidationResult(
                check_name=f"event_sourcing_integrity_{start_year}_{end_year}",
                status=ValidationStatus.PASSED,
                severity=severity,
                message=message,
                details={
                    "events_validated": total_events,
                    "audit_trail_gaps": audit_trail_gaps
                },
                execution_time_seconds=execution_time,
                events_validated=total_events,
                missing_events=missing_events,
                duplicate_events=duplicate_events,
                uuid_violations=uuid_violations,
                immutability_violations=immutability_violations,
                audit_trail_gaps=audit_trail_gaps
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Event sourcing integrity validation failed: {e}")

            return EventSourcingValidationResult(
                check_name=f"event_sourcing_integrity_{start_year}_{end_year}",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Event sourcing validation error: {e}",
                details={"error": str(e), "years": f"{start_year}-{end_year}"},
                execution_time_seconds=execution_time
            )

    def validate_business_logic_compliance(
        self,
        start_year: int,
        end_year: int,
        scenario_id: Optional[str] = None
    ) -> BusinessLogicValidationResult:
        """
        Validate business logic compliance across simulation years.

        Args:
            start_year: Starting year for validation
            end_year: Ending year for validation
            scenario_id: Optional scenario ID for filtering

        Returns:
            Business logic validation result with rule compliance analysis
        """
        start_time = time.time()
        logger.info(f"Validating business logic compliance: {start_year}-{end_year}")

        try:
            rule_violations = []
            compensation_violations = []
            hiring_pattern_anomalies = []
            termination_pattern_anomalies = []
            rules_checked = 0

            with self.db_manager.get_connection(read_only=True) as conn:
                # 1. Validate compensation growth patterns
                compensation_query = """
                    WITH yearly_compensation AS (
                        SELECT
                            simulation_year,
                            AVG(compensation) as avg_compensation,
                            COUNT(*) as employee_count,
                            STDDEV(compensation) as compensation_stddev
                        FROM fct_workforce_snapshot
                        WHERE simulation_year BETWEEN ? AND ?
                        AND employment_status = 'active'
                        {scenario_filter}
                        GROUP BY simulation_year
                        ORDER BY simulation_year
                    ),
                    compensation_growth AS (
                        SELECT
                            simulation_year,
                            avg_compensation,
                            LAG(avg_compensation) OVER (ORDER BY simulation_year) as prev_avg_compensation,
                            (avg_compensation - LAG(avg_compensation) OVER (ORDER BY simulation_year)) /
                             LAG(avg_compensation) OVER (ORDER BY simulation_year) as growth_rate
                        FROM yearly_compensation
                    )
                    SELECT
                        simulation_year,
                        avg_compensation,
                        growth_rate
                    FROM compensation_growth
                    WHERE growth_rate IS NOT NULL
                    AND (growth_rate < -0.02 OR growth_rate > 0.15)  -- Outside -2% to +15%
                """

                scenario_filter = "AND scenario_id = ?" if scenario_id else ""
                formatted_query = compensation_query.format(scenario_filter=scenario_filter)

                params = [start_year, end_year]
                if scenario_id:
                    params.append(scenario_id)

                comp_results = conn.execute(formatted_query, params).fetchall()
                rules_checked += 1

                for result in comp_results:
                    year, avg_comp, growth_rate = result
                    compensation_violations.append(
                        f"Year {year}: Compensation growth rate {growth_rate:.2%} outside expected range"
                    )

                # 2. Validate hiring patterns and growth rates
                hiring_query = """
                    WITH yearly_hires AS (
                        SELECT
                            simulation_year,
                            COUNT(*) as hire_count
                        FROM fct_yearly_events
                        WHERE simulation_year BETWEEN ? AND ?
                        AND event_type = 'hire'
                        {scenario_filter}
                        GROUP BY simulation_year
                    ),
                    yearly_workforce AS (
                        SELECT
                            simulation_year,
                            COUNT(*) as workforce_size
                        FROM fct_workforce_snapshot
                        WHERE simulation_year BETWEEN ? AND ?
                        AND employment_status = 'active'
                        {scenario_filter}
                        GROUP BY simulation_year
                    )
                    SELECT
                        h.simulation_year,
                        h.hire_count,
                        w.workforce_size,
                        CAST(h.hire_count AS FLOAT) / w.workforce_size as hire_rate
                    FROM yearly_hires h
                    JOIN yearly_workforce w ON h.simulation_year = w.simulation_year
                    WHERE CAST(h.hire_count AS FLOAT) / w.workforce_size > 0.25  -- More than 25% hire rate
                """

                formatted_query = hiring_query.format(scenario_filter=scenario_filter)

                params = [start_year, end_year, start_year, end_year]
                if scenario_id:
                    params.extend([scenario_id, scenario_id])

                hiring_results = conn.execute(formatted_query, params).fetchall()
                rules_checked += 1

                for result in hiring_results:
                    year, hire_count, workforce_size, hire_rate = result
                    hiring_pattern_anomalies.append({
                        "year": year,
                        "hire_count": hire_count,
                        "workforce_size": workforce_size,
                        "hire_rate": float(hire_rate),
                        "anomaly_type": "excessive_hiring_rate"
                    })

                # 3. Validate termination patterns
                termination_query = """
                    WITH yearly_terminations AS (
                        SELECT
                            simulation_year,
                            COUNT(*) as termination_count,
                            COUNT(CASE WHEN JSON_EXTRACT_STRING(payload, 'termination_reason') = 'involuntary' THEN 1 END) as involuntary_count,
                            COUNT(CASE WHEN JSON_EXTRACT_STRING(payload, 'termination_reason') = 'voluntary' THEN 1 END) as voluntary_count
                        FROM fct_yearly_events
                        WHERE simulation_year BETWEEN ? AND ?
                        AND event_type = 'termination'
                        {scenario_filter}
                        GROUP BY simulation_year
                    ),
                    yearly_workforce AS (
                        SELECT
                            simulation_year,
                            COUNT(*) as workforce_size
                        FROM fct_workforce_snapshot
                        WHERE simulation_year BETWEEN ? AND ?
                        AND employment_status = 'active'
                        {scenario_filter}
                        GROUP BY simulation_year
                    )
                    SELECT
                        t.simulation_year,
                        t.termination_count,
                        t.involuntary_count,
                        t.voluntary_count,
                        w.workforce_size,
                        CAST(t.termination_count AS FLOAT) / w.workforce_size as termination_rate,
                        CAST(t.involuntary_count AS FLOAT) / t.termination_count as involuntary_ratio
                    FROM yearly_terminations t
                    JOIN yearly_workforce w ON t.simulation_year = w.simulation_year
                    WHERE CAST(t.termination_count AS FLOAT) / w.workforce_size > 0.30  -- More than 30% termination rate
                    OR CAST(t.involuntary_count AS FLOAT) / t.termination_count > 0.80  -- More than 80% involuntary
                """

                formatted_query = termination_query.format(scenario_filter=scenario_filter)

                termination_results = conn.execute(formatted_query, params).fetchall()
                rules_checked += 1

                for result in termination_results:
                    (year, term_count, invol_count, vol_count, workforce_size,
                     term_rate, invol_ratio) = result

                    anomaly_type = "excessive_termination_rate"
                    if invol_ratio and invol_ratio > 0.80:
                        anomaly_type = "excessive_involuntary_terminations"

                    termination_pattern_anomalies.append({
                        "year": year,
                        "termination_count": term_count,
                        "workforce_size": workforce_size,
                        "termination_rate": float(term_rate),
                        "involuntary_ratio": float(invol_ratio or 0),
                        "anomaly_type": anomaly_type
                    })

                # 4. Validate promotion patterns and job level distributions
                promotion_query = """
                    WITH yearly_promotions AS (
                        SELECT
                            simulation_year,
                            COUNT(*) as promotion_count,
                            AVG(CAST(JSON_EXTRACT_STRING(payload, 'new_job_level') AS INTEGER) -
                                CAST(JSON_EXTRACT_STRING(payload, 'job_level') AS INTEGER)) as avg_level_jump
                        FROM fct_yearly_events
                        WHERE simulation_year BETWEEN ? AND ?
                        AND event_type = 'promotion'
                        {scenario_filter}
                        GROUP BY simulation_year
                    )
                    SELECT
                        simulation_year,
                        promotion_count,
                        avg_level_jump
                    FROM yearly_promotions
                    WHERE avg_level_jump > 2.0  -- Average promotion more than 2 levels
                """

                formatted_query = promotion_query.format(scenario_filter=scenario_filter)

                promotion_results = conn.execute(formatted_query, params).fetchall()
                rules_checked += 1

                for result in promotion_results:
                    year, promo_count, avg_jump = result
                    rule_violations.append({
                        "rule": "promotion_level_jump",
                        "year": year,
                        "violation": f"Average promotion level jump {avg_jump:.1f} exceeds maximum of 2.0",
                        "severity": "warning"
                    })

            # Determine validation result
            execution_time = time.time() - start_time

            # Critical violations
            critical_violations = [v for v in rule_violations if v.get("severity") == "critical"]

            if critical_violations or len(compensation_violations) > 2:
                return BusinessLogicValidationResult(
                    check_name=f"business_logic_compliance_{start_year}_{end_year}",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Critical business logic violations: {len(critical_violations + compensation_violations)}",
                    details={
                        "critical_violations": critical_violations,
                        "compensation_violations": compensation_violations,
                        "hiring_anomalies": hiring_pattern_anomalies,
                        "termination_anomalies": termination_pattern_anomalies
                    },
                    execution_time_seconds=execution_time,
                    business_rules_checked=rules_checked,
                    rule_violations=rule_violations,
                    compensation_violations=compensation_violations,
                    hiring_pattern_anomalies=hiring_pattern_anomalies,
                    termination_pattern_anomalies=termination_pattern_anomalies
                )

            # Warning conditions
            severity = ValidationSeverity.INFO
            message = f"Business logic compliance validated: {rules_checked} rules checked"

            if (rule_violations or compensation_violations or hiring_pattern_anomalies or
                termination_pattern_anomalies):
                total_warnings = (len(rule_violations) + len(compensation_violations) +
                                len(hiring_pattern_anomalies) + len(termination_pattern_anomalies))
                severity = ValidationSeverity.WARNING
                message = f"Business logic validated with {total_warnings} warnings"

            return BusinessLogicValidationResult(
                check_name=f"business_logic_compliance_{start_year}_{end_year}",
                status=ValidationStatus.PASSED,
                severity=severity,
                message=message,
                details={
                    "rules_checked": rules_checked,
                    "rule_violations": rule_violations,
                    "compensation_violations": compensation_violations,
                    "hiring_anomalies": hiring_pattern_anomalies,
                    "termination_anomalies": termination_pattern_anomalies
                },
                execution_time_seconds=execution_time,
                business_rules_checked=rules_checked,
                rule_violations=rule_violations,
                compensation_violations=compensation_violations,
                hiring_pattern_anomalies=hiring_pattern_anomalies,
                termination_pattern_anomalies=termination_pattern_anomalies
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Business logic compliance validation failed: {e}")

            return BusinessLogicValidationResult(
                check_name=f"business_logic_compliance_{start_year}_{end_year}",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Business logic validation error: {e}",
                details={"error": str(e), "years": f"{start_year}-{end_year}"},
                execution_time_seconds=execution_time
            )

    def validate_workforce_state_consistency(
        self,
        year: int,
        scenario_id: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate workforce state consistency for a specific year.

        Args:
            year: Simulation year to validate
            scenario_id: Optional scenario ID for filtering

        Returns:
            Validation result for workforce state consistency
        """
        start_time = time.time()
        logger.info(f"Validating workforce state consistency for year {year}")

        try:
            issues = []

            with self.db_manager.get_connection(read_only=True) as conn:
                # Check for orphaned events (events without corresponding workforce records)
                orphan_query = """
                    SELECT COUNT(*) as orphan_count
                    FROM fct_yearly_events e
                    LEFT JOIN fct_workforce_snapshot w ON e.employee_id = w.employee_id
                        AND e.simulation_year = w.simulation_year
                    WHERE e.simulation_year = ?
                    AND w.employee_id IS NULL
                    {scenario_filter}
                """

                scenario_filter = "AND e.scenario_id = ?" if scenario_id else ""
                formatted_query = orphan_query.format(scenario_filter=scenario_filter)

                params = [year]
                if scenario_id:
                    params.append(scenario_id)

                orphan_result = conn.execute(formatted_query, params).fetchone()

                if orphan_result and orphan_result[0] > 0:
                    issues.append(f"{orphan_result[0]} orphaned events found")

                # Check for workforce records without any events
                missing_events_query = """
                    SELECT COUNT(*) as missing_events_count
                    FROM fct_workforce_snapshot w
                    LEFT JOIN fct_yearly_events e ON w.employee_id = e.employee_id
                        AND w.simulation_year = e.simulation_year
                    WHERE w.simulation_year = ?
                    AND e.employee_id IS NULL
                    {scenario_filter}
                """

                scenario_filter = "AND w.scenario_id = ?" if scenario_id else ""
                formatted_query = missing_events_query.format(scenario_filter=scenario_filter)

                missing_result = conn.execute(formatted_query, params).fetchone()

                if missing_result and missing_result[0] > 0:
                    issues.append(f"{missing_result[0]} workforce records without events")

            execution_time = time.time() - start_time

            if issues:
                return ValidationResult(
                    check_name=f"workforce_state_consistency_{year}",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"Workforce state consistency issues: {len(issues)}",
                    details={"issues": issues},
                    execution_time_seconds=execution_time
                )

            return ValidationResult(
                check_name=f"workforce_state_consistency_{year}",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.INFO,
                message=f"Workforce state consistency validated for year {year}",
                details={"year": year},
                execution_time_seconds=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Workforce state consistency validation failed: {e}")

            return ValidationResult(
                check_name=f"workforce_state_consistency_{year}",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Workforce validation error: {e}",
                details={"error": str(e), "year": year},
                execution_time_seconds=execution_time
            )

    def get_validation_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for validation operations."""
        return {
            **self._performance_metrics,
            "enable_performance_optimization": self.enable_performance_optimization,
            "batch_size": self.batch_size,
            "max_validation_time_seconds": self.max_validation_time_seconds
        }

    def validate_simulation_reproducibility(
        self,
        simulation_id_1: str,
        simulation_id_2: str,
        tolerance: float = 0.01
    ) -> ValidationResult:
        """
        Validate that two simulations with identical parameters produce consistent results.

        Args:
            simulation_id_1: First simulation ID for comparison
            simulation_id_2: Second simulation ID for comparison
            tolerance: Acceptable difference tolerance (default 1%)

        Returns:
            Validation result for simulation reproducibility
        """
        start_time = time.time()
        logger.info(f"Validating simulation reproducibility: {simulation_id_1} vs {simulation_id_2}")

        try:
            differences = []

            with self.db_manager.get_connection(read_only=True) as conn:
                # Compare workforce sizes by year
                workforce_query = """
                    SELECT
                        s1.simulation_year,
                        s1.workforce_count as count_1,
                        s2.workforce_count as count_2,
                        ABS(s1.workforce_count - s2.workforce_count) as diff,
                        ABS(s1.workforce_count - s2.workforce_count) / CAST(s1.workforce_count AS FLOAT) as diff_pct
                    FROM (
                        SELECT simulation_year, COUNT(*) as workforce_count
                        FROM fct_workforce_snapshot
                        WHERE scenario_id = ?
                        GROUP BY simulation_year
                    ) s1
                    JOIN (
                        SELECT simulation_year, COUNT(*) as workforce_count
                        FROM fct_workforce_snapshot
                        WHERE scenario_id = ?
                        GROUP BY simulation_year
                    ) s2 ON s1.simulation_year = s2.simulation_year
                    WHERE ABS(s1.workforce_count - s2.workforce_count) / CAST(s1.workforce_count AS FLOAT) > ?
                """

                workforce_results = conn.execute(
                    workforce_query,
                    [simulation_id_1, simulation_id_2, tolerance]
                ).fetchall()

                for result in workforce_results:
                    year, count_1, count_2, diff, diff_pct = result
                    differences.append({
                        "type": "workforce_size",
                        "year": year,
                        "simulation_1": count_1,
                        "simulation_2": count_2,
                        "difference": diff,
                        "difference_pct": float(diff_pct)
                    })

            execution_time = time.time() - start_time

            if differences:
                return ValidationResult(
                    check_name="simulation_reproducibility",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"Reproducibility issues found: {len(differences)} differences",
                    details={
                        "differences": differences,
                        "tolerance": tolerance,
                        "simulation_1": simulation_id_1,
                        "simulation_2": simulation_id_2
                    },
                    execution_time_seconds=execution_time
                )

            return ValidationResult(
                check_name="simulation_reproducibility",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.INFO,
                message=f"Simulations are reproducible within {tolerance:.1%} tolerance",
                details={
                    "tolerance": tolerance,
                    "simulation_1": simulation_id_1,
                    "simulation_2": simulation_id_2
                },
                execution_time_seconds=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Simulation reproducibility validation failed: {e}")

            return ValidationResult(
                check_name="simulation_reproducibility",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Reproducibility validation error: {e}",
                details={"error": str(e)},
                execution_time_seconds=execution_time
            )

    def validate_year_in_progress(
        self,
        year: int,
        scenario_id: Optional[str] = None
    ) -> ValidationResult:
        """
        Perform lightweight validation during year processing for real-time feedback.

        Args:
            year: Current simulation year being processed
            scenario_id: Optional scenario ID for filtering

        Returns:
            Validation result for in-progress year validation
        """
        if self._circuit_breaker_open:
            return ValidationResult(
                check_name=f"year_in_progress_{year}",
                status=ValidationStatus.SKIPPED,
                severity=ValidationSeverity.WARNING,
                message="Validation skipped due to circuit breaker",
                details={"circuit_breaker_open": True}
            )

        start_time = time.time()
        logger.debug(f"Performing in-progress validation for year {year}")

        try:
            issues = []
            warnings = []

            with self.db_manager.get_connection(read_only=True) as conn:
                # Quick check for basic data consistency
                quick_check_query = """
                    SELECT
                        COUNT(*) as total_events,
                        COUNT(CASE WHEN event_id IS NULL THEN 1 END) as null_event_ids,
                        COUNT(CASE WHEN employee_id IS NULL THEN 1 END) as null_employee_ids,
                        COUNT(DISTINCT employee_id) as unique_employees
                    FROM fct_yearly_events
                    WHERE simulation_year = ?
                    {scenario_filter}
                """

                scenario_filter = "AND scenario_id = ?" if scenario_id else ""
                formatted_query = quick_check_query.format(scenario_filter=scenario_filter)

                params = [year]
                if scenario_id:
                    params.append(scenario_id)

                result = conn.execute(formatted_query, params).fetchone()

                if result:
                    total_events, null_event_ids, null_employee_ids, unique_employees = result

                    if null_event_ids > 0:
                        issues.append(f"{null_event_ids} events with NULL event IDs")

                    if null_employee_ids > 0:
                        issues.append(f"{null_employee_ids} events with NULL employee IDs")

                    if total_events == 0:
                        warnings.append("No events found for current year")
                    elif unique_employees < 10:  # Very small workforce
                        warnings.append(f"Very small workforce detected: {unique_employees} employees")

            execution_time = time.time() - start_time

            # Update performance tracking
            self._performance_metrics[f"year_{year}_validation_time"] = execution_time

            if issues:
                self._validation_failures += 1
                if self._validation_failures >= self._max_validation_failures:
                    self._circuit_breaker_open = True
                    logger.warning("Validation circuit breaker opened due to repeated failures")

                return ValidationResult(
                    check_name=f"year_in_progress_{year}",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"In-progress validation issues: {len(issues)} errors",
                    details={"issues": issues, "warnings": warnings},
                    execution_time_seconds=execution_time
                )

            # Reset failure counter on success
            self._validation_failures = max(0, self._validation_failures - 1)

            severity = ValidationSeverity.WARNING if warnings else ValidationSeverity.INFO
            message = f"Year {year} in-progress validation passed"
            if warnings:
                message += f" with {len(warnings)} warnings"

            return ValidationResult(
                check_name=f"year_in_progress_{year}",
                status=ValidationStatus.PASSED,
                severity=severity,
                message=message,
                details={"warnings": warnings},
                execution_time_seconds=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"In-progress validation failed for year {year}: {e}")

            self._validation_failures += 1
            if self._validation_failures >= self._max_validation_failures:
                self._circuit_breaker_open = True

            return ValidationResult(
                check_name=f"year_in_progress_{year}",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"In-progress validation error: {e}",
                details={"error": str(e), "year": year},
                execution_time_seconds=execution_time
            )

    def validate_financial_calculations_integrity(
        self,
        start_year: int,
        end_year: int,
        scenario_id: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate financial calculation integrity across years.

        Args:
            start_year: Starting year for validation
            end_year: Ending year for validation
            scenario_id: Optional scenario ID for filtering

        Returns:
            Validation result for financial calculations integrity
        """
        start_time = time.time()
        logger.info(f"Validating financial calculations integrity: {start_year}-{end_year}")

        try:
            calculation_errors = []
            consistency_issues = []

            with self.db_manager.get_connection(read_only=True) as conn:
                # 1. Validate compensation calculation consistency
                compensation_validation_query = """
                    WITH yearly_compensation_stats AS (
                        SELECT
                            simulation_year,
                            AVG(compensation) as avg_compensation,
                            STDDEV(compensation) as stddev_compensation,
                            MIN(compensation) as min_compensation,
                            MAX(compensation) as max_compensation,
                            COUNT(*) as employee_count
                        FROM fct_workforce_snapshot
                        WHERE simulation_year BETWEEN ? AND ?
                        AND employment_status = 'active'
                        {scenario_filter}
                        GROUP BY simulation_year
                    ),
                    compensation_changes AS (
                        SELECT
                            simulation_year,
                            avg_compensation,
                            LAG(avg_compensation) OVER (ORDER BY simulation_year) as prev_avg_compensation,
                            (avg_compensation - LAG(avg_compensation) OVER (ORDER BY simulation_year)) /
                             LAG(avg_compensation) OVER (ORDER BY simulation_year) as growth_rate,
                            stddev_compensation / avg_compensation as coefficient_of_variation
                        FROM yearly_compensation_stats
                    )
                    SELECT
                        simulation_year,
                        avg_compensation,
                        growth_rate,
                        coefficient_of_variation
                    FROM compensation_changes
                    WHERE (
                        (growth_rate IS NOT NULL AND (growth_rate < -0.05 OR growth_rate > 0.20)) OR
                        (coefficient_of_variation > 2.0)  -- Very high variance
                    )
                """

                scenario_filter = "AND scenario_id = ?" if scenario_id else ""
                formatted_query = compensation_validation_query.format(scenario_filter=scenario_filter)

                params = [start_year, end_year]
                if scenario_id:
                    params.append(scenario_id)

                comp_results = conn.execute(formatted_query, params).fetchall()

                for result in comp_results:
                    year, avg_comp, growth_rate, cv = result
                    if growth_rate is not None and (growth_rate < -0.05 or growth_rate > 0.20):
                        calculation_errors.append({
                            "type": "unusual_compensation_growth",
                            "year": year,
                            "growth_rate": float(growth_rate),
                            "avg_compensation": float(avg_comp)
                        })

                    if cv and cv > 2.0:
                        consistency_issues.append({
                            "type": "high_compensation_variance",
                            "year": year,
                            "coefficient_of_variation": float(cv)
                        })

                # 2. Validate event-driven compensation changes
                event_compensation_query = """
                    WITH compensation_events AS (
                        SELECT
                            employee_id,
                            simulation_year,
                            event_type,
                            CAST(JSON_EXTRACT_STRING(payload, 'compensation_change') AS DECIMAL) as comp_change,
                            CAST(JSON_EXTRACT_STRING(payload, 'new_compensation') AS DECIMAL) as new_compensation,
                            CAST(JSON_EXTRACT_STRING(payload, 'previous_compensation') AS DECIMAL) as prev_compensation
                        FROM fct_yearly_events
                        WHERE simulation_year BETWEEN ? AND ?
                        AND event_type IN ('merit', 'promotion', 'raise')
                        AND JSON_EXTRACT_STRING(payload, 'compensation_change') IS NOT NULL
                        {scenario_filter}
                    ),
                    invalid_calculations AS (
                        SELECT
                            employee_id,
                            simulation_year,
                            event_type,
                            comp_change,
                            new_compensation,
                            prev_compensation,
                            ABS((new_compensation - prev_compensation) - comp_change) as calculation_error
                        FROM compensation_events
                        WHERE new_compensation IS NOT NULL
                        AND prev_compensation IS NOT NULL
                        AND prev_compensation > 0
                        AND ABS((new_compensation - prev_compensation) - comp_change) > 0.01  -- More than 1 cent difference
                    )
                    SELECT
                        COUNT(*) as invalid_count,
                        AVG(calculation_error) as avg_error,
                        MAX(calculation_error) as max_error
                    FROM invalid_calculations
                """

                formatted_query = event_compensation_query.format(scenario_filter=scenario_filter)

                event_result = conn.execute(formatted_query, params).fetchone()

                if event_result and event_result[0] > 0:
                    invalid_count, avg_error, max_error = event_result
                    calculation_errors.append({
                        "type": "compensation_calculation_mismatch",
                        "invalid_count": invalid_count,
                        "average_error": float(avg_error or 0),
                        "maximum_error": float(max_error or 0)
                    })

                # 3. Validate workforce size calculations
                workforce_consistency_query = """
                    WITH workforce_changes AS (
                        SELECT
                            simulation_year,
                            COUNT(*) as workforce_size,
                            LAG(COUNT(*)) OVER (ORDER BY simulation_year) as prev_workforce_size
                        FROM fct_workforce_snapshot
                        WHERE simulation_year BETWEEN ? AND ?
                        AND employment_status = 'active'
                        {scenario_filter}
                        GROUP BY simulation_year
                    ),
                    event_changes AS (
                        SELECT
                            simulation_year,
                            COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as hires,
                            COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as terminations
                        FROM fct_yearly_events
                        WHERE simulation_year BETWEEN ? AND ?
                        {scenario_filter}
                        GROUP BY simulation_year
                    )
                    SELECT
                        w.simulation_year,
                        w.workforce_size,
                        w.prev_workforce_size,
                        e.hires,
                        e.terminations,
                        (w.prev_workforce_size + e.hires - e.terminations) as calculated_workforce,
                        ABS(w.workforce_size - (w.prev_workforce_size + e.hires - e.terminations)) as difference
                    FROM workforce_changes w
                    JOIN event_changes e ON w.simulation_year = e.simulation_year
                    WHERE w.prev_workforce_size IS NOT NULL
                    AND ABS(w.workforce_size - (w.prev_workforce_size + e.hires - e.terminations)) > 5  -- More than 5 employee difference
                """

                formatted_query = workforce_consistency_query.format(scenario_filter=scenario_filter)

                params_workforce = [start_year, end_year, start_year, end_year]
                if scenario_id:
                    params_workforce.extend([scenario_id, scenario_id])

                workforce_results = conn.execute(formatted_query, params_workforce).fetchall()

                for result in workforce_results:
                    (year, actual_size, prev_size, hires, terms,
                     calculated_size, difference) = result
                    consistency_issues.append({
                        "type": "workforce_calculation_mismatch",
                        "year": year,
                        "actual_workforce": actual_size,
                        "calculated_workforce": calculated_size,
                        "difference": difference,
                        "hires": hires,
                        "terminations": terms
                    })

            execution_time = time.time() - start_time

            # Determine result severity
            if calculation_errors:
                return ValidationResult(
                    check_name=f"financial_calculations_integrity_{start_year}_{end_year}",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Financial calculation errors detected: {len(calculation_errors)} issues",
                    details={
                        "calculation_errors": calculation_errors,
                        "consistency_issues": consistency_issues
                    },
                    execution_time_seconds=execution_time
                )

            severity = ValidationSeverity.WARNING if consistency_issues else ValidationSeverity.INFO
            message = f"Financial calculations integrity validated"
            if consistency_issues:
                message += f" with {len(consistency_issues)} consistency warnings"

            return ValidationResult(
                check_name=f"financial_calculations_integrity_{start_year}_{end_year}",
                status=ValidationStatus.PASSED,
                severity=severity,
                message=message,
                details={"consistency_issues": consistency_issues},
                execution_time_seconds=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Financial calculations integrity validation failed: {e}")

            return ValidationResult(
                check_name=f"financial_calculations_integrity_{start_year}_{end_year}",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Financial validation error: {e}",
                details={"error": str(e), "years": f"{start_year}-{end_year}"},
                execution_time_seconds=execution_time
            )

    def validate_uuid_integrity_comprehensive(
        self,
        start_year: int,
        end_year: int,
        scenario_id: Optional[str] = None
    ) -> ValidationResult:
        """
        Comprehensive UUID integrity validation with audit trail verification.

        Args:
            start_year: Starting year for validation
            end_year: Ending year for validation
            scenario_id: Optional scenario ID for filtering

        Returns:
            Validation result for comprehensive UUID integrity
        """
        start_time = time.time()
        logger.info(f"Validating comprehensive UUID integrity: {start_year}-{end_year}")

        try:
            uuid_issues = []
            audit_trail_issues = []

            with self.db_manager.get_connection(read_only=True) as conn:
                # 1. Validate UUID format and uniqueness
                uuid_format_query = """
                    SELECT
                        COUNT(*) as total_events,
                        COUNT(CASE WHEN event_id IS NULL THEN 1 END) as null_uuids,
                        COUNT(CASE WHEN LENGTH(event_id) != 36 THEN 1 END) as invalid_length,
                        COUNT(CASE WHEN event_id NOT LIKE '%-%-%-%-%' THEN 1 END) as invalid_format,
                        COUNT(DISTINCT event_id) as unique_uuids
                    FROM fct_yearly_events
                    WHERE simulation_year BETWEEN ? AND ?
                    {scenario_filter}
                """

                scenario_filter = "AND scenario_id = ?" if scenario_id else ""
                formatted_query = uuid_format_query.format(scenario_filter=scenario_filter)

                params = [start_year, end_year]
                if scenario_id:
                    params.append(scenario_id)

                uuid_result = conn.execute(formatted_query, params).fetchone()

                if uuid_result:
                    (total_events, null_uuids, invalid_length,
                     invalid_format, unique_uuids) = uuid_result

                    if null_uuids > 0:
                        uuid_issues.append({
                            "type": "null_uuids",
                            "count": null_uuids,
                            "severity": "critical"
                        })

                    if invalid_length > 0:
                        uuid_issues.append({
                            "type": "invalid_uuid_length",
                            "count": invalid_length,
                            "severity": "critical"
                        })

                    if invalid_format > 0:
                        uuid_issues.append({
                            "type": "invalid_uuid_format",
                            "count": invalid_format,
                            "severity": "critical"
                        })

                    if total_events != unique_uuids:
                        duplicate_count = total_events - unique_uuids
                        uuid_issues.append({
                            "type": "duplicate_uuids",
                            "count": duplicate_count,
                            "severity": "critical"
                        })

                # 2. Validate UUID sequence and gaps
                uuid_sequence_query = """
                    WITH event_sequence AS (
                        SELECT
                            event_id,
                            employee_id,
                            simulation_year,
                            effective_date,
                            created_at,
                            ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY effective_date, created_at) as seq_num
                        FROM fct_yearly_events
                        WHERE simulation_year BETWEEN ? AND ?
                        {scenario_filter}
                        ORDER BY employee_id, effective_date, created_at
                    ),
                    sequence_gaps AS (
                        SELECT
                            employee_id,
                            COUNT(*) as total_events,
                            MIN(seq_num) as first_seq,
                            MAX(seq_num) as last_seq,
                            MAX(seq_num) - MIN(seq_num) + 1 as expected_events
                        FROM event_sequence
                        GROUP BY employee_id
                        HAVING COUNT(*) != (MAX(seq_num) - MIN(seq_num) + 1)
                    )
                    SELECT
                        COUNT(*) as employees_with_gaps,
                        SUM(expected_events - total_events) as total_missing_events
                    FROM sequence_gaps
                """

                formatted_query = uuid_sequence_query.format(scenario_filter=scenario_filter)

                sequence_result = conn.execute(formatted_query, params).fetchone()

                if sequence_result and sequence_result[0] > 0:
                    employees_with_gaps, missing_events = sequence_result
                    audit_trail_issues.append({
                        "type": "event_sequence_gaps",
                        "employees_affected": employees_with_gaps,
                        "missing_events": missing_events or 0,
                        "severity": "warning"
                    })

                # 3. Validate audit trail completeness
                audit_completeness_query = """
                    WITH employee_lifecycle AS (
                        SELECT
                            employee_id,
                            MIN(CASE WHEN event_type = 'hire' THEN effective_date END) as hire_date,
                            MAX(CASE WHEN event_type = 'termination' THEN effective_date END) as term_date,
                            COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as hire_count,
                            COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as term_count,
                            COUNT(*) as total_events
                        FROM fct_yearly_events
                        WHERE simulation_year BETWEEN ? AND ?
                        {scenario_filter}
                        GROUP BY employee_id
                    )
                    SELECT
                        COUNT(*) as total_employees,
                        COUNT(CASE WHEN hire_count = 0 THEN 1 END) as no_hire_events,
                        COUNT(CASE WHEN hire_count > 1 THEN 1 END) as multiple_hire_events,
                        COUNT(CASE WHEN term_date < hire_date THEN 1 END) as invalid_lifecycles
                    FROM employee_lifecycle
                """

                formatted_query = audit_completeness_query.format(scenario_filter=scenario_filter)

                audit_result = conn.execute(formatted_query, params).fetchone()

                if audit_result:
                    (total_employees, no_hire, multiple_hire, invalid_lifecycles) = audit_result

                    if no_hire > 0:
                        audit_trail_issues.append({
                            "type": "missing_hire_events",
                            "count": no_hire,
                            "total_employees": total_employees,
                            "severity": "warning"
                        })

                    if multiple_hire > 0:
                        audit_trail_issues.append({
                            "type": "multiple_hire_events",
                            "count": multiple_hire,
                            "severity": "warning"
                        })

                    if invalid_lifecycles > 0:
                        audit_trail_issues.append({
                            "type": "invalid_employee_lifecycles",
                            "count": invalid_lifecycles,
                            "severity": "error"
                        })

            execution_time = time.time() - start_time

            # Determine validation result
            critical_issues = [issue for issue in uuid_issues if issue.get("severity") == "critical"]
            error_issues = [issue for issue in audit_trail_issues if issue.get("severity") == "error"]

            if critical_issues:
                return ValidationResult(
                    check_name=f"uuid_integrity_comprehensive_{start_year}_{end_year}",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Critical UUID integrity violations: {len(critical_issues)} issues",
                    details={
                        "uuid_issues": uuid_issues,
                        "audit_trail_issues": audit_trail_issues,
                        "critical_issues": critical_issues
                    },
                    execution_time_seconds=execution_time
                )

            if error_issues:
                return ValidationResult(
                    check_name=f"uuid_integrity_comprehensive_{start_year}_{end_year}",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"UUID integrity errors: {len(error_issues)} issues",
                    details={
                        "uuid_issues": uuid_issues,
                        "audit_trail_issues": audit_trail_issues
                    },
                    execution_time_seconds=execution_time
                )

            severity = ValidationSeverity.WARNING if (uuid_issues or audit_trail_issues) else ValidationSeverity.INFO
            message = f"UUID integrity validation completed"
            if uuid_issues or audit_trail_issues:
                total_warnings = len(uuid_issues) + len(audit_trail_issues)
                message += f" with {total_warnings} warnings"

            return ValidationResult(
                check_name=f"uuid_integrity_comprehensive_{start_year}_{end_year}",
                status=ValidationStatus.PASSED,
                severity=severity,
                message=message,
                details={
                    "uuid_issues": uuid_issues,
                    "audit_trail_issues": audit_trail_issues
                },
                execution_time_seconds=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Comprehensive UUID integrity validation failed: {e}")

            return ValidationResult(
                check_name=f"uuid_integrity_comprehensive_{start_year}_{end_year}",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"UUID validation error: {e}",
                details={"error": str(e), "years": f"{start_year}-{end_year}"},
                execution_time_seconds=execution_time
            )

    def reset_circuit_breaker(self) -> None:
        """Reset the validation circuit breaker."""
        self._circuit_breaker_open = False
        self._validation_failures = 0
        logger.info("Validation circuit breaker reset")

    def get_validation_history(self) -> List[Dict[str, Any]]:
        """Get validation execution history."""
        return self._validation_history.copy()

    def get_comprehensive_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics including circuit breaker status."""
        base_metrics = self.get_validation_performance_metrics()

        return {
            **base_metrics,
            "circuit_breaker_status": {
                "open": self._circuit_breaker_open,
                "failure_count": self._validation_failures,
                "max_failures": self._max_validation_failures
            },
            "validation_mode": self.validation_mode.value if hasattr(self.validation_mode, 'value') else str(self.validation_mode),
            "real_time_validation_enabled": self.enable_real_time_validation,
            "fail_fast_enabled": self.fail_fast,
            "validation_history_count": len(self._validation_history)
        }
