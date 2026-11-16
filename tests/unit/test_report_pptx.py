"""Native PowerPoint report: real tables and charts whose figures equal the PDF's."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import pytest

from planalign_api.models.report import (
    ReportDefinition,
    ReportPlanDesign,
    ReportProvenance,
    ReportScenario,
    ReportYear,
    ScenarioReport,
)
from planalign_api.services.report_pptx import (
    CHART_NAME,
    FOOTER_TOP,
    GREEN,
    table_shape_name,
)
from planalign_api.services.report_render import (
    ReportTable,
    cost_series,
    provenance_table,
    render_html,
    render_report,
    report_tables,
)

pptx = pytest.importorskip("pptx")
from pptx.enum.text import PP_ALIGN  # noqa: E402

pytestmark = [pytest.mark.fast]

LONG = (
    "100% of the first 3%, then 50% of the next 2% deferred (up to 4% of pay). "
    "Requires 1,000 hours in the year and employment on the last day of the year."
)


def _scenario(index: int, years: list[int], gap: int | None) -> ReportScenario:
    cost = 31_400_000 * (1 + 0.21 * index)
    rows = [
        ReportYear(
            year=year,
            employer_cost=None if year == gap else cost * 1.042**k,
            cost_pct_of_capped_pay=4.1 + 0.6 * index,
            participation_rate=71.2 + k,
            average_deferral_rate=None if year == gap else 5.4,
            difference_from_anchor=None if index == 0 else cost * 0.2,
        )
        for k, year in enumerate(years)
    ]
    return ReportScenario(
        scenario_id=f"s{index}",
        name=f"Design {index}",
        is_anchor=index == 0,
        design=ReportPlanDesign(
            eligibility="Eligible to defer after 3 months of service.",
            auto_enrollment="New hires are auto-enrolled at 3% of pay and may opt out.",
            escalation="Deferrals rise 1% a year, up to 10% of pay.",
            match=LONG,
            core="2% of pay, whether or not the employee defers.",
        ),
        years=rows,
        total_employer_cost=sum(r.employer_cost or 0 for r in rows),
        total_cost_pct_of_capped_pay=4.2,
        total_difference_from_anchor=None if index == 0 else -1_234_567.0,
        total_difference_pct_of_anchor=None if index == 0 else -3.45,
    )


def _report(count: int, years: int, missing: bool = False) -> ScenarioReport:
    span = list(range(2026, 2026 + years))
    scenarios = [_scenario(i, span, gap=2028 if i == 1 else None) for i in range(count)]
    if missing:
        scenarios.append(
            ReportScenario(
                scenario_id="gone",
                name="Not run",
                missing_reason="Not run yet.",
                design=scenarios[0].design,
            )
        )
    return ScenarioReport(
        title="Plan design comparison",
        generated_at=datetime(2026, 11, 14, tzinfo=timezone.utc),
        anchor_scenario_id="s0",
        scenarios=scenarios,
        definitions=[
            ReportDefinition(term="design", text="Designs note."),
            ReportDefinition(term="employer_cost", text="Cost note."),
        ],
        provenance=[
            ReportProvenance(
                workspace_id="ws",
                scenario_id=s.scenario_id,
                scenario_name=s.name,
                run_id=f"run-{s.scenario_id}",
                config_fingerprint="f" * 12,
            )
            for s in scenarios
            if s.available
        ],
    )


def _deck(report: ScenarioReport, tmp_path: Path) -> Any:
    return pptx.Presentation(str(render_report(report, tmp_path / "r.pptx", "pptx")))


def _tables(deck: Any, table: ReportTable) -> list[Any]:
    name = table_shape_name(table)
    return [s.table for slide in deck.slides for s in slide.shapes if s.name == name]


def _cells(grid: Any) -> list[list[str]]:
    return [[cell.text for cell in row.cells] for row in grid.rows]


def _slide_titles(deck: Any) -> list[str]:
    return [
        next(s.text_frame.text for s in slide.shapes if s.name == "title")
        for slide in deck.slides
    ]


@pytest.mark.parametrize(
    "report",
    [_report(3, 5, missing=True), _report(6, 10), _report(6, 25), _report(1, 5)],
    ids=["3x5-missing", "6x10", "6x25-paginated", "single"],
)
def test_every_table_cell_equals_the_pdf_table(report, tmp_path):
    deck = _deck(report, tmp_path)
    html = render_html(report)
    for table in [*report_tables(report), provenance_table(report)]:
        pages = _tables(deck, table)
        assert pages, table.key
        rows: list[list[str]] = []
        for grid in pages:
            header, *body = _cells(grid)
            assert header == table.header
            rows += body
        assert rows == table.rows
        for row in table.rows:  # the HTML/PDF renders the same strings
            assert "".join(f"<td>{escape(c)}</td>" for c in row) in html


def test_cells_are_formatted_aligned_and_styled_like_the_pdf(tmp_path):
    report = _report(3, 5, missing=True)
    deck = _deck(report, tmp_path)
    by_key = {t.key: _tables(deck, t)[0] for t in report_tables(report)}
    summary, design = by_key["summary"], by_key["design"]
    total, difference, share = _cells(summary)[2][1:4]
    assert total.startswith("$") and "," in total
    assert (difference, share) == ("−$1,234,567", "−3.5%")
    years = _tables(deck, report_tables(report)[2])[0]
    assert "—" in [row[2] for row in _cells(years)]  # unavailable year is a dash
    for row_index, row in enumerate(summary.rows):
        for col, cell in enumerate(row.cells):
            paragraph = cell.text_frame.paragraphs[0]
            expected = PP_ALIGN.LEFT if col == 0 else PP_ALIGN.RIGHT
            assert paragraph.alignment == expected
            assert paragraph.runs[0].font.size.pt >= 10
            if row_index == 0:
                assert cell.fill.fore_color.rgb == pptx.dml.color.RGBColor.from_string(
                    GREEN
                )
                assert paragraph.runs[0].font.bold
    for row in design.rows:
        for cell in row.cells:
            assert cell.text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT


def test_chart_is_native_with_the_models_series(tmp_path):
    report = _report(3, 5, missing=True)
    deck = _deck(report, tmp_path)
    frames = [s for slide in deck.slides for s in slide.shapes if s.name == CHART_NAME]
    assert len(frames) == 1 and frames[0].has_chart
    chart = frames[0].chart
    assert chart.part.chart_workbook.xlsx_part is not None  # editable data
    plot = chart.plots[0]
    assert list(plot.categories) == [str(y) for y in report.years]
    expected = cost_series(report)
    assert [s.name for s in plot.series] == [s.name for s in expected]
    for series, line in zip(plot.series, expected):
        assert list(series.values) == pytest.approx(line.values)
    assert None in list(plot.series[1].values)  # a gap, not a zero
    assert chart.has_legend
    axis = chart.value_axis.tick_labels
    assert axis.number_format == '$#,##0.0,,"M"' and not axis.number_format_is_linked
    widths = [s.format.line.width for s in plot.series]
    assert widths[0] > widths[1]  # the anchor stands out
    assert '<c:dispBlanksAs val="gap"/>' in chart.part.blob.decode()


def test_six_scenarios_by_ten_years_fit_every_slide(tmp_path):
    deck = _deck(_report(6, 10), tmp_path)
    width, footer = deck.slide_width, pptx.util.Inches(FOOTER_TOP)
    for slide in deck.slides:
        for shape in slide.shapes:
            assert shape.left >= 0 and shape.left + shape.width <= width, shape.name
            if shape.has_table or shape.has_chart:
                assert shape.top + shape.height <= footer, shape.name
    assert not any("(continued)" in t for t in _slide_titles(deck))


def test_long_tables_continue_on_another_slide(tmp_path):
    deck = _deck(_report(6, 25), tmp_path)
    titles = _slide_titles(deck)
    assert "Employer cost by year (continued)" in titles
    footer = pptx.util.Inches(FOOTER_TOP)
    tables = [s for slide in deck.slides for s in slide.shapes if s.has_table]
    assert all(s.top + s.height <= footer for s in tables)


def test_single_scenario_and_missing_result_decks_render(tmp_path):
    single = _deck(_report(1, 5), tmp_path)
    assert not any(t.startswith("Difference") for t in _slide_titles(single))
    lead = " ".join(
        s.text_frame.text for s in single.slides[0].shapes if s.has_text_frame
    )
    assert "Design 0: $" in lead
    missing = _deck(_report(2, 3, missing=True), tmp_path)
    text = " ".join(
        s.text_frame.text for s in missing.slides[0].shapes if s.has_text_frame
    )
    assert "Not run: Not run yet." in text
    design = _tables(missing, report_tables(_report(2, 3, missing=True))[0])[0]
    assert _cells(design)[0][-1] == "Not run (no result)"
