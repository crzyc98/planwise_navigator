"""Hand-computed calibration metrics, independent of production census data."""

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from scripts.deferral_calibration_report import build_report, compare_targets

pytestmark = pytest.mark.fast


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    db = duckdb.connect()
    db.execute("""CREATE TABLE fct_workforce_snapshot (
        scenario_id VARCHAR, plan_design_id VARCHAR, employee_id VARCHAR,
        simulation_year INTEGER, employment_status VARCHAR, is_enrolled_flag BOOLEAN,
        current_deferral_rate DECIMAL(8,6), current_age INTEGER,
        current_compensation DOUBLE, current_tenure DOUBLE)""")
    db.execute("""CREATE TABLE fct_yearly_events (
        scenario_id VARCHAR, plan_design_id VARCHAR, employee_id VARCHAR,
        simulation_year INTEGER, event_type VARCHAR, event_category VARCHAR)""")
    # same, aip, proactive, decrease, stop, restart, other, near-same
    for employee, before, after in [
        ("same", 0.05, 0.05),
        ("aip", 0.05, 0.06),
        ("pro", 0.05, 0.08),
        ("down", 0.05, 0.03),
        ("stop", 0.05, 0),
        ("restart", 0, 0.04),
        ("other", 0.05, 0.07),
        ("near", 0.05, 0.05001),
    ]:
        for year, rate in [(2025, before), (2026, after)]:
            db.execute(
                "INSERT INTO fct_workforce_snapshot VALUES ('s', 'p', ?, ?, 'active', TRUE, ?, 30, 40000, 2)",
                [employee, year, rate],
            )
    db.execute("""INSERT INTO fct_workforce_snapshot VALUES
        ('s','p','new',2026,'active',TRUE,.10,70,250000,.5),
        ('s','p','gone',2025,'active',TRUE,.05,70,250000,30),
        ('s','p','gone',2026,'terminated',TRUE,.10,70,250000,30),
        ('s','p','out',2025,'active',FALSE,.05,70,250000,30),
        ('s','p','out',2026,'active',TRUE,.10,70,250000,30),
        ('other','p','aip',2025,'active',TRUE,.01,70,250000,30),
        ('other','p','aip',2026,'active',TRUE,.01,70,250000,30)""")
    db.execute("""INSERT INTO fct_yearly_events VALUES
        ('s','p','aip',2026,'deferral_escalation','deferral_escalation'),
        ('s','p','pro',2026,'deferral_escalation','deferral_escalation'),
        ('s','p','pro',2026,'deferral_change','proactive_increase'),
        ('s','p','pro',2026,'deferral_change','proactive_increase'),
        ('s','p','restart',2026,'deferral_change','restart'),
        ('other','p','other',2026,'deferral_change','proactive_increase')""")
    yield db
    db.close()


def test_exact_metrics(connection: duckdb.DuckDBPyConnection) -> None:
    rows = build_report(connection, "s")
    overall = next(row for row in rows if row["dimension"] == "overall")
    expected = {
        "n_continuous": 8,
        "pct_same": 25,
        "pct_increase": 50,
        "pct_decrease": 25,
        "pct_to_zero": 12.5,
        "pct_from_zero": 12.5,
        "pct_increases_aip": 25,
        "pct_increases_proactive": 50,
        "pct_increases_other": 25,
        "avg_increase_pp_aip": 1,
        "avg_increase_pp_proactive": 3.5,
        "avg_increase_pp": 2.5,
        "avg_decrease_pp": -3.5,
        "net_change_pp": 0.375125,
    }
    for metric, value in expected.items():
        assert overall[metric] == pytest.approx(value), metric
    assert {(row["dimension"], row["band"]) for row in rows} == {
        ("overall", "overall"),
        ("age", "30-39"),
        ("income", "40-50k"),
        ("tenure", "2-3"),
    }
    assert all(row["n_continuous"] == 8 for row in rows)
    assert build_report(connection, "missing") == []


def test_targets(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    targets = tmp_path / "targets.csv"
    targets.write_text(
        "dimension,band,metric,value\noverall,overall,pct_increase,40\nage,70+,pct_same,10\n"
    )
    assert compare_targets(build_report(connection, "s"), targets) == [
        {
            "simulation_year": 2026,
            "dimension": "overall",
            "band": "overall",
            "metric": "pct_increase",
            "simulated": 50,
            "target": 40,
            "diff": 10,
        }
    ]


def test_band_exclusion_and_empty_increases(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    connection.execute(
        "UPDATE fct_workforce_snapshot SET current_tenure = .5 WHERE scenario_id = 'other'"
    )
    rows = build_report(connection, "other")
    assert not any(row["dimension"] == "tenure" for row in rows)
    overall = next(row for row in rows if row["dimension"] == "overall")
    assert overall["n_continuous"] == 1
    assert overall["pct_same"] == 100
    assert overall["pct_increases_aip"] is None
    assert overall["avg_increase_pp"] is None


def test_tolerance_boundary(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        "UPDATE fct_workforce_snapshot SET current_deferral_rate = .05005 WHERE employee_id = 'near' AND simulation_year = 2026"
    )
    overall = next(
        row for row in build_report(connection, "s") if row["dimension"] == "overall"
    )
    assert overall["pct_same"] == 12.5
    assert overall["pct_increase"] == 62.5
