"""Render a ``ScenarioReport`` as an editable PowerPoint deck.

Tables are native PowerPoint tables and the cost chart is a native line chart
with its data in an embedded workbook, so an analyst can restyle or edit both.
Cell text comes from ``report_tables`` and chart values from ``cost_series``,
the same builders behind the HTML/PDF, so slide figures equal the PDF's.

python-pptx is imported at call time; ``render_pptx`` raises ``RuntimeError``
when it is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from planalign_api.models.report import ScenarioReport
from planalign_core.spreadsheet_safety import neutralize_formula
from planalign_api.services.report_render import (
    PALETTE,
    ReportTable,
    cost_series,
    generated_line,
    largest_cost,
    lead_lines,
    missing_lines,
    provenance_table,
    report_tables,
    tie_out_cells,
    tie_out_title,
    trace_line,
)

# Layout, in inches, on a 16:9 slide.
SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.5
CONTENT_W = SLIDE_W - 2 * MARGIN
BODY_TOP = 1.25
FOOTER_TOP = 7.02
NOTE_H = 0.6
INTRO_H = 0.45
BODY_BOTTOM = FOOTER_TOP - 0.12
CELL_PAD_X, CELL_PAD_Y = 0.08, 0.04
LINE_SPACING = 1.2
# Average Arial glyph width as a share of the point size, rounded up so the
# row-height estimate errs toward taller rows (no overflow).
CHAR_EM = 0.5
DESIGN_LABEL_W = 1.55

GREEN, DARK, INK, MUTED = "2F7D32", "1F3B2A", "273238", "64736D"
BAND, WHITE, RED = "F1F6F2", "FFFFFF", "B42318"
FONT = "Arial"
CHART_NAME = "chart:employer-cost"


def table_shape_name(table: ReportTable) -> str:
    return f"table:{table.key}"


@dataclass(frozen=True)
class _TablePlan:
    """Column widths, font size and row pages for one report table."""

    widths: list[float]
    font_pt: int
    header_h: float
    row_h: list[float]
    pages: list[list[int]]
    top: float


@dataclass(frozen=True)
class _TableText:
    """Slide text around a table: title, a line above it, a footnote below."""

    title: str
    intro: str | None = None
    note: str | None = None


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def render_pptx(report: ScenarioReport, output: Path) -> None:
    try:
        from pptx import Presentation
        from pptx.util import Inches
    except ImportError as exc:
        raise RuntimeError(
            "PowerPoint reports need the python-pptx package, which isn't "
            "installed. Install it with 'uv pip install python-pptx', then "
            "restart Studio."
        ) from exc
    deck = Presentation()
    deck.slide_width, deck.slide_height = Inches(SLIDE_W), Inches(SLIDE_H)
    _lead_slide(deck, report)
    for table in report_tables(report):
        text = _TableText(table.title, note=_note_text(report, table.note))
        _table_slides(deck, report, table, text)
    if any(s.available for s in report.scenarios):
        _chart_slide(deck, report)
    _tie_out_slides(deck, report)
    _notes_slide(deck, report)
    appendix = _TableText("Appendix: provenance", intro=generated_line(report))
    _table_slides(deck, report, provenance_table(report), appendix)
    if report.warnings:
        _data_notes_slide(deck, report)
    deck.save(str(output))


def _note_text(report: ScenarioReport, note: int | None) -> str | None:
    if note is None:
        return None
    return f"{note}. {report.definitions[note - 1].text}"


# --------------------------------------------------------------------------
# Slide furniture: title, rule, footer, text
# --------------------------------------------------------------------------
def _new_slide(deck: Any, report: ScenarioReport, title: str) -> Any:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    slide = deck.slides.add_slide(deck.slide_layouts[6])  # blank
    _text_block(slide, 0.35, 0.7, [(title, 26, DARK, True, False)], name="title")
    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(MARGIN),
        Inches(1.05),
        Inches(CONTENT_W),
        Inches(0.04),
    )
    rule.fill.solid()
    rule.fill.fore_color.rgb = _rgb(GREEN)
    rule.line.fill.background()
    footer = f"Traceable PlanAlign report — {trace_line(report)}"
    _text_block(slide, FOOTER_TOP, 0.3, [(footer, 8, MUTED, False, False)])
    return slide


Paragraph = tuple[str, int, str, bool, bool]
"""(text, size_pt, color, bold, bullet)."""


def _text_block(
    slide: Any,
    top: float,
    height: float,
    paragraphs: list[Paragraph],
    name: str | None = None,
) -> Any:
    from pptx.util import Inches, Pt

    box = slide.shapes.add_textbox(
        Inches(MARGIN), Inches(top), Inches(CONTENT_W), Inches(height)
    )
    if name:
        box.name = name
    frame = box.text_frame
    frame.word_wrap = True
    for index, (text, size, color, bold, bullet) in enumerate(paragraphs):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        run = paragraph.add_run()
        run.text = text
        _font(run.font, size, color, bold)
        paragraph.space_after = Pt(size * 0.5)
        if bullet:
            _bullet(paragraph)
    return box


def _bullet(paragraph: Any) -> None:
    """A real PowerPoint bullet (hanging indent), not a typed character."""
    from pptx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    p_pr.set("marL", "342900")
    p_pr.set("indent", "-228600")
    p_pr.append(p_pr.makeelement(qn("a:buFont"), {"typeface": FONT}))
    p_pr.append(p_pr.makeelement(qn("a:buChar"), {"char": "•"}))


def _font(font: Any, size: float, color: str, bold: bool = False) -> None:
    from pptx.util import Pt

    font.name = FONT
    font.size = Pt(size)
    font.bold = bold
    font.color.rgb = _rgb(color)


def _rgb(hex_color: str) -> Any:
    from pptx.dml.color import RGBColor

    return RGBColor.from_string(hex_color)


def _lead_slide(deck: Any, report: ScenarioReport) -> None:
    lead, *glance = lead_lines(report)
    paragraphs: list[Paragraph] = [(lead, 20, INK, False, False)]
    paragraphs += [(line, 16, INK, False, True) for line in glance]
    missing = missing_lines(report)
    if missing:
        paragraphs.append(("Not included (no usable result):", 14, RED, True, False))
        paragraphs += [(line, 14, RED, False, True) for line in missing]
    slide = _new_slide(deck, report, report.title)
    _text_block(slide, BODY_TOP + 0.1, BODY_BOTTOM - BODY_TOP - 0.1, paragraphs)


def _notes_slide(deck: Any, report: ScenarioReport) -> None:
    slide = _new_slide(deck, report, "Notes")
    _text_block(
        slide,
        BODY_TOP,
        BODY_BOTTOM - BODY_TOP,
        [
            (_note_text(report, i) or "", 12, INK, False, False)
            for i in range(1, len(report.definitions) + 1)
        ],
    )


def _tie_out_slides(deck: Any, report: ScenarioReport) -> None:
    """The current plan's census tie-out as a native table, before the notes.

    A gap's message follows its metric in the first cell, as on the Overview
    panel, so the planned row heights (and any continuation slide) include it.
    The source note sits where other tables put their footnote.
    """
    scenario = report.tie_out_scenario
    tie_out = scenario.census_tie_out if scenario else None
    if scenario is None or tie_out is None:
        return
    title = tie_out_title(scenario)
    if not tie_out.available:
        slide = _new_slide(deck, report, title)
        reason = tie_out.unavailable_reason or ""
        _text_block(slide, BODY_TOP, 1.0, [(reason, 14, INK, False, False)])
        return
    header, *rows = tie_out_cells(tie_out)
    for cells, row in zip(rows, tie_out.rows):
        if row.status == "gap":
            cells[0] = f"{row.label}: {row.message}"
    table = ReportTable("census-tie-out", title, header, rows)
    _table_slides(deck, report, table, _TableText(title, note=tie_out.source_note))


def _data_notes_slide(deck: Any, report: ScenarioReport) -> None:
    slide = _new_slide(deck, report, "Appendix: data notes")
    _text_block(
        slide,
        BODY_TOP,
        BODY_BOTTOM - BODY_TOP,
        [
            (w.message, 12, RED if w.severity == "error" else INK, False, True)
            for w in report.warnings
        ],
    )


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
def _table_slides(
    deck: Any,
    report: ScenarioReport,
    table: ReportTable,
    text: _TableText,
) -> None:
    """One slide per page of rows; later pages say "(continued)"."""
    plan = plan_table(table, intro=bool(text.intro), note=bool(text.note))
    for page_number, rows in enumerate(plan.pages):
        title = text.title + (" (continued)" if page_number else "")
        slide = _new_slide(deck, report, title)
        height = _add_table(slide, table, rows, plan)
        if text.intro:
            _text_block(slide, BODY_TOP, INTRO_H, [(text.intro, 12, INK, False, False)])
        if not table.rows:
            _text_block(
                slide,
                plan.top + height + 0.1,
                0.4,
                [("No results.", 12, MUTED, False, False)],
            )
        if text.note:
            _text_block(
                slide,
                BODY_BOTTOM - NOTE_H,
                NOTE_H,
                [(text.note, 9, MUTED, False, False)],
            )


def plan_table(
    table: ReportTable, intro: bool = False, note: bool = False
) -> _TablePlan:
    """Size columns to their content and split rows into slide-high pages."""
    font_pt = 11 if table.numeric else 10
    widths = _column_widths(table, font_pt)
    header_h = _row_height(table.header, widths, font_pt)
    row_h = [_row_height(row, widths, font_pt) for row in table.rows]
    top = BODY_TOP + (INTRO_H if intro else 0)
    room = BODY_BOTTOM - top - (NOTE_H + 0.1 if note else 0) - header_h
    pages: list[list[int]] = [[]]
    used = 0.0
    for index, height in enumerate(row_h):
        if pages[-1] and used + height > room:
            pages.append([])
            used = 0.0
        pages[-1].append(index)
        used += height
    return _TablePlan(widths, font_pt, header_h, row_h, pages, top)


def _text_width(text: str, font_pt: int) -> float:
    return len(text) * font_pt * CHAR_EM / 72 + 2 * CELL_PAD_X


def _column_widths(table: ReportTable, font_pt: int) -> list[float]:
    columns = list(zip(table.header, *table.rows))
    rest = len(columns) - 1
    if not table.numeric and table.key == "design":
        return [DESIGN_LABEL_W] + [(CONTENT_W - DESIGN_LABEL_W) / rest] * rest
    natural = [
        max(
            [_text_width(cell, font_pt) for cell in column[1:]]
            + [_text_width(max(column[0].split() or [""], key=len), font_pt)]
        )
        for column in columns
    ]
    if not table.numeric:  # text: stretch to the slide width in proportion
        return _fit(natural, stretch=True)
    first = min(max(natural[0], 1.0), 3.2)
    share = (CONTENT_W - first) / rest if rest else 0.0
    return _fit([first] + [max(min(share, 2.3), w) for w in natural[1:]])


def _fit(widths: list[float], stretch: bool = False) -> list[float]:
    """Shrink columns to the content width (or stretch them to it)."""
    scale = CONTENT_W / sum(widths)
    return [w * (scale if stretch else min(1.0, scale)) for w in widths]


def _wrapped_lines(text: str, width: float, font_pt: int) -> int:
    per_line = max(1, int((width - 2 * CELL_PAD_X) * 72 / (font_pt * CHAR_EM)))
    lines, used = 1, 0
    for word in text.split():
        if used and used + 1 + len(word) > per_line:
            lines, used = lines + 1, 0
        if used:
            used += 1 + len(word)
        else:  # a word longer than the line breaks across lines
            lines += (len(word) - 1) // per_line
            used = (len(word) - 1) % per_line + 1
    return lines


def _row_height(cells: list[str], widths: list[float], font_pt: int) -> float:
    lines = max(_wrapped_lines(c, w, font_pt) for c, w in zip(cells, widths))
    return lines * font_pt * LINE_SPACING / 72 + 2 * CELL_PAD_Y + 0.04


def _add_table(
    slide: Any, table: ReportTable, rows: list[int], plan: _TablePlan
) -> float:
    """Place the header plus ``rows``; return the table's height in inches."""
    from pptx.util import Inches

    height = plan.header_h + sum(plan.row_h[i] for i in rows)
    shape = slide.shapes.add_table(
        len(rows) + 1,
        len(table.header),
        Inches(MARGIN),
        Inches(plan.top),
        Inches(sum(plan.widths)),
        Inches(height),
    )
    shape.name = table_shape_name(table)
    grid = shape.table
    grid.first_row, grid.horz_banding = True, False
    for column, width in enumerate(plan.widths):
        grid.columns[column].width = Inches(width)
    grid.rows[0].height = Inches(plan.header_h)
    _fill_row(grid, 0, table.header, table, plan.font_pt, header=True)
    for position, index in enumerate(rows, 1):
        grid.rows[position].height = Inches(plan.row_h[index])
        _fill_row(grid, position, table.rows[index], table, plan.font_pt)
    return height


