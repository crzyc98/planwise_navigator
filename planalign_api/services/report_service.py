"""Assemble the plan-design comparison report.

Every figure is read from ``AnalyticsService.get_employer_cost_summary``, the
same by-year rows and totals ``get_dc_plan_analytics`` gives the Studio Cost
Comparison page, so report figures equal that page's default view: all
employees, gross of forfeitures, with no grandfathering. The only arithmetic
here is presentation: differences from the anchor scenario. Rendering lives in
``report_render``.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from typing import Any

import duckdb

from planalign_api.models.census_tie_out import CensusTieOut
from planalign_api.models.comparison import RunTrustResult
from planalign_api.models.report import (
    MAX_REPORT_SCENARIOS,
    ReportDefinition,
    ReportProvenance,
    ReportScenario,
    ReportWarning,
    ReportYear,
    ScenarioReport,
)
from planalign_api.models.scenario import Scenario
from planalign_api.services.analytics_service import (
    AnalyticsService,
    EmployerCostSummary,
)
from planalign_api.services.config_diff_service import ConfigDiffService
from planalign_api.services.database_path_resolver import (
    ResolvedDatabasePath,
    create_api_database_path_resolver,
    is_selected_result,
)
from planalign_api.services.census_tie_out import CensusTieOutService
from planalign_api.services.report_design import describe_plan_design
from planalign_api.services.report_render import ReportTemplateError, render_report
from planalign_api.services.run_trust import add_current_config_drift, read_run_trust
from planalign_api.storage.workspace_storage import WorkspaceStorage

__all__ = [
    "ReportAnchorError",
    "ReportNotFoundError",
    "ReportRequestError",
    "ReportTemplateError",
    "build_scenario_report",
    "render_report",
]

logger = logging.getLogger(__name__)


class ReportNotFoundError(ValueError):
    """A selected scenario does not exist, or none has a usable result."""


class ReportRequestError(ValueError):
    """The report request itself is invalid (too many scenarios)."""


class ReportAnchorError(ReportRequestError):
    """The anchor is not one of the selected scenarios."""


_MISSING_REASONS = {
    "not_run": "Not run yet.",
    "queued": "Its run has not finished.",
    "running": "Its run has not finished.",
    "failed": "Its run failed and it has no earlier successful result.",
    "cancelled": "Its run was cancelled and it has no earlier successful result.",
    "completed": "Its result database is missing.",
}
_UNREADABLE = "Its results could not be read."
_TRUST_MESSAGES = {
    "mixed_generation": "the result mixes configuration or seed generations.",
    "current_config_mismatch": "the current configuration differs from the one this result ran with.",
    "current_seed_mismatch": "the current seed differs from the one this result ran with.",
}


def build_scenario_report(
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario_id: str,
    comparison_ids: list[str] | None = None,
    anchor: str | None = None,
) -> ScenarioReport:
    """Build a report for the primary scenario plus up to five comparisons.

    ``anchor`` (ID or name) picks the scenario differences are measured
    against; it defaults to the primary scenario and must be one of the
    selected scenarios.
    """
    scenarios = _selected_scenarios(storage, workspace_id, scenario_id, comparison_ids)
    anchor_id = _resolve_anchor(anchor, scenarios)
    report = ScenarioReport(
        title=_title(scenarios),
        generated_at=datetime.now(timezone.utc),
        anchor_scenario_id=anchor_id,
    )
    for scenario in scenarios:
        section = _scenario_section(report, storage, workspace_id, scenario, anchor_id)
        if section.available and scenario.models_current_plan:
            section.census_tie_out = _census_tie_out(
                report, storage, workspace_id, scenario
            )
        report.scenarios.append(section)
    if not any(item.available for item in report.scenarios):
        missing = "; ".join(f"{s.name}: {s.missing_reason}" for s in report.scenarios)
        raise ReportNotFoundError(
            f"None of the selected scenarios has a usable result ({missing})"
        )
    _apply_anchor_differences(report)
    report.definitions = _definitions(report)
    return report


def _selected_scenarios(
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario_id: str,
    comparison_ids: list[str] | None,
) -> list[Scenario]:
    identifiers = list(dict.fromkeys([scenario_id, *(comparison_ids or [])]))
    scenarios: list[Scenario] = []
    for identifier in identifiers:
        scenario = _resolve_scenario(storage, workspace_id, identifier)
        if scenario is None:
            raise ReportNotFoundError(f"Scenario {identifier} was not found")
        if all(item.id != scenario.id for item in scenarios):
            scenarios.append(scenario)
    if len(scenarios) > MAX_REPORT_SCENARIOS:
        raise ReportRequestError(
            f"A report compares at most {MAX_REPORT_SCENARIOS} scenarios; "
            f"{len(scenarios)} were selected"
        )
    return scenarios


def _resolve_scenario(
    storage: WorkspaceStorage, workspace_id: str, identifier: str
) -> Scenario | None:
    """Accept stable IDs and human-facing scenario names in CLI workflows."""
    scenario = storage.get_scenario(workspace_id, identifier)
    if scenario is not None:
        return scenario
    return next(
        (s for s in storage.list_scenarios(workspace_id) if s.name == identifier),
        None,
    )


def _resolve_anchor(anchor: str | None, scenarios: list[Scenario]) -> str:
    if anchor is None or not anchor.strip():
        return scenarios[0].id
    for scenario in scenarios:
        if anchor.strip() in (scenario.id, scenario.name):
            return scenario.id
    names = ", ".join(s.name for s in scenarios)
    raise ReportAnchorError(
        f"Anchor {anchor!r} is not one of the selected scenarios ({names})"
    )


def _title(scenarios: list[Scenario]) -> str:
    if len(scenarios) == 1:
        return f"Plan design and employer cost: {scenarios[0].name}"
    return "Plan design comparison"


def _scenario_section(
    report: ScenarioReport,
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario: Scenario,
    anchor_id: str,
) -> ReportScenario:
    """One scenario's design and figures, all read from a single resolve.

    Figures, the design's config and provenance come from the same resolved
    database, so a run finishing mid-report cannot mix two runs.
    """
    section = ReportScenario(
        scenario_id=scenario.id, name=scenario.name, is_anchor=scenario.id == anchor_id
    )
    resolved = create_api_database_path_resolver(storage).resolve(
        workspace_id, scenario.id
    )
    current_config = storage.get_merged_config(workspace_id, scenario.id)
    if not is_selected_result(resolved, scenario.status):
        section.missing_reason = _MISSING_REASONS.get(scenario.status, _UNREADABLE)
        section.design = describe_plan_design(current_config)
        return section
    section.design = describe_plan_design(
        _design_config(report, section, storage, workspace_id, resolved)
        or current_config
    )
    summary = _read_figures(storage, workspace_id, scenario, resolved)
    if summary is None or not summary.contribution_by_year:
        section.missing_reason = _UNREADABLE
        return section
    _fill_figures(section, summary)
    if scenario.status != "completed":
        report.warnings.append(
            ReportWarning(
                code="latest_run_not_completed",
                message=f"{scenario.name}: the latest run is {scenario.status}; "
                "this report uses its last successful result.",
            )
        )
    _append_provenance(report, workspace_id, scenario, resolved, current_config)
    return section


def _census_tie_out(
    report: ScenarioReport,
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario: Scenario,
) -> CensusTieOut | None:
    """The same tie-out the Overview panel shows; a failure only adds a warning.

    Only the scenario marked as the current plan gets one (at most one per
    workspace), because a plan-design alternative differs from the census on
    purpose.
    """
    try:
        return CensusTieOutService(storage).get_tie_out(
            workspace_id, scenario.id, scenario.name
        )
    except Exception:  # the tie-out is advisory and must never block a report
        logger.exception("Census tie-out failed for scenario %s", scenario.id)
        report.warnings.append(
            ReportWarning(
                code="census_tie_out_unavailable",
                message=f"{scenario.name}: the census tie-out could not be "
                "computed for this report.",
            )
        )
        return None


def _design_config(
    report: ScenarioReport,
    section: ReportScenario,
    storage: WorkspaceStorage,
    workspace_id: str,
    resolved: ResolvedDatabasePath,
) -> dict[str, Any] | None:
    """The config archived with the resolved run: the design that actually ran.

    None when the run archived no config (a legacy result) or its config cannot
    be read; the caller then shows the current config. An unreadable archive is
    flagged on the section and in the report warnings.
    """
    if resolved.config_path is None:
        return None
    try:
        return ConfigDiffService(storage).get_effective_config(
            workspace_id, section.scenario_id, resolved=resolved
        )
    except ValueError as exc:
        logger.warning("Saved config unreadable for %s: %s", section.scenario_id, exc)
        section.design_from_current_config = True
        report.warnings.append(_saved_config_warning(section.name))
        return None


def _saved_config_warning(name: str) -> ReportWarning:
    return ReportWarning(
        code="saved_config_unreadable",
        message=f"{name}: the configuration saved with its result could not be "
        "read, so the plan design shown is the scenario's current configuration, "
        "which may differ from the one that ran.",
    )


def _read_figures(
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario: Scenario,
    resolved: ResolvedDatabasePath,
) -> EmployerCostSummary | None:
    """Employer-cost figures from the resolved database, or None if unreadable."""
    if resolved.path is None:
        return None
    try:
        return AnalyticsService(storage).get_employer_cost_summary(
            resolved.path, workspace_id, scenario.id
        )
    except (duckdb.Error, TypeError, ValueError) as exc:
        logger.warning("Report figures unreadable for %s: %s", scenario.id, exc)
        return None


def _fill_figures(section: ReportScenario, analytics: EmployerCostSummary) -> None:
    section.years = [
        ReportYear(
            year=item.year,
            employer_cost=item.total_employer_cost,
            cost_pct_of_capped_pay=(
                item.employer_cost_pct_of_capped_compensation
                if item.total_capped_compensation > 0
                else None
            ),
            participation_rate=(
                item.participation_rate if item.total_eligible_count > 0 else None
            ),
            average_deferral_rate=(
                item.average_deferral_rate * 100
                if item.total_eligible_count > 0
                else None
            ),
        )
        for item in analytics.contribution_by_year
    ]
    section.total_employer_cost = analytics.total_employer_cost
    section.total_cost_pct_of_capped_pay = (
        analytics.employer_cost_pct_of_capped_compensation
        if analytics.total_capped_compensation > 0
        else None
    )


def _apply_anchor_differences(report: ScenarioReport) -> None:
    """Employer cost minus the anchor's, per year and over the horizon."""
    anchor = report.anchor
    if not report.is_comparison:
        return
    if not anchor.available:
        report.warnings.append(
            ReportWarning(
                code="anchor_unavailable",
                message=f"{anchor.name} has no result, so differences from it "
                "cannot be shown.",
                severity="error",
            )
        )
        return
    base = {item.year: item.employer_cost for item in anchor.years}
    for scenario in report.scenarios:
        if scenario.is_anchor or not scenario.available:
            continue
        for item in scenario.years:
            item.difference_from_anchor = _difference(
                item.employer_cost, base.get(item.year)
            )
        _horizon_difference(report, scenario, anchor)


