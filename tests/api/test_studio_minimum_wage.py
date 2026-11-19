"""Studio minimum wage (#1231): save/reload, run config, census preview,
results by year and the scenario comparison. Census rows are synthetic."""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.comparison_integrity import RunRecord, compare_records
from planalign_api.services.file_service import FileService
from planalign_api.services.simulation.results_reader import _query_minimum_wage
from planalign_api.services.simulation.run_execution import write_config
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_orchestrator.config.export import to_dbt_vars
from planalign_orchestrator.config.loader import load_simulation_config
from planalign_orchestrator.run_metadata import compute_config_fingerprint

pytestmark = [pytest.mark.fast]

# The shape Studio's buildConfigPayload saves: date order.
STEPS = [
    {"hourly_rate": 20.0, "effective_date": "2026-07-01"},
    {"hourly_rate": 22.0, "effective_date": "2027-01-01"},
]


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[WorkspaceStorage, str]:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    config = yaml.safe_load(Path("tests/fixtures/invariant_config.yaml").read_text())
    saved = storage.create_workspace(WorkspaceCreate(name="Minimum wage"), config)
    return storage, saved.id


def _run_config(
    storage: WorkspaceStorage, workspace_id: str, scenario_id: str, tmp_path: Path
):
    """Load the scenario's merged config the way a Studio run writes it."""
    merged = storage.get_merged_config(workspace_id, scenario_id)
    assert merged is not None
    path = tmp_path / f"{scenario_id}.yaml"
    write_config(merged, path)
    return load_simulation_config(path, env_overrides=False)


def test_saved_minimum_wage_reloads_and_reaches_the_run_config(workspace, tmp_path):
    storage, workspace_id = workspace
    scenario = storage.create_scenario(workspace_id, ScenarioCreate(name="Floor"))
    overrides = {"compensation": {"minimum_wage": copy.deepcopy(STEPS)}}
    storage.update_scenario(workspace_id, scenario.id, config_overrides=overrides)

    reloaded = storage.get_scenario(workspace_id, scenario.id)
    assert reloaded is not None
    # What the scenario API sends Studio on reload.
    assert reloaded.model_dump(mode="json")["config_overrides"] == overrides

    config = _run_config(storage, workspace_id, scenario.id, tmp_path)
    steps = [step.model_dump(mode="json") for step in config.compensation.minimum_wage]
    assert steps == STEPS
    assert to_dbt_vars(config)["minimum_wage_steps"] == STEPS


def test_no_or_removed_minimum_wage_keeps_the_config_fingerprint(workspace, tmp_path):
    storage, workspace_id = workspace
    plain = storage.create_scenario(workspace_id, ScenarioCreate(name="Plain"))
    # Studio would save [] only if every step were removed from a saved scenario.
    removed = storage.create_scenario(
        workspace_id,
        ScenarioCreate(
            name="Removed", config_overrides={"compensation": {"minimum_wage": []}}
        ),
    )
    plain_config = _run_config(storage, workspace_id, plain.id, tmp_path)
    removed_config = _run_config(storage, workspace_id, removed.id, tmp_path)

    assert "minimum_wage_steps" not in to_dbt_vars(plain_config)
    assert compute_config_fingerprint(plain_config) == compute_config_fingerprint(
        removed_config
    )


# --- Census preview --------------------------------------------------------

# id, active, pay, hourly_rate, hours_worked
CENSUS = [
    ("A", True, 36000.0, 18.0, None),  # 2,000 hours at $18
    ("B", True, 42000.0, None, 2000.0),  # $21 from hours worked
    ("C", True, 50000.0, 25.0, None),  # above both minimums
    ("D", True, 30000.0, None, None),  # no rate
    ("E", True, 30000.0, 5.0, None),  # implausible: no rate
    ("F", False, 20000.0, 10.0, None),  # not active
]


def _census(tmp_path: Path, with_rates: bool) -> tuple[FileService, str]:
    data = tmp_path / "ws" / "data"
    data.mkdir(parents=True)
    columns = "employee_id, active, employee_gross_compensation"
    if with_rates:
        columns += ", hourly_rate, hours_worked"
    rows = [row if with_rates else row[:3] for row in CENSUS]
    values = ", ".join(
        "(" + ", ".join("NULL" if v is None else repr(v) for v in row) + ")"
        for row in rows
    )
    with duckdb.connect() as conn:
        conn.execute(
            f"COPY (SELECT * FROM (VALUES {values}) t({columns})) "
            f"TO '{data / 'census.parquet'}' (FORMAT PARQUET)"
        )
    return FileService(tmp_path), "data/census.parquet"


