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


def test_event_sequence_rule_uses_fact_effective_date_and_counts_failures():
    import duckdb

    connection = duckdb.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE fct_yearly_events ("
            "employee_id VARCHAR, event_type VARCHAR, simulation_year INTEGER, "
            "effective_date DATE)"
        )
        connection.execute(
            "INSERT INTO fct_yearly_events VALUES "
            "('E1', 'termination', 2026, DATE '2026-06-01'), "
            "('E1', 'raise', 2026, DATE '2026-07-01')"
        )
        result = EventSequenceRule().validate(connection, 2026)
    finally:
        connection.close()
    assert result.passed is False
    assert result.affected_records == 1
