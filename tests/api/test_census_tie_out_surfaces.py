"""Census tie-out carried into Run Health and the scenario report (Epic C, C3)."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from planalign_api.models.census_tie_out import CensusTieOut
from planalign_api.models.report import ScenarioReport
from planalign_api.models.run_health import RunHealthCounts, RunHealthReport
from planalign_api.routers import simulations
from planalign_api.services import report_service
from planalign_api.services.census_tie_out import CensusTieOutService
from planalign_api.services.current_result import publish_current_result
from planalign_api.services.report_service import (
    _render_html,
    render_report,
    tie_out_difference,
    tie_out_value,
)
from planalign_api.services.run_health import with_census_tie_out
from planalign_api.storage.workspace_storage import WorkspaceStorage
from tests.api.test_census_tie_out import (
    CENSUS,
    CONFIG,
    SIMULATED,
    _create_census,
    _create_snapshot,
)
from tests.fixtures.run_provenance import RUN_ID, build_archive

pytestmark = pytest.mark.fast

# Same census, but the first simulated year pays twice the match and core.
OVER_MATCH = replace(SIMULATED, match_rate=0.06, core_rate=0.04)


def _build_tied_run(root: Path, sim=SIMULATED) -> Path:
    """A completed, selected run with provenance and an archived census."""
    run_dir = build_archive(root)
    (run_dir / "config.yaml").write_text(CONFIG, encoding="utf-8")
    with duckdb.connect(str(run_dir / "simulation.duckdb")) as conn:
        _create_census(conn, CENSUS)
        _create_snapshot(conn, sim)
    publish_current_result(run_dir.parent.parent, RUN_ID)
    return run_dir


def _tie_out(root: Path) -> CensusTieOut:
    return CensusTieOutService(WorkspaceStorage(root)).get_tie_out(
        "workspace", "scenario-a", "Scenario A"
    )


def _report(run_id: str = RUN_ID) -> RunHealthReport:
    return RunHealthReport(
        status="clean",
        scenario_id="scenario-a",
        run_id=run_id,
        counts=RunHealthCounts(passed=1, warning=0, failed=0, total=1),
    )


# ---------------------------------------------------------------------------
# Run Health
# ---------------------------------------------------------------------------


def test_gaps_add_one_run_health_line(tmp_path: Path) -> None:
    _build_tied_run(tmp_path, OVER_MATCH)
    report = with_census_tie_out(_report(), lambda: _tie_out(tmp_path))
    assert report.census_tie_out is not None
    assert report.census_tie_out.labels == ["Employer match", "Employer core"]
    assert report.census_tie_out.message == (
        "2 census tie-out rows differ from the census: Employer match, Employer core"
    )
    assert report.status == "clean"  # advisory: validation status is unchanged


def test_one_gap_reads_singular(tmp_path: Path) -> None:
    _build_tied_run(tmp_path, replace(SIMULATED, core_rate=0.04))
    report = with_census_tie_out(_report(), lambda: _tie_out(tmp_path))
    assert report.census_tie_out is not None
    assert report.census_tie_out.message == (
        "1 census tie-out row differs from the census: Employer core"
    )


def test_tied_run_adds_nothing(tmp_path: Path) -> None:
    _build_tied_run(tmp_path)
    assert with_census_tie_out(_report(), lambda: _tie_out(tmp_path)) == _report()


def test_unavailable_tie_out_adds_nothing(tmp_path: Path) -> None:
    tie_out = _tie_out(tmp_path)  # no run at all
    assert tie_out.available is False
    assert with_census_tie_out(_report(), lambda: tie_out) == _report()


def test_tie_out_for_another_run_is_ignored(tmp_path: Path) -> None:
    _build_tied_run(tmp_path, OVER_MATCH)
    other = _report(run_id="00000000-0000-4000-8000-000000000000")
    assert with_census_tie_out(other, lambda: _tie_out(tmp_path)) == other


def test_tie_out_failure_is_logged_and_run_health_still_returns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken() -> CensusTieOut:
        raise duckdb.IOException("Could not set lock on file")

    with caplog.at_level(logging.ERROR, logger="planalign_api.services.run_health"):
        report = with_census_tie_out(_report(), broken)
    assert report == _report()
    assert "Census tie-out failed" in caplog.text


@pytest.fixture()
def health_client(client_factory, monkeypatch):
    workspace = SimpleNamespace(id="workspace", name="Workspace")
    scenario = SimpleNamespace(id="scenario-a", name="Scenario A")
    monkeypatch.setattr(
        simulations,
        "_find_scenario_and_workspace",
        lambda storage_arg, scenario_id: (workspace, scenario),
    )
    return client_factory(None)


def test_run_health_endpoints_carry_the_gap_line(health_client, tmp_path) -> None:
    _build_tied_run(tmp_path / "workspaces", OVER_MATCH)
    for path in ("run-health", f"runs/{RUN_ID}/health"):
        body = health_client.get(f"/api/scenarios/scenario-a/{path}").json()
        assert body["status"] == "clean"
        assert body["census_tie_out"]["labels"] == ["Employer match", "Employer core"]


def test_run_health_endpoint_survives_a_tie_out_failure(
    health_client, tmp_path, monkeypatch
) -> None:
    _build_tied_run(tmp_path / "workspaces", OVER_MATCH)

    def broken(*args: object) -> CensusTieOut:
        raise RuntimeError("boom")

    monkeypatch.setattr(CensusTieOutService, "get_tie_out", broken)
    response = health_client.get("/api/scenarios/scenario-a/run-health")
    assert response.status_code == 200
    assert response.json()["census_tie_out"] is None


def test_non_selected_run_is_not_tied_out(health_client, tmp_path, monkeypatch) -> None:
    root = tmp_path / "workspaces"
    _build_tied_run(root, OVER_MATCH)
    newer = "00000000-0000-4000-8000-000000000001"
    build_archive(root, run_id=newer)
    calls: list[object] = []
    monkeypatch.setattr(
        CensusTieOutService, "get_tie_out", lambda *args: calls.append(args)
    )
    body = health_client.get(f"/api/scenarios/scenario-a/runs/{newer}/health").json()
    assert body["census_tie_out"] is None
    assert calls == []


# ---------------------------------------------------------------------------
# Scenario report
# ---------------------------------------------------------------------------


def test_report_table_matches_the_service_rows(tmp_path: Path) -> None:
    _build_tied_run(tmp_path, OVER_MATCH)
    tie_out = _tie_out(tmp_path)
    report = ScenarioReport(
        title="Report",
        generated_at=datetime.now(timezone.utc),
        census_tie_out=tie_out,
    )
    html = _render_html(report, None)
    assert "<h2>Census tie-out</h2>" in html
    assert tie_out.source_note and tie_out.source_note in html
    assert "Meaningful only for a scenario that models the current plan." in html
    assert "census_2024.parquet (census year 2024) with 2025" in html
    body = html.split("<h2>Census tie-out</h2>", 1)[1]
    for row in tie_out.rows:
        status = {"ties": "Ties", "gap": "Gap", "not_in_census": "Not in census"}
        cells = (
            f"<td>{tie_out_value(row, row.census_value)}</td>"
            f"<td>{tie_out_value(row, row.simulated_value)}</td>"
            f"<td>{tie_out_difference(row)}</td>"
            f"<td class='tie-{row.status}'>{status[row.status]}</td>"
        )
        assert row.label in body and cells in body
        assert (row.message in body) == (row.status == "gap")


def test_report_formats_values_like_the_panel(tmp_path: Path) -> None:
    _build_tied_run(tmp_path, OVER_MATCH)
    rows = {row.metric: row for row in _tie_out(tmp_path).rows}
    match = rows["employer_match"]
    assert tie_out_value(match, match.census_value) == "$90,000"
    assert tie_out_difference(match) == "+$105,300"
    rate = rows["participation_rate"]
    assert tie_out_value(rate, rate.census_value) == "60.0%"
    assert tie_out_difference(rate) == "+0.2 pts"
    count = rows["active_headcount"]
    assert (tie_out_value(count, count.census_value), tie_out_difference(count)) == (
        "100",
        "+3",
    )


def test_unavailable_tie_out_states_the_reason(tmp_path: Path) -> None:
    tie_out = _tie_out(tmp_path)
    report = ScenarioReport(
        title="Report", generated_at=datetime.now(timezone.utc), census_tie_out=tie_out
    )
    html = _render_html(report, None)
    assert f"<h2>Census tie-out</h2><p>{tie_out.unavailable_reason}</p>" in html


def test_report_tie_out_failure_becomes_a_warning(tmp_path, monkeypatch) -> None:
    def broken(*args: object) -> CensusTieOut:
        raise RuntimeError("boom")

    monkeypatch.setattr(CensusTieOutService, "get_tie_out", broken)
    report = ScenarioReport(title="Report", generated_at=datetime.now(timezone.utc))
    scenario = SimpleNamespace(id="scenario-a", name="Scenario A")
    result = report_service._census_tie_out(
        report, WorkspaceStorage(tmp_path), "workspace", scenario
    )
    assert result is None
    assert [w.code for w in report.warnings] == ["census_tie_out_unavailable"]


@pytest.mark.parametrize(
    ("unit", "difference", "shown"),
    [
        ("count", -0.4, "+0"),
        ("dollars", -0.5, "+$0"),
        ("rate", -0.0004, "+0.0 pts"),
        ("dollars", -0.6, "-$1"),
        ("rate", -0.0006, "-0.1 pts"),
    ],
)
def test_difference_that_rounds_to_zero_has_no_minus_sign(
    tmp_path: Path, unit: str, difference: float, shown: str
) -> None:
    _build_tied_run(tmp_path)
    row = (
        _tie_out(tmp_path)
        .rows[0]
        .model_copy(update={"unit": unit, "difference": difference})
    )
    assert tie_out_difference(row) == shown


def _all_gaps(tie_out: CensusTieOut) -> CensusTieOut:
    """Every row a gap, so the slide carries the longest possible content."""
    rows = [
        row.model_copy(update={"status": "gap", "message": row.message * 2})
        for row in tie_out.rows
    ]
    return tie_out.model_copy(update={"rows": rows})


def test_pptx_tie_out_slide_fits_and_wraps(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    pytest.importorskip("pptx.enum.text")
    _build_tied_run(tmp_path / "run", OVER_MATCH)
    tie_out = _all_gaps(_tie_out(tmp_path / "run"))
    report = ScenarioReport(
        title="Report", generated_at=datetime.now(timezone.utc), census_tie_out=tie_out
    )
    output = render_report(report, tmp_path / "report.pptx", "pptx")

    deck = pptx.Presentation(str(output))
    slide = next(
        s
        for s in deck.slides
        if s.shapes.title and s.shapes.title.text == "Census tie-out"
    )
    footer = slide.shapes[-1]
    body = [
        shape for shape in slide.shapes if shape not in (slide.shapes.title, footer)
    ]
    assert len(body) == 3  # source note, table, gap messages
    for shape in body:
        assert shape.left >= 0 and shape.top >= 0
        assert shape.left + shape.width <= deck.slide_width
        assert shape.top + shape.height <= footer.top
    note, table, gaps = body
    for frame in (note.text_frame, gaps.text_frame):
        assert frame.word_wrap
        assert frame.auto_size == pptx.enum.text.MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    assert note.text_frame.text == tie_out.source_note
    assert len(gaps.text_frame.paragraphs) == len(tie_out.rows)
    assert all(p.font.size.pt == 9 for p in gaps.text_frame.paragraphs)
    cells = table.table
    assert (len(cells.rows), len(cells.columns)) == (len(tie_out.rows) + 1, 5)
    assert cells.cell(6, 0).text == "Employer match"
    assert cells.cell(6, 3).text == tie_out_difference(tie_out.rows[5])
