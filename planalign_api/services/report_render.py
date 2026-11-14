"""Render a ``ScenarioReport`` as HTML, PDF (WeasyPrint) or PPTX.

All three formats draw on the same ``report_tables`` and ``lead_lines``, so a
figure on a slide is the same text as in the PDF. Unknown values print as a
dash, never as zero.
"""

from __future__ import annotations

import base64
import io
import os
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Callable

from planalign_api.models.report import ReportScenario, ReportYear, ScenarioReport

DASH = "—"
_DESIGN_ROWS = (
    ("Eligibility", "eligibility"),
    ("Auto-enrollment", "auto_enrollment"),
    ("Escalation", "escalation"),
    ("Employer match", "match"),
    ("Core contribution", "core"),
)
_PALETTE = ("#2f7d32", "#1f5fa8", "#b0631a", "#7a3f9d", "#3f8f8f", "#9a3b3b")


@dataclass(frozen=True)
class ReportTable:
    """A titled grid of already-formatted cells."""

    key: str
    title: str
    header: list[str]
    rows: list[list[str]]
    note: int | None = None


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def _money(value: float | None) -> str:
    return DASH if value is None else f"${value:,.0f}"


def _signed_money(value: float | None) -> str:
    if value is None:
        return DASH
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def _pct(value: float | None, digits: int = 1) -> str:
    return DASH if value is None else f"{value:.{digits}f}%"


def _signed_pct(value: float | None) -> str:
    if value is None:
        return DASH
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}{abs(value):.1f}%"


def _span(years: list[int]) -> str:
    if not years:
        return DASH
    return str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}"


def _period(report: ScenarioReport) -> str:
    return _span(report.years)


def _scenario_period(scenario: ReportScenario) -> str:
    return _span(sorted(y.year for y in scenario.years))


def _periods_differ(report: ScenarioReport) -> bool:
    """Whether the scenarios with results cover different years."""
    spans = {
        tuple(sorted(y.year for y in s.years)) for s in report.scenarios if s.available
    }
    return len(spans) > 1


def _label(report: ScenarioReport, scenario: ReportScenario) -> str:
    if report.is_comparison and scenario.is_anchor:
        return f"{scenario.name} (anchor)"
    return scenario.name


# --------------------------------------------------------------------------
# Shared content: the lead and the tables
# --------------------------------------------------------------------------
def lead_lines(report: ScenarioReport) -> list[str]:
    """The opening sentences: what is compared and what each design costs."""
    available = [s for s in report.scenarios if s.available]
    if not report.is_comparison:
        lines = [f"Employer cost of one plan design over {_period(report)}."]
    else:
        coverage = (
            ", though not every scenario covers every year"
            if _periods_differ(report)
            else ""
        )
        lines = [
            f"{len(report.scenarios)} plan designs compared over {_period(report)}"
            f"{coverage}. Differences are measured against {report.anchor.name}."
        ]
    for scenario in available:
        lines.append(_glance(report, scenario))
    return lines


def _glance(report: ScenarioReport, scenario: ReportScenario) -> str:
    total = f"{scenario.name}: {_money(scenario.total_employer_cost)} employer cost"
    if _periods_differ(report):
        total += f" over {_scenario_period(scenario)}"
    if not report.is_comparison or scenario.is_anchor:
        return (
            f"{total} ({_pct(scenario.total_cost_pct_of_capped_pay, 2)} of capped pay)."
        )
    difference = scenario.total_difference_from_anchor
    anchor = report.anchor
    if (
        difference is None
        and anchor.available
        and _scenario_period(scenario) != _scenario_period(anchor)
    ):
        return (
            f"{total}; it covers different years from {report.anchor.name}, "
            "so the totals are not compared."
        )
    if difference is None:
        return f"{total}; difference from {report.anchor.name} unavailable."
    if difference == 0:
        return f"{total}, the same as {report.anchor.name}."
    direction = "more" if difference > 0 else "less"
    share = _signed_pct(scenario.total_difference_pct_of_anchor)
    return (
        f"{total}, {_money(abs(difference))} {direction} than "
        f"{report.anchor.name} ({share})."
    )


