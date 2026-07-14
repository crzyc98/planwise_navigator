from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.validation import (
    DataValidator,
    EventSequenceRule,
    ValidationResult,
    ValidationRule,
    ValidationSeverity,
)

pytestmark = pytest.mark.fast


class _Rule(ValidationRule):
    name = "rule"
    severity = ValidationSeverity.ERROR

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def validate(self, conn, year):
        if self.error:
            raise self.error
        return self.result


def _validator():
    manager = MagicMock()

    @contextmanager
    def connection():
        yield MagicMock()

    manager.get_connection = connection
    return DataValidator(manager)


def _result(severity, passed, affected=None):
    return ValidationResult(
        "check", severity, passed, "unsafe message", {"raw": "data"}, affected
    )


def test_safe_results_have_counts_and_severity_disposition():
    results = [
        _result(ValidationSeverity.INFO, True),
        _result(ValidationSeverity.WARNING, False, 3),
    ]
    safe = DataValidator.to_safe_results(results)
    assert safe["disposition"] == "passed_with_warnings"
    assert safe["results"][0]["affected_record_count"] == 0
    assert safe["results"][1]["affected_record_count"] == 3
    assert "message" not in safe["results"][0]
    assert (
        DataValidator.disposition([_result(ValidationSeverity.ERROR, False, 1)])
        == "failed"
    )


def test_rule_exception_becomes_failed_error_with_unknown_count():
    validator = _validator()
    validator.register_rule(_Rule(error=RuntimeError("boom")))
    result = validator.validate_year_results(2025)[0]
    assert result.passed is False
    assert result.severity == ValidationSeverity.ERROR
    assert result.affected_records is None


@pytest.mark.parametrize(
    ("employee_id", "event_date", "expected_count"),
    [
        ("before", "2026-05-31", 0),
        ("same-day", "2026-06-01", 0),
        ("after", "2026-06-02", 1),
    ],
)
def test_event_sequence_rule_applies_strict_date_boundary(
    employee_id, event_date, expected_count
):
    connection = _event_connection()
    try:
        connection.execute(
            "INSERT INTO fct_yearly_events VALUES "
            "('scenario-a', 'plan-a', ?, 'termination', 2026, DATE '2026-06-01'), "
            "('scenario-a', 'plan-a', ?, 'raise', 2026, ?::DATE)",
            [employee_id, employee_id, event_date],
        )
        result = EventSequenceRule().validate(connection, 2026)
    finally:
        connection.close()
    assert result.affected_records == expected_count


def _event_connection():
    import duckdb

    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE fct_yearly_events ("
        "scenario_id VARCHAR, plan_design_id VARCHAR, employee_id VARCHAR, "
        "event_type VARCHAR, simulation_year INTEGER, effective_date DATE)"
    )
    return connection


def test_event_sequence_rule_uses_lifetime_earliest_scoped_termination():
    connection = _event_connection()
    try:
        connection.execute(
            "INSERT INTO fct_yearly_events VALUES "
            "('scenario-a', 'plan-a', 'duplicate', 'termination', 2025, DATE '2025-09-01'), "
            "('scenario-a', 'plan-a', 'duplicate', 'TERMINATION', 2026, DATE '2026-08-01'), "
            "('scenario-a', 'plan-a', 'duplicate', 'promotion', 2026, DATE '2026-01-01'), "
            "('scenario-b', 'plan-a', 'duplicate', 'raise', 2026, DATE '2026-07-01'), "
            "('scenario-a', 'plan-b', 'duplicate', 'raise', 2026, DATE '2026-07-01')"
        )
        result = EventSequenceRule().validate(connection, 2026)
    finally:
        connection.close()
    assert result.severity == ValidationSeverity.ERROR
    assert result.passed is False
    assert result.affected_records == 1
    assert result.details == {"invalid_events": 1}


def test_event_sequence_rule_excludes_termination_and_null_dates():
    connection = _event_connection()
    try:
        connection.execute(
            "INSERT INTO fct_yearly_events VALUES "
            "('scenario-a', 'plan-a', 'employee', 'termination', 2025, DATE '2025-09-01'), "
            "('scenario-a', 'plan-a', 'employee', 'TeRmInAtIoN', 2026, DATE '2026-09-01'), "
            "('scenario-a', 'plan-a', 'employee', 'raise', 2026, NULL)"
        )
        result = EventSequenceRule().validate(connection, 2026)
    finally:
        connection.close()
    assert result.passed is True
    assert result.affected_records == 0


def test_event_sequence_rule_preserves_configurable_column_names():
    import duckdb

    connection = duckdb.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE custom_events (sid VARCHAR, pid VARCHAR, person VARCHAR, "
            "kind VARCHAR, yr INTEGER, happened DATE)"
        )
        connection.execute(
            "INSERT INTO custom_events VALUES "
            "('s', 'p', 'e', 'termination', 2025, DATE '2025-01-01'), "
            "('s', 'p', 'e', 'raise', 2026, DATE '2026-01-01')"
        )
        result = EventSequenceRule(
            table="custom_events",
            event_col="kind",
            date_col="happened",
            year_col="yr",
            scenario_col="sid",
            plan_design_col="pid",
            employee_col="person",
        ).validate(connection, 2026)
    finally:
        connection.close()
    assert result.affected_records == 1
