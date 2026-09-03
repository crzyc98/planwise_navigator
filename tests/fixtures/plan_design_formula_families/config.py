"""Config and census builders for Feature 633 acceptance coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from planalign_orchestrator.config import (
    PlanDesignAssignmentSettings,
    PlanDesignParametersMap,
    SimulationConfig,
)
from tests.fixtures.performance_census import generate_performance_census

MATCH_FAMILIES = (
    "deferral_based",
    "graded_by_service",
    "tenure_graded",
    "points_based",
)
CORE_FAMILIES = ("flat", "graded_by_service", "points_based", "age_banded")

MATCH_SCHEDULES: dict[str, dict[str, list[dict[str, Any]]]] = {
    "deferral_based": {
        "tiers": [
            {"employee_min": 0.00, "employee_max": 0.03, "match_rate": 1.00},
            {"employee_min": 0.03, "employee_max": 0.05, "match_rate": 0.50},
        ]
    },
    "graded_by_service": {
        "graded_schedule": [
            {
                "min_value": 0,
                "max_value": None,
                "match_rate": 0.50,
                "max_deferral_pct": 0.06,
            },
        ]
    },
    "tenure_graded": {
        "tenure_graded_bands": [
            {
                "min_years": 0,
                "max_years": 5,
                "tiers": [
                    {"employee_min": 0.00, "employee_max": 0.04, "match_rate": 0.50}
                ],
            },
            {
                "min_years": 5,
                "max_years": None,
                "tiers": [
                    {"employee_min": 0.00, "employee_max": 0.03, "match_rate": 1.00},
                    {"employee_min": 0.03, "employee_max": 0.06, "match_rate": 0.50},
                ],
            },
        ]
    },
    "points_based": {
        "points_tiers": [
            {
                "min_value": 0,
                "max_value": 60,
                "match_rate": 0.50,
                "max_deferral_pct": 0.04,
            },
            {
                "min_value": 60,
                "max_value": None,
                "match_rate": 1.00,
                "max_deferral_pct": 0.06,
            },
        ]
    },
}

CORE_SCHEDULES: dict[str, dict[str, list[dict[str, Any]]]] = {
    "flat": {},
    "graded_by_service": {
        "graded_schedule": [
            {"min_years": 0, "max_years": 5, "rate": 0.02},
            {"min_years": 5, "max_years": None, "rate": 0.04},
        ]
    },
    "points_based": {
        "points_schedule": [
            {"min_points": 0, "max_points": 60, "rate": 2.0},
            {"min_points": 60, "max_points": None, "rate": 4.0},
        ]
    },
    "age_banded": {
        "age_schedule": [
            {"min_age": 0, "max_age": 40, "rate": 2.0},
            {"min_age": 40, "max_age": 55, "rate": 3.0},
            {"min_age": 55, "max_age": None, "rate": 4.0},
        ]
    },
}


def _parameters(
    match_family: str,
    core_family: str,
    *,
    integration_enabled: bool = False,
    match_template: str = "tiered",
) -> dict[str, Any]:
    """Return one complete design parameter payload."""
    return {
        "match": {
            "family": match_family,
            "match_template": match_template,
            "cap_percent": 0.04,
            **MATCH_SCHEDULES[match_family],
        },
        "employer_core": {
            "family": core_family,
            "contribution_rate": 0.02,
            **CORE_SCHEDULES[core_family],
            "integration_enabled": integration_enabled,
            "integration_level_mode": "ss_wage_base",
            "integration_level_value": None,
            "integration_disparity_rate": 0.0054 if integration_enabled else 0.0,
        },
        "auto_enrollment": {
            "default_deferral_rate": 0.04,
            "window_days": 45,
            "scope": "all_eligible_employees",
        },
        "deferral_escalation": {"increment": 0.01, "cap": 0.06},
        "eligibility": {"waiting_period_days": 0},
    }


def relation_contract_payload() -> dict[str, Any]:
    """Return sorted designs covering scalar, age, points, and empty schedules."""
    return {
        "age_design": _parameters(
            "deferral_based", "age_banded", integration_enabled=True
        ),
        "points_design": _parameters("points_based", "points_based"),
    }


def apply_single_design_formula(
    config: SimulationConfig,
    match_family: str,
    core_family: str,
    *,
    integration_enabled: bool = False,
) -> SimulationConfig:
    """Configure one design with independently selected match and core families."""
    configured = config.model_copy(deep=True)
    design_id = configured.plan_design_id or "default"
    configured.plan_design_assignment = None
    configured.plan_design_parameters = PlanDesignParametersMap.model_validate(
        {
            design_id: _parameters(
                match_family, core_family, integration_enabled=integration_enabled
            )
        }
    )
    return configured


def apply_two_design_formulas(config: SimulationConfig) -> SimulationConfig:
    """Configure the canonical legacy/new-hire grandfathering scenario."""
    configured = config.model_copy(deep=True)
    configured.plan_design_id = None
    configured.plan_design_assignment = PlanDesignAssignmentSettings.model_validate(
        {
            "default_plan_design_id": "legacy",
            "rules": [
                {
                    "type": "hire_date_cutoff",
                    "cutoff": "2015-01-01",
                    "plan_design_id": "new_hires",
                }
            ],
        }
    )
    configured.plan_design_parameters = PlanDesignParametersMap.model_validate(
        {
            "legacy": _parameters("deferral_based", "flat"),
            "new_hires": _parameters(
                "tenure_graded", "age_banded", integration_enabled=True
            ),
        }
    )
    return configured


def apply_legacy_single_design_formula(
    config: SimulationConfig,
    match_family: str,
    core_family: str,
    *,
    integration_enabled: bool = False,
) -> SimulationConfig:
    """Configure the pre-feature run-global surfaces for baseline capture."""
    configured = config.model_copy(deep=True)
    match = configured.employer_match.model_copy(deep=True)
    match.employer_match_status = match_family
    match.tenure_match_tiers = []
    match.points_match_tiers = []
    match.tenure_graded_bands = []
    schedule = MATCH_SCHEDULES[match_family]
    if match_family == "graded_by_service":
        match.tenure_match_tiers = [
            {
                "min_years": band["min_value"],
                "max_years": band["max_value"],
                "match_rate": band["match_rate"] * 100,
                "max_deferral_pct": band["max_deferral_pct"] * 100,
            }
            for band in schedule["graded_schedule"]
        ]
    elif match_family == "tenure_graded":
        match.tenure_graded_bands = schedule["tenure_graded_bands"]
    elif match_family == "points_based":
        match.points_match_tiers = [
            {
                "min_points": band["min_value"],
                "max_points": band["max_value"],
                "match_rate": band["match_rate"] * 100,
                "max_deferral_pct": band["max_deferral_pct"] * 100,
            }
            for band in schedule["points_tiers"]
        ]
    configured.employer_match = match
    core_schedule = CORE_SCHEDULES[core_family]
    core: dict[str, Any] = {
        "enabled": True,
        "status": core_family,
        "contribution_rate": 0.02,
        "integration": {
            "enabled": integration_enabled,
            "level_mode": "ss_wage_base",
            "level_value": None,
            "disparity_rate": 0.0054 if integration_enabled else 0.0,
        },
    }
    for key, bands in core_schedule.items():
        converted = []
        for band in bands:
            item = dict(band)
            item["contribution_rate"] = (
                item.pop("rate") / 100
                if core_family in {"age_banded", "points_based"}
                else item.pop("rate")
            )
            converted.append(item)
        core[key] = converted
    configured.employer_core_contribution = core
    return configured


def match_gap_parameters() -> dict[str, Any]:
    payload = _parameters("graded_by_service", "flat")
    payload["match"]["graded_schedule"] = [
        {"min_value": 0, "max_value": 1, "match_rate": 0.5, "max_deferral_pct": 0.04}
    ]
    return payload


def match_overlap_parameters() -> dict[str, Any]:
    payload = _parameters("graded_by_service", "flat")
    payload["match"]["graded_schedule"] = [
        {"min_value": 0, "max_value": 20, "match_rate": 0.5, "max_deferral_pct": 0.04},
        {
            "min_value": 10,
            "max_value": None,
            "match_rate": 1.0,
            "max_deferral_pct": 0.06,
        },
    ]
    return payload


def core_gap_parameters() -> dict[str, Any]:
    payload = _parameters("deferral_based", "age_banded")
    payload["employer_core"]["age_schedule"] = [
        {"min_age": 0, "max_age": 30, "rate": 2.0}
    ]
    return payload


def core_overlap_parameters() -> dict[str, Any]:
    payload = _parameters("deferral_based", "age_banded")
    payload["employer_core"]["age_schedule"] = [
        {"min_age": 0, "max_age": 50, "rate": 2.0},
        {"min_age": 40, "max_age": None, "rate": 4.0},
    ]
    return payload


def build_capacity_census(
    source: Path, destination: Path, count: int = 100_000
) -> Path:
    """Build a deterministic disposable census for scale validation."""
    return generate_performance_census(source, destination, count)