def missing_lines(report: ScenarioReport) -> list[str]:
    return [
        f"{s.name}: {s.missing_reason}" for s in report.scenarios if not s.available
    ]


def report_tables(report: ScenarioReport) -> list[ReportTable]:
    available = [s for s in report.scenarios if s.available]
    tables = [_design_table(report), _summary_table(report, available)]
    tables.append(
        _year_table(report, available, "Employer cost by year", "employer_cost", _money)
    )
    if report.is_comparison and report.anchor.available:
        tables.append(
            _year_table(
                report,
                [s for s in available if not s.is_anchor],
                f"Difference from {report.anchor.name} by year",
                "difference_from_anchor",
                _signed_money,
                note=report.note("difference"),
            )
        )
    tables += [
        _year_table(
            report,
            available,
            "Employer cost as % of capped pay",
            "cost_pct_of_capped_pay",
            lambda v: _pct(v, 2),
            note=report.note("capped_pay"),
        ),
        _year_table(
            report,
            available,
            "Participation",
            "participation_rate",
            _pct,
            note=report.note("participation"),
        ),
        _year_table(
            report,
            available,
            "Average deferral rate",
            "average_deferral_rate",
            _pct,
            note=report.note("participation"),
        ),
    ]
    return tables


def _design_label(report: ScenarioReport, scenario: ReportScenario) -> str:
    label = _label(report, scenario)
    return label if scenario.available else f"{label} (no result)"


def _design_table(report: ScenarioReport) -> ReportTable:
    rows = [
        [title] + [getattr(s.design, field, DASH) for s in report.scenarios]
        for title, field in _DESIGN_ROWS
    ]
    header = ["", *(_design_label(report, s) for s in report.scenarios)]
    if not report.is_comparison:
        header = ["", "Design"]
    return ReportTable("design", "Plan designs", header, rows, report.note("design"))


def _summary_table(
    report: ScenarioReport, available: list[ReportScenario]
) -> ReportTable:
    """Totals per scenario over its own years.

    When scenarios cover different years each row names its period and the
    year columns say "final year", so no total reads as covering years it
    does not; differences from the anchor are blank for a mismatched period.
    """
    differ = _periods_differ(report)
    finals = {s.years[-1].year for s in available if s.years}
    last = next(iter(finals)) if len(finals) == 1 else "final year" if finals else None
    header = ["Scenario", "Total employer cost"]
    if report.is_comparison:
        header += [f"Difference from {report.anchor.name}", "Difference (%)"]
    header += [
        "% of capped pay",
        f"Participation ({last})" if last else "Participation",
        f"Average deferral ({last})" if last else "Average deferral",
    ]
    rows = []
    for scenario in available:
        final = scenario.years[-1] if scenario.years else ReportYear(year=0)
        label = _label(report, scenario)
        if differ:
            label += f" ({_scenario_period(scenario)})"
        row = [label, _money(scenario.total_employer_cost)]
        if report.is_comparison:
            row += _summary_difference(scenario)
        row += [
            _pct(scenario.total_cost_pct_of_capped_pay, 2),
            _pct(final.participation_rate),
            _pct(final.average_deferral_rate),
        ]
        rows.append(row)
    title = "Employer cost" if differ else f"Employer cost, {_period(report)}"
    return ReportTable("summary", title, header, rows, report.note("employer_cost"))


def _summary_difference(scenario: ReportScenario) -> list[str]:
    if scenario.is_anchor:
        return ["Anchor", DASH]
    return [
        _signed_money(scenario.total_difference_from_anchor),
        _signed_pct(scenario.total_difference_pct_of_anchor),
    ]


def _year_table(
    report: ScenarioReport,
    scenarios: list[ReportScenario],
    title: str,
    field: str,
    fmt: Callable[[Any], str],
    note: int | None = None,
) -> ReportTable:
    by_year = [{y.year: getattr(y, field) for y in s.years} for s in scenarios]
    rows = [
        [str(year), *(fmt(values.get(year)) for values in by_year)]
        for year in report.years
    ]
    header = ["Year", *(_label(report, s) for s in scenarios)]
    key = field.replace("_", "-")
    return ReportTable(key, title, header, rows, note or report.note("employer_cost"))


