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
from planalign_api.models.report import ReportScenario, ReportYear, ScenarioReport
from planalign_api.models.run_health import RunHealthCounts, RunHealthReport
from planalign_api.routers import simulations
from planalign_api.services import report_service
from planalign_api.services.census_tie_out import CensusTieOutService
from planalign_api.services.current_result import publish_current_result
from planalign_api.services.report_pptx import FOOTER_TOP
from planalign_api.services.report_render import (
    render_html,
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
def health_client(client_factory, monkeypatch, request):
    """Run Health client for scenario-a, marked as the current plan unless the
    test is parametrized indirectly with ``False``."""
    workspace = SimpleNamespace(id="workspace", name="Workspace")
    scenario = SimpleNamespace(
        id="scenario-a",
        name="Scenario A",
        models_current_plan=getattr(request, "param", True),
    )
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


@pytest.mark.parametrize("health_client", [False], indirect=True)
def test_unmarked_scenario_gets_no_line_and_its_db_is_not_opened(
    health_client, tmp_path, monkeypatch
) -> None:
    _build_tied_run(tmp_path / "workspaces", OVER_MATCH)
    calls: list[object] = []
    monkeypatch.setattr(
        CensusTieOutService, "get_tie_out", lambda *args: calls.append(args)
    )
    for path in ("run-health", f"runs/{RUN_ID}/health"):
        body = health_client.get(f"/api/scenarios/scenario-a/{path}").json()
        assert body["census_tie_out"] is None
    assert calls == []


# ---------------------------------------------------------------------------
# Scenario report
# ---------------------------------------------------------------------------


def _section(
    scenario_id: str, tie_out: CensusTieOut | None = None, *, anchor: bool = True
) -> ReportScenario:
    return ReportScenario(
        scenario_id=scenario_id,
        name=f"Scenario {scenario_id[-1].upper()}",
        is_anchor=anchor,
        years=[ReportYear(year=2025, employer_cost=1000.0)],
        total_employer_cost=1000.0,
        census_tie_out=tie_out,
    )


def _brief(*sections: ReportScenario) -> ScenarioReport:
    return ScenarioReport(
        title="Report",
        generated_at=datetime.now(timezone.utc),
        anchor_scenario_id=sections[0].scenario_id,
        scenarios=list(sections),
    )


@pytest.fixture()
def report_inputs(tmp_path: Path, monkeypatch):
    """build_scenario_report over stub scenarios; returns (build, tie-out calls)."""
    _build_tied_run(tmp_path, OVER_MATCH)
    computed = _tie_out(tmp_path)
    calls: list[str] = []

    def tie_out(service: object, workspace_id: str, scenario_id: str, name: str):
        calls.append(scenario_id)
        return computed

    monkeypatch.setattr(CensusTieOutService, "get_tie_out", tie_out)
    monkeypatch.setattr(
        report_service,
        "_scenario_section",
        lambda report, storage, workspace_id, scenario, anchor_id: _section(
            scenario.id, anchor=scenario.id == anchor_id
        ),
    )

    def build(marked: dict[str, bool]) -> ScenarioReport:
        scenarios = {
            scenario_id: SimpleNamespace(
                id=scenario_id,
                name=f"Scenario {scenario_id[-1].upper()}",
                models_current_plan=is_marked,
            )
            for scenario_id, is_marked in marked.items()
        }
        monkeypatch.setattr(
            report_service, "_resolve_scenario", lambda s, w, i: scenarios.get(i)
        )
        first, *others = scenarios
        return report_service.build_scenario_report(
            WorkspaceStorage(tmp_path), "workspace", first, others
        )

    return build, calls


@pytest.mark.parametrize("marked", [True, False])
def test_report_tie_out_only_for_the_current_plan(report_inputs, marked) -> None:
    build, calls = report_inputs
    report = build({"scenario-a": marked})
    assert (report.scenarios[0].census_tie_out is not None) == marked
    assert calls == (["scenario-a"] if marked else [])


def test_comparison_report_ties_out_the_selected_current_plan(report_inputs) -> None:
    build, calls = report_inputs
    report = build({"scenario-a": False, "scenario-b": True, "scenario-c": False})
    assert calls == ["scenario-b"]
    assert report.tie_out_scenario is not None
    assert report.tie_out_scenario.scenario_id == "scenario-b"
    html = render_html(report)
    assert html.count("Census tie-out") == 1
    assert "<h2>Census tie-out: Scenario B</h2>" in html


def test_comparison_without_the_current_plan_has_no_tie_out(report_inputs) -> None:
    build, calls = report_inputs
    report = build({"scenario-a": False, "scenario-b": False})
    assert calls == []
    assert report.tie_out_scenario is None
    assert "Census tie-out" not in render_html(report)


def test_report_tie_out_failure_becomes_a_warning(report_inputs, monkeypatch) -> None:
    build, _ = report_inputs

    def broken(*args: object) -> CensusTieOut:
        raise RuntimeError("boom")

    monkeypatch.setattr(CensusTieOutService, "get_tie_out", broken)
    report = build({"scenario-a": True})
    assert report.scenarios[0].census_tie_out is None
    assert [w.code for w in report.warnings] == ["census_tie_out_unavailable"]
    assert "Census tie-out" not in render_html(report)


def test_report_table_matches_the_service_rows(tmp_path: Path) -> None:
    _build_tied_run(tmp_path, OVER_MATCH)
    tie_out = _tie_out(tmp_path)
    html = render_html(_brief(_section("scenario-a", tie_out)))
    heading = "<h2>Census tie-out: Scenario A</h2>"
    assert heading in html
    body = html.split(heading, 1)[1].split("</section>", 1)[0]
    assert tie_out.source_note and f"<p>{tie_out.source_note}</p>" in body
    assert "Meaningful only for a scenario that models the current plan." in body
    assert "<th>Census 2024</th><th>Simulated 2025</th>" in body
    status = {"ties": "Ties", "gap": "Gap", "not_in_census": "Not in census"}
    for row in tie_out.rows:
        cells = (
            f"<tr class='tie-{row.status}'><td>{row.label}</td>"
            f"<td>{tie_out_value(row, row.census_value)}</td>"
            f"<td>{tie_out_value(row, row.simulated_value)}</td>"
            f"<td>{tie_out_difference(row)}</td>"
            f"<td>{status[row.status]}</td></tr>"
        )
        assert cells in body
        assert (row.message in body) == (row.status == "gap")


def test_report_tie_out_sits_after_the_figures_before_the_notes(
    tmp_path: Path,
) -> None:
    _build_tied_run(tmp_path, OVER_MATCH)
    html = render_html(_brief(_section("scenario-a", _tie_out(tmp_path))))
    tie_out = html.index("Census tie-out")
    assert html.index("class='chart'") < tie_out < html.index("<h2>Notes</h2>")


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
    html = render_html(_brief(_section("scenario-a", tie_out)))
    assert tie_out.unavailable_reason
    assert (
        f"<h2>Census tie-out: Scenario A</h2><p>{tie_out.unavailable_reason}</p>"
        in html
    )


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


def _deck_titles(deck) -> list[str]:
    return [
        next(shape.text_frame.text for shape in slide.shapes if shape.name == "title")
        for slide in deck.slides
    ]


def test_pptx_tie_out_is_a_native_table_that_fits(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    _build_tied_run(tmp_path / "run", OVER_MATCH)
    tie_out = _all_gaps(_tie_out(tmp_path / "run"))
    report = _brief(
        _section("scenario-a"), _section("scenario-b", tie_out, anchor=False)
    )
    deck = pptx.Presentation(
        str(render_report(report, tmp_path / "report.pptx", "pptx"))
    )

    titles = _deck_titles(deck)
    title = "Census tie-out: Scenario B"
    assert title in titles
    assert titles.index("Notes") - 1 == max(
        i for i, t in enumerate(titles) if t.startswith(title)
    )
    slides = [s for s, t in zip(deck.slides, titles) if t.startswith(title)]
    shapes = [shape for slide in slides for shape in slide.shapes]
    tables = [s for s in shapes if s.name == "table:census-tie-out"]
    footer = pptx.util.Inches(FOOTER_TOP)
    for shape in shapes:
        assert shape.left >= 0 and shape.left + shape.width <= deck.slide_width
        if shape.has_table:
            assert shape.top + shape.height <= footer
    header = [cell.text for cell in tables[0].table.rows[0].cells]
    assert header == ["Metric", "Census 2024", "Simulated 2025", "Difference", "Status"]
    body = [
        [c.text for c in row.cells] for t in tables for row in list(t.table.rows)[1:]
    ]
    assert len(body) == len(tie_out.rows)
    for cells, row in zip(body, tie_out.rows):
        assert cells == [
            f"{row.label}: {row.message}",
            tie_out_value(row, row.census_value),
            tie_out_value(row, row.simulated_value),
            tie_out_difference(row),
            "Gap",
        ]
    notes = [s.text_frame.text for s in shapes if s.has_text_frame]
    assert tie_out.source_note in notes


def test_pptx_tie_out_ties_show_the_metric_alone(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    _build_tied_run(tmp_path / "run")
    tie_out = _tie_out(tmp_path / "run")
    deck = pptx.Presentation(
        str(
            render_report(
                _brief(_section("scenario-a", tie_out)), tmp_path / "r.pptx", "pptx"
            )
        )
    )
    table = next(
        shape.table
        for slide in deck.slides
        for shape in slide.shapes
        if shape.name == "table:census-tie-out"
    )
    labels = [row.cells[0].text for row in list(table.rows)[1:]]
    assert labels == [row.label for row in tie_out.rows]


def test_pptx_unavailable_tie_out_states_the_reason(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    tie_out = _tie_out(tmp_path)
    deck = pptx.Presentation(
        str(
            render_report(
                _brief(_section("scenario-a", tie_out)), tmp_path / "r.pptx", "pptx"
            )
        )
    )
    slide = deck.slides[_deck_titles(deck).index("Census tie-out: Scenario A")]
    texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
    assert tie_out.unavailable_reason in texts


def test_pptx_without_the_current_plan_has_no_tie_out_slide(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    output = render_report(
        _brief(_section("scenario-a")), tmp_path / "report.pptx", "pptx"
    )
    titles = _deck_titles(pptx.Presentation(str(output)))
    assert not any(title.startswith("Census tie-out") for title in titles)
