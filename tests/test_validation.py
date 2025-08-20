from pathlib import Path

import duckdb

from navigator_orchestrator.utils import DatabaseConnectionManager
from navigator_orchestrator.validation import (DataValidator,
                                               EventSequenceRule,
                                               EventSpikeRule,
                                               HireTerminationRatioRule,
                                               RowCountDriftRule,
                                               ValidationResult,
                                               ValidationSeverity)


def _db(db_path: Path):
    conn = duckdb.connect(str(db_path))
    return conn


def test_data_quality_rules_configurable_thresholds(tmp_path: Path):
    dbp = tmp_path / "dq.duckdb"
    conn = _db(dbp)
    conn.execute("CREATE TABLE raw(year INTEGER, id INTEGER)")
    conn.execute("CREATE TABLE stg(year INTEGER, id INTEGER)")
    conn.execute(
        "INSERT INTO raw VALUES (2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5)"
    )
    conn.execute("INSERT INTO stg VALUES (2026, 1), (2026, 2), (2026, 3), (2026, 4)")
    conn.close()

    mgr = DatabaseConnectionManager(db_path=dbp)
    rule = RowCountDriftRule("raw", "stg", year_column="year", threshold=0.21)
    res = rule.validate(mgr.get_connection(), 2026)  # direct connection OK
    assert res.passed is True  # 1/5 = 0.2 <= 0.21


def test_business_rule_validation_hire_termination_ratios(tmp_path: Path):
    dbp = tmp_path / "dq.duckdb"
    conn = _db(dbp)
    conn.execute(
        "CREATE TABLE fct_yearly_events(employee_id VARCHAR, event_type VARCHAR, simulation_year INTEGER, event_date DATE)"
    )
    conn.execute("INSERT INTO fct_yearly_events VALUES ('E1','hire',2025,'2025-01-01')")
    conn.execute(
        "INSERT INTO fct_yearly_events VALUES ('E2','termination',2025,'2025-12-31')"
    )
    conn.close()

    mgr = DatabaseConnectionManager(db_path=dbp)
    rule = HireTerminationRatioRule(min_ratio=0.2, max_ratio=10.0)
    res = rule.validate(mgr.get_connection(), 2025)
    assert res.severity == ValidationSeverity.WARNING
    assert res.passed is True


def test_anomaly_detection_unusual_patterns(tmp_path: Path):
    dbp = tmp_path / "dq.duckdb"
    conn = _db(dbp)
    conn.execute(
        "CREATE TABLE fct_yearly_events(event_type VARCHAR, simulation_year INTEGER)"
    )
    # previous year 10 events, current 25 -> ratio 2.5
    conn.execute("INSERT INTO fct_yearly_events SELECT 'hire', 2025 FROM range(10)")
    conn.execute("INSERT INTO fct_yearly_events SELECT 'hire', 2026 FROM range(25)")
    conn.close()

    mgr = DatabaseConnectionManager(db_path=dbp)
    rule = EventSpikeRule(spike_ratio=2.0)
    res = rule.validate(mgr.get_connection(), 2026)
    assert res.passed is False
    assert "spike" in res.message.lower()


def test_validation_severity_levels(tmp_path: Path):
    dbp = tmp_path / "dq.duckdb"
    conn = _db(dbp)
    conn.execute(
        "CREATE TABLE fct_yearly_events(employee_id VARCHAR, event_type VARCHAR, simulation_year INTEGER, event_date DATE)"
    )
    conn.close()

    mgr = DatabaseConnectionManager(db_path=dbp)
    ratio_rule = HireTerminationRatioRule()
    res = ratio_rule.validate(mgr.get_connection(), 2025)
    assert res.severity == ValidationSeverity.WARNING


def test_custom_validation_rule_registration(tmp_path: Path):
    dbp = tmp_path / "dq.duckdb"
    conn = _db(dbp)
    conn.execute("CREATE TABLE t(x INTEGER)")
    conn.close()

    class DummyRule:
        name = "dummy"
        severity = ValidationSeverity.INFO

        def validate(self, conn, year: int) -> ValidationResult:
            return ValidationResult("dummy", ValidationSeverity.INFO, True, "ok", {})

    dv = DataValidator(DatabaseConnectionManager(db_path=dbp))
    dv.register_rule(DummyRule())
    results = dv.validate_year_results(2025)
    assert any(r.rule_name == "dummy" and r.passed for r in results)


def test_validation_report_generation(tmp_path: Path):
    dbp = tmp_path / "dq.duckdb"
    conn = _db(dbp)
    conn.execute(
        "CREATE TABLE fct_yearly_events(event_type VARCHAR, simulation_year INTEGER, event_date DATE)"
    )
    conn.close()

    mgr = DatabaseConnectionManager(db_path=dbp)
    dv = DataValidator(mgr)
    dv.register_rule(HireTerminationRatioRule())
    dv.register_rule(EventSequenceRule())
    results = dv.validate_year_results(2025)
    report = DataValidator.to_report_dict(results)
    assert "summary" in report and "results" in report
    assert isinstance(report["summary"]["total"], int)