def _trace(report: ScenarioReport) -> str:
    return " | ".join(
        f"{p.scenario_id} / config {p.config_fingerprint or 'unavailable'}"
        for p in report.provenance
    )


def _provenance_rows(report: ScenarioReport) -> list[list[str]]:
    return [
        [
            p.scenario_name,
            p.run_id or DASH,
            p.config_fingerprint or DASH,
            str(p.random_seed) if p.random_seed is not None else DASH,
            p.run_timestamp.strftime("%Y-%m-%d %H:%M UTC") if p.run_timestamp else DASH,
            (p.git_sha or DASH)[:12],
        ]
        for p in report.provenance
    ]


_PROVENANCE_HEADER = ["Scenario", "Run", "Config", "Seed", "Run time", "Report build"]


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def render_report(
    report: ScenarioReport, output: Path, fmt: str, template_dir: Path | None = None
) -> Path:
    """Render HTML, PDF, or PPTX; optional render dependencies fail explicitly."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "html":
        output.write_text(render_html(report, template_dir), encoding="utf-8")
    elif fmt == "pdf":
        _write_pdf(render_html(report, template_dir), output)
    elif fmt == "pptx":
        _render_pptx(report, output)
    else:
        raise ValueError(f"Unsupported report format: {fmt}")
    return output


def _write_pdf(html: str, output: Path) -> None:
    _configure_macos_weasyprint_paths()
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "PDF reports require WeasyPrint plus its native macOS libraries. "
            "Install with 'brew install weasyprint', then restart Studio."
        ) from exc
    try:
        HTML(string=html, base_url=str(output.parent)).write_pdf(str(output))
    except (OSError, AssertionError) as exc:
        raise RuntimeError(
            "WeasyPrint could not render the report template. "
            "Restart Studio after updating PlanAlign and retry."
        ) from exc


def _configure_macos_weasyprint_paths() -> None:
    """Expose Homebrew's native libraries to WeasyPrint on macOS."""
    if sys.platform != "darwin":
        return
    candidates = [
        "/opt/homebrew/lib",
        "/opt/homebrew/opt/glib/lib",
        "/opt/homebrew/opt/pango/lib",
        "/opt/homebrew/opt/cairo/lib",
        "/usr/local/lib",
        "/usr/local/opt/glib/lib",
        "/usr/local/opt/pango/lib",
        "/usr/local/opt/cairo/lib",
    ]
    existing = [path for path in candidates if Path(path).is_dir()]
    if existing:
        current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(
            dict.fromkeys(existing + ([current] if current else []))
        )


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------
def _html_table(table: ReportTable) -> str:
    note = f"<sup>{table.note}</sup>" if table.note else ""
    head = "".join(f"<th>{escape(cell)}</th>" for cell in table.header)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
        for row in table.rows
    )
    if not table.rows:
        body = f"<tr><td colspan='{len(table.header)}'>No results.</td></tr>"
    return (
        f"<section class='{table.key}'><h2>{escape(table.title)}{note}</h2>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></section>"
    )


def _html_list(items: list[str], css: str = "") -> str:
    if not items:
        return ""
    cls = f" class='{css}'" if css else ""
    return f"<ul{cls}>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>"


def _html_body(report: ScenarioReport) -> str:
    lead, *glance = lead_lines(report)
    missing = missing_lines(report)
    parts = [f"<p class='lead'>{escape(lead)}</p>", _html_list(glance, "glance")]
    if missing:
        parts.append(
            "<div class='missing'><strong>Not included (no usable result):</strong>"
            f"{_html_list(missing)}</div>"
        )
    parts += [_html_table(table) for table in report_tables(report)]
    if any(s.available for s in report.scenarios):
        parts.append(
            f"<section class='chart'><img src='{_cost_chart(report)}' "
            "alt='Employer cost by year'/></section>"
        )
    notes = "".join(f"<li>{escape(d.text)}</li>" for d in report.definitions)
    parts.append(f"<section class='notes'><h2>Notes</h2><ol>{notes}</ol></section>")
    parts.append(_html_appendix(report))
    return "\n".join(parts)