def test_preview_estimates_each_step_on_the_rates_earlier_steps_left(tmp_path):
    service, path = _census(tmp_path, with_rates=True)
    # Out of order on purpose: steps apply by date.
    steps = [(22.0, date(2027, 1, 1)), (20.0, date(2026, 7, 1))]
    result = service.analyze_minimum_wage("ws", path, steps)

    assert result["headcount"] == 5
    summary = result["hourly_rate_summary"]
    assert (summary["with_rate"], summary["blank"], summary["out_of_bounds"]) == (
        3,
        1,
        1,
    )
    assert result["columns_needed"] == [
        "hourly_rate",
        "hours_worked",
        "scheduled_hours_per_week",
    ]
    # $20: A rises $2 x 2,000 hours. $22: A from $20 and B from $21.
    assert [
        (s["hourly_rate"], s["people_below"], s["added_annual_pay"])
        for s in result["steps"]
    ] == [(20.0, 1, pytest.approx(4000.0)), (22.0, 2, pytest.approx(6000.0))]


def test_preview_skips_rates_without_pay_as_the_run_does():
    """The engine never raises someone with no census pay, so neither does the preview."""
    from planalign_orchestrator.census_hourly_rate import estimate_minimum_wage

    with duckdb.connect() as conn:
        conn.execute(
            "CREATE TABLE census AS SELECT * FROM (VALUES "
            "(36000.0, 18.0), (0.0, 10.0), (NULL, 10.0)"
            ") t(employee_gross_compensation, hourly_rate)"
        )
        (step,) = estimate_minimum_wage(
            conn,
            "census",
            ["employee_gross_compensation", "hourly_rate"],
            [(20.0, date(2026, 7, 1))],
        )
    assert (step.people_below, step.added_annual_pay) == (1, pytest.approx(4000.0))


def test_preview_of_a_census_without_hourly_columns_has_no_rates(tmp_path):
    service, path = _census(tmp_path, with_rates=False)
    result = service.analyze_minimum_wage("ws", path, [(20.0, date(2026, 7, 1))])
    assert result["hourly_rate_summary"] is None
    assert result["steps"] == []
    assert result["headcount"] == 5


def test_preview_endpoint_validates_steps(client_factory, tmp_path):
    client = client_factory(None)
    data = tmp_path / "workspaces" / "ws" / "data"
    data.mkdir(parents=True)
    with duckdb.connect() as conn:
        conn.execute(
            "COPY (SELECT 'A' AS employee_id, 36000.0 AS employee_gross_compensation, "
            f"18.0 AS hourly_rate) TO '{data / 'census.parquet'}' (FORMAT PARQUET)"
        )
    url = "/api/workspaces/ws/analyze-minimum-wage"
    body = {"file_path": "data/census.parquet", "steps": [STEPS[0]]}
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["steps"][0]["people_below"] == 1

    bad = {**body, "steps": [{"hourly_rate": 0, "effective_date": "2026-07-01"}]}
    assert client.post(url, json=bad).status_code == 422

    same_year = [
        {"hourly_rate": 20, "effective_date": "2026-01-01"},
        {"hourly_rate": 21, "effective_date": "2026-07-01"},
    ]
    response = client.post(url, json={**body, "steps": same_year})
    assert response.status_code == 422
    assert "one minimum wage step per calendar year" in response.text


# --- Results by year -------------------------------------------------------


def _results_db(with_steps_table: bool = True) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute(
        "CREATE TABLE fct_yearly_events (employee_id VARCHAR, simulation_year INTEGER, "
        "event_type VARCHAR, previous_compensation DOUBLE, compensation_amount DOUBLE)"
    )
    conn.execute(
        "CREATE TABLE fct_workforce_snapshot (employee_id VARCHAR, simulation_year "
        "INTEGER, employment_status VARCHAR, current_compensation DOUBLE)"
    )
    if with_steps_table:
        conn.execute(
            "CREATE TABLE fct_minimum_wage_steps (scenario_id VARCHAR, simulation_year "
            "INTEGER, effective_date DATE, minimum_hourly_rate DOUBLE, people_raised "
            "BIGINT, people_with_rate BIGINT, people_without_rate BIGINT, "
            "people_not_covered BIGINT, added_annual_pay DOUBLE)"
        )
    return conn


