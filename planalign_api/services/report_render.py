"""Render a ``ScenarioReport`` as HTML, PDF (WeasyPrint) or PPTX.

All three formats draw on the same ``report_tables``, ``lead_lines`` and
``cost_series`` (PPTX lives in ``report_pptx``), so a figure on a slide is the
same text as in the PDF. Unknown values print as a
dash, never as zero.
"""

from __future__ import annotations

import base64
import io
import math
import os
import re
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Callable

from planalign_api.models.census_tie_out import CensusTieOut, CensusTieOutRow
from planalign_api.models.report import ReportScenario, ReportYear, ScenarioReport

DASH = "—"
_DESIGN_ROWS = (
    ("Eligibility", "eligibility"),
    ("Auto-enrollment", "auto_enrollment"),
    ("Escalation", "escalation"),
    ("Employer match", "match"),
    ("Core contribution", "core"),
)
PALETTE = ("#2f7d32", "#1f5fa8", "#b0631a", "#7a3f9d", "#3f8f8f", "#9a3b3b")


@dataclass(frozen=True)
class ReportTable:
    """A titled grid of already-formatted cells."""

    key: str
    title: str
    header: list[str]
    rows: list[list[str]]
    note: int | None = None
    numeric: bool = True
    """Columns after the first hold figures (right-aligned); False for text."""


@dataclass(frozen=True)
class CostSeries:
    """One line of the employer-cost chart; ``None`` is a year without a figure."""

    name: str
    values: list[float | None]
    is_anchor: bool


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


def scenario_label(report: ScenarioReport, scenario: ReportScenario) -> str:
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
    label = scenario_label(report, scenario)
    return label if scenario.available else f"{label} (no result)"


def _design_table(report: ScenarioReport) -> ReportTable:
    rows = [
        [title] + [getattr(s.design, field, DASH) for s in report.scenarios]
        for title, field in _DESIGN_ROWS
    ]
    header = ["", *(_design_label(report, s) for s in report.scenarios)]
    if not report.is_comparison:
        header = ["", "Design"]
    return ReportTable(
        "design", "Plan designs", header, rows, report.note("design"), numeric=False
    )


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
        label = scenario_label(report, scenario)
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
    header = ["Year", *(scenario_label(report, s) for s in scenarios)]
    key = field.replace("_", "-")
    return ReportTable(key, title, header, rows, note or report.note("employer_cost"))


def trace_line(report: ScenarioReport) -> str:
    return " | ".join(
        f"{p.scenario_id} / config {p.config_fingerprint or 'unavailable'}"
        for p in report.provenance
    )


def provenance_table(report: ScenarioReport) -> ReportTable:
    """The runs behind every figure, for the appendix."""
    return ReportTable(
        "provenance",
        "Results used",
        ["Scenario", "Run", "Config", "Seed", "Run time", "Report build"],
        _provenance_rows(report),
        numeric=False,
    )


def generated_line(report: ScenarioReport) -> str:
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    return f"Generated {generated}. Each figure is traceable to the run below."


def cost_series(report: ScenarioReport) -> list[CostSeries]:
    """Employer cost by year (``report.years``), one series per usable scenario."""
    series = []
    for scenario in (s for s in report.scenarios if s.available):
        by_year = {y.year: y.employer_cost for y in scenario.years}
        series.append(
            CostSeries(
                scenario_label(report, scenario),
                [by_year.get(year) for year in report.years],
                scenario.is_anchor,
            )
        )
    return series


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


# --------------------------------------------------------------------------
# Census tie-out (the scenario marked as the current plan only)
# --------------------------------------------------------------------------
_TIE_OUT_STATUS = {"ties": "Ties", "gap": "Gap", "not_in_census": "Not in census"}


def tie_out_value(row: CensusTieOutRow, value: float | None) -> str:
    """A tie-out value as the Studio panel formats it."""
    if value is None:
        return DASH
    if row.unit == "rate":
        return f"{value * 100:.1f}%"
    whole = f"{math.floor(value + 0.5):,}"  # half up, like JavaScript Math.round
    return f"${whole}" if row.unit == "dollars" else whole


def tie_out_difference(row: CensusTieOutRow) -> str:
    """A tie-out difference as the Studio panel formats it."""
    value = row.difference
    if value is None:
        return DASH
    # The sign follows the shown figure, so a value that rounds to zero reads "+0".
    if row.unit == "rate":
        points = f"{abs(value * 100):.1f}"
        return f"{'-' if value < 0 and float(points) else '+'}{points} pts"
    whole = abs(math.floor(value + 0.5))
    sign = "-" if value < 0 and whole else "+"
    return f"{sign}{'$' if row.unit == 'dollars' else ''}{whole:,}"


