"""The Cost Comparison summary workbook: the page's tables as an .xlsx.

Figures arrive already derived by the page (see ``models/cost_summary.py``),
so this module only lays them out. It reads nothing but each selected run's
``run_metadata`` rows for provenance — no workforce rows.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Optional

from ..models.comparison import RunTrustResult
from ..models.cost_summary import (
    CostSummaryExportRequest,
    CostSummaryFigures,
    CostSummaryView,
    SummaryField,
)
from ..models.employer_cost import POLICY_REDUCES_EMPLOYER_COST, ForfeiturePolicy
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import (
    DatabasePathResolver,
    create_api_database_path_resolver,
)
from .run_trust import read_run_trust
from .vesting_service import SCHEDULE_INFO

MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

ColumnKind = Literal["currency", "difference", "percent", "points"]

_NUMBER_FORMATS: dict[ColumnKind, str] = {
    "currency": '"$"#,##0;-"$"#,##0',
    "difference": '+"$"#,##0;-"$"#,##0;"$"0',
    "percent": "0.00%",
    "points": '+0.00" pp";-0.00" pp";0.00" pp"',
}

POLICY_LABELS: dict[ForfeiturePolicy, str] = {
    ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS: "Offset employer contributions",
    ForfeiturePolicy.PAY_PLAN_EXPENSES: "Pay plan expenses",
    ForfeiturePolicy.REALLOCATE_TO_PARTICIPANTS: "Reallocate to participants",
}


class SummaryExportError(ValueError):
    """The request does not describe a consistent comparison."""


class StaleSummaryError(RuntimeError):
    """A scenario's selected run changed after the page loaded its figures."""


@dataclass(frozen=True)
class Column:
    field: SummaryField
    label: str
    kind: ColumnKind
    by_year: bool = True


@dataclass(frozen=True)
class SummaryScenarioSource:
    """Server-side identity of one exported scenario."""

    scenario_id: str
    name: str
    run: RunTrustResult


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class ComparisonSummaryExportService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: DatabasePathResolver | None = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    def sources(
        self,
        workspace_id: str,
        request: CostSummaryExportRequest,
        names: dict[str, str],
    ) -> list[SummaryScenarioSource]:
        """Pin each scenario to the run the page read, rejecting stale figures."""
        return [
            self._source(workspace_id, item.scenario_id, item.run_id, names)
            for item in request.scenarios
        ]

    def _source(
        self,
        workspace_id: str,
        scenario_id: str,
        loaded_run_id: Optional[str],
        names: dict[str, str],
    ) -> SummaryScenarioSource:
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        scenario = self.storage.get_scenario(workspace_id, scenario_id)
        # Same rule the scenario list uses for ``selected_result_run_id``.
        current = resolved.run_id or (scenario.last_run_id if scenario else None)
        if (
            loaded_run_id is not None
            and current is not None
            and loaded_run_id != current
        ):
            raise StaleSummaryError(
                f"{names[scenario_id]} has a newer run than the page loaded. "
                "Refresh the page and download again."
            )
        run = (
            read_run_trust(resolved.path, current)
            if resolved.path is not None
            else RunTrustResult(available=False, run_id=current)
        )
        return SummaryScenarioSource(scenario_id, names[scenario_id], run)


def validate_request(request: CostSummaryExportRequest) -> None:
    """Reject requests whose view and scenarios cannot describe one page state."""
    ids = [item.scenario_id for item in request.scenarios]
    if len(set(ids)) != len(ids):
        raise SummaryExportError("Each scenario can appear only once")
    if request.view.anchor_scenario_id not in ids:
        raise SummaryExportError("The anchor scenario must be one of the scenarios")
    view = request.view
    if view.cost_view == "net" and (
        view.vesting_schedule is None or view.forfeiture_policy is None
    ):
        raise SummaryExportError(
            "Net of forfeitures needs a vesting schedule and forfeiture policy"
        )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def summary_columns(view: CostSummaryView) -> list[Column]:
    """The columns the page shows for this view, in page order."""
    columns = [
        Column("employer_cost", "Employer cost", "currency"),
        Column("employer_cost_vs_anchor", "Difference from anchor", "difference"),
        Column("cost_pct_of_capped_pay", "Cost % of capped pay", "percent"),
        Column(
            "cost_pct_vs_anchor_pp",
            "Cost % difference from anchor",
            "points",
            by_year=False,
        ),
    ]
    if view.breakdown == "split":
        columns += [
            Column("employer_match", "Employer match", "currency"),
            Column("employer_core", "Non-elective core", "currency"),
        ]
    if view.cost_view == "net":
        columns += _net_columns(view)
    return columns + [
        Column("total_compensation", "Total compensation", "currency"),
        Column(
            "total_compensation_vs_anchor",
            "Compensation difference from anchor",
            "difference",
            by_year=False,
        ),
    ]