def test_results_by_year_count_each_step_and_estimate_the_carryover():
    conn = _results_db()
    conn.execute(
        "INSERT INTO fct_minimum_wage_steps VALUES "
        "('s', 2026, DATE '2026-07-01', 20, 2, 5, 1, 3, 7000), "
        "('s', 2027, DATE '2027-01-01', 22, 1, 4, 1, 6, 4100)"
    )
    conn.execute(
        "INSERT INTO fct_yearly_events VALUES "
        "('E1', 2026, 'minimum_wage', 36000, 40000), "
        "('E2', 2026, 'minimum_wage', 30000, 33000), "
        "('E1', 2027, 'minimum_wage', 41000, 45100), "
        "('E1', 2026, 'raise', 40000, 41000)"
    )
    conn.execute(
        "INSERT INTO fct_workforce_snapshot VALUES "
        "('E1', 2026, 'active', 41000), ('E2', 2026, 'active', 33000), "
        "('E1', 2027, 'active', 46000), ('E2', 2027, 'terminated', 33000), "
        "('E3', 2027, 'active', 50000)"
    )
    years = {row.simulation_year: row for row in _query_minimum_wage(conn, 2025, 2027)}

    assert sorted(years) == [2025, 2026, 2027]
    assert years[2025].people_raised is None
    assert (years[2025].raised_still_active, years[2025].estimated_added_pay) == (0, 0)
    step = years[2026]
    assert (step.effective_date, step.minimum_hourly_rate) == (date(2026, 7, 1), 20)
    assert (step.people_raised, step.added_annual_pay) == (2, 7000)
    assert (step.people_without_rate, step.people_not_covered) == (1, 3)
    # E1 kept 1/10 of 41,000; E2 kept 1/11 of 33,000.
    assert step.raised_still_active == 2
    assert step.estimated_added_pay == pytest.approx(4100 + 3000)
    # E2 left. E1's ratios multiply: 10/9 x 1.1 = 11/9, so 2/11 of 46,000.
    assert years[2027].raised_still_active == 1
    assert years[2027].estimated_added_pay == pytest.approx(46000 * 2 / 11)


def test_results_without_a_minimum_wage_report_none():
    assert _query_minimum_wage(_results_db(), 2025, 2027) == []


def test_results_built_before_the_minimum_wage_report_none():
    assert _query_minimum_wage(_results_db(with_steps_table=False), 2025, 2027) == []


# --- Scenario comparison ---------------------------------------------------


def _record(scenario_id: str, compensation: dict[str, Any]) -> RunRecord:
    config = {"compensation": {"merit_budget": 0.03, **compensation}}
    return RunRecord(
        scenario_id=scenario_id, name=scenario_id, has_run_record=True, config=config
    )


def _minimum_wage_reasons(anchor: RunRecord, scenario: RunRecord):
    return [
        reason
        for reason in compare_records(anchor, scenario).reasons
        if reason.path == "compensation.minimum_wage"
    ]


def test_comparison_says_when_only_one_side_has_a_minimum_wage():
    reasons = _minimum_wage_reasons(
        _record("base", {}), _record("floor", {"minimum_wage": STEPS})
    )
    assert len(reasons) == 1
    assert reasons[0].effect == "breaks"
    assert reasons[0].group == "workforce_and_pay"
    assert reasons[0].anchor_value is None
    assert reasons[0].scenario_value == STEPS


def test_comparison_treats_an_empty_minimum_wage_as_none():
    removed = _record("removed", {"minimum_wage": []})
    assert _minimum_wage_reasons(_record("base", {}), removed) == []


def test_comparison_flags_a_different_minimum():
    higher = [{**STEPS[0], "hourly_rate": 21.0}, STEPS[1]]
    reasons = _minimum_wage_reasons(
        _record("a", {"minimum_wage": STEPS}), _record("b", {"minimum_wage": higher})
    )
    assert len(reasons) == 1