def tie_out_title(scenario: ReportScenario) -> str:
    return f"Census tie-out: {scenario.name}"


def tie_out_cells(tie_out: CensusTieOut) -> list[list[str]]:
    """Header and one row per metric, as the Overview panel shows them."""
    header = [
        "Metric",
        f"Census {tie_out.census_year}",
        f"Simulated {tie_out.first_simulated_year}",
        "Difference",
        "Status",
    ]
    return [header] + [
        [
            row.label,
            tie_out_value(row, row.census_value),
            tie_out_value(row, row.simulated_value),
            tie_out_difference(row),
            _TIE_OUT_STATUS[row.status],
        ]
        for row in tie_out.rows
    ]


def _tie_out_gaps(tie_out: CensusTieOut) -> list[str]:
    return [
        f"{row.label}: {row.message}" for row in tie_out.rows if row.status == "gap"
    ]


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
        from planalign_api.services.report_pptx import render_pptx

        render_pptx(report, output)
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
_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{\{ (title|body|trace) \}\}")


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
        f"<section class='{escape(table.key)}'>"
        f"<h2>{escape(table.title)}{note}</h2>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></section>"
    )


def _html_list(items: list[str], css: str = "") -> str:
    if not items:
        return ""
    cls = f" class='{escape(css)}'" if css else ""
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
    parts.append(_html_tie_out(report))
    notes = "".join(f"<li>{escape(d.text)}</li>" for d in report.definitions)
    parts.append(f"<section class='notes'><h2>Notes</h2><ol>{notes}</ol></section>")
    parts.append(_html_appendix(report))
    return "\n".join(parts)


def _html_tie_out(report: ScenarioReport) -> str:
    scenario = report.tie_out_scenario
    if scenario is None or scenario.census_tie_out is None:
        return ""
    tie_out = scenario.census_tie_out
    heading = f"<h2>{escape(tie_out_title(scenario))}</h2>"
    if not tie_out.available:
        reason = escape(tie_out.unavailable_reason or "")
        return f"<section class='tie-out'>{heading}<p>{reason}</p></section>"
    header, *rows = tie_out_cells(tie_out)
    head = "".join(f"<th>{escape(cell)}</th>" for cell in header)
    body = "".join(
        f"<tr class='tie-{escape(row.status)}'>"
        + "".join(f"<td>{escape(cell)}</td>" for cell in cells)
        + "</tr>"
        for row, cells in zip(tie_out.rows, rows)
    )
    return (
        f"<section class='tie-out'>{heading}"
        f"<p>{escape(tie_out.source_note or '')}</p>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        f"{_html_list(_tie_out_gaps(tie_out), 'tie-out-gaps')}</section>"
    )


def _html_appendix(report: ScenarioReport) -> str:
    warnings = "".join(
        f"<li class='{escape(w.severity)}'>{escape(w.message)}</li>"
        for w in report.warnings
    )
    return (
        "<section class='appendix'><h2>Appendix: provenance</h2>"
        f"<p>{escape(generated_line(report))}</p>"
        f"{_html_table(provenance_table(report))}"
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
    replacements = {
        "title": escape(report.title),
        "body": _html_body(report),
        "trace": escape(trace_line(report)),
    }
    return _TEMPLATE_PLACEHOLDER_RE.sub(
        lambda match: replacements[match.group(1)], template
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


def largest_cost(series: list[CostSeries]) -> float:
    return max((v for s in series for v in s.values if v is not None), default=0.0)


def _cost_chart(report: ScenarioReport) -> str:
    """Employer cost by year, one line per scenario with a result."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    figure, axis = plt.subplots(figsize=(8.4, 2.8), dpi=120)
    series = cost_series(report)
    for index, line in enumerate(series):
        axis.plot(
            report.years,
            [float("nan") if v is None else v for v in line.values],
            color=PALETTE[index % len(PALETTE)],
            marker="o",
            linewidth=2.4 if line.is_anchor else 1.6,
            label=line.name,
        )
    axis.set_title("Employer cost by year", fontsize=10)
    axis.yaxis.set_major_formatter(FuncFormatter(_axis_money(largest_cost(series))))
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
  .tie-out tr.tie-gap td:last-child { color: #9a6700; font-weight: bold; }
  .tie-out-gaps li { color: #3d4a45; }
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