def _html_appendix(report: ScenarioReport) -> str:
    provenance = ReportTable(
        "provenance", "Results used", _PROVENANCE_HEADER, _provenance_rows(report)
    )
    warnings = "".join(
        f"<li class='{w.severity}'>{escape(w.message)}</li>" for w in report.warnings
    )
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    return (
        "<section class='appendix'><h2>Appendix: provenance</h2>"
        f"<p>Generated {generated}. Each figure is traceable to the run below.</p>"
        f"{_html_table(provenance)}"
        + (f"<h3>Data notes</h3><ul>{warnings}</ul>" if warnings else "")
        + "</section>"
    )


class ReportTemplateError(ValueError):
    """A custom report template is missing or lacks the ``{{ body }}`` slot."""


_PLACEHOLDERS = "{{ title }}, {{ body }} and {{ trace }}"


def _template(template_dir: Path | None) -> str:
    if template_dir is None:
        return _DEFAULT_TEMPLATE
    path = template_dir / "report.html"
    try:
        template = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReportTemplateError(f"Cannot read report template {path}: {exc}") from exc
    if "{{ body }}" not in template:
        raise ReportTemplateError(
            f"Report template {path} has no {{{{ body }}}} placeholder, so it would "
            f"render without any figures. Supported placeholders: {_PLACEHOLDERS}. "
            "Templates written for {{ rows }}, {{ charts }}, {{ provenance }} or "
            "{{ warnings }} must be updated to use {{ body }}."
        )
    return template


def render_html(report: ScenarioReport, template_dir: Path | None = None) -> str:
    """Fill the template's {{ title }}, {{ body }} and {{ trace }} placeholders."""
    template = _template(template_dir)
    return (
        template.replace("{{ title }}", escape(report.title))
        .replace("{{ body }}", _html_body(report))
        .replace("{{ trace }}", escape(_trace(report)))
    )


# --------------------------------------------------------------------------
# Chart
# --------------------------------------------------------------------------
def _axis_money(largest: float) -> Callable[[float, int], str]:
    """Axis labels scaled to the data, so small plans do not read as $0.0M."""
    if largest >= 1e6:
        return lambda v, _: f"${v / 1e6:,.1f}M"
    if largest >= 1e4:
        return lambda v, _: f"${v / 1e3:,.0f}K"
    return lambda v, _: f"${v:,.0f}"