def _fill_row(
    grid: Any,
    position: int,
    cells: list[str],
    table: ReportTable,
    font_pt: int,
    header: bool = False,
) -> None:
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    fill = GREEN if header else (BAND if position % 2 == 0 else WHITE)
    for column, text in enumerate(cells):
        cell = grid.cell(position, column)
        cell.text = text
        cell.fill.solid()
        cell.fill.fore_color.rgb = _rgb(fill)
        cell.margin_left = cell.margin_right = Inches(CELL_PAD_X)
        cell.margin_top = cell.margin_bottom = Inches(CELL_PAD_Y)
        paragraph = cell.text_frame.paragraphs[0]
        right = table.numeric and column > 0
        paragraph.alignment = PP_ALIGN.RIGHT if right else PP_ALIGN.LEFT
        bold = header or (column == 0 and not table.numeric)
        for run in paragraph.runs:
            _font(run.font, font_pt, WHITE if header else INK, bold)


# --------------------------------------------------------------------------
# Chart
# --------------------------------------------------------------------------
def axis_number_format(largest: float) -> str:
    """Excel format for the value axis, scaled like the PDF chart's labels."""
    if largest >= 1e6:
        return '$#,##0.0,,"M"'
    if largest >= 1e4:
        return '$#,##0,"K"'
    return "$#,##0"


