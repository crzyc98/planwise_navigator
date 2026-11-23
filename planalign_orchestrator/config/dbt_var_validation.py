"""Validate exported vars whose SQL consumers require specific scalar or structured types."""

from __future__ import annotations

import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, TypedDict, TypeGuard, get_args

from pydantic import BaseModel, TypeAdapter, ValidationError

from .participant_behavior import (
    BelowDefaultMultipliers,
    BelowDefaultSettings,
    DeferralChangeDecreaseMultipliers,
    DeferralChangeDirectionMultipliers,
    DeferralRateChangesSettings,
    EasyEnrollSettings,
)
from .plan_design import PlanDesignParametersMap, check_identifier
from .simulation import PromotionDistributionType

# Plans may require age 21 at most, so no simulated hire is ever too young to
# be eligible. Census employees are trusted as given, whatever their age (#1040).
MIN_NEW_HIRE_AGE = 21

_JINJA_DELIMITERS = ("{{", "}}", "{%", "%}", "{#", "#}")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ACQUISITION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,31}$")
_DECIMAL_STRING_RE = re.compile(r"^\d+(?:\.\d+)?$")
_NON_NEG_INT_KEY_RE = re.compile(r"^\d+$")


class DbtVarProblem(TypedDict):
    section: str
    field: str
    message: str


