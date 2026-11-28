"""Effective year on Cost Comparison (#791).

Before the effective year, every scenario other than the anchor shows the
anchor's figures; from that year on it shows its own run. The page and the
comparison exports combine runs with the rules here.

Each run still uses its own design from the first simulation year, so the
combined series is an approximation. Match and core formula changes are close
to exact: the workforce is the same under the same census and seed, and
employer cost is computed each year from that year's state. Settings that
build up history (auto-enrollment, deferral escalation, eligibility, vesting)
are not: the scenario's run has history a mid-run switch would not have yet.
``history_warnings`` names the scenarios that differ in those settings.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from ..models.analytics import (
    ContributionYearSource,
    ContributionYearSummary,
    DCPlanAnalytics,
)
from .comparison_integrity import read_run_config
from .config_diff_service import diff_configs, shown_differences
from .config_paths import matches
from .database_path_resolver import DatabasePathResolver

# Dotted config path prefixes (matched like CONFIG_GROUP_PREFIXES) for settings
# whose effect builds up over the years, with the label the warning uses.
# Studio's flat DC plan form and the engine-shaped sections are both listed.
HISTORY_DEPENDENT_PREFIXES: dict[str, str] = {
    "dc_plan.auto_enroll": "auto-enrollment",
    "dc_plan.default_deferral_percent": "auto-enrollment",
    "dc_plan.reenrollment_sweep": "auto-enrollment",
    "dc_plan.easy_enroll": "auto-enrollment",
    "enrollment.auto_enrollment": "auto-enrollment",
    "easy_enroll": "auto-enrollment",
    "dc_plan.auto_escalation": "deferral escalation",
    "dc_plan.escalation": "deferral escalation",
    "deferral_auto_escalation": "deferral escalation",
    "dc_plan.eligibility_months": "eligibility",
    "plan_eligibility": "eligibility",
    "eligibility.waiting_period_days": "eligibility",
    "setup.eligibility_waiting_period_days": "eligibility",
    "dc_plan.vesting": "vesting",
    "vesting": "vesting",
}
_LABEL_ORDER = ("auto-enrollment", "deferral escalation", "eligibility", "vesting")


def effective_year_applies(first_year: int, effective_year: Optional[int]) -> bool:
    """An effective year on or before the first simulation year changes nothing."""
    return effective_year is not None and effective_year > first_year


def combine_contribution_years(
    anchor: DCPlanAnalytics,
    scenario: DCPlanAnalytics,
    effective_year: int,
    simulated_years: Mapping[str, set[int]],
) -> tuple[list[ContributionYearSummary], list[ContributionYearSource]]:
    """The anchor's rows before ``effective_year``, the scenario's own from it on.

    A year the supplying run did not simulate is recorded as unavailable and
    has no row. A simulated year with no row (an empty cohort) stays as it is.
    """
    rows_by_source = {
        anchor.scenario_id: {row.year: row for row in anchor.contribution_by_year},
        scenario.scenario_id: {row.year: row for row in scenario.contribution_by_year},
    }
    years = sorted(
        simulated_years[anchor.scenario_id] | simulated_years[scenario.scenario_id]
    )
    rows: list[ContributionYearSummary] = []
    sources: list[ContributionYearSource] = []
    for year in years:
        source = anchor if year < effective_year else scenario
        available = year in simulated_years[source.scenario_id]
        sources.append(
            ContributionYearSource(
                year=year,
                scenario_id=source.scenario_id,
                run_id=source.run_id,
                available=available,
            )
        )
        row = rows_by_source[source.scenario_id].get(year)
        if available and row is not None:
            rows.append(row.model_copy())
    return rows, sources


def history_dependent_settings(
    anchor_config: Mapping[str, Any], scenario_config: Mapping[str, Any]
) -> list[str]:
    """Labels of the history-dependent settings that differ, in a fixed order."""
    differences, _ = diff_configs(anchor_config, scenario_config)
    found = {
        label
        for delta in shown_differences(differences)
        for prefix, label in HISTORY_DEPENDENT_PREFIXES.items()
        if matches(delta.path, prefix)
    }
    return [label for label in _LABEL_ORDER if label in found]


def history_warnings(
    resolver: DatabasePathResolver,
    workspace_id: str,
    anchor_id: str,
    names: Mapping[str, str],
    effective_year: int,
) -> list[str]:
    """One warning per scenario whose run builds history the switch would not have.

    Compares each selected run's archived config with the anchor's. A config
    that cannot be read is reported, since a difference cannot be ruled out.
    """
    anchor_config = _run_config(resolver, workspace_id, anchor_id)
    anchor_name = names[anchor_id]
    warnings: list[str] = []
    for scenario_id, name in names.items():
        if scenario_id == anchor_id:
            continue
        config = _run_config(resolver, workspace_id, scenario_id)
        if anchor_config is None or config is None:
            warnings.append(
                f"{name}'s run settings could not be compared with {anchor_name}'s, "
                f"so its figures from {effective_year} on may include participation "
                f"and vesting history that a switch in {effective_year} would not "
                "have yet."
            )
            continue
        settings = history_dependent_settings(anchor_config, config)
        if settings:
            warnings.append(
                f"{name} differs from {anchor_name} in {_join(settings)}. Its run "
                "has used that design since the first simulation year, so its "
                f"figures from {effective_year} on include participation and vesting "
                f"history that a switch in {effective_year} would not have yet. "
                "Treat them as an approximation."
            )
    return warnings


def _run_config(
    resolver: DatabasePathResolver, workspace_id: str, scenario_id: str
) -> Optional[dict[str, Any]]:
    return read_run_config(resolver.resolve(workspace_id, scenario_id).config_path)


def _join(labels: list[str]) -> str:
    if len(labels) < 3:
        return " and ".join(labels)
    return ", ".join(labels[:-1]) + f" and {labels[-1]}"
