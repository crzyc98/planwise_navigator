"""Describe a scenario's plan design in plain words for the client report.

Reads the Studio ``dc_plan`` block, the same source the Cost Comparison page's
plan summary reads, and mirrors its wording. A setting the config does not
carry is said to be "not recorded" rather than assumed from an engine default,
because a wrong plan design in a client brief reads as fact.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from planalign_api.models.report import ReportPlanDesign

NOT_RECORDED = "Not recorded in this scenario's plan design."

Config = Mapping[str, Any]
Band = Mapping[str, Any]


def describe_plan_design(config: Config | None) -> ReportPlanDesign:
    """Plain-language eligibility, enrollment, escalation, match and core."""
    dc = (config or {}).get("dc_plan")
    if not isinstance(dc, Mapping) or not dc:
        return ReportPlanDesign(
            eligibility=NOT_RECORDED,
            auto_enrollment=NOT_RECORDED,
            escalation=NOT_RECORDED,
            match=NOT_RECORDED,
            core=NOT_RECORDED,
        )
    return ReportPlanDesign(
        eligibility=_eligibility(dc),
        auto_enrollment=_auto_enrollment(dc),
        escalation=_escalation(dc),
        match=_match(dc),
        core=_core(dc, config or {}),
    )


def _pct(fraction: Any) -> str:
    """0.035 -> '3.5%'. Rates are stored as fractions."""
    return f"{round(float(fraction or 0) * 100, 2):g}%"


def _pct_points(percent: Any) -> str:
    """3.0 -> '3%'. For settings Studio stores as whole percentages."""
    return f"{round(float(percent or 0), 2):g}%"


def _plural(count: int, unit: str) -> str:
    return f"{count} {unit}" if count == 1 else f"{count} {unit}s"


def _range(low: Any, high: Any, unit: str) -> str:
    if high is None:
        return f"{low}+ {unit}"
    return f"{low}–{high} {unit}"


# --------------------------------------------------------------------------
# Eligibility, auto-enrollment, escalation
# --------------------------------------------------------------------------
def _eligibility(dc: Config) -> str:
    months = dc.get("eligibility_months")
    if months is None:
        return NOT_RECORDED
    if int(months) == 0:
        return "Eligible to defer immediately on hire."
    return f"Eligible to defer after {_plural(int(months), 'month')} of service."


def _auto_enrollment(dc: Config) -> str:
    enabled = dc.get("auto_enroll")
    if enabled is None:
        return NOT_RECORDED
    if not enabled:
        return "No auto-enrollment; employees enroll themselves."
    rate = dc.get("default_deferral_percent")
    rate_text = f"at {_pct_points(rate)} of pay" if rate is not None else ""
    if dc.get("auto_enroll_scope") == "all_eligible":
        who = "All eligible employees, including current ones, are auto-enrolled"
    else:
        who = "New hires are auto-enrolled"
        cutoff = dc.get("auto_enroll_hire_date_cutoff")
        if cutoff:
            who = f"Employees hired on or after {cutoff} are auto-enrolled"
    return f"{who} {rate_text}".strip() + " and may opt out."


def _escalation(dc: Config) -> str:
    enabled = dc.get("auto_escalation")
    if enabled is None:
        return NOT_RECORDED
    if not enabled:
        return "No automatic escalation."
    step = _pct_points(dc.get("escalation_rate_percent"))
    cap = _pct_points(dc.get("escalation_cap_percent"))
    text = f"Deferrals rise {step} a year, up to {cap} of pay"
    if dc.get("escalation_mode") == "participant_elected":
        text = (
            f"Opt-in: participants who sign up rise {step} a year, up to {cap} of pay"
        )
    delay = int(dc.get("escalation_delay_years") or 0)
    if delay > 0:
        text += f", starting {_plural(delay, 'year')} after enrollment"
    return text + "."


# --------------------------------------------------------------------------
# Employer match
# --------------------------------------------------------------------------
def _deferral_tiers(tiers: list[Band]) -> str:
    """'100% of the first 3% deferred, then 50% of the next 2%'."""
    parts = []
    for index, tier in enumerate(tiers):
        width = float(tier.get("employee_max") or 0) - float(
            tier.get("employee_min") or 0
        )
        word = "the first" if index == 0 else "the next"
        parts.append(f"{_pct(tier.get('match_rate'))} of {word} {_pct(width)}")
    return ", then ".join(parts) + " deferred"


def _deferral_match(dc: Config) -> str:
    tiers = list(dc.get("match_tiers") or [])
    if not tiers:
        return NOT_RECORDED
    total = sum(
        float(t.get("match_rate") or 0)
        * (float(t.get("employee_max") or 0) - float(t.get("employee_min") or 0))
        for t in tiers
    )
    return f"{_deferral_tiers(tiers)} (up to {_pct(total)} of pay)."


def _banded_match(bands: list[Band], low: str, high: str, unit: str) -> str:
    if not bands:
        return NOT_RECORDED
    parts = [
        f"{_range(b.get(low), b.get(high), unit)}: {_pct(b.get('match_rate'))} "
        f"of up to {_pct(b.get('max_deferral_pct'))} deferred"
        for b in bands
    ]
    return "; ".join(parts) + "."


def _tenure_graded_match(dc: Config) -> str:
    bands = list(dc.get("tenure_graded_bands") or [])
    if not bands:
        return NOT_RECORDED
    parts = [
        f"{_range(b.get('min_years'), b.get('max_years'), 'years')}: "
        f"{_deferral_tiers(list(b.get('tiers') or []))}"
        for b in bands
    ]
    return "By years of service. " + "; ".join(parts) + "."


_MATCH_MODES: dict[str, Callable[[Config], str]] = {
    "deferral_based": _deferral_match,
    "tenure_based": lambda dc: (
        "By years of service. "
        + _banded_match(
            list(dc.get("tenure_match_tiers") or []), "min_years", "max_years", "years"
        )
    ),
    "graded_by_service": lambda dc: (
        "By years of service. "
        + _banded_match(
            list(dc.get("match_graded_schedule") or []),
            "service_years_min",
            "service_years_max",
            "years",
        )
    ),
    "points_based": lambda dc: (
        "By points (age plus years of service). "
        + _banded_match(
            list(dc.get("points_match_tiers") or []),
            "min_points",
            "max_points",
            "points",
        )
    ),
    "tenure_graded": _tenure_graded_match,
}


def _match(dc: Config) -> str:
    if dc.get("match_enabled") is False:
        return "No employer match."
    mode = str(dc.get("match_status") or "deferral_based")
    describe = _MATCH_MODES.get(mode)
    if describe is None:
        return f"{mode.replace('_', ' ').capitalize()} match."
    return describe(dc) + _conditions(dc, "match")


# --------------------------------------------------------------------------
# Employer core (nonelective)
# --------------------------------------------------------------------------
def _core_bands(bands: list[Band], low: str, high: str, unit: str) -> str:
    if not bands:
        return NOT_RECORDED
    parts = [
        f"{_pct(b.get('contribution_rate'))} ({_range(b.get(low), b.get(high), unit)})"
        for b in bands
    ]
    return ", ".join(parts)


_CORE_MODES: dict[str, Callable[[Config], str]] = {
    "graded_by_service": lambda dc: (
        "By years of service: "
        + _core_bands(
            list(dc.get("core_graded_schedule") or []),
            "service_years_min",
            "service_years_max",
            "years",
        )
    ),
    "points_based": lambda dc: (
        "By points (age plus years of service): "
        + _core_bands(
            list(dc.get("core_points_schedule") or []),
            "min_points",
            "max_points",
            "points",
        )
    ),
    "age_banded": lambda dc: (
        "By age: "
        + _core_bands(
            list(dc.get("core_age_schedule") or []), "min_age", "max_age", "age"
        )
    ),
}


def _core(dc: Config, config: Config) -> str:
    if dc.get("core_enabled") is False or dc.get("core_status") == "none":
        return "No core contribution."
    status = str(dc.get("core_status") or "flat")
    describe = _CORE_MODES.get(status)
    if describe is not None:
        base = describe(dc)
    elif dc.get("core_contribution_rate_percent") is None:
        return NOT_RECORDED
    else:
        base = f"{_pct_points(dc.get('core_contribution_rate_percent'))} of pay"
    text = base.rstrip(".") + _integration(dc, config)
    return f"{text}, whether or not the employee defers." + _conditions(dc, "core")


def _integration(dc: Config, config: Config) -> str:
    """Social Security integration suffix, or '' when integration is off."""
    if "core_integration_enabled" in dc:
        enabled = dc.get("core_integration_enabled")
        mode = dc.get("core_integration_level_mode")
        value = dc.get("core_integration_level_value")
        rate = dc.get("core_integration_disparity_rate")
    else:
        raw = (config.get("employer_core_contribution") or {}).get("integration") or {}
        enabled, mode = raw.get("enabled"), raw.get("level_mode")
        value, rate = raw.get("level_value"), raw.get("disparity_rate")
    if not enabled:
        return ""
    level = "the Social Security wage base"
    if mode == "percent_of_ss_wage_base":
        level = f"{value}% of the Social Security wage base"
    elif mode == "fixed_dollar":
        level = f"${float(value or 0):,.0f}"
    return f", plus {_pct(rate)} of pay above {level}"


def _conditions(dc: Config, prefix: str) -> str:
    """' Requires 1,000 hours and employment on the last day of the year.'"""
    needs = []
    hours = int(dc.get(f"{prefix}_min_hours_annual") or 0)
    if hours > 0:
        needs.append(f"{hours:,} hours in the year")
    tenure = int(dc.get(f"{prefix}_min_tenure_years") or 0)
    if tenure > 0:
        needs.append(f"{_plural(tenure, 'year')} of service")
    if dc.get(f"{prefix}_require_year_end_active"):
        needs.append("employment on the last day of the year")
    if not needs:
        return ""
    return " Requires " + " and ".join(needs) + "."
