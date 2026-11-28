"""Cost Comparison effective year (#791): the page's data and the exports.

Synthetic three-year runs: before the effective year every non-anchor scenario
shows the anchor's figures, from that year on its own. With the effective year
at the first simulation year, every response is unchanged.
"""

from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml
from openpyxl import load_workbook

from planalign_api import config as api_config
from planalign_api.main import create_app
from planalign_api.models.comparison import RunTrustResult
from planalign_api.models.cost_summary import CostSummaryExportRequest
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import analytics as analytics_router
from planalign_api.services.analytics_service import AnalyticsService
from planalign_api.services.comparison_export_service import ComparisonExportService
from planalign_api.services.comparison_summary_export import (
    EFFECTIVE_YEAR_WITH_GRANDFATHER,
    ComparisonSummaryExportService,
    SummaryScenarioSource,
    build_summary_workbook,
)
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.effective_year import history_dependent_settings
from planalign_api.storage.workspace_storage import WorkspaceStorage
from tests.api.test_dc_plan_analytics_contract import SNAPSHOT_DDL

pytestmark = [pytest.mark.fast]

COMPARE = "/api/workspaces/{workspace_id}/analytics/dc-plan/compare"
EXPORT = "/api/workspaces/{workspace_id}/analytics/compare/export"
SUMMARY = "/api/workspaces/{workspace_id}/analytics/compare/summary-export"
SUMMARY_FIXTURE = Path(__file__).parent / "snapshots" / "cost_summary_request.json"

BASE_CONFIG: dict[str, Any] = {
    "employer_match": {"formula": "simple"},
    "enrollment": {"auto_enrollment": {"enabled": False}},
}
# name -> (employer match by year, run config). Core is 500 every year.
SCENARIOS: dict[str, tuple[dict[int, int], dict[str, Any]]] = {
    "Baseline": ({2025: 1000, 2026: 1100, 2027: 1200}, BASE_CONFIG),
    # A formula-only change: no accuracy warning.
    "Rich match": (
        {2025: 2000, 2026: 2200, 2027: 2400},
        {**BASE_CONFIG, "employer_match": {"formula": "rich"}},
    ),
    # A history-dependent change: auto-enrollment differs.
    "Auto enroll": (
        {2025: 3000, 2026: 3300, 2027: 3600},
        {**BASE_CONFIG, "enrollment": {"auto_enrollment": {"enabled": True}}},
    ),
    # Simulated one year fewer than the anchor.
    "Short run": ({2025: 4000, 2026: 4400}, BASE_CONFIG),
}
CORE = 500


def _build_run(run_dir: Path, match: dict[int, int], config: dict[str, Any]) -> Path:
    run_dir.mkdir(parents=True)
    path = run_dir / "simulation.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute(SNAPSHOT_DDL)
        conn.execute(
            "CREATE TABLE config_irs_limits (limit_year INTEGER, "
            "compensation_limit DECIMAL(12, 2))"
        )
        conn.execute(
            "CREATE TABLE stg_census_data (employee_id VARCHAR, hire_year INTEGER)"
        )
        conn.execute("INSERT INTO stg_census_data VALUES ('e1', 2022)")
        for year, amount in match.items():
            conn.execute("INSERT INTO config_irs_limits VALUES (?, 350000)", [year])
            conn.execute(
                "INSERT INTO fct_workforce_snapshot (employee_id, simulation_year, "
                "employment_status, employee_hire_date, is_enrolled_flag, "
                "prorated_annual_contributions, employer_match_amount, "
                "employer_core_amount, current_deferral_rate, "
                "prorated_annual_compensation) VALUES "
                "('e1', ?, 'ACTIVE', DATE '2022-01-01', true, 3000, ?, ?, 0.06, 100000)",
                [year, amount, CORE],
            )
    (run_dir / "config.yaml").write_text(yaml.safe_dump(config))
    return path


class _StubResolver:
    def __init__(self, paths: dict[str, Path]):
        self._paths = paths

    def resolve(self, workspace_id: str, scenario_id: str) -> ResolvedDatabasePath:
        path = self._paths[scenario_id]
        return ResolvedDatabasePath(
            path=path,
            source="scenario",
            run_id=f"run-{scenario_id[:6]}",
            config_path=path.parent / "config.yaml",
        )


