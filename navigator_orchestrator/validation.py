#!/usr/bin/env python3
"""
Data Quality & Validation Framework for Navigator Orchestrator.

Provides a rule-based validation engine with configurable thresholds,
business rule checks, and simple anomaly detection utilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

from .utils import DatabaseConnectionManager


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    rule_name: str
    severity: ValidationSeverity
    passed: bool
    message: str
    details: Dict[str, Any]
    affected_records: Optional[int] = None


class ValidationRule(Protocol):
    name: str
    severity: ValidationSeverity

    def validate(self, db_connection, year: int) -> ValidationResult:  # pragma: no cover - Protocol
        ...


class DataValidator:
    """Main validation orchestrator."""

    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager
        self.rules: List[ValidationRule] = []

    def register_rule(self, rule: ValidationRule) -> None:
        self.rules.append(rule)

    def clear_rules(self) -> None:
        self.rules.clear()

    def validate_year_results(self, year: int) -> List[ValidationResult]:
        results: List[ValidationResult] = []
        with self.db_manager.get_connection() as conn:
            for rule in self.rules:
                try:
                    results.append(rule.validate(conn, year))
                except Exception as e:  # Defensive: capture rule errors as failed results
                    results.append(
                        ValidationResult(
                            rule_name=getattr(rule, "name", rule.__class__.__name__),
                            severity=ValidationSeverity.ERROR,
                            passed=False,
                            message=f"Validation rule failed: {e}",
                            details={"error": str(e)},
                        )
                    )
        return results

    @staticmethod
    def to_report_dict(results: List[ValidationResult]) -> Dict[str, Any]:
        summary = {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "by_severity": {
                s.value: sum(1 for r in results if r.severity == s and not r.passed)
                for s in ValidationSeverity
            },
        }
        return {
            "summary": summary,
            "results": [r.__dict__ for r in results],
        }


# Built-in rules
class RowCountDriftRule:
    """Validate row count drift between two tables for the given year.

    Parameters allow adapting to different schemas for testing and integration.
    """

    def __init__(
        self,
        source_table: str,
        target_table: str,
        *,
        year_column: str = "year",
        threshold: float = 0.005,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        name: str = "row_count_drift",
    ):
        self.source_table = source_table
        self.target_table = target_table
        self.year_column = year_column
        self.threshold = threshold
        self.severity = severity
        self.name = name

    def validate(self, conn, year: int) -> ValidationResult:
        raw_sql = f"SELECT COUNT(*) FROM {self.source_table} WHERE {self.year_column} = ?"
        staged_sql = f"SELECT COUNT(*) FROM {self.target_table} WHERE {self.year_column} = ?"
        raw_count = conn.execute(raw_sql, [year]).fetchone()[0]
        staged_count = conn.execute(staged_sql, [year]).fetchone()[0]

        drift = 0.0 if raw_count == 0 else abs(raw_count - staged_count) / max(1, raw_count)
        passed = drift <= self.threshold
        return ValidationResult(
            rule_name=self.name,
            severity=self.severity,
            passed=passed,
            message=f"Row count drift: {drift:.6f} (threshold={self.threshold})",
            details={
                "source_table": self.source_table,
                "target_table": self.target_table,
                "raw_count": raw_count,
                "staged_count": staged_count,
                "drift": drift,
                "threshold": self.threshold,
            },
            affected_records=abs(raw_count - staged_count),
        )


class HireTerminationRatioRule:
    """Validate hire to termination ratios are reasonable for a given year."""

    def __init__(
        self,
        *,
        table: str = "fct_yearly_events",
        event_col: str = "event_type",
        year_col: str = "simulation_year",
        max_ratio: float = 3.0,
        min_ratio: float = 0.3,
        severity: ValidationSeverity = ValidationSeverity.WARNING,
        name: str = "hire_termination_ratio",
    ):
        self.table = table
        self.event_col = event_col
        self.year_col = year_col
        self.max_ratio = max_ratio
        self.min_ratio = min_ratio
        self.severity = severity
        self.name = name

    def validate(self, conn, year: int) -> ValidationResult:
        query = f"""
        SELECT
            COUNT(CASE WHEN lower({self.event_col}) = 'hire' THEN 1 END) as hires,
            COUNT(CASE WHEN lower({self.event_col}) = 'termination' THEN 1 END) as terminations
        FROM {self.table}
        WHERE {self.year_col} = ?
        """
        hires, terms = conn.execute(query, [year]).fetchone()

        if terms == 0:
            ratio = float("inf")
            passed = False
            message = "No terminations found - unusual pattern"
        else:
            ratio = hires / terms
            passed = self.min_ratio <= ratio <= self.max_ratio
            message = f"Hire/termination ratio: {ratio:.2f} ({'PASS' if passed else 'FAIL'})"

        return ValidationResult(
            rule_name=self.name,
            severity=self.severity,
            passed=passed,
            message=message,
            details={
                "hires": hires,
                "terminations": terms,
                "ratio": ratio,
                "min_ratio": self.min_ratio,
                "max_ratio": self.max_ratio,
            },
        )


class EventSequenceRule:
    """Validate that no events occur after termination within the same year."""

    def __init__(
        self,
        *,
        table: str = "fct_yearly_events",
        event_col: str = "event_type",
        date_col: str = "event_date",
        year_col: str = "simulation_year",
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        name: str = "event_sequence_validation",
    ):
        self.table = table
        self.event_col = event_col
        self.date_col = date_col
        self.year_col = year_col
        self.severity = severity
        self.name = name

    def validate(self, conn, year: int) -> ValidationResult:
        invalid_sql = f"""
        WITH terms AS (
            SELECT employee_id, MIN({self.date_col}) AS term_date
            FROM {self.table}
            WHERE lower({self.event_col}) = 'termination' AND {self.year_col} = ?
            GROUP BY employee_id
        )
        SELECT COUNT(*) FROM {self.table} e
        JOIN terms t ON e.employee_id = t.employee_id
        WHERE e.{self.year_col} = ?
          AND lower(e.{self.event_col}) <> 'termination'
          AND e.{self.date_col} > t.term_date
        """
        count = conn.execute(invalid_sql, [year, year]).fetchone()[0]
        passed = count == 0
        return ValidationResult(
            rule_name=self.name,
            severity=self.severity,
            passed=passed,
            message=("No invalid post-termination events" if passed else f"{count} invalid post-termination events"),
            details={"invalid_events": count},
            affected_records=count,
        )


class EventSpikeRule:
    """Detect unusual spike in total events compared to previous year."""

    def __init__(
        self,
        *,
        table: str = "fct_yearly_events",
        year_col: str = "simulation_year",
        spike_ratio: float = 2.0,
        severity: ValidationSeverity = ValidationSeverity.WARNING,
        name: str = "event_spike_detection",
    ):
        self.table = table
        self.year_col = year_col
        self.spike_ratio = spike_ratio
        self.severity = severity
        self.name = name

    def validate(self, conn, year: int) -> ValidationResult:
        q = f"SELECT COUNT(*) FROM {self.table} WHERE {self.year_col} = ?"
        cur = conn.execute(q, [year]).fetchone()[0]
        prev = conn.execute(q, [year - 1]).fetchone()[0]
        ratio = float("inf") if prev == 0 else cur / prev
        passed = prev == 0 or ratio <= self.spike_ratio
        return ValidationResult(
            rule_name=self.name,
            severity=self.severity,
            passed=passed,
            message=(
                "No spike detected" if passed else f"Event spike detected: ratio={ratio:.2f} (> {self.spike_ratio})"
            ),
            details={"current": cur, "previous": prev, "ratio": ratio, "threshold": self.spike_ratio},
        )