def _horizon_difference(
    report: ScenarioReport, scenario: ReportScenario, anchor: ReportScenario
) -> None:
    if [y.year for y in scenario.years] != [y.year for y in anchor.years]:
        report.warnings.append(
            ReportWarning(
                code="year_mismatch",
                message=f"{scenario.name} covers different years from "
                f"{anchor.name}, so only matching years are compared.",
            )
        )
        return
    difference = _difference(scenario.total_employer_cost, anchor.total_employer_cost)
    scenario.total_difference_from_anchor = difference
    if difference is not None and anchor.total_employer_cost:
        scenario.total_difference_pct_of_anchor = (
            difference / anchor.total_employer_cost * 100
        )


def _difference(value: float | None, base: float | None) -> float | None:
    return None if value is None or base is None else value - base


def _append_provenance(
    report: ScenarioReport,
    workspace_id: str,
    scenario: Scenario,
    resolved: ResolvedDatabasePath,
    current_config: dict[str, Any] | None,
) -> None:
    run_id = resolved.run_id or scenario.selected_result_run_id or scenario.last_run_id
    trust = add_current_config_drift(
        read_run_trust(resolved.path, run_id), current_config
    )
    report.warnings.extend(_trust_warnings(scenario.name, trust))
    report.provenance.append(
        ReportProvenance(
            workspace_id=workspace_id,
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            run_id=trust.run_id or run_id,
            config_fingerprint=trust.config_fingerprint,
            random_seed=trust.random_seed,
            run_timestamp=trust.run_timestamp,
            source_result=str(resolved.path),
            git_sha=_git_sha(),
        )
    )