def _chart_slide(deck: Any, report: ScenarioReport) -> None:
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.util import Inches

    series = cost_series(report)
    data = CategoryChartData(number_format="$#,##0")
    data.categories = [neutralize_formula(str(year)) for year in report.years]
    for line in series:
        data.add_series(neutralize_formula(line.name), line.values)
    slide = _new_slide(deck, report, "Employer cost by year")
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE_MARKERS,
        Inches(MARGIN),
        Inches(BODY_TOP),
        Inches(CONTENT_W),
        Inches(BODY_BOTTOM - BODY_TOP - NOTE_H - 0.1),
        data,
    )
    frame.name = CHART_NAME
    chart = frame.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    _font(chart.font, 12, INK)
    _style_axes(chart, axis_number_format(largest_cost(series)))
    for index, line in enumerate(series):
        _style_series(chart.plots[0].series[index], index, line.is_anchor)
    note = _note_text(report, report.note("employer_cost"))
    if note:
        _text_block(
            slide, BODY_BOTTOM - NOTE_H, NOTE_H, [(note, 9, MUTED, False, False)]
        )


def _style_axes(chart: Any, number_format: str) -> None:
    value_axis = chart.value_axis
    value_axis.tick_labels.number_format = number_format
    value_axis.tick_labels.number_format_is_linked = False
    value_axis.has_major_gridlines = True
    value_axis.major_gridlines.format.line.color.rgb = _rgb("D6DED9")
    value_axis.format.line.fill.background()
    chart.category_axis.format.line.color.rgb = _rgb("9AA6A0")


def _style_series(plot_series: Any, index: int, is_anchor: bool) -> None:
    from pptx.enum.chart import XL_MARKER_STYLE
    from pptx.util import Pt

    color = _rgb(PALETTE[index % len(PALETTE)].lstrip("#"))
    plot_series.smooth = False
    plot_series.format.line.color.rgb = color
    plot_series.format.line.width = Pt(3.5 if is_anchor else 2)
    marker = plot_series.marker
    marker.style = XL_MARKER_STYLE.CIRCLE
    marker.size = 9 if is_anchor else 6
    marker.format.fill.solid()
    marker.format.fill.fore_color.rgb = color
    marker.format.line.color.rgb = color