def _cost_chart(report: ScenarioReport) -> str:
    """Employer cost by year, one line per scenario with a result."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    figure, axis = plt.subplots(figsize=(8.4, 2.8), dpi=120)
    available = [s for s in report.scenarios if s.available]
    for index, scenario in enumerate(available):
        axis.plot(
            [y.year for y in scenario.years],
            [
                y.employer_cost if y.employer_cost is not None else float("nan")
                for y in scenario.years
            ],
            color=_PALETTE[index % len(_PALETTE)],
            marker="o",
            linewidth=2.4 if scenario.is_anchor else 1.6,
            label=_label(report, scenario),
        )
    axis.set_title("Employer cost by year", fontsize=10)
    costs = [y.employer_cost or 0.0 for s in available for y in s.years]
    axis.yaxis.set_major_formatter(FuncFormatter(_axis_money(max(costs, default=0.0))))
    axis.set_xticks(report.years)
    axis.grid(alpha=0.2)
    axis.legend(fontsize=8, frameon=False)
    figure.tight_layout()
    stream = io.BytesIO()
    figure.savefig(stream, format="png")
    plt.close(figure)
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode(
        "ascii"
    )


# --------------------------------------------------------------------------
# PPTX (text and image; native tables are a follow-up)
# --------------------------------------------------------------------------
def _render_pptx(report: ScenarioReport, output: Path) -> None:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise RuntimeError(
            "PowerPoint reports require the optional python-pptx dependency"
        ) from exc
    presentation = Presentation()
    missing = missing_lines(report)
    lead = lead_lines(report)
    if missing:
        lead += ["", "Not included (no usable result):", *missing]
    _text_slide(presentation, report, report.title, lead, size=16)
    for scenario in report.scenarios:
        _text_slide(
            presentation,
            report,
            f"Plan design: {_design_label(report, scenario)}",
            [
                f"{title}: {getattr(scenario.design, field, DASH)}"
                for title, field in _DESIGN_ROWS
            ],
            size=14,
        )
    for table in report_tables(report)[1:]:
        lines = [" | ".join(table.header), *(" | ".join(row) for row in table.rows)]
        _text_slide(presentation, report, table.title, lines, size=12)
    if any(s.available for s in report.scenarios):
        _chart_slide(presentation, report)
    _text_slide(
        presentation,
        report,
        "Notes",
        [f"{i}. {d.text}" for i, d in enumerate(report.definitions, 1)],
        size=11,
    )
    appendix = [" | ".join(_PROVENANCE_HEADER)]
    appendix += [" | ".join(row) for row in _provenance_rows(report)]
    appendix += [w.message for w in report.warnings]
    _text_slide(presentation, report, "Appendix: provenance", appendix, size=10)
    presentation.save(str(output))


def _text_slide(
    presentation: Any, report: ScenarioReport, title: str, lines: list[str], size: int
) -> None:
    from pptx.util import Emu, Pt

    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = title
    frame = slide.shapes.add_textbox(
        Emu(500000), Emu(1500000), Emu(8100000), Emu(5000000)
    ).text_frame
    frame.word_wrap = True
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = line
        paragraph.font.size = Pt(size)
    _add_pptx_footer(slide, report)


def _chart_slide(presentation: Any, report: ScenarioReport) -> None:
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Employer cost by year"
    raw = base64.b64decode(_cost_chart(report).split(",", 1)[1])
    slide.shapes.add_picture(io.BytesIO(raw), 400000, 1700000, width=8300000)
    _add_pptx_footer(slide, report)


def _add_pptx_footer(slide: Any, report: ScenarioReport) -> None:
    from pptx.util import Pt

    frame = slide.shapes.add_textbox(400000, 6650000, 8300000, 250000).text_frame
    frame.text = f"Traceable PlanAlign report — {_trace(report)}"
    frame.paragraphs[0].font.size = Pt(8)


_DEFAULT_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
<style>
  @page { size: letter landscape; margin: 0.45in 0.45in 0.6in; }
  body { font-family: Arial, Helvetica, sans-serif; color: #273238; font-size: 11px; }
  h1 { color: #2f7d32; border-bottom: 4px solid #2f7d32; padding-bottom: 10px; margin-bottom: 8px; }
  h2 { color: #1f3b2a; font-size: 14px; margin: 18px 0 6px; }
  h3 { font-size: 12px; margin: 12px 0 4px; }
  sup { color: #64736d; font-weight: normal; }
  .lead { font-size: 14px; margin: 6px 0; }
  .glance li { font-size: 13px; margin: 2px 0; }
  .missing { border-left: 4px solid #b42318; background: #fdf3f2; padding: 6px 12px; margin: 10px 0; }
  .missing ul { margin: 4px 0; }
  table { border-collapse: collapse; width: 100%; page-break-inside: avoid; }
  th { background: #2f7d32; color: white; font-weight: bold; }
  td, th { padding: 6px 8px; border: 1px solid #d6ded9; text-align: right; vertical-align: top; }
  td:first-child, th:first-child { text-align: left; }
  .design table { table-layout: fixed; }
  .design td, .design th { text-align: left; }
  .design td:first-child { font-weight: bold; }
  .design th:first-child { width: 14%; }
  .chart img { width: 100%; }
  .notes ol { padding-left: 18px; color: #3d4a45; }
  .appendix { page-break-before: always; }
  .appendix td { text-align: left; font-family: monospace; font-size: 10px; }
  .warning { color: #9a6700; }
  .error { color: #b42318; }
  footer { position: fixed; bottom: -0.4in; font-size: 8px; color: #64736d; }
</style>
</head>
<body>
<h1>{{ title }}</h1>
{{ body }}
<footer>Traceable PlanAlign report — {{ trace }}</footer>
</body>
</html>
"""