# These are the exported vars used in SQL date casts, arithmetic, boolean
# expressions, or fixed-string branches. Optional vars are checked if present.
IDENTIFIER_VARS = frozenset(
    {
        "scenario_id",
        "plan_design_id",
        "parameter_scenario_id",
    }
)
DATE_VARS = frozenset(
    {
        "auto_enrollment_hire_date_cutoff",
        "census_as_of_date",
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
        "deferral_rate_changes_post_escalation_decrease_leaves_escalation",
        "auto_enrollment_enabled",
        "reenrollment_sweep_enabled",
        "reenrollment_sweep_include_non_contributors",
        "reenrollment_sweep_include_below_default",
        "reenrollment_sweep_include_below_aip_cap",
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
        "reenrollment_sweep_decline_probability",
        "deferral_escalation_participant_elected_signup_probability",
        "easy_enroll_channel_share_without_auto_enrollment",
        "easy_enroll_channel_share_with_auto_enrollment",
        "easy_enroll_escalation_cap",
        "deferral_rate_changes_with_escalation_increase_probability",
        "deferral_rate_changes_with_escalation_decrease_probability",
        "deferral_rate_changes_without_escalation_increase_probability",
        "deferral_rate_changes_without_escalation_decrease_probability",
        "deferral_rate_changes_stop_probability",
        "deferral_rate_changes_restart_probability",
        "auto_enrollment_default_deferral_rate",
        "deferral_escalation_increment",
        "deferral_escalation_cap",
        "employer_core_contribution_rate",
        "employer_core_integration_disparity_rate",
        "employer_match_max_deferral_rate",
        "enrollment_match_magnet_probability",
        "match_cap_percent",
        "new_hire_ineligible_pct",
        "new_hire_opt_out_rate",
        "opt_out_rate_target",
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
        "deferral_rate_changes_post_escalation_decrease_window_days",
        "auto_enrollment_window_days",
        "auto_enrollment_opt_out_grace_period",
        "deferral_escalation_first_delay_years",
        "eligibility_waiting_period_days",
        "plan_eligibility_waiting_period_days",
        "proactive_enrollment_min_days",
        "proactive_enrollment_max_days",
        "simulation_year",
        "simulation_start_year",
        "simulation_end_year",
        "start_year",
        "end_year",
        "minimum_age",
        "random_seed",
    }
)
ENUM_VARS = {
    "census_pay_basis": {"annual_rate", "earnings"},
    "reenrollment_sweep_method": {"enroll_at_default", "into_aip"},
    "match_template": frozenset({"simple", "tiered", "stretch", "safe_harbor", "qaca"}),
    "deferral_escalation_mode": frozenset({"automatic", "participant_elected"}),
    "auto_enrollment_scope": frozenset({"all_eligible_employees", "new_hires_only"}),
    "promotion_distribution_type": frozenset(get_args(PromotionDistributionType)),
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
_LIST_MODELS: dict[str, tuple[type[BaseModel], str]] = {
    "easy_enroll_packages": (EasyEnrollSettings, "packages"),
    "below_default_share_tiers": (BelowDefaultSettings, "share_tiers"),
    "below_default_steps": (BelowDefaultSettings, "steps"),
    "deferral_rate_changes_increase_steps": (
        DeferralRateChangesSettings,
        "increase_steps",
    ),
    "deferral_rate_changes_decrease_shares": (
        DeferralRateChangesSettings,
        "decrease_shares",
    ),
}

_LIST_MODELS["deferral_rate_changes_multipliers_decrease_rate"] = (
    DeferralChangeDecreaseMultipliers,
    "rate",
)

for _dimension in ("age", "income"):
    _LIST_MODELS[f"opt_out_multipliers_{_dimension}"] = (
        DeferralChangeDirectionMultipliers,
        _dimension,
    )
    _LIST_MODELS[f"below_default_multipliers_{_dimension}"] = (
        BelowDefaultMultipliers,
        _dimension,
    )

for _direction in ("increase", "decrease"):
    for _dimension in ("age", "income", "tenure"):
        _LIST_MODELS[f"deferral_rate_changes_multipliers_{_direction}_{_dimension}"] = (
            DeferralChangeDirectionMultipliers,
            _dimension,
        )


class _NumericRowSchema(TypedDict, total=False):
    required: frozenset[str]
    nullable: frozenset[str]
    whole: frozenset[str]
    optional_str: frozenset[str]


_NUMERIC_ROW_SCHEMAS: dict[str, _NumericRowSchema] = {
    "job_level_compensation": {
        "required": frozenset({"level", "min_compensation", "max_compensation"}),
        "whole": frozenset({"level"}),
        "optional_str": frozenset({"name"}),
    },
    "match_tiers": {
        "required": frozenset({"employee_min", "employee_max", "match_rate"}),
    },
    "tenure_match_tiers": {
        "required": frozenset({"min_years", "rate", "max_deferral_pct"}),
        "nullable": frozenset({"max_years"}),
        "whole": frozenset({"min_years", "max_years"}),
    },
    "employer_match_graded_schedule": {
        "required": frozenset({"min_years", "rate", "max_deferral_pct"}),
        "nullable": frozenset({"max_years"}),
        "whole": frozenset({"min_years", "max_years"}),
    },
    "points_match_tiers": {
        "required": frozenset({"min_points", "rate", "max_deferral_pct"}),
        "nullable": frozenset({"max_points"}),
        "whole": frozenset({"min_points", "max_points"}),
    },
    "employer_core_graded_schedule": {
        "required": frozenset({"min_years", "rate"}),
        "nullable": frozenset({"max_years"}),
    },
    "employer_core_points_schedule": {
        "required": frozenset({"min_points", "rate"}),
        "nullable": frozenset({"max_points"}),
    },
    "employer_core_age_schedule": {
        "required": frozenset({"min_age", "rate"}),
        "nullable": frozenset({"max_age"}),
    },
}

_ELIGIBILITY_BOOL_FIELDS = frozenset(
    {
        "allow_new_hires",
        "allow_terminated_new_hires",
        "allow_experienced_terminations",
        "require_active_at_year_end",
    }
)
_ELIGIBILITY_INT_FIELDS = frozenset({"minimum_tenure_years", "minimum_hours_annual"})
_ELIGIBILITY_KEYS = _ELIGIBILITY_BOOL_FIELDS | _ELIGIBILITY_INT_FIELDS

_ACQUISITION_REQUIRED = frozenset({"id", "headcount", "effective_date"})
_ACQUISITION_NUMERIC_OPTIONAL = frozenset(
    {
        "starting_participation_rate",
        "starting_deferral_rate",
        "average_pay",
        "relative_pay",
        "average_age",
        "average_service",
    }
)
_ACQUISITION_ALLOWED = (
    _ACQUISITION_REQUIRED
    | _ACQUISITION_NUMERIC_OPTIONAL
    | frozenset({"service_credit", "plan_entry"})
)

_PLAN_DESIGN_TOP_KEYS = frozenset(
    {
        "match",
        "employer_core",
        "auto_enrollment",
        "deferral_escalation",
        "eligibility",
    }
)
_PLAN_DESIGN_SECTION_KEYS: dict[str, frozenset[str]] = {
    "match": frozenset(
        {
            "family",
            "match_template",
            "cap_percent",
            "tiers",
            "graded_schedule",
            "tenure_graded_bands",
            "points_tiers",
        }
    ),
    "employer_core": frozenset(
        {
            "family",
            "contribution_rate",
            "graded_schedule",
            "age_schedule",
            "points_schedule",
            "points_min_service_years",
            "points_pre_service_rate",
            "integration_enabled",
            "integration_level_mode",
            "integration_level_value",
            "integration_disparity_rate",
        }
    ),
    "auto_enrollment": frozenset(
        {"default_deferral_rate", "window_days", "scope", "reenrollment_sweep"}
    ),
    "deferral_escalation": frozenset({"increment", "cap"}),
    "eligibility": frozenset({"waiting_period_days"}),
}
_PLAN_DESIGN_SWEEP_KEYS = frozenset(
    {
        "enabled",
        "interval_years",
        "first_year",
        "method",
        "include_non_contributors",
        "include_below_default",
        "include_below_aip_cap",
        "decline_probability",
    }
)
_PLAN_DESIGN_LIST_ITEM_KEYS: dict[str, frozenset[str]] = {
    "tiers": frozenset({"employee_min", "employee_max", "match_rate"}),
    "graded_schedule": frozenset(
        {"min_value", "max_value", "match_rate", "max_deferral_pct"}
    ),
    "points_tiers": frozenset(
        {"min_value", "max_value", "match_rate", "max_deferral_pct"}
    ),
    "tenure_graded_bands": frozenset({"min_years", "max_years", "tiers"}),
    "core_graded_schedule": frozenset({"min_years", "max_years", "rate"}),
    "core_age_schedule": frozenset({"min_age", "max_age", "rate"}),
    "core_points_schedule": frozenset({"min_points", "max_points", "rate"}),
}


def _problem(field: str, message: str) -> DbtVarProblem:
    return {"section": "engine_variables", "field": field, "message": message}


def _is_finite_number(value: Any) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_whole_number(value: Any) -> TypeGuard[int | float]:
    return _is_finite_number(value) and value == int(value)


def _is_strict_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _parse_decimal_like(value: Any) -> Decimal | None:
    if _is_finite_number(value):
        return Decimal(str(value))
    if isinstance(value, str) and _DECIMAL_STRING_RE.fullmatch(value):
        try:
            parsed = Decimal(value)
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None
    return None


def _has_nonfinite_number(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_has_nonfinite_number(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_nonfinite_number(item) for item in value)
    return False


def _check_jinja_delimiters(
    value: Any, path: str, problems: list[DbtVarProblem]
) -> None:
    if isinstance(value, str):
        if any(token in value for token in _JINJA_DELIMITERS):
            problems.append(
                _problem(
                    path,
                    "must not contain template delimiters ({{, }}, {%, %}, {#, #})",
                )
            )
    elif isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and any(
                token in key for token in _JINJA_DELIMITERS
            ):
                problems.append(
                    _problem(
                        child,
                        "must not contain template delimiters ({{, }}, {%, %}, {#, #})",
                    )
                )
            _check_jinja_delimiters(item, child, problems)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _check_jinja_delimiters(item, f"{path}[{idx}]", problems)


def _check_keys(
    item: Mapping[str, Any], required: frozenset[str], allowed: frozenset[str]
) -> str | None:
    keys = set(item.keys())
    extra = sorted(str(k) for k in keys - allowed)
    if extra:
        return f"unexpected keys: {', '.join(extra)}"
    missing = sorted(str(k) for k in required - keys)
    if missing:
        return f"missing required keys: {', '.join(missing)}"
    return None


def _validate_numeric_row(item: Any, idx: int, schema: _NumericRowSchema) -> str | None:
    if not isinstance(item, Mapping):
        return f"entry {idx} must be an object"
    required = schema.get("required", frozenset())
    nullable = schema.get("nullable", frozenset())
    whole = schema.get("whole", frozenset())
    optional_str = schema.get("optional_str", frozenset())
    key_err = _check_keys(item, required, required | nullable | optional_str)
    if key_err:
        return f"entry {idx} has {key_err}"
    for key, val in item.items():
        if key in optional_str:
            if val is not None and not isinstance(val, str):
                return f"entry {idx}.{key} must be a string or null"
        elif key in nullable and val is None:
            continue
        elif key in whole:
            if not _is_whole_number(val):
                return f"entry {idx}.{key} must be a finite whole number"
        elif not _is_finite_number(val):
            return f"entry {idx}.{key} must be a finite number"
    return None


def _validate_numeric_rows(value: Any, schema: _NumericRowSchema) -> str | None:
    if not isinstance(value, list):
        return "must be a list"
    for idx, item in enumerate(value):
        problem = _validate_numeric_row(item, idx, schema)
        if problem:
            return problem
    return None


def _validate_tenure_graded_bands(value: Any) -> str | None:
    if not isinstance(value, list):
        return "must be a list"
    required = frozenset({"min_years", "tiers"})
    allowed = frozenset({"min_years", "max_years", "tiers"})
    tier_schema = _NUMERIC_ROW_SCHEMAS["match_tiers"]
    for idx, band in enumerate(value):
        if not isinstance(band, Mapping):
            return f"band {idx} must be an object"
        key_err = _check_keys(band, required, allowed)
        if key_err:
            return f"band {idx} has {key_err}"
        if not _is_whole_number(band["min_years"]):
            return f"band {idx}.min_years must be a finite whole number"
        max_years = band.get("max_years")
        if max_years is not None and not _is_whole_number(max_years):
            return f"band {idx}.max_years must be a finite whole number or null"
        tiers_err = _validate_numeric_rows(band["tiers"], tier_schema)
        if tiers_err:
            return f"band {idx}.tiers: {tiers_err}"
    return None


def _validate_promotion_level_overrides(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return "must be a mapping of job level to finite number"
    for key, rate in value.items():
        valid_key = (_is_strict_int(key) and key >= 0) or (
            isinstance(key, str) and bool(_NON_NEG_INT_KEY_RE.fullmatch(key))
        )
        if not valid_key:
            return f"level key {key!r} must be a non-negative integer"
        if not _is_finite_number(rate):
            return f"override for level {key!r} must be a finite number"
    return None


def _validate_promotion_market_adjustments(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return "must be a mapping of market label to finite number"
    for key, factor in value.items():
        if not isinstance(key, str) or not key:
            return f"market adjustment key {key!r} must be a non-empty string"
        if not _is_finite_number(factor):
            return f"market adjustment for {key!r} must be a finite number"
    return None


def _validate_minimum_wage_steps(value: Any) -> str | None:
    if not isinstance(value, list):
        return "must be a list"
    required = frozenset({"hourly_rate", "effective_date"})
    for idx, item in enumerate(value):
        if not isinstance(item, Mapping):
            return f"step {idx} must be an object"
        key_err = _check_keys(item, required, required)
        if key_err:
            return f"step {idx} has {key_err}"
        if not _is_finite_number(item["hourly_rate"]) or item["hourly_rate"] <= 0:
            return f"step {idx}.hourly_rate must be a finite number greater than 0"
        if not _is_iso_date(item["effective_date"]):
            return f"step {idx}.effective_date must be an ISO date (YYYY-MM-DD)"
    return None


def _validate_acquisition_item(item: Any, idx: int) -> str | None:
    if not isinstance(item, Mapping):
        return f"entry {idx} must be an object"
    key_err = _check_keys(item, _ACQUISITION_REQUIRED, _ACQUISITION_ALLOWED)
    if key_err:
        return f"entry {idx} has {key_err}"
    acq_id = item["id"]
    if not isinstance(acq_id, str) or not _ACQUISITION_ID_RE.fullmatch(acq_id):
        return f"entry {idx}.id must match ^[A-Za-z0-9][A-Za-z0-9-]{{0,31}}$"
    if not _is_strict_int(item["headcount"]) or item["headcount"] <= 0:
        return f"entry {idx}.headcount must be a positive integer"
    if not _is_iso_date(item["effective_date"]):
        return f"entry {idx}.effective_date must be an ISO date (YYYY-MM-DD)"
    if "service_credit" in item and item["service_credit"] not in {
        "prior_service",
        "acquisition_date",
    }:
        return f"entry {idx}.service_credit must be prior_service or acquisition_date"
    if "plan_entry" in item and item["plan_entry"] not in {
        "acquisition_date",
        "waiting_period",
    }:
        return f"entry {idx}.plan_entry must be acquisition_date or waiting_period"
    for key in _ACQUISITION_NUMERIC_OPTIONAL:
        if key in item and item[key] is not None and not _is_finite_number(item[key]):
            return f"entry {idx}.{key} must be a finite number"
    return None


def _validate_acquisitions(value: Any) -> str | None:
    if not isinstance(value, list):
        return "must be a list"
    for idx, item in enumerate(value):
        problem = _validate_acquisition_item(item, idx)
        if problem:
            return problem
    return None


def _validate_plan_design_assignment(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return "must be an object"
    key_err = _check_keys(
        value,
        frozenset({"default_plan_design_id"}),
        frozenset({"default_plan_design_id", "rules"}),
    )
    if key_err:
        return key_err
    id_err = _identifier_problem(value["default_plan_design_id"])
    if id_err:
        return f"default_plan_design_id {id_err}"
    rules = value.get("rules", [])
    if not isinstance(rules, list):
        return "rules must be a list"
    for idx, rule in enumerate(rules):
        if not isinstance(rule, Mapping):
            return f"rules[{idx}] must be an object"
        rule_err = _check_keys(
            rule,
            frozenset({"cutoff", "plan_design_id"}),
            frozenset({"type", "cutoff", "plan_design_id"}),
        )
        if rule_err:
            return f"rules[{idx}] has {rule_err}"
        if "type" in rule and rule["type"] != "hire_date_cutoff":
            return f"rules[{idx}].type must be hire_date_cutoff"
        if not _is_iso_date(rule["cutoff"]):
            return f"rules[{idx}].cutoff must be an ISO date (YYYY-MM-DD)"
        rule_id_err = _identifier_problem(rule["plan_design_id"])
        if rule_id_err:
            return f"rules[{idx}].plan_design_id {rule_id_err}"
    return None


def _check_plan_design_nested_keys(design_id: str, params: Any) -> str | None:
    if not isinstance(params, Mapping):
        return f"{design_id} must be an object"
    top_err = _check_keys(params, _PLAN_DESIGN_TOP_KEYS, _PLAN_DESIGN_TOP_KEYS)
    if top_err:
        return f"{design_id} has {top_err}"
    for section, allowed in _PLAN_DESIGN_SECTION_KEYS.items():
        body = params[section]
        if not isinstance(body, Mapping):
            return f"{design_id}.{section} must be an object"
        sec_err = _check_keys(body, frozenset(), allowed)
        if sec_err:
            return f"{design_id}.{section} has {sec_err}"
    return _check_plan_design_list_keys(design_id, params)


def _check_mapping_list_keys(
    path: str, items: Any, allowed: frozenset[str]
) -> str | None:
    if not isinstance(items, list):
        return None
    for idx, item in enumerate(items):
        if not isinstance(item, Mapping):
            return f"{path}[{idx}] must be an object"
        item_err = _check_keys(item, frozenset(), allowed)
        if item_err:
            return f"{path}[{idx}] has {item_err}"
    return None


def _check_plan_design_list_keys(
    design_id: str, params: Mapping[str, Any]
) -> str | None:
    sweep = params["auto_enrollment"].get("reenrollment_sweep")
    if isinstance(sweep, Mapping):
        sweep_err = _check_keys(sweep, frozenset(), _PLAN_DESIGN_SWEEP_KEYS)
        if sweep_err:
            return f"{design_id}.auto_enrollment.reenrollment_sweep has {sweep_err}"
    checks = (
        ("match", "tiers", "tiers"),
        ("match", "graded_schedule", "graded_schedule"),
        ("match", "points_tiers", "points_tiers"),
        ("match", "tenure_graded_bands", "tenure_graded_bands"),
        ("employer_core", "graded_schedule", "core_graded_schedule"),
        ("employer_core", "age_schedule", "core_age_schedule"),
        ("employer_core", "points_schedule", "core_points_schedule"),
    )
    for section, field, schema_name in checks:
        path = f"{design_id}.{section}.{field}"
        items = params[section].get(field)
        list_err = _check_mapping_list_keys(
            path, items, _PLAN_DESIGN_LIST_ITEM_KEYS[schema_name]
        )
        if list_err:
            return list_err
    bands = params["match"].get("tenure_graded_bands")
    if isinstance(bands, list):
        for idx, band in enumerate(bands):
            tier_err = _check_mapping_list_keys(
                f"{design_id}.match.tenure_graded_bands[{idx}].tiers",
                band.get("tiers"),
                _PLAN_DESIGN_LIST_ITEM_KEYS["tiers"],
            )
            if tier_err:
                return tier_err
    return None


def _validate_plan_design_parameters(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return "must be a mapping of plan design parameters"
    if _has_nonfinite_number(value):
        return "must not contain non-finite numbers"
    for design_id, params in value.items():
        if not isinstance(design_id, str):
            return "design identifiers must be strings"
        key_err = _check_plan_design_nested_keys(design_id, params)
        if key_err:
            return key_err
    try:
        PlanDesignParametersMap.model_validate(value, strict=True)
    except ValidationError as exc:
        return str(exc)
    return None


def _validate_projected_thresholds(value: Any) -> str | None:
    if not isinstance(value, list):
        return "projected_thresholds must be a list"
    required = frozenset({"year", "threshold", "provenance"})
    for idx, item in enumerate(value):
        if not isinstance(item, Mapping):
            return f"projected_thresholds[{idx}] must be an object"
        key_err = _check_keys(item, required, required)
        if key_err:
            return f"projected_thresholds[{idx}] has {key_err}"
        if not _is_strict_int(item["year"]):
            return f"projected_thresholds[{idx}].year must be an integer"
        threshold = _parse_decimal_like(item["threshold"])
        if threshold is None or threshold <= 0:
            return f"projected_thresholds[{idx}].threshold must be a positive finite number"
        if not isinstance(item["provenance"], str) or not item["provenance"]:
            return f"projected_thresholds[{idx}].provenance must be a non-empty string"
    return None


def _validate_contribution_sources(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return "must be an object"
    allowed = frozenset(
        {
            "policy",
            "roth_fraction",
            "roth_available",
            "mandatory_roth_enabled",
            "applicability",
            "employer_id",
            "projected_thresholds",
        }
    )
    key_err = _check_keys(value, frozenset(), allowed)
    if key_err:
        return key_err
    if "policy" in value and value["policy"] not in {
        "legacy_estimate",
        "assumed_split",
    }:
        return "policy must be legacy_estimate or assumed_split"
    if "applicability" in value and value["applicability"] not in {
        "single_employer_401k",
        "unsupported",
    }:
        return "applicability must be single_employer_401k or unsupported"
    for flag in ("roth_available", "mandatory_roth_enabled"):
        if flag in value and not isinstance(value[flag], bool):
            return f"{flag} must be a boolean"
    if "roth_fraction" in value:
        frac = _parse_decimal_like(value["roth_fraction"])
        if frac is None or not (Decimal("0") <= frac <= Decimal("1")):
            return "roth_fraction must be a finite decimal between 0 and 1"
    if "employer_id" in value and value["employer_id"] is not None:
        if not isinstance(value["employer_id"], str):
            return "employer_id must be a string or null"
    if "projected_thresholds" in value:
        return _validate_projected_thresholds(value["projected_thresholds"])
    return None


def _validate_list(field: str, value: Any) -> str | None:
    model, key = _LIST_MODELS[field]
    if not isinstance(value, list):
        return "must be a JSON-compatible list"
    annotation = model.model_fields[key].annotation
    if annotation is None:
        raise TypeError(f"{model.__name__}.{key} has no type annotation")
    try:
        TypeAdapter(annotation).validate_python(value, strict=True)
        model.model_validate({key: value})
    except ValidationError as exc:
        return str(exc)
    return None


def _hire_age_problem(age: Any) -> str | None:
    if not isinstance(age, (int, float)) or isinstance(age, bool):
        return "each entry needs a numeric age"
    if not math.isfinite(age) or age != int(age):
        return "new-hire ages must be whole numbers"
    if not MIN_NEW_HIRE_AGE <= age <= 100:
        return f"new-hire ages must be {MIN_NEW_HIRE_AGE}-100"
    return None


def new_hire_age_problem(value: Any) -> str | None:
    """Check a new-hire age distribution; shared by config and calibration."""
    if not isinstance(value, list):
        return "must be a JSON-compatible list"
    weights = []
    allowed = frozenset({"age", "weight"})
    for item in value:
        if not isinstance(item, Mapping):
            return "each entry must be an {age, weight} object"
        extra = sorted(str(k) for k in set(item.keys()) - allowed)
        if extra:
            return f"unexpected keys in entry: {', '.join(extra)}"
        problem = _hire_age_problem(item.get("age"))
        if problem:
            return problem
        weight = item.get("weight")
        if not _is_finite_number(weight) or weight < 0:
            return "new-hire age weights must be finite and >= 0"
        weights.append(weight)
    if sum(weights) <= 0:
        return "new-hire age weights must sum to a positive value"
    return None


def _identifier_problem(value: Any) -> str | None:
    if not isinstance(value, str):
        return "must be a valid identifier string"
    try:
        check_identifier(value)
    except ValueError as exc:
        return str(exc)
    return None


def _census_path_problem(value: Any) -> str | None:
    if not isinstance(value, str) or "'" in value:
        return "must be a path without a single quote"
    return None


def _month_day_problem(value: Any) -> str | None:
    message = "must be a month and day (MM-DD)"
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}-\d{2}", value):
        return message
    try:
        date.fromisoformat(f"2000-{value}")
    except ValueError:
        return message
    return None


def _date_problem(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return "must be an ISO date (YYYY-MM-DD); omit it to use the default"
    if not _is_iso_date(value):
        return "must be a valid ISO date (YYYY-MM-DD)"
    return None


_STRUCTURED_VALIDATORS: dict[str, Callable[[Any], str | None]] = {
    "tenure_graded_bands": _validate_tenure_graded_bands,
    "promotion_level_overrides": _validate_promotion_level_overrides,
    "promotion_market_adjustments": _validate_promotion_market_adjustments,
    "minimum_wage_steps": _validate_minimum_wage_steps,
    "acquisitions": _validate_acquisitions,
    "plan_design_assignment": _validate_plan_design_assignment,
    "plan_design_parameters": _validate_plan_design_parameters,
    "contribution_sources": _validate_contribution_sources,
}


def _validate_scalar(field: str, value: Any) -> str | None:
    if field in IDENTIFIER_VARS:
        return _identifier_problem(value)
    if field == "census_parquet_path":
        return _census_path_problem(value)
    if field == "new_hire_age_distribution":
        return new_hire_age_problem(value)
    if field in {"minimum_age", "plan_eligibility_minimum_age"} and (
        _is_strict_int(value) and value > MIN_NEW_HIRE_AGE
    ):
        return f"a plan's minimum age can't exceed {MIN_NEW_HIRE_AGE}"
    if field in {"reenrollment_sweep_interval_years", "reenrollment_sweep_first_year"}:
        if field == "reenrollment_sweep_first_year" and value is None:
            return None
        if not _is_strict_int(value):
            return "must be an integer"
        if field == "reenrollment_sweep_interval_years" and value < 1:
            return "must be at least 1"
    if field in DATE_VARS:
        return _date_problem(value)
    if field == "deferral_escalation_effective_mmdd":
        return _month_day_problem(value)
    if field in BOOLEAN_VARS and not isinstance(value, bool):
        return "must be a boolean"
    if field in RATE_VARS or field.startswith(RATE_PREFIXES):
        if not _is_finite_number(value) or not 0 <= value <= 1:
            return "must be a finite decimal rate between 0 and 1"
    if field in INTEGER_VARS and (not _is_strict_int(value) or value < 0):
        return "must be a non-negative integer"
    if field in ENUM_VARS and (
        not isinstance(value, str) or value not in ENUM_VARS[field]
    ):
        return f"must be one of: {', '.join(sorted(ENUM_VARS[field]))}"
    return None


def _validate_eligibility_block(
    prefix: str, eligibility: Any, problems: list[DbtVarProblem]
) -> None:
    if not isinstance(eligibility, Mapping):
        problems.append(_problem(prefix, "must be an object"))
        return
    key_err = _check_keys(eligibility, frozenset(), _ELIGIBILITY_KEYS)
    if key_err:
        problems.append(_problem(prefix, key_err))
    for field in _ELIGIBILITY_BOOL_FIELDS:
        if field in eligibility and not isinstance(eligibility[field], bool):
            problems.append(_problem(f"{prefix}.{field}", "must be a boolean"))
    for field in _ELIGIBILITY_INT_FIELDS:
        if field in eligibility and (
            not _is_whole_number(eligibility[field]) or eligibility[field] < 0
        ):
            problems.append(
                _problem(f"{prefix}.{field}", "must be a non-negative integer")
            )


def _validate_employer_match_dict(value: Any, problems: list[DbtVarProblem]) -> None:
    if not isinstance(value, Mapping):
        problems.append(_problem("employer_match", "must be an object"))
        return
    key_err = _check_keys(
        value, frozenset(), frozenset({"apply_eligibility", "eligibility"})
    )
    if key_err:
        problems.append(_problem("employer_match", key_err))
    if "apply_eligibility" in value and not isinstance(
        value["apply_eligibility"], bool
    ):
        problems.append(
            _problem("employer_match.apply_eligibility", "must be a boolean")
        )
    if "eligibility" in value:
        _validate_eligibility_block(
            "employer_match.eligibility", value["eligibility"], problems
        )


def _validate_core_schedule_entries(
    value: Any, allowed_keys: frozenset[str], nullable_keys: frozenset[str]
) -> str | None:
    if not isinstance(value, list):
        return "must be a list"
    for idx, item in enumerate(value):
        if not isinstance(item, Mapping):
            return f"entry {idx} must be an object"
        key_err = _check_keys(item, frozenset(), allowed_keys)
        if key_err:
            return f"entry {idx} has {key_err}"
        for key, val in item.items():
            if key in nullable_keys and val is None:
                continue
            if not _is_finite_number(val):
                return f"entry {idx}.{key} must be a finite number"
    return None


def _validate_core_integration_dict(value: Any, problems: list[DbtVarProblem]) -> None:
    prefix = "employer_core_contribution.integration"
    if not isinstance(value, Mapping):
        problems.append(_problem(prefix, "must be an object"))
        return
    allowed = frozenset({"enabled", "level_mode", "level_value", "disparity_rate"})
    key_err = _check_keys(value, frozenset(), allowed)
    if key_err:
        problems.append(_problem(prefix, key_err))
    if "enabled" in value and not isinstance(value["enabled"], bool):
        problems.append(_problem(f"{prefix}.enabled", "must be a boolean"))
    if "level_mode" in value and (
        not isinstance(value["level_mode"], str)
        or value["level_mode"] not in ENUM_VARS["employer_core_integration_level_mode"]
    ):
        problems.append(
            _problem(f"{prefix}.level_mode", "invalid integration level_mode")
        )
    if (
        "level_value" in value
        and value["level_value"] is not None
        and not _is_finite_number(value["level_value"])
    ):
        problems.append(
            _problem(f"{prefix}.level_value", "must be a finite number or null")
        )
    if "disparity_rate" in value and not _is_finite_number(value["disparity_rate"]):
        problems.append(_problem(f"{prefix}.disparity_rate", "must be a finite number"))


_CORE_DICT_ALLOWED_KEYS = frozenset(
    {
        "enabled",
        "contribution_rate",
        "status",
        "eligibility",
        "graded_schedule",
        "points_schedule",
        "age_schedule",
        "points_min_service_years",
        "points_pre_service_rate",
        "integration",
    }
)
_CORE_SCHEDULE_SPECS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "graded_schedule": (
        frozenset(
            {
                "service_years_min",
                "service_years_max",
                "min_years",
                "max_years",
                "contribution_rate",
                "rate",
            }
        ),
        frozenset({"service_years_max", "max_years"}),
    ),
    "points_schedule": (
        frozenset({"min_points", "max_points", "contribution_rate", "rate"}),
        frozenset({"max_points"}),
    ),
    "age_schedule": (
        frozenset({"min_age", "max_age", "contribution_rate", "rate"}),
        frozenset({"max_age"}),
    ),
}


def _validate_employer_core_scalars(
    value: Mapping[str, Any], problems: list[DbtVarProblem]
) -> None:
    prefix = "employer_core_contribution"
    if "enabled" in value and not isinstance(value["enabled"], bool):
        problems.append(_problem(f"{prefix}.enabled", "must be a boolean"))
    if "contribution_rate" in value and not _is_finite_number(
        value["contribution_rate"]
    ):
        problems.append(
            _problem(f"{prefix}.contribution_rate", "must be a finite number")
        )
    if "status" in value and (
        not isinstance(value["status"], str)
        or value["status"] not in ENUM_VARS["employer_core_status"]
    ):
        problems.append(_problem(f"{prefix}.status", "invalid employer_core_status"))
    min_years = value.get("points_min_service_years")
    if min_years is not None and (not _is_strict_int(min_years) or min_years < 1):
        problems.append(
            _problem(f"{prefix}.points_min_service_years", "must be an integer >= 1")
        )
    pre_rate = value.get("points_pre_service_rate")
    if pre_rate is not None and not _is_finite_number(pre_rate):
        problems.append(
            _problem(f"{prefix}.points_pre_service_rate", "must be a finite number")
        )


def _validate_employer_core_dict(value: Any, problems: list[DbtVarProblem]) -> None:
    prefix = "employer_core_contribution"
    if not isinstance(value, Mapping):
        problems.append(_problem(prefix, "must be an object"))
        return
    key_err = _check_keys(value, frozenset(), _CORE_DICT_ALLOWED_KEYS)
    if key_err:
        problems.append(_problem(prefix, key_err))
    _validate_employer_core_scalars(value, problems)
    if "eligibility" in value:
        _validate_eligibility_block(
            f"{prefix}.eligibility", value["eligibility"], problems
        )
    if "integration" in value:
        _validate_core_integration_dict(value["integration"], problems)
    for sched_key, (allowed, nullable) in _CORE_SCHEDULE_SPECS.items():
        if sched_key in value:
            sched_err = _validate_core_schedule_entries(
                value[sched_key], allowed, nullable
            )
            if sched_err:
                problems.append(_problem(f"{prefix}.{sched_key}", sched_err))


def validate_dbt_vars(variables: Mapping[str, Any]) -> list[DbtVarProblem]:
    """Return field-level problems before exported vars reach a dbt command."""
    problems: list[DbtVarProblem] = []
    for field, value in variables.items():
        if field == "employer_match":
            _validate_employer_match_dict(value, problems)
            continue
        if field == "employer_core_contribution":
            _validate_employer_core_dict(value, problems)
            continue
        if field in _LIST_MODELS:
            message = _validate_list(field, value)
        elif field in _NUMERIC_ROW_SCHEMAS:
            message = _validate_numeric_rows(value, _NUMERIC_ROW_SCHEMAS[field])
        elif field in _STRUCTURED_VALIDATORS:
            message = _STRUCTURED_VALIDATORS[field](value)
        else:
            message = _validate_scalar(field, value)
        if message:
            problems.append(_problem(field, message))
    _check_jinja_delimiters(variables, "", problems)
    return problems