def _net_columns(view: CostSummaryView) -> list[Column]:
    columns = [Column("forfeiture_offset", "Forfeiture offset", "currency")]
    policy = view.forfeiture_policy
    if policy is not None and not POLICY_REDUCES_EMPLOYER_COST[policy]:
        columns.append(
            Column(
                "reallocated_to_participants", "Reallocated to participants", "currency"
            )
        )
    return columns + [
        Column("net_employer_cost", "Net employer cost", "currency"),
        Column(
            "net_employer_cost_vs_anchor",
            "Net difference from anchor",
            "difference",
            by_year=False,
        ),
    ]


def excel_value(column: Column, value: Optional[float]) -> Optional[float]:
    """Percent figures arrive in percent units; Excel stores percent as a fraction."""
    if value is None or column.kind != "percent":
        return value
    return value / 100


@dataclass
class _BlankCell:
    sheet: str
    scenario: str
    year: Optional[int]
    column: str
    reason: str


def build_summary_workbook(
    request: CostSummaryExportRequest,
    sources: list[SummaryScenarioSource],
    workspace_name: str,
    exported_at: datetime | None = None,
) -> bytes:
    """Summary, By year and Notes sheets as an .xlsx file."""
    from openpyxl import Workbook

    names = {
        source.scenario_id: _display_name(source, request.view) for source in sources
    }
    columns = summary_columns(request.view)
    blanks: list[_BlankCell] = []
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    _write_summary(summary, request, names, columns, blanks)
    _write_by_year(workbook.create_sheet("By year"), request, names, columns, blanks)
    notes = workbook.create_sheet("Notes")
    _write_notes(notes, request, sources, workspace_name, blanks, exported_at)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _display_name(source: SummaryScenarioSource, view: CostSummaryView) -> str:
    anchor = source.scenario_id == view.anchor_scenario_id
    return f"{source.name} (anchor)" if anchor else source.name


def _write_summary(
    sheet: Any,
    request: CostSummaryExportRequest,
    names: dict[str, str],
    columns: list[Column],
    blanks: list[_BlankCell],
) -> None:
    _write_header(sheet, ["Scenario", *(column.label for column in columns)])
    for row, item in enumerate(request.scenarios, start=2):
        _text(sheet.cell(row=row, column=1), names[item.scenario_id])
        context = _BlankCell("Summary", names[item.scenario_id], None, "", "")
        _write_figures(sheet, row, 2, columns, item.totals, context, blanks)
    _finish(sheet, len(columns) + 1)


def _write_by_year(
    sheet: Any,
    request: CostSummaryExportRequest,
    names: dict[str, str],
    columns: list[Column],
    blanks: list[_BlankCell],
) -> None:
    yearly = [column for column in columns if column.by_year]
    _write_header(sheet, ["Scenario", "Year", *(column.label for column in yearly)])
    row = 2
    for item in request.scenarios:
        for year in item.years:
            _text(sheet.cell(row=row, column=1), names[item.scenario_id])
            sheet.cell(row=row, column=2, value=year.year)
            context = _BlankCell("By year", names[item.scenario_id], year.year, "", "")
            _write_figures(sheet, row, 3, yearly, year, context, blanks)
            row += 1
    _finish(sheet, len(yearly) + 2)


def _write_figures(
    sheet: Any,
    row: int,
    first_column: int,
    columns: list[Column],
    figures: CostSummaryFigures,
    context: _BlankCell,
    blanks: list[_BlankCell],
) -> None:
    """Numbers get a format; blanks get a comment and a line on the Notes sheet."""
    from openpyxl.comments import Comment

    for offset, column in enumerate(columns):
        cell = sheet.cell(row=row, column=first_column + offset)
        value = excel_value(column, getattr(figures, column.field))
        if value is not None:
            cell.value = value
            cell.number_format = _NUMBER_FORMATS[column.kind]
            continue
        reason = figures.notes.get(column.field)
        if reason:
            cell.comment = Comment(reason, "PlanAlign")
            blanks.append(
                _BlankCell(
                    context.sheet, context.scenario, context.year, column.label, reason
                )
            )


# ---------------------------------------------------------------------------
# Notes sheet
# ---------------------------------------------------------------------------


def view_rows(
    view: CostSummaryView,
    workspace_name: str,
    names: dict[str, str],
    exported_at: datetime,
) -> list[tuple[str, str]]:
    """Plain-language view settings, in the order the page shows its controls."""
    rows = [
        ("Workspace", workspace_name),
        ("Exported (UTC)", exported_at.strftime("%Y-%m-%d %H:%M")),
        ("Anchor scenario", names[view.anchor_scenario_id]),
        ("Population", _cohort_label(view)),
        ("Employer cost", "Net of forfeitures" if view.cost_view == "net" else "Gross"),
        ("Match and core", "Split" if view.breakdown == "split" else "Total only"),
        ("Grandfather existing employees", _grandfather_label(view)),
    ]
    if view.vesting_schedule is not None and view.cost_view == "net":
        rows.append(("Vesting schedule", SCHEDULE_INFO[view.vesting_schedule].name))
    if view.forfeiture_policy is not None and view.cost_view == "net":
        rows.append(("Forfeiture policy", POLICY_LABELS[view.forfeiture_policy]))
    rows.append(
        (
            "Figures",
            "Annual. The page's Cumulative view is a running total of the By year sheet.",
        )
    )
    return rows


