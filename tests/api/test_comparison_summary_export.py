"""Cost Comparison summary workbook: the page's tables as an .xlsx.

``snapshots/cost_summary_request.json`` is written by the Studio test
``planalign_studio/components/costSummary.test.ts`` from the same figures the
page's tables render. These tests prove every one of those figures lands in the
workbook unchanged, and every unavailable one is a blank cell with its note.
"""

from __future__ import annotations

import copy
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest
from openpyxl import load_workbook

from planalign_api import config as api_config
from planalign_api.main import create_app
from planalign_api.models.comparison import RunTrustResult
from planalign_api.models.cost_summary import CostSummaryExportRequest
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import analytics as analytics_router
from planalign_api.services.comparison_summary_export import (
    ComparisonSummaryExportService,
    SummaryScenarioSource,
    build_summary_workbook,
    excel_value,
    summary_columns,
)
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = [pytest.mark.fast]

FIXTURE = Path(__file__).parent / "snapshots" / "cost_summary_request.json"
ENDPOINT = "/api/workspaces/{workspace_id}/analytics/compare/summary-export"
NAMES = {"base": "Baseline", "rich": "Rich match"}


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def _sources(request: CostSummaryExportRequest) -> list[SummaryScenarioSource]:
    return [
        SummaryScenarioSource(
            item.scenario_id,
            NAMES.get(item.scenario_id, item.scenario_id),
            RunTrustResult(available=False, run_id=item.run_id),
        )
        for item in request.scenarios
    ]


def _workbook(request: CostSummaryExportRequest) -> Any:
    content = build_summary_workbook(request, _sources(request), "My WS")
    return load_workbook(io.BytesIO(content))


def _assert_figure(cell: Any, column: Any, figures: dict[str, Any]) -> None:
    value = figures[column.field]
    if value is None:
        assert cell.value is None, (column.field, cell.value)
        note = figures["notes"].get(column.field)
        assert note, f"{column.field} is blank without a note"
        assert cell.comment is not None and cell.comment.text == note
    else:
        assert cell.value == pytest.approx(excel_value(column, value), rel=1e-12)
        assert isinstance(cell.value, (int, float))
        assert cell.number_format != "General"


def test_every_page_figure_lands_in_the_workbook_unchanged():
    payload = _fixture()
    request = CostSummaryExportRequest.model_validate(payload)
    workbook = _workbook(request)
    columns = summary_columns(request.view)
    yearly = [column for column in columns if column.by_year]

    summary = workbook["Summary"]
    by_year = workbook["By year"]
    assert [cell.value for cell in summary[1]][1:] == [c.label for c in columns]
    assert [cell.value for cell in by_year[1]][2:] == [c.label for c in yearly]

    year_row = 2
    for row, scenario in enumerate(payload["scenarios"], start=2):
        for offset, column in enumerate(columns):
            _assert_figure(summary.cell(row, 2 + offset), column, scenario["totals"])
        for year in scenario["years"]:
            assert by_year.cell(year_row, 2).value == year["year"]
            for offset, column in enumerate(yearly):
                _assert_figure(by_year.cell(year_row, 3 + offset), column, year)
            year_row += 1
    assert summary.cell(2, 1).value == "Baseline (anchor)"
    assert by_year.max_row == year_row - 1


def test_notes_sheet_records_view_runs_and_every_blank_cell():
    request = CostSummaryExportRequest.model_validate(_fixture())
    notes = _workbook(request)["Notes"]
    rows = [
        tuple(c for c in row if c is not None)
        for row in notes.iter_rows(values_only=True)
    ]
    assert ("Anchor scenario", "Baseline") in rows
    assert ("Population", "Hired during the simulation (2025+)") in rows
    assert ("Employer cost", "Net of forfeitures") in rows
    assert ("Vesting schedule", "5-Year Graded") in rows
    assert ("Forfeiture policy", "Offset employer contributions") in rows
    assert any(row[:3] == ("Baseline", "base", "run-base") for row in rows)
    blank_rows = rows[
        rows.index(("Sheet", "Scenario", "Year", "Column", "Reason")) + 1 :
    ]
    assert (
        "By year",
        "Rich match",
        2025,
        "Employer cost",
        "No employees in cohort",
    ) in blank_rows


def test_columns_follow_the_view():
    payload = _fixture()
    gross = copy.deepcopy(payload["view"]) | {
        "cost_view": "gross",
        "breakdown": "split",
    }
    gross_fields = [c.field for c in summary_columns(_view(gross))]
    assert "employer_match" in gross_fields and "forfeiture_offset" not in gross_fields

    reallocate = payload["view"] | {"forfeiture_policy": "reallocate_to_participants"}
    assert "reallocated_to_participants" in [
        c.field for c in summary_columns(_view(reallocate))
    ]


def _view(view: dict[str, Any]) -> Any:
    payload = _fixture()
    payload["view"] = view
    return CostSummaryExportRequest.model_validate(payload).view


