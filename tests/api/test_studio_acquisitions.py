"""Studio acquisitions (#1228): save/reload, run config, results and comparison."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.comparison_integrity import RunRecord, compare_records
from planalign_api.models.provenance import (
    AnnualWorkforceReconciliation,
    RunProvenanceManifest,
)
from planalign_api.services.provenance.render import render_markdown
from planalign_api.services.provenance.report import build_provenance_report
from planalign_api.services.simulation.results_reader import (
    _query_acquired_hires,
    _query_acquisition_split,
)
from planalign_orchestrator.pipeline.telemetry_emitter import TelemetryEmitter
from tests.fixtures.run_provenance import RUN_ID, build_archive
from planalign_api.services.simulation.run_execution import write_config
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_orchestrator.config.export import to_dbt_vars
from planalign_orchestrator.config.loader import load_simulation_config
from planalign_orchestrator.run_metadata import compute_config_fingerprint

pytestmark = [pytest.mark.fast]

# The shape Studio's buildConfigPayload saves.
ACQUISITIONS = [
    {
        "id": "acme",
        "name": "Acme Corp",
        "headcount": 250,
        "effective_date": "2026-07-01",
        "service_credit": "acquisition_date",
        "plan_entry": "waiting_period",
        "starting_participation_rate": 0.6,
        "starting_deferral_rate": 0.05,
        "relative_pay": 0.9,
        "average_age": 44,
        "average_service": 7.5,
    },
    {"id": "beta-2", "name": "Beta", "headcount": 5, "effective_date": "2027-01-01"},
]


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[WorkspaceStorage, str]:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    config = yaml.safe_load(Path("tests/fixtures/invariant_config.yaml").read_text())
    saved = storage.create_workspace(WorkspaceCreate(name="Acquisitions"), config)
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


def test_saved_acquisitions_reload_and_reach_the_run_config(workspace, tmp_path):
    storage, workspace_id = workspace
    scenario = storage.create_scenario(workspace_id, ScenarioCreate(name="Plain"))
    overrides = {"workforce": {"acquisitions": copy.deepcopy(ACQUISITIONS)}}
    storage.update_scenario(workspace_id, scenario.id, config_overrides=overrides)

    reloaded = storage.get_scenario(workspace_id, scenario.id)
    assert reloaded is not None
    assert reloaded.config_overrides == overrides

    config = _run_config(storage, workspace_id, scenario.id, tmp_path)
    assert [
        item.model_dump(mode="json", exclude_defaults=True)
        for item in config.workforce.acquisitions
    ] == ACQUISITIONS
    # Plan settings go to dbt resolved; unset overrides are left out.
    defaults = {"service_credit": "prior_service", "plan_entry": "acquisition_date"}
    assert to_dbt_vars(config)["acquisitions"] == [
        {**defaults, **{key: value for key, value in item.items() if key != "name"}}
        for item in ACQUISITIONS
    ]


def test_no_or_removed_acquisitions_keep_the_config_fingerprint(workspace, tmp_path):
    storage, workspace_id = workspace
    plain = storage.create_scenario(workspace_id, ScenarioCreate(name="Plain"))
    # Studio saves [] when every acquisition is removed from a saved scenario.
    removed = storage.create_scenario(
        workspace_id,
        ScenarioCreate(
            name="Removed", config_overrides={"workforce": {"acquisitions": []}}
        ),
    )
    plain_config = _run_config(storage, workspace_id, plain.id, tmp_path)
    removed_config = _run_config(storage, workspace_id, removed.id, tmp_path)

    assert "acquisitions" not in to_dbt_vars(plain_config)
    assert compute_config_fingerprint(plain_config) == compute_config_fingerprint(
        removed_config
    )


def _events_db(with_column: bool) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    column = ", acquisition_id VARCHAR" if with_column else ""
    conn.execute(
        "CREATE TABLE fct_yearly_events "
        f"(employee_id VARCHAR, simulation_year INTEGER, event_type VARCHAR{column})"
    )
    return conn


def test_acquired_hires_are_counted_per_year_apart_from_organic_hires():
    conn = _events_db(with_column=True)
    conn.executemany(
        "INSERT INTO fct_yearly_events VALUES (?, ?, ?, ?)",
        [
            ("E1", 2025, "hire", None),
            ("ACQ_acme_1", 2026, "hire", "acme"),
            ("ACQ_acme_2", 2026, "hire", "acme"),
            ("ACQ_acme_1", 2027, "termination", "acme"),
        ],
    )
    assert _query_acquired_hires(conn, 2025, 2027) == [0, 2, 0]


def test_results_without_acquisitions_report_none():
    conn = _events_db(with_column=True)
    conn.execute("INSERT INTO fct_yearly_events VALUES ('E1', 2025, 'hire', NULL)")
    assert _query_acquired_hires(conn, 2025, 2027) == []


def test_results_built_before_acquisitions_report_none():
    conn = _events_db(with_column=False)
    conn.execute("INSERT INTO fct_yearly_events VALUES ('E1', 2025, 'hire')")
    assert _query_acquired_hires(conn, 2025, 2027) == []


def _record(scenario_id: str, workforce: dict[str, Any]) -> RunRecord:
    config = {"workforce": {"total_termination_rate": 0.12, **workforce}}
    return RunRecord(
        scenario_id=scenario_id, name=scenario_id, has_run_record=True, config=config
    )


def _acquisition_reasons(anchor: RunRecord, scenario: RunRecord):
    return [
        reason
        for reason in compare_records(anchor, scenario).reasons
        if reason.path == "workforce.acquisitions"
    ]


def test_comparison_flags_acquisitions_on_one_side_only():
    reasons = _acquisition_reasons(
        _record("base", {}), _record("acq", {"acquisitions": ACQUISITIONS})
    )
    assert len(reasons) == 1
    assert reasons[0].effect == "breaks"
    assert reasons[0].group == "workforce_and_pay"
    assert reasons[0].anchor_value is None
    assert reasons[0].scenario_value == ACQUISITIONS


def test_comparison_treats_removed_acquisitions_as_none():
    assert (
        _acquisition_reasons(
            _record("base", {}), _record("removed", {"acquisitions": []})
        )
        == []
    )


def test_comparison_reads_acquisitions_in_a_section_only_one_run_has():
    """A run config without a workforce section still compares per setting."""
    base = RunRecord(scenario_id="base", name="base", has_run_record=True, config={})
    renamed = [{**item, "name": "Renamed"} for item in ACQUISITIONS]

    def reasons(scenario: dict[str, Any]) -> list[Any]:
        other = RunRecord(
            scenario_id="x", name="x", has_run_record=True, config=scenario
        )
        return compare_records(base, other).reasons

    assert reasons({"workforce": {"acquisitions": []}}) == []
    [reason] = reasons({"workforce": {"acquisitions": renamed}})
    assert reason.path == "workforce.acquisitions"


def test_comparison_ignores_acquisition_names():
    renamed = [{**item, "name": f"{item['name']} (renamed)"} for item in ACQUISITIONS]
    assert (
        _acquisition_reasons(
            _record("base", {"acquisitions": ACQUISITIONS}),
            _record("renamed", {"acquisitions": renamed}),
        )
        == []
    )


def test_comparison_ignores_plan_settings_spelled_out_at_their_defaults():
    spelled_out = [
        ACQUISITIONS[0],
        {
            **ACQUISITIONS[1],
            "service_credit": "prior_service",
            "plan_entry": "acquisition_date",
            "starting_participation_rate": None,
            "starting_deferral_rate": None,
        },
    ]
    assert (
        _acquisition_reasons(
            _record("base", {"acquisitions": ACQUISITIONS}),
            _record("spelled", {"acquisitions": spelled_out}),
        )
        == []
    )


def test_comparison_flags_a_changed_acquisition_date():
    moved = [{**ACQUISITIONS[0], "effective_date": "2027-07-01"}, ACQUISITIONS[1]]
    reasons = _acquisition_reasons(
        _record("base", {"acquisitions": ACQUISITIONS}),
        _record("moved", {"acquisitions": moved}),
    )
    assert len(reasons) == 1


# --- Slice 2: the headcount step and the pay/cost split ---------------------


def _snapshot_db(with_column: bool) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    column = ", acquisition_id VARCHAR" if with_column else ""
    conn.execute(
        "CREATE TABLE fct_workforce_snapshot (employee_id VARCHAR, "
        "simulation_year INTEGER, employment_status VARCHAR, "
        "prorated_annual_compensation DOUBLE, employer_match_amount DOUBLE, "
        f"employer_core_amount DOUBLE{column})"
    )
    return conn


SNAPSHOT_ROWS = [
    ("E1", 2025, "active", 100.0, 4.0, 2.0, None),
    ("E2", 2025, "terminated", 50.0, 1.0, None, None),
    ("E1", 2026, "active", 110.0, 4.0, 2.0, None),
    ("ACQ_acme_000001", 2026, "active", 40.0, None, 1.0, "acme"),
    ("ACQ_acme_000002", 2026, "active", 60.0, 3.0, 0.0, "acme"),
]


def test_split_separates_acquired_and_existing_pay_and_cost():
    conn = _snapshot_db(with_column=True)
    conn.executemany(
        "INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?, ?, ?, ?, ?)",
        SNAPSHOT_ROWS,
    )
    active = " AND LOWER(employment_status) = 'active'"
    assert _query_acquisition_split(conn, 2025, 2026, active) == [
        {
            "simulation_year": 2025,
            "acquired_headcount": 0,
            "acquired_compensation": 0.0,
            "acquired_employer_cost": 0.0,
            "existing_headcount": 1,
            "existing_compensation": 100.0,
            "existing_employer_cost": 6.0,
        },
        {
            "simulation_year": 2026,
            "acquired_headcount": 2,
            "acquired_compensation": 100.0,
            "acquired_employer_cost": 4.0,
            "existing_headcount": 1,
            "existing_compensation": 110.0,
            "existing_employer_cost": 6.0,
        },
    ]
    everyone = _query_acquisition_split(conn, 2025, 2026)
    assert everyone[0]["existing_compensation"] == 150.0


def test_split_is_empty_without_acquired_members_or_the_column():
    conn = _snapshot_db(with_column=True)
    conn.execute(
        "INSERT INTO fct_workforce_snapshot VALUES "
        "('E1', 2025, 'active', 1.0, 0, 0, NULL)"
    )
    assert _query_acquisition_split(conn, 2025, 2027) == []
    legacy = _snapshot_db(with_column=False)
    legacy.execute(
        "INSERT INTO fct_workforce_snapshot VALUES ('E1', 2025, 'active', 1.0, 0, 0)"
    )
    assert _query_acquisition_split(legacy, 2025, 2027) == []


class _Manager:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self.conn = conn

    def get_connection(self, **_: Any):
        from contextlib import nullcontext

        return nullcontext(self.conn)


def _reconciliation_db(acquired: int) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute(
        "CREATE TABLE fct_yearly_events AS SELECT * FROM (VALUES "
        "('E1', 2026, 'hire', NULL::VARCHAR), ('E2', 2026, 'termination', NULL)"
        ") t(employee_id, simulation_year, event_type, acquisition_id)"
    )
    conn.execute(
        "INSERT INTO fct_yearly_events SELECT 'ACQ_acme_' || i, 2026, 'hire', "
        "'acme' FROM range(?) r(i)",
        [acquired],
    )
    conn.execute(
        "CREATE TABLE fct_workforce_snapshot AS SELECT * FROM (VALUES "
        "(2025, 'active'), (2025, 'active'), (2026, 'active'), (2026, 'active')"
        ") t(simulation_year, employment_status)"
    )
    conn.execute(
        "INSERT INTO fct_workforce_snapshot SELECT 2026, 'active' FROM range(?)",
        [acquired],
    )
    return conn


def test_reconciliation_shows_acquired_members_as_their_own_step():
    conn = _reconciliation_db(acquired=3)
    emitter = TelemetryEmitter(db_manager=_Manager(conn), enabled=True)
    emitter._start_year = 2025
    counts = {"HIRE": 4, "TERMINATION": 1}
    assert emitter._query_reconciliation(2026, counts) == {
        "opening_workforce": 2,
        "hires": 1,
        "acquired": 3,
        "terminations": 1,
        "expected_closing_workforce": 5,
        "actual_closing_workforce": 5,
        "variance": 0,
        "opening_source": "prior_year_snapshot",
    }


def test_reconciliation_without_acquisitions_is_unchanged():
    conn = _reconciliation_db(acquired=0)
    emitter = TelemetryEmitter(db_manager=_Manager(conn), enabled=True)
    emitter._start_year = 2025
    result = emitter._query_reconciliation(2026, {"HIRE": 1, "TERMINATION": 1})
    assert "acquired" not in result
    assert result["hires"] == 1 and result["expected_closing_workforce"] == 2


def _report_with(reconciliation: AnnualWorkforceReconciliation | None, tmp_path):
    run_dir = build_archive(tmp_path)
    path = run_dir / "provenance.json"
    if reconciliation is not None:
        manifest = RunProvenanceManifest.model_validate_json(path.read_text())
        manifest.workforce_reconciliations = [reconciliation]
        path.write_text(manifest.model_dump_json(indent=2))
    return path, build_provenance_report(tmp_path, RUN_ID)


def test_report_reconciles_with_an_acquired_step(tmp_path):
    step = AnnualWorkforceReconciliation(
        simulation_year=2025,
        opening_workforce=10,
        hires=2,
        acquired=5,
        terminations=1,
        expected_closing_workforce=16,
        actual_closing_workforce=16,
        variance=0,
        opening_source="baseline",
    )
    path, report = _report_with(step, tmp_path)
    assert '"acquired": 5' in path.read_text()
    assert report.verification_disposition == "fully_verified"
    markdown = render_markdown(report)
    assert "| Year | Opening | Hires | Acquired | Terminations |" in markdown
    assert "| 2025 | 10 | 2 | 5 | 1 | 16 | 16 | 0 | baseline |" in markdown


def test_report_without_acquisitions_looks_as_before(tmp_path):
    path, report = _report_with(None, tmp_path)
    assert "acquired" not in path.read_text()
    assert "acquired" not in report.model_dump_json()
    markdown = render_markdown(report)
    assert (
        "| Year | Opening | Hires | Terminations | Expected close | Actual close "
        "| Variance | Opening source |\n|---:|---:|---:|---:|---:|---:|---:|---|\n"
        "| 2025 | 10 | 0 | 0 | 10 | 10 | 0 | baseline |"
    ) in markdown


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("service_credit", "prior_service"),
        ("plan_entry", "acquisition_date"),
        ("starting_participation_rate", 0.7),
        ("relative_pay", 1.1),
        ("average_pay", 80_000),
        ("average_age", 50),
        ("average_service", 3),
    ],
)
def test_comparison_flags_a_changed_plan_setting_or_override(key: str, value: Any):
    changed = [{**ACQUISITIONS[0], key: value}, ACQUISITIONS[1]]
    reasons = _acquisition_reasons(
        _record("base", {"acquisitions": ACQUISITIONS}),
        _record("changed", {"acquisitions": changed}),
    )
    assert len(reasons) == 1