def _cohort_label(view: CostSummaryView) -> str:
    if view.cohort == "new_hires":
        start = view.first_simulation_year or "?"
        return f"Hired during the simulation ({start}+)"
    return "Starting census" if view.cohort == "baseline" else "All employees"


def _grandfather_label(view: CostSummaryView) -> str:
    if view.grandfather_cutoff_year is None:
        return "No"
    return (
        "Yes. Existing employees use the anchor design; hires in "
        f"{view.grandfather_cutoff_year} or later use each scenario's design."
    )


DEFINITIONS = (
    "Employer cost is employer match plus employer core, summed across every "
    "employee in the workforce snapshot for each simulation year.",
    "Cost % of capped pay divides employer cost by prorated pay for all employees, "
    "capped employee by employee at the IRS 401(a)(17) limit. The total row divides "
    "horizon cost by horizon capped pay; it is not an average of annual percentages.",
    "Differences from the anchor reflect every difference between the runs "
    "(workforce, pay and census as well as plan design).",
    "Forfeiture offsets apply the year after the terminations that generated them. "
    "A blank offset has no measurable basis; it is not a $0 offset.",
    "Blank cells are unavailable values, never zero. Each has a comment, listed "
    "under Blank cells below.",
)

_RUN_HEADERS = (
    "Scenario",
    "Scenario ID",
    "Run ID",
    "Run time (UTC)",
    "Config fingerprint",
    "Random seed",
    "PlanAlign version",
)


def _write_notes(
    sheet: Any,
    request: CostSummaryExportRequest,
    sources: list[SummaryScenarioSource],
    workspace_name: str,
    blanks: list[_BlankCell],
    exported_at: datetime | None,
) -> None:
    names = {source.scenario_id: source.name for source in sources}
    when = exported_at or datetime.now(timezone.utc)
    rows: list[tuple[Any, ...]] = [("View",)]
    rows += view_rows(request.view, workspace_name, names, when)
    rows += [(), ("Definitions",), *((line,) for line in DEFINITIONS)]
    rows += [(), ("Runs",), _RUN_HEADERS, *(_run_row(source) for source in sources)]
    rows += [(), ("Blank cells",), ("Sheet", "Scenario", "Year", "Column", "Reason")]
    rows += [(b.sheet, b.scenario, b.year, b.column, b.reason) for b in blanks]
    _append_rows(sheet, rows)
    sheet.column_dimensions["A"].width = 32
    for letter in "BCDEFG":
        sheet.column_dimensions[letter].width = 24


def _run_row(source: SummaryScenarioSource) -> tuple[Any, ...]:
    run = source.run
    if not run.available:
        return (source.name, source.scenario_id, run.run_id, "Run metadata unavailable")
    timestamp = run.run_timestamp
    return (
        source.name,
        source.scenario_id,
        run.run_id,
        (
            timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
            if timestamp
            else None
        ),
        run.config_fingerprint,
        run.random_seed,
        run.planalign_version,
    )


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------


_SECTION_TITLES = {"View", "Definitions", "Runs", "Blank cells"}


def _append_rows(sheet: Any, rows: Iterable[tuple[Any, ...]]) -> None:
    from openpyxl.styles import Font

    for row_number, values in enumerate(rows, start=1):
        for column_number, value in enumerate(values, start=1):
            cell = sheet.cell(row=row_number, column=column_number)
            if isinstance(value, str):
                _text(cell, value)
            else:
                cell.value = value
        if len(values) == 1 and values[0] in _SECTION_TITLES:
            sheet.cell(row=row_number, column=1).font = Font(bold=True)


def _write_header(sheet: Any, labels: list[str]) -> None:
    from openpyxl.styles import Font

    for column, label in enumerate(labels, start=1):
        cell = sheet.cell(row=1, column=column)
        _text(cell, label)
        cell.font = Font(bold=True)


def _finish(sheet: Any, width: int) -> None:
    from openpyxl.utils import get_column_letter

    sheet.freeze_panes = "B2"
    sheet.column_dimensions["A"].width = 32
    for column in range(2, width + 1):
        sheet.column_dimensions[get_column_letter(column)].width = 18


def _text(cell: Any, value: str) -> None:
    """Write text as text: a name like ``=HYPERLINK(...)`` must never become a formula."""
    cell.value = value
    cell.data_type = "s"