@pytest.fixture
def env(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
    monkeypatch.setattr(api_config, "settings", settings)
    storage = WorkspaceStorage(settings.workspaces_root)
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    ids: dict[str, str] = {}
    paths: dict[str, Path] = {}
    for name, (match, config) in SCENARIOS.items():
        scenario = storage.create_scenario(workspace.id, ScenarioCreate(name=name))
        storage.update_scenario_status(workspace.id, scenario.id, "completed")
        ids[name] = scenario.id
        paths[scenario.id] = _build_run(tmp_path / "runs" / scenario.id, match, config)
    resolver = _StubResolver(paths)

    app = create_app()
    overrides = app.dependency_overrides
    overrides[analytics_router.get_analytics_service] = lambda: AnalyticsService(
        storage=storage, db_resolver=resolver
    )
    overrides[analytics_router.get_comparison_export_service] = lambda: (
        ComparisonExportService(storage, resolver)
    )
    overrides[analytics_router.get_comparison_summary_export_service] = lambda: (
        ComparisonSummaryExportService(storage, resolver)
    )
    return TestClient(app), workspace, ids


def _compare(env, names: list[str], **params: Any):
    client, workspace, ids = env
    return client.get(
        COMPARE.format(workspace_id=workspace.id),
        params={"scenarios": ",".join(ids[name] for name in names), **params},
    )


def _costs(body: dict[str, Any], scenario_id: str) -> dict[int, float]:
    analytics = next(a for a in body["analytics"] if a["scenario_id"] == scenario_id)
    return {
        row["year"]: row["total_employer_cost"]
        for row in analytics["contribution_by_year"]
    }


def _analytics(body: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    return next(a for a in body["analytics"] if a["scenario_id"] == scenario_id)


# ---------------------------------------------------------------------------
# Page data: the comparison endpoint
# ---------------------------------------------------------------------------


def test_first_year_or_no_effective_year_is_unchanged(env):
    _, _, ids = env
    names = ["Baseline", "Rich match"]

    today = _compare(env, names)
    at_first_year = _compare(env, names, anchor=ids["Baseline"], effective_year=2025)
    before_first_year = _compare(
        env, names, anchor=ids["Baseline"], effective_year=2020
    )

    assert today.status_code == 200
    assert at_first_year.json() == today.json() == before_first_year.json()
    assert today.json()["effective_year"] is None
    assert today.json()["warnings"] == []
    assert _analytics(today.json(), ids["Rich match"])["year_sources"] == []


def test_years_before_the_effective_year_show_the_anchor(env):
    _, _, ids = env
    body = _compare(
        env, ["Baseline", "Rich match"], anchor=ids["Baseline"], effective_year=2026
    ).json()

    assert body["effective_year"] == 2026
    assert _costs(body, ids["Baseline"]) == {2025: 1500, 2026: 1600, 2027: 1700}
    assert _costs(body, ids["Rich match"]) == {2025: 1500, 2026: 2700, 2027: 2900}
    rich = _analytics(body, ids["Rich match"])
    assert [(s["year"], s["scenario_id"]) for s in rich["year_sources"]] == [
        (2025, ids["Baseline"]),
        (2026, ids["Rich match"]),
        (2027, ids["Rich match"]),
    ]
    assert rich["year_sources"][0]["run_id"] == f"run-{ids['Baseline'][:6]}"
    # The anchor is never combined.
    assert _analytics(body, ids["Baseline"])["year_sources"] == []


def test_totals_add_up_the_combined_years(env):
    _, _, ids = env
    body = _compare(
        env, ["Baseline", "Rich match"], anchor=ids["Baseline"], effective_year=2027
    ).json()

    rich = _analytics(body, ids["Rich match"])
    assert rich["total_employer_match"] == 1000 + 1100 + 2400
    assert rich["total_employer_core"] == 3 * CORE
    assert rich["total_employer_cost"] == 1500 + 1600 + 2900
    assert rich["total_capped_compensation"] == 300_000


def test_a_year_the_supplying_run_did_not_simulate_is_unavailable(env):
    _, _, ids = env
    body = _compare(
        env, ["Baseline", "Short run"], anchor=ids["Baseline"], effective_year=2026
    ).json()

    short = _analytics(body, ids["Short run"])
    assert _costs(body, ids["Short run"]) == {2025: 1500, 2026: 4900}
    assert [(s["year"], s["available"]) for s in short["year_sources"]] == [
        (2025, True),
        (2026, True),
        (2027, False),
    ]


def test_warning_only_when_history_dependent_settings_differ(env):
    _, _, ids = env
    names = ["Baseline", "Rich match", "Auto enroll"]

    later = _compare(env, names, anchor=ids["Baseline"], effective_year=2026).json()
    first = _compare(env, names, anchor=ids["Baseline"], effective_year=2025).json()

    assert len(later["warnings"]) == 1
    assert later["warnings"][0].startswith(
        "Auto enroll differs from Baseline in auto-enrollment."
    )
    assert "2026" in later["warnings"][0]
    assert first["warnings"] == []


def test_effective_year_needs_an_anchor_and_a_simulated_year(env):
    _, _, ids = env
    names = ["Baseline", "Rich match"]

    no_anchor = _compare(env, names, effective_year=2026)
    after_last = _compare(env, names, anchor=ids["Baseline"], effective_year=2028)

    assert no_anchor.status_code == 400
    assert "anchor" in no_anchor.json()["detail"]
    assert after_last.status_code == 400
    assert "after the last simulated year" in after_last.json()["detail"]


def test_history_dependent_settings_cover_studio_and_engine_paths():
    base = {
        "dc_plan": {"match_tiers": [1], "auto_escalation": False},
        "plan_eligibility": {"minimum_age": 21},
    }
    changed = {
        "dc_plan": {"match_tiers": [2], "auto_escalation": True},
        "plan_eligibility": {"minimum_age": 18},
    }

    assert history_dependent_settings(base, base) == []
    assert history_dependent_settings(base, changed) == [
        "deferral escalation",
        "eligibility",
    ]


# ---------------------------------------------------------------------------
# Comparison exports: Excel and Parquet (Hyper shares the same queries)
# ---------------------------------------------------------------------------


def _export(env, fmt: str, **params: Any):
    client, workspace, ids = env
    return client.get(
        EXPORT.format(workspace_id=workspace.id),
        params={
            "scenarios": f"{ids['Baseline']},{ids['Auto enroll']}",
            "format": fmt,
            "anchor": ids["Baseline"],
            **params,
        },
    )


def _workbook(response) -> dict[str, list[tuple]]:
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    return {
        name: list(workbook[name].iter_rows(values_only=True))
        for name in workbook.sheetnames
    }


def _snapshot_matches(rows: list[tuple]) -> list[tuple[str, int, float]]:
    header = rows[0]
    name, year, match = (
        header.index(column)
        for column in ("scenario_name", "simulation_year", "employer_match_amount")
    )
    return [(row[name], row[year], float(row[match])) for row in rows[1:]]


def test_export_at_the_first_year_matches_todays_export(env):
    today = _workbook(_export(env, "xlsx"))
    first = _workbook(_export(env, "xlsx", effective_year=2025))

    # Only the export timestamp may differ.
    assert first["Workforce_Snapshot"] == today["Workforce_Snapshot"]
    assert first["Metadata"][2:] == today["Metadata"][2:]
    assert "effective_year" not in {row[0] for row in first["Metadata"]}


def test_excel_export_takes_early_rows_from_the_anchor(env):
    _, _, ids = env
    sheets = _workbook(_export(env, "xlsx", effective_year=2026))

    assert _snapshot_matches(sheets["Workforce_Snapshot"]) == [
        ("Baseline", 2025, 1000.0),
        ("Baseline", 2026, 1100.0),
        ("Baseline", 2027, 1200.0),
        ("Auto enroll", 2025, 1000.0),
        ("Auto enroll", 2026, 3300.0),
        ("Auto enroll", 2027, 3600.0),
    ]
    metadata = dict(
        (field, value)
        for field, value in sheets["Metadata"]
        if field in {"effective_year", "supplied_by"}
    )
    assert metadata["effective_year"] == "2026"
    assert metadata["supplied_by"] == (
        f"simulation_year < 2026: Baseline run run-{ids['Baseline'][:6]}; "
        f"simulation_year >= 2026: Auto enroll run run-{ids['Auto enroll'][:6]}"
    )
    notes = [value for field, value in sheets["Metadata"] if field == "accuracy_note"]
    assert len(notes) == 1 and "auto-enrollment" in notes[0]


def test_parquet_export_follows_the_same_rule(env, tmp_path):
    response = _export(env, "parquet", effective_year=2027)

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(tmp_path / "parquet")
    with duckdb.connect() as conn:
        rows = conn.execute(
            "SELECT scenario_name, simulation_year, employer_match_amount "
            "FROM read_parquet(?) WHERE scenario_name = 'Auto enroll' "
            "ORDER BY simulation_year",
            [str(tmp_path / "parquet" / "workforce_snapshot.parquet")],
        ).fetchall()
        metadata = dict(
            conn.execute(
                "SELECT field, value FROM read_parquet(?) "
                "WHERE field = 'effective_year'",
                [str(tmp_path / "parquet" / "metadata.parquet")],
            ).fetchall()
        )
    assert [(year, float(match)) for _, year, match in rows] == [
        (2025, 1000.0),
        (2026, 1100.0),
        (2027, 3600.0),
    ]
    assert metadata == {"effective_year": "2027"}


def test_export_effective_year_needs_an_anchor_and_a_simulated_year(env):
    client, workspace, ids = env
    no_anchor = client.get(
        EXPORT.format(workspace_id=workspace.id),
        params={"scenarios": ids["Baseline"], "effective_year": 2026},
    )

    assert no_anchor.status_code == 400
    assert _export(env, "xlsx", effective_year=2030).status_code == 400


# ---------------------------------------------------------------------------
# Summary workbook: the page's figures, labelled with the effective year
# ---------------------------------------------------------------------------


def _summary_payload(ids: dict[str, str], **view: Any) -> dict[str, Any]:
    payload = json.loads(SUMMARY_FIXTURE.read_text())
    keys = {"base": ids["Baseline"], "rich": ids["Auto enroll"]}
    payload["view"].update(
        anchor_scenario_id=keys["base"],
        cost_view="gross",
        vesting_schedule=None,
        forfeiture_policy=None,
        cohort="all",
        **view,
    )
    for scenario in payload["scenarios"]:
        scenario["scenario_id"] = keys[scenario["scenario_id"]]
        scenario["run_id"] = None
    return payload


def _notes_rows(content: bytes) -> list[tuple]:
    sheet = load_workbook(io.BytesIO(content), read_only=True)["Notes"]
    return list(sheet.iter_rows(values_only=True))


def test_summary_records_the_effective_year_and_accuracy_note(env):
    client, workspace, ids = env

    response = client.post(
        SUMMARY.format(workspace_id=workspace.id),
        json=_summary_payload(ids, effective_year=2026),
    )

    assert response.status_code == 200
    labels = {row[0]: row[1] for row in _notes_rows(response.content) if row}
    assert labels["Effective year"].startswith(
        "2026. Before 2026, every other scenario shows Baseline's figures"
    )
    assert "auto-enrollment" in labels["Accuracy note"]


def test_summary_at_the_first_year_is_unchanged():
    payload = json.loads(SUMMARY_FIXTURE.read_text())
    default = CostSummaryExportRequest.model_validate(payload)
    first_year = copy.deepcopy(payload)
    first_year["view"]["effective_year"] = payload["view"]["first_simulation_year"]
    at_first = CostSummaryExportRequest.model_validate(first_year)
    sources = [
        SummaryScenarioSource(
            item.scenario_id, item.scenario_id, RunTrustResult(available=False)
        )
        for item in default.scenarios
    ]

    def notes(request: CostSummaryExportRequest) -> list[tuple]:
        return [
            row
            for row in _notes_rows(build_summary_workbook(request, sources, "W"))
            if row and row[0] != "Exported (UTC)"
        ]

    assert notes(at_first) == notes(default)


@pytest.mark.parametrize(
    ("view", "expected"),
    [
        ({"grandfather_cutoff_year": 2026}, EFFECTIVE_YEAR_WITH_GRANDFATHER),
        (
            {
                "cost_view": "net",
                "vesting_schedule": "graded_5_year",
                "forfeiture_policy": "offset_employer_contributions",
            },
            "net of forfeitures",
        ),
    ],
)
def test_summary_rejects_combinations_not_supported_yet(env, view, expected):
    client, workspace, ids = env
    payload = _summary_payload(ids, effective_year=2026)
    payload["view"].update(view)

    response = client.post(SUMMARY.format(workspace_id=workspace.id), json=payload)

    assert response.status_code == 400
    assert expected in response.json()["detail"]