def _trust_warnings(name: str, trust: RunTrustResult) -> list[ReportWarning]:
    return [
        ReportWarning(
            code=reason, message=f"{name}: {_TRUST_MESSAGES.get(reason, reason)}"
        )
        for reason in trust.reasons
    ]


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _current_design_note(report: ScenarioReport) -> str:
    names = [s.name for s in report.scenarios if s.design_from_current_config]
    if not names:
        return ""
    return (
        f" For {', '.join(names)}, the configuration saved with the result could "
        "not be read, so the current configuration is shown instead."
    )


def _definitions(report: ScenarioReport) -> list[ReportDefinition]:
    """Cost definitions, worded as on the Studio Cost Comparison page."""
    notes = [
        ReportDefinition(
            term="design",
            text="Plan designs are read from the configuration saved with each "
            "scenario's result, or the current configuration for a scenario without "
            "one. \u201cNot recorded\u201d means the setting is not in that "
            "configuration." + _current_design_note(report),
        ),
        ReportDefinition(
            term="employer_cost",
            text="Employer cost is employer match plus employer core (nonelective) "
            "contributions, summed across every employee in the workforce snapshot "
            "for each plan year. Employee deferrals and salary are not included. "
            "Figures are gross of forfeitures.",
        ),
        ReportDefinition(
            term="capped_pay",
            text="Cost as % of capped pay divides employer cost by prorated pay for "
            "all employees, including ineligible and terminated employees, capped "
            "employee by employee at the annual IRS 401(a)(17) limit. The total "
            "divides total cost by total capped pay; it is not an average of the "
            "yearly percentages.",
        ),
        ReportDefinition(
            term="participation",
            text="Participation is the share of all employees in the year's "
            "workforce snapshot, including ineligible and terminated employees, who "
            "are enrolled. Average deferral is the average deferral rate across the "
            "same employees, counting those not enrolled as 0%.",
        ),
    ]
    if report.is_comparison:
        anchor = report.anchor.name
        notes.insert(
            2,
            ReportDefinition(
                term="difference",
                text=f"Difference from {anchor} is a scenario's employer cost minus "
                f"{anchor}'s. It reflects every difference between the two runs "
                "\u2014 workforce growth, pay and census as well as plan design "
                "\u2014 so it does not isolate the effect of the design alone.",
            ),
        )
    return notes
