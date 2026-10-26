"""Validate exported vars whose SQL consumers require specific scalar types."""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Mapping, TypedDict

from pydantic import TypeAdapter, ValidationError

from .participant_behavior import (
    BelowDefaultSettings,
    DeferralRateChangesSettings,
    EasyEnrollSettings,
)


class DbtVarProblem(TypedDict):
    section: str
    field: str
    message: str


# These are the exported vars used in SQL date casts, arithmetic, boolean
# expressions, or fixed-string branches. Optional vars are checked if present.
DATE_VARS = frozenset(
    {
        "auto_enrollment_hire_date_cutoff",
        "deferral_escalation_hire_date_cutoff",
        "plan_year_start_date",
        "plan_year_end_date",
        "simulation_effective_date",
    }
)
BOOLEAN_VARS = frozenset(
    {
        "easy_enroll_enabled",
        "enrollment_match_magnet_downward_enabled",
        "deferral_rate_changes_enabled",
        "deferral_rate_changes_aip_response_opts_out",
        "auto_enrollment_enabled",
        "deferral_escalation_enabled",
        "deferral_escalation_require_enrollment",
        "deferral_match_response_enabled",
        "deferral_match_response_downward_enabled",
        "employer_core_enabled",
        "employer_core_integration_enabled",
        "employer_match_enabled",
        "enrollment_match_magnet_enabled",
        "year_over_year_conversion_enabled",
        "core_allow_new_hires",
        "core_allow_terminated_new_hires",
        "core_allow_experienced_terminations",
        "core_require_active_eoy",
    }
)
RATE_VARS = frozenset(
    {
        "deferral_escalation_participant_elected_signup_rate",
        "easy_enroll_channel_share",
        "easy_enroll_aip_cap",
        "deferral_rate_changes_in_aip_increase_rate",
        "deferral_rate_changes_in_aip_decrease_rate",
        "deferral_rate_changes_not_in_aip_increase_rate",
        "deferral_rate_changes_not_in_aip_decrease_rate",
        "deferral_rate_changes_stop_rate",
        "deferral_rate_changes_restart_rate",
        "auto_enrollment_default_deferral_rate",
        "deferral_escalation_increment",
        "deferral_escalation_cap",
        "employer_core_contribution_rate",
        "employer_core_integration_disparity_rate",
        "employer_match_max_deferral_rate",
        "enrollment_match_magnet_probability",
        "new_hire_ineligible_pct",
        "new_hire_opt_out_rate",
        "new_hire_termination_rate",
        "part_time_new_hire_pct",
        "promotion_max_cap_pct",
        "voluntary_enrollment_rate",
        "voluntary_max_deferral_rate",
        "year_over_year_conversion_rate",
        "deferral_match_response_upward_participation_rate",
        "deferral_match_response_downward_participation_rate",
        "deferral_match_response_upward_maximize_rate",
        "deferral_match_response_downward_reduce_to_max_rate",
    }
)
RATE_PREFIXES = (
    "opt_out_rate_",
    "proactive_enrollment_rate_",
    "voluntary_enrollment_base_rates_by_age_",
    "voluntary_enrollment_deferral_rates_demographic_base_rates_",
    "year_over_year_conversion_base_rates_by_age_",
    "year_over_year_conversion_deferral_rates_",
)
INTEGER_VARS = frozenset(
    {
        "deferral_rate_changes_aip_response_window_days",
        "auto_enrollment_window_days",
        "auto_enrollment_opt_out_grace_period",
        "deferral_escalation_first_delay_years",
        "eligibility_waiting_period_days",
        "plan_eligibility_waiting_period_days",
        "proactive_enrollment_min_days",
        "proactive_enrollment_max_days",
        "simulation_start_year",
        "simulation_end_year",
        "start_year",
        "end_year",
        "minimum_age",
        "random_seed",
    }
)
ENUM_VARS = {
    "deferral_escalation_mode": frozenset({"automatic", "participant_elected"}),
    "auto_enrollment_scope": frozenset({"all_eligible_employees", "new_hires_only"}),
    "promotion_distribution_type": frozenset({"uniform", "normal"}),
    "employer_match_status": frozenset(
        {
            "deferral_based",
            "graded_by_service",
            "tenure_based",
            "tenure_graded",
            "points_based",
            "none",
        }
    ),
    "employer_core_status": frozenset(
        {"none", "flat", "graded_by_service", "points_based", "age_banded"}
    ),
    "employer_core_integration_level_mode": frozenset(
        {"ss_wage_base", "explicit", "percent_of_ss_wage_base", "fixed_dollar"}
    ),
}


# Reuse field validators so exported JSON and YAML follow the same constraints.
_LIST_MODELS = {
    "easy_enroll_packages": (EasyEnrollSettings, "packages"),
    "below_default_share_tiers": (BelowDefaultSettings, "share_tiers"),
    "below_default_step_weights": (BelowDefaultSettings, "step_weights"),
    "deferral_rate_changes_increase_steps": (
        DeferralRateChangesSettings,
        "increase_steps",
    ),
    "deferral_rate_changes_decrease_steps": (
        DeferralRateChangesSettings,
        "decrease_steps",
    ),
}


def _validate_list(field: str, value: Any) -> str | None:
    model, key = _LIST_MODELS[field]
    if not isinstance(value, list):
        return "must be a JSON-compatible list"
    try:
        TypeAdapter(model.model_fields[key].annotation).validate_python(
            value, strict=True
        )
        model.model_validate({key: value})
    except ValidationError as exc:
        return str(exc)
    return None


def _problem(field: str, message: str) -> DbtVarProblem:
    return {"section": "engine_variables", "field": field, "message": message}


def _validate_scalar(field: str, value: Any) -> str | None:
    if field in DATE_VARS:
        if not isinstance(value, str) or not value or value != value.strip():
            return "must be an ISO date (YYYY-MM-DD); omit it to use the default"
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return "must be a valid ISO date (YYYY-MM-DD)"
        if parsed.isoformat() != value:
            return "must be an ISO date (YYYY-MM-DD)"
    if field in BOOLEAN_VARS and not isinstance(value, bool):
        return "must be a boolean"
    if field in RATE_VARS or field.startswith(RATE_PREFIXES):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            return "must be a finite decimal rate between 0 and 1"
    if field in INTEGER_VARS and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ):
        return "must be a non-negative integer"
    if field in ENUM_VARS and (
        not isinstance(value, str) or value not in ENUM_VARS[field]
    ):
        return f"must be one of: {', '.join(sorted(ENUM_VARS[field]))}"
    return None


def validate_dbt_vars(variables: Mapping[str, Any]) -> list[DbtVarProblem]:
    """Return field-level problems before exported vars reach a dbt command."""
    problems = []
    for field, value in variables.items():
        message = (
            _validate_list(field, value)
            if field in _LIST_MODELS
            else _validate_scalar(field, value)
        )
        if message:
            problems.append(_problem(field, message))
    match = variables.get("employer_match")
    if isinstance(match, dict):
        eligibility = match.get("eligibility")
        if isinstance(eligibility, dict):
            for field in (
                "allow_new_hires",
                "allow_terminated_new_hires",
                "allow_experienced_terminations",
                "require_active_at_year_end",
            ):
                if field in eligibility and not isinstance(eligibility[field], bool):
                    problems.append(
                        _problem(
                            f"employer_match.eligibility.{field}", "must be a boolean"
                        )
                    )
    return problems
