"""Describe a scenario's plan design in plain words for the client report.

Reads the Studio ``dc_plan`` block and states what the engine does with it:
units and fallbacks mirror ``planalign_orchestrator.config.export`` (how each
setting reaches dbt) and the dbt macros that apply it. A setting the config
does not carry is said to be "not recorded" rather than assumed, unless the
engine applies a fixed default that is read from the engine itself, because a
wrong plan design in a client brief reads as fact.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from planalign_api.models.report import ReportPlanDesign
from planalign_orchestrator.config.permitted_disparity import (
    normalize_dc_plan_integration,
)

NOT_RECORDED = "Not recorded in this scenario's plan design."

# Defaults of the dbt vars in dbt/macros/enrollment_eligibility.sql, applied
# when neither dc_plan nor enrollment.auto_enrollment sets the value. A test
# reads the macro so these cannot drift from the engine.
ENGINE_AUTO_ENROLL_SCOPE = "all_eligible_employees"
ENGINE_AUTO_ENROLL_CUTOFF = "2020-01-01"
# export._SCOPE_MAP: the Studio value -> the engine's scope.
_SCOPES = {
    "new_hires_only": "new_hires_only",
    "all_eligible": "all_eligible_employees",
    "all_eligible_employees": "all_eligible_employees",
}

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
        auto_enrollment=_auto_enrollment(dc, config or {}),
        escalation=_escalation(dc),
        match=_match(dc),
        core=_core(dc, config or {}),
    )


def _num(value: Any) -> float | None:
    """A recorded number, or None when the setting is absent or blank."""
    if value is None or isinstance(value, bool) or value == "":
        return None
    return float(value)


def _pct(fraction: float) -> str:
    """0.035 -> '3.5%'. For rates stored as fractions."""
    return f"{round(fraction * 100, 2):g}%"


def _pct_points(percent: float) -> str:
    """3.0 -> '3%'. For rates stored as whole percentages."""
    return f"{round(percent, 2):g}%"


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


def _auto_settings(config: Config) -> Config:
    enrollment = config.get("enrollment")
    auto = (
        enrollment.get("auto_enrollment") if isinstance(enrollment, Mapping) else None
    )
    return auto if isinstance(auto, Mapping) else {}


def _auto_cutoff(dc: Config, auto: Config) -> str:
    """Hire-date cutoff as export resolves it; a blank dc_plan value removes it."""
    if "auto_enroll_hire_date_cutoff" in dc:
        cutoff = str(dc.get("auto_enroll_hire_date_cutoff") or "").strip()
    else:
        cutoff = str(auto.get("hire_date_cutoff") or "").strip()
    return cutoff or f"{ENGINE_AUTO_ENROLL_CUTOFF} (the engine default)"


def _auto_rate(dc: Config, auto: Config) -> str:
    percent = _num(dc.get("default_deferral_percent"))
    if percent is not None:
        return f" at {_pct_points(percent)} of pay"
    fraction = _num(auto.get("default_deferral_rate"))
    return f" at {_pct(fraction)} of pay" if fraction is not None else ""


def _auto_enrollment(dc: Config, config: Config) -> str:
    auto = _auto_settings(config)
    enabled = dc.get("auto_enroll", auto.get("enabled"))
    if enabled is None:
        return NOT_RECORDED
    if not enabled:
        return "No auto-enrollment; employees enroll themselves."
    raw_scope = dc.get("auto_enroll_scope") or auto.get("scope")
    scope = _SCOPES.get(str(raw_scope)) if raw_scope else ENGINE_AUTO_ENROLL_SCOPE
    if scope is None:
        return NOT_RECORDED
    cutoff = _auto_cutoff(dc, auto)
    rate = _auto_rate(dc, auto)
    if scope == "all_eligible_employees":
        return (
            f"Eligible employees hired on or after {cutoff} who are not yet "
            f"enrolled are auto-enrolled{rate} and may opt out."
        )
    return (
        f"In the first plan year, eligible employees hired on or after {cutoff} "
        f"who are not yet enrolled are auto-enrolled{rate}; after that, only "
        "each year's new hires are. Employees may opt out."
    )


def _escalation(dc: Config) -> str:
    enabled = dc.get("auto_escalation")
    if enabled is None:
        return NOT_RECORDED
    if not enabled:
        return "No automatic escalation."
    step = _num(dc.get("escalation_rate_percent"))
    cap = _num(dc.get("escalation_cap_percent"))
    rise = f"rise {_pct_points(step)} a year" if step is not None else "rise each year"
    limit = (
        f", up to {_pct_points(cap)} of pay"
        if cap is not None
        else " (cap not recorded)"
    )
    text = f"Deferrals {rise}{limit}"
    if step is None:
        text += "; the yearly increase is not recorded"
    if dc.get("escalation_mode") == "participant_elected":
        text = "Opt-in: participants who sign up " + text[len("Deferrals ") :]
    delay = int(dc.get("escalation_delay_years") or 0)
    if delay > 0:
        text += f", starting {_plural(delay, 'year')} after enrollment"
    return text + "."


# --------------------------------------------------------------------------
# Employer match
# --------------------------------------------------------------------------
def _deferral_tiers(tiers: list[Band]) -> str | None:
    """'100% of the first 3%, then 50% of the next 2% deferred'.

    Tiers reach the engine unconverted, so their rates are fractions. A tier
    missing a bound or rate is not stated at all.
    """
    parts = []
    for index, tier in enumerate(tiers):
        low, high = _num(tier.get("employee_min")), _num(tier.get("employee_max"))
        rate = _num(tier.get("match_rate"))
        if low is None or high is None or rate is None:
            return None
        word = "the first" if index == 0 else "the next"
        parts.append(f"{_pct(rate)} of {word} {_pct(high - low)}")
    return ", then ".join(parts) + " deferred"


def _deferral_match(dc: Config) -> str:
    tiers = list(dc.get("match_tiers") or [])
    text = _deferral_tiers(tiers) if tiers else None
    if text is None:
        return NOT_RECORDED
    cap = _num(dc.get("match_cap_percent"))
    if cap is None:
        return f"{text}; the cap on the match is not recorded."
    total = sum(
        float(t["match_rate"]) * (float(t["employee_max"]) - float(t["employee_min"]))
        for t in tiers
    )
    return f"{text} (up to {_pct(min(total, cap))} of pay)."


def _band_percents(band: Band) -> tuple[float, float] | None:
    """(match rate %, deferral limit %) as export converts service/points tiers.

    Mirrors ``_export_employer_match_vars``: a ``match_rate`` of 2 or less is a
    fraction (x100), otherwise a whole percent, falling back to ``rate``; a
    ``max_deferral_pct`` of 1 or less is a fraction. Absent values are not
    recorded rather than the export's fallbacks.
    """
    match_rate = _num(band.get("match_rate"))
    if match_rate is not None and match_rate <= 2:
        rate: float | None = match_rate * 100
    else:
        rate = _num(band.get("rate")) if "rate" in band else match_rate
    limit = _num(band.get("max_deferral_pct"))
    if rate is None or limit is None:
        return None
    return rate, (limit * 100 if limit <= 1 else limit)


def _banded_match(bands: list[Band], low: str, high: str, unit: str) -> str:
    parts = []
    for band in bands:
        percents = _band_percents(band)
        if percents is None:
            return NOT_RECORDED
        rate, limit = percents
        lo = band.get(low, band.get(f"min_{unit}"))
        hi = band.get(high, band.get(f"max_{unit}"))
        parts.append(
            f"{_range(lo, hi, unit)}: {_pct_points(rate)} "
            f"of up to {_pct_points(limit)} deferred"
        )
    return "; ".join(parts) + "." if parts else NOT_RECORDED


def _tenure_graded_match(dc: Config) -> str:
    bands = list(dc.get("tenure_graded_bands") or [])
    parts = []
    for band in bands:
        tiers = _deferral_tiers(list(band.get("tiers") or []))
        if tiers is None:
            return NOT_RECORDED
        years = _range(band.get("min_years"), band.get("max_years"), "years")
        parts.append(f"{years}: {tiers}")
    if not parts:
        return NOT_RECORDED
    return "By years of service. " + "; ".join(parts) + "."


def _by(prefix: str, describe: Callable[[Config], str]) -> Callable[[Config], str]:
    def wrapped(dc: Config) -> str:
        text = describe(dc)
        return text if text == NOT_RECORDED else prefix + text

    return wrapped


_MATCH_MODES: dict[str, Callable[[Config], str]] = {
    "deferral_based": _deferral_match,
    "tenure_based": _by(
        "By years of service. ",
        lambda dc: _banded_match(
            list(dc.get("tenure_match_tiers") or []), "min_years", "max_years", "years"
        ),
    ),
    # Only dc_plan.match_graded_schedule reaches the engine; a legacy
    # employer_match.graded_schedule is not exported, so it is not stated.
    "graded_by_service": _by(
        "By years of service. ",
        lambda dc: _banded_match(
            list(dc.get("match_graded_schedule") or []),
            "service_years_min",
            "service_years_max",
            "years",
        ),
    ),
    "points_based": _by(
        "By points (age plus years of service). ",
        lambda dc: _banded_match(
            list(dc.get("points_match_tiers") or []),
            "min_points",
            "max_points",
            "points",
        ),
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
    text = describe(dc)
    return text if text == NOT_RECORDED else text + _conditions(dc, "match")


# --------------------------------------------------------------------------
# Employer core (nonelective)
# --------------------------------------------------------------------------
def _core_rate(band: Band) -> float | None:
    """Percent of pay as export converts core tiers.

    ``contribution_rate`` is a fraction; a bare ``rate`` is already a percent.
    """
    fraction = _num(band.get("contribution_rate"))
    if fraction is not None:
        return fraction * 100
    return _num(band.get("rate"))


def _core_bands(bands: list[Band], low: str, high: str, unit: str) -> str:
    parts = []
    for band in bands:
        rate = _core_rate(band)
        if rate is None:
            return NOT_RECORDED
        lo = band.get(low, band.get(f"min_{unit}"))
        hi = band.get(high, band.get(f"max_{unit}"))
        parts.append(f"{_pct_points(rate)} ({_range(lo, hi, unit)})")
    return ", ".join(parts) if parts else NOT_RECORDED


_CORE_MODES: dict[str, Callable[[Config], str]] = {
    "graded_by_service": _by(
        "By years of service: ",
        lambda dc: _core_bands(
            list(dc.get("core_graded_schedule") or []),
            "service_years_min",
            "service_years_max",
            "years",
        ),
    ),
    "points_based": _by(
        "By points (age plus years of service): ",
        lambda dc: _core_bands(
            list(dc.get("core_points_schedule") or []),
            "min_points",
            "max_points",
            "points",
        ),
    ),
    "age_banded": _by(
        "By age: ",
        lambda dc: _core_bands(
            list(dc.get("core_age_schedule") or []), "min_age", "max_age", "age"
        ),
    ),
}


def _core(dc: Config, config: Config) -> str:
    if dc.get("core_enabled") is False or dc.get("core_status") == "none":
        return "No core contribution."
    status = str(dc.get("core_status") or "flat")
    describe = _CORE_MODES.get(status)
    if describe is not None:
        base = describe(dc)
    else:
        rate = _num(dc.get("core_contribution_rate_percent"))
        base = NOT_RECORDED if rate is None else f"{_pct_points(rate)} of pay"
    if base == NOT_RECORDED:
        return NOT_RECORDED
    text = base.rstrip(".") + _integration(dc, config)
    return f"{text}, whether or not the employee defers." + _conditions(dc, "core")


def _integration_settings(dc: Config, config: Config) -> dict[str, Any]:
    """Integration in the engine's decimal shape, or {} when not recorded."""
    if "core_integration_enabled" in dc:
        has_rate = (
            "core_integration_disparity_rate_percent" in dc
            or "core_integration_disparity_rate" in dc
        )
        settings = normalize_dc_plan_integration(dc)
        if not has_rate:
            settings["disparity_rate"] = None
        return settings
    raw = (config.get("employer_core_contribution") or {}).get("integration") or {}
    return {
        "enabled": raw.get("enabled"),
        "level_mode": raw.get("level_mode"),
        "level_value": raw.get("level_value"),
        "disparity_rate": _num(raw.get("disparity_rate")),
    }


def _integration(dc: Config, config: Config) -> str:
    """Social Security integration suffix, or '' when integration is off."""
    settings = _integration_settings(dc, config)
    if not settings.get("enabled"):
        return ""
    mode, value = settings.get("level_mode"), _num(settings.get("level_value"))
    level = "the Social Security wage base"
    if mode in ("percent_of_ss_wage_base", "fixed_dollar"):
        if value is None:
            level = "an integration level that is not recorded"
        elif mode == "percent_of_ss_wage_base":
            level = f"{_pct_points(value)} of the Social Security wage base"
        else:
            level = f"${value:,.0f}"
    rate = settings.get("disparity_rate")
    if rate is None:
        return f", plus an extra contribution on pay above {level} (rate not recorded)"
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