def test_text_is_never_written_as_a_formula():
    request = CostSummaryExportRequest.model_validate(_fixture())
    sources = [
        SummaryScenarioSource(
            s.scenario_id, '=HYPERLINK("x")', RunTrustResult(available=False)
        )
        for s in request.scenarios
    ]
    workbook = load_workbook(
        io.BytesIO(build_summary_workbook(request, sources, "=1+1"))
    )
    cell = workbook["Summary"].cell(3, 1)
    assert cell.data_type == "s" and cell.value.startswith("=HYPERLINK")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def _metadata_only_db(path: Path, run_id: str) -> Path:
    """A run database with run_metadata and no workforce tables at all."""
    conn = duckdb.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE run_metadata (run_id VARCHAR, run_timestamp TIMESTAMP, "
            "run_type VARCHAR, config_fingerprint VARCHAR, random_seed INTEGER, "
            "full_reset BOOLEAN, planalign_version VARCHAR)"
        )
        conn.execute(
            "INSERT INTO run_metadata VALUES (?, TIMESTAMP '2026-11-01 09:30:00', "
            "'simulation', 'abc123def456', 42, TRUE, '3.2.0')",
            [run_id],
        )
    finally:
        conn.close()
    return path


class _StubResolver:
    def __init__(self, runs: dict[str, tuple[Path, str]]):
        self._runs = runs

    def resolve(self, workspace_id: str, scenario_id: str) -> ResolvedDatabasePath:
        path, run_id = self._runs[scenario_id]
        return ResolvedDatabasePath(path=path, source="run", run_id=run_id)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
    monkeypatch.setattr(api_config, "settings", settings)
    storage = WorkspaceStorage(settings.workspaces_root)
    workspace = storage.create_workspace(WorkspaceCreate(name="My WS"), {})
    ids: dict[str, str] = {}
    runs: dict[str, tuple[Path, str]] = {}
    for key, name in NAMES.items():
        scenario = storage.create_scenario(workspace.id, ScenarioCreate(name=name))
        storage.update_scenario_status(workspace.id, scenario.id, "completed")
        ids[key] = scenario.id
        run_id = f"run-{key}"
        runs[scenario.id] = (
            _metadata_only_db(tmp_path / f"{key}.duckdb", run_id),
            run_id,
        )

    app = create_app()
    app.dependency_overrides[analytics_router.get_comparison_summary_export_service] = (
        lambda: ComparisonSummaryExportService(storage, _StubResolver(runs))
    )
    return TestClient(app), workspace, ids


def _request_for(ids: dict[str, str]) -> dict[str, Any]:
    payload = _fixture()
    payload["view"]["anchor_scenario_id"] = ids["base"]
    for scenario in payload["scenarios"]:
        scenario["scenario_id"] = ids[scenario["scenario_id"]]
    return payload


def test_endpoint_downloads_workbook_with_server_names_and_provenance(env):
    client, workspace, ids = env

    response = client.post(
        ENDPOINT.format(workspace_id=workspace.id), json=_request_for(ids)
    )

    assert response.status_code == 200, response.text
    assert "My_WS_cost_comparison_summary_" in response.headers["content-disposition"]
    workbook = load_workbook(io.BytesIO(response.content))
    assert workbook.sheetnames == ["Summary", "By year", "Notes"]
    assert workbook["Summary"].cell(3, 1).value == "Rich match"
    notes = [row for row in workbook["Notes"].iter_rows(values_only=True)]
    run_row = next(row for row in notes if row[0] == "Rich match")
    assert run_row[2:7] == ("run-rich", "2026-11-01 09:30", "abc123def456", 42, "3.2.0")


def test_endpoint_rejects_figures_from_a_superseded_run(env):
    client, workspace, ids = env
    payload = _request_for(ids)
    payload["scenarios"][1]["run_id"] = "older-run"

    response = client.post(ENDPOINT.format(workspace_id=workspace.id), json=payload)

    assert response.status_code == 409
    assert "Refresh the page" in response.json()["detail"]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda p: p["view"].update(anchor_scenario_id="other"), 400),
        (lambda p: p["view"].update(forfeiture_policy=None), 400),
        (lambda p: p["scenarios"].append(copy.deepcopy(p["scenarios"][0])), 400),
        (lambda p: p["scenarios"][1].update(scenario_id="missing"), 404),
        (lambda p: p["scenarios"][0]["totals"].update(employer_cost="NaN"), 422),
        (lambda p: p.update(scenarios=p["scenarios"] * 4), 422),
    ],
)
def test_endpoint_rejects_inconsistent_requests(env, change, expected):
    client, workspace, ids = env
    payload = _request_for(ids)
    change(payload)

    response = client.post(ENDPOINT.format(workspace_id=workspace.id), json=payload)

    assert response.status_code == expected, response.text


def test_build_is_stamped_with_export_time():
    request = CostSummaryExportRequest.model_validate(_fixture())
    when = datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc)
    content = build_summary_workbook(request, _sources(request), "My WS", when)
    rows = list(load_workbook(io.BytesIO(content))["Notes"].iter_rows(values_only=True))
    assert ("Exported (UTC)", "2026-11-14 08:00") in [row[:2] for row in rows]
