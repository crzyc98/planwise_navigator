"""Census tie-out: archived census vs the first simulated year (Epic C, C1).

Every database here is a tiny synthetic DuckDB under tmp_path. The consistent
pair models a 100-person census (2024) carried into 2025 at the configured 3%
growth and 5% raises, so it ties on every row; each other case breaks exactly
one thing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

import duckdb
import pytest

from planalign_api.services import census_tie_out
from planalign_api.services.census_tie_out import (
    BAD_CONFIG_REASON,
    NO_ARCHIVED_CENSUS_REASON,
    NO_RUN_REASON,
    UNREADABLE_DATABASE_REASON,
    CensusTieOutService,
    DriftAssumptions,
    _METRICS,
    classify,
    expected_factor,
    tolerance_for,
)
from planalign_api.services.current_result import publish_current_result
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = pytest.mark.fast

RUN_ID = "12345678-1234-5678-9234-567812345678"
WORKSPACE = "workspace"
SCENARIO = "scenario-a"
CONFIG = (
    "simulation:\n  start_year: 2025\n  end_year: 2026\n  target_growth_rate: 0.03\n"
    "compensation:\n  cola_rate: 0.02\n  merit_budget: 0.03\n"
    "setup:\n  census_parquet_path: data/census_2024.parquet\n"
)


@dataclass(frozen=True)
class Population:
    """A uniform synthetic population: every employee has the same values."""

    headcount: int
    participants: int
    pay: float
    deferral: float
    match_rate: float
    core_rate: float
    ineligible: int = 0


CENSUS = Population(100, 60, 50_000.0, 0.06, 0.03, 0.02)
# 3% growth, 5% raises (2% COLA + 3% merit), same plan design.
SIMULATED = Population(103, 62, 52_500.0, 0.06, 0.03, 0.02)


def _create_census(
    conn: duckdb.DuckDBPyConnection,
    census: Population,
    *,
    with_contributions: bool = True,
) -> None:
    """stg_census_data as the staging model writes it (absent columns are NULL)."""
    match = f"{census.pay * census.match_rate}" if with_contributions else "NULL"
    core = f"{census.pay * census.core_rate}" if with_contributions else "NULL"
    conn.execute(f"""
        CREATE TABLE stg_census_data AS
        SELECT
          'C' || i AS employee_id,
          CASE WHEN i < 10 THEN DATE '2024-03-01' ELSE DATE '2015-06-01' END
            AS employee_hire_date,
          NULL::DATE AS employee_termination_date,
          TRUE AS active,
          {census.pay}::DOUBLE AS employee_plan_year_compensation,
          CASE WHEN i < {census.participants} THEN {census.deferral} ELSE 0 END
            ::DECIMAL(9, 5) AS employee_deferral_rate,
          CASE WHEN i < {census.participants} THEN {match} END::DECIMAL(12, 2)
            AS employer_match_contribution,
          {core}::DECIMAL(12, 2) AS employer_core_contribution,
          CASE WHEN i >= {census.headcount - census.ineligible}
            THEN DATE '2030-01-01' ELSE DATE '2016-01-01' END
            AS eligibility_entry_date
        FROM range({census.headcount}) t(i)
        UNION ALL
        -- A terminated census row never counts as active.
        SELECT 'T1', DATE '2010-01-01', DATE '2024-05-01', FALSE, 40000, 0.1,
          {match}, {core}, DATE '2010-01-01'
    """)


def _create_snapshot(conn: duckdb.DuckDBPyConnection, sim: Population) -> None:
    conn.execute(f"""
        CREATE TABLE fct_workforce_snapshot AS
        SELECT
          'S' || i AS employee_id,
          year AS simulation_year,
          'active' AS employment_status,
          CASE WHEN i >= {sim.headcount - sim.ineligible}
            THEN 'pending' ELSE 'eligible' END AS current_eligibility_status,
          i < {sim.participants} AS is_enrolled_flag,
          CASE WHEN i < {sim.participants} THEN {sim.deferral} ELSE 0 END
            ::DECIMAL(5, 4) AS current_deferral_rate,
          {sim.pay}::DOUBLE AS prorated_annual_compensation,
          CASE WHEN i < {sim.participants}
            THEN {sim.pay * sim.match_rate} ELSE 0 END::DOUBLE
            AS employer_match_amount,
          {sim.pay * sim.core_rate}::DOUBLE AS employer_core_amount
        FROM range({sim.headcount}) t(i), (VALUES (2025), (2026)) y(year)
        UNION ALL
        SELECT 'X1', 2025, 'terminated', 'eligible', TRUE, 0.1, 99999, 999, 999
    """)


def _build_run(
    root: Path,
    census: Optional[Population] = CENSUS,
    sim: Population = SIMULATED,
    *,
    with_contributions: bool = True,
) -> Path:
    """A completed Studio run with its own archived census, selected as current."""
    scenario_dir = root / WORKSPACE / "scenarios" / SCENARIO
    run_dir = scenario_dir / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    metadata = {
        "run_id": RUN_ID,
        "status": "completed",
        "start_year": 2025,
        "end_year": 2026,
    }
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata))
    (run_dir / "config.yaml").write_text(CONFIG)
    with duckdb.connect(str(run_dir / "simulation.duckdb")) as conn:
        if census is not None:
            _create_census(conn, census, with_contributions=with_contributions)
        _create_snapshot(conn, sim)
    publish_current_result(scenario_dir, RUN_ID)
    return scenario_dir


def _tie_out(root: Path):
    service = CensusTieOutService(WorkspaceStorage(root))
    return service.get_tie_out(WORKSPACE, SCENARIO, "Scenario A")


def _statuses(result) -> dict[str, str]:
    return {row.metric: row.status for row in result.rows}


def _row(result, metric: str):
    return next(row for row in result.rows if row.metric == metric)


def test_consistent_census_and_first_year_tie(tmp_path: Path) -> None:
    _build_run(tmp_path)

    result = _tie_out(tmp_path)

    assert result.available
    assert set(_statuses(result).values()) == {"ties"}
    assert result.run_id == RUN_ID
    assert result.census_file == "census_2024.parquet"
    assert result.census_year == 2024
    assert result.census_as_of_date.isoformat() == "2024-12-31"
    assert result.first_simulated_year == 2025
    assert result.growth_rate == pytest.approx(0.03)
    assert result.raise_rate == pytest.approx(0.05)
    headcount = _row(result, "active_headcount")
    assert (headcount.census_value, headcount.simulated_value) == (100, 103)
    assert headcount.expected_value == pytest.approx(103)
    assert headcount.relative_difference == pytest.approx(0.03)
    pay = _row(result, "total_pay")
    assert pay.census_value == pytest.approx(5_000_000)
    assert pay.expected_value == pytest.approx(5_000_000 * 1.03 * 1.05)
    assert _row(result, "participation_rate").relative_difference is None
    assert all(row.message for row in result.rows)
    assert result.source_note == (
        "Compares census_2024.parquet (census year 2024) with 2025, the first "
        "simulated year, allowing for one year of the configured growth and "
        "raises. Meaningful only for a scenario that models the current plan."
    )


def test_wrong_match_formula_is_a_match_gap(tmp_path: Path) -> None:
    _build_run(tmp_path, sim=replace(SIMULATED, match_rate=0.06))

    result = _tie_out(tmp_path)

    assert _statuses(result)["employer_match"] == "gap"
    assert _statuses(result)["employer_core"] == "ties"
    message = _row(result, "employer_match").message
    assert message.startswith("Employer match is ")
    assert "above the census" in message
    assert "Check the match formula and match eligibility." in message


def test_wrong_eligibility_rule_is_an_eligible_count_gap(tmp_path: Path) -> None:
    # The census says everyone is eligible; the run's rule leaves 30 pending.
    _build_run(tmp_path, sim=replace(SIMULATED, ineligible=30))

    result = _tie_out(tmp_path)

    row = _row(result, "eligible_count")
    assert row.status == "gap"
    assert row.census_value == 100 and row.simulated_value == 73
    assert "below the census" in row.message
    assert "eligibility rule" in row.message
    assert _statuses(result)["active_headcount"] == "ties"


def test_mis_mapped_deferral_column_is_a_deferral_gap(tmp_path: Path) -> None:
    # Deferral mapped from a whole-percent column: 6 instead of 0.06.
    _build_run(tmp_path, census=replace(CENSUS, deferral=6.0))

    result = _tie_out(tmp_path)

    row = _row(result, "average_deferral_rate")
    assert row.status == "gap"
    assert "fractions (0.06 for 6%)" in row.message
    assert _statuses(result)["participation_rate"] == "ties"


def test_census_without_contribution_columns_is_not_in_census(tmp_path: Path) -> None:
    _build_run(tmp_path, with_contributions=False)

    result = _tie_out(tmp_path)

    for metric in ("employer_match", "employer_core"):
        row = _row(result, metric)
        assert row.status == "not_in_census"
        assert row.census_value is None and row.difference is None
        assert row.simulated_value > 0
        assert "census has no employer" in row.message
    assert _statuses(result)["total_pay"] == "ties"


def test_zero_core_column_is_compared_not_missing(tmp_path: Path) -> None:
    _build_run(tmp_path, census=replace(CENSUS, core_rate=0.0))

    row = _row(_tie_out(tmp_path), "employer_core")

    assert row.status == "gap"
    assert row.census_value == 0
    assert row.relative_difference is None
    assert "above the census" in row.message


def test_census_without_eligibility_dates_compares_all_active(tmp_path: Path) -> None:
    _build_run(tmp_path, sim=replace(SIMULATED, ineligible=30))
    run_db = tmp_path / WORKSPACE / "scenarios" / SCENARIO / "runs" / RUN_ID
    with duckdb.connect(str(run_db / "simulation.duckdb")) as conn:
        conn.execute("UPDATE stg_census_data SET eligibility_entry_date = NULL")

    result = _tie_out(tmp_path)

    assert _statuses(result)["eligible_count"] == "not_in_census"
    # Both sides use every active employee, so the run's pending hires don't
    # move participation.
    assert _statuses(result)["participation_rate"] == "ties"


def test_archived_census_is_used_over_the_current_workspace_census(
    tmp_path: Path,
) -> None:
    _build_run(tmp_path)
    # The workspace's census has since been replaced with a much larger one.
    current = tmp_path / WORKSPACE / "data" / "census_2024.parquet"
    current.parent.mkdir(parents=True)
    with duckdb.connect() as conn:
        _create_census(conn, replace(CENSUS, headcount=500, pay=90_000.0))
        conn.execute(f"COPY stg_census_data TO '{current}' (FORMAT PARQUET)")

    result = _tie_out(tmp_path)

    assert _row(result, "active_headcount").census_value == 100
    assert _row(result, "total_pay").census_value == pytest.approx(5_000_000)


def test_run_without_archived_census_is_unavailable(tmp_path: Path) -> None:
    _build_run(tmp_path, census=None)
    current = tmp_path / WORKSPACE / "data" / "census_2024.parquet"
    current.parent.mkdir(parents=True)
    with duckdb.connect() as conn:
        _create_census(conn, CENSUS)
        conn.execute(f"COPY stg_census_data TO '{current}' (FORMAT PARQUET)")

    result = _tie_out(tmp_path)

    assert not result.available
    assert result.unavailable_reason == NO_ARCHIVED_CENSUS_REASON
    assert result.rows == []


def test_scenario_without_a_run_is_unavailable(tmp_path: Path) -> None:
    scenario_dir = tmp_path / WORKSPACE / "scenarios" / SCENARIO
    scenario_dir.mkdir(parents=True)
    with duckdb.connect(str(scenario_dir / "simulation.duckdb")) as conn:
        _create_census(conn, CENSUS)
        _create_snapshot(conn, SIMULATED)

    result = _tie_out(tmp_path)

    assert not result.available
    assert result.unavailable_reason == NO_RUN_REASON


def test_tolerance_allows_configured_drift() -> None:
    one_year = DriftAssumptions(growth_rate=0.03, raise_rate=0.05)
    pay = next(spec for spec in _METRICS if spec.metric == "total_pay")
    factor = expected_factor("growth_and_raises", one_year)
    tolerance = tolerance_for(pay, 1000 * factor, factor)

    assert factor == pytest.approx(1.0815)
    # 5% of expected plus half the expected 8.15% change.
    assert tolerance == pytest.approx(1081.5 * (0.05 + 0.5 * 0.0815))
    assert classify(1081.5 + tolerance, 1081.5, tolerance) == "ties"
    assert classify(1081.5 + tolerance + 1, 1081.5, tolerance) == "gap"
    assert expected_factor("growth", one_year) == pytest.approx(1.03)
    assert expected_factor("none", one_year) == 1.0


def test_endpoint_returns_tie_out(client_factory, tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    scenario_dir = _build_run(root)
    (scenario_dir / "scenario.json").write_text(
        json.dumps(
            {
                "id": SCENARIO,
                "workspace_id": WORKSPACE,
                "name": "Scenario A",
                "status": "completed",
                "created_at": "2025-01-01T00:00:00",
            }
        )
    )
    client = client_factory(None)

    response = client.get(
        f"/api/workspaces/{WORKSPACE}/scenarios/{SCENARIO}/analytics/census-tie-out"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert [row["metric"] for row in body["rows"]] == [m.metric for m in _METRICS]


def _run_dir(root: Path) -> Path:
    return root / WORKSPACE / "scenarios" / SCENARIO / "runs" / RUN_ID


def test_census_rows_with_a_later_termination_date_are_not_active(
    tmp_path: Path,
) -> None:
    # The engine starts only rows with no termination date (int_baseline_workforce).
    _build_run(tmp_path)
    with duckdb.connect(str(_run_dir(tmp_path) / "simulation.duckdb")) as conn:
        conn.execute("""
            INSERT INTO stg_census_data
            SELECT 'L' || i, DATE '2015-06-01', DATE '2025-03-01', TRUE, 50000,
              0.06, 1500, 1000, DATE '2016-01-01'
            FROM range(5) t(i)
        """)

    row = _row(_tie_out(tmp_path), "active_headcount")

    assert row.census_value == 100
    assert row.status == "ties"


def test_non_calendar_plan_year_sets_the_as_of_date(tmp_path: Path) -> None:
    # Ten census employees become eligible on 2025-03-01: inside a plan year
    # ending 2025-06-30, after a calendar year ending 2024-12-31.
    _build_run(tmp_path, census=replace(CENSUS, ineligible=10))
    run_dir = _run_dir(tmp_path)
    with duckdb.connect(str(run_dir / "simulation.duckdb")) as conn:
        conn.execute(
            "UPDATE stg_census_data SET eligibility_entry_date = DATE '2025-03-01' "
            "WHERE eligibility_entry_date = DATE '2030-01-01'"
        )
    assert _row(_tie_out(tmp_path), "eligible_count").census_value == 90

    (run_dir / "config.yaml").write_text(
        CONFIG.replace("setup:\n", "setup:\n  plan_year_start_date: '2024-07-01'\n")
    )
    result = _tie_out(tmp_path)

    assert result.census_year == 2024
    assert result.census_as_of_date.isoformat() == "2025-06-30"
    assert _row(result, "eligible_count").census_value == 100
    assert "(census plan year ending June 30, 2025)" in result.source_note


@pytest.mark.parametrize(
    "config",
    [
        CONFIG.replace("target_growth_rate: 0.03", "target_growth_rate: null"),
        "simulation: [unclosed\n",
        CONFIG.replace("cola_rate: 0.02", "cola_rate: lots"),
        CONFIG + "  plan_year_end_date: not-a-date\n",
    ],
    ids=["null-growth", "malformed-yaml", "invalid-compensation", "bad-plan-date"],
)
def test_bad_archived_config_is_unavailable_not_an_error(
    tmp_path: Path, config: str
) -> None:
    _build_run(tmp_path)
    (_run_dir(tmp_path) / "config.yaml").write_text(config)

    result = _tie_out(tmp_path)

    assert not result.available
    assert result.unavailable_reason == BAD_CONFIG_REASON
    assert result.run_id == RUN_ID


def test_unreadable_database_is_unavailable_not_an_error(tmp_path: Path) -> None:
    _build_run(tmp_path)
    (_run_dir(tmp_path) / "simulation.duckdb").write_bytes(b"not a database")

    result = _tie_out(tmp_path)

    assert not result.available
    assert result.unavailable_reason == UNREADABLE_DATABASE_REASON


def test_measurement_is_cached_until_the_database_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build_run(tmp_path)
    opened: list[str] = []
    real_connect = duckdb.connect

    def counting_connect(path: str, **kwargs: object) -> duckdb.DuckDBPyConnection:
        opened.append(path)
        return real_connect(path, **kwargs)

    monkeypatch.setattr(census_tie_out.duckdb, "connect", counting_connect)
    first = _tie_out(tmp_path)
    assert _tie_out(tmp_path) == first
    assert len(opened) == 1

    database = _run_dir(tmp_path) / "simulation.duckdb"
    with real_connect(str(database)) as conn:
        conn.execute("DELETE FROM stg_census_data WHERE employee_id = 'C0'")
    stat = database.stat()
    os.utime(database, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    assert _row(_tie_out(tmp_path), "active_headcount").census_value == 99
    assert len(opened) == 2
