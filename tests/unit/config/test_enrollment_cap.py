"""The effective voluntary cap must leave room for every active AE floor."""

from typing import Any

import pytest
from pydantic import ValidationError

from planalign_orchestrator.config import SimulationConfig, load_simulation_config
from planalign_orchestrator.config.export import to_dbt_vars

pytestmark = [pytest.mark.fast, pytest.mark.config]
TIERS = [
    {"max_auto_enroll_default_rate": 0.03, "share": 0.0},
    {"max_auto_enroll_default_rate": None, "share": 0.15},
]


@pytest.fixture
def payload() -> dict[str, Any]:
    data = load_simulation_config("config/simulation_config.yaml").model_dump()
    data["enrollment"]["auto_enrollment"]["default_deferral_rate"] = 0.06
    data["enrollment"]["match_magnet"]["max_deferral_rate"] = 0.04
    data["enrollment"]["below_default"]["share_tiers"] = TIERS
    return data


def _design(default: float) -> dict[str, Any]:
    return {
        "match": {
            "cap_percent": 0.04,
            "tiers": [{"employee_min": 0.0, "employee_max": 0.04, "match_rate": 1.0}],
        },
        "employer_core": {"contribution_rate": 0.02},
        "auto_enrollment": {
            "default_deferral_rate": default,
            "window_days": 45,
            "scope": "all_eligible_employees",
        },
        "deferral_escalation": {"increment": 0.01, "cap": 0.10},
        "eligibility": {"waiting_period_days": 0},
    }


@pytest.mark.parametrize("export", [False, True])
@pytest.mark.parametrize(
    "source", ["global", "per_design", "studio_cap", "studio_default"]
)
def test_conflicting_cap_rejected(
    payload: dict[str, Any], source: str, export: bool
) -> None:
    if source == "per_design":
        payload["enrollment"]["auto_enrollment"]["default_deferral_rate"] = 0.03
        payload["plan_design_parameters"] = {"design_A": _design(0.06)}
        payload["plan_design_id"] = "design_A"
    elif source == "studio_cap":
        payload["enrollment"]["match_magnet"]["max_deferral_rate"] = 0.15
        payload["dc_plan"] = {"max_voluntary_deferral_percent": 0.04}
    elif source == "studio_default":
        payload["enrollment"]["auto_enrollment"]["default_deferral_rate"] = 0.03
        payload["dc_plan"] = {"default_deferral_percent": 6.0}
    if export:
        # Studio and other callers can mutate an already validated config.
        cfg = load_simulation_config("config/simulation_config.yaml")
        cfg.enrollment = type(cfg.enrollment).model_validate(payload["enrollment"])
        setattr(cfg, "dc_plan", payload.get("dc_plan"))
        cfg.plan_design_id = payload.get("plan_design_id")
        cfg.plan_design_parameters = payload.get("plan_design_parameters")
        with pytest.raises(
            ValueError,
            match=r"voluntary_max_deferral_rate \(0.04\).*auto_enrollment_default_deferral_rate \(0.06\)",
        ):
            to_dbt_vars(cfg)
    else:
        with pytest.raises(
            ValidationError,
            match=r"voluntary_max_deferral_rate \(0.04\).*auto_enrollment_default_deferral_rate \(0.06\)",
        ):
            SimulationConfig.model_validate(payload)


@pytest.mark.parametrize(
    "allowed",
    [
        "equal_cap",
        "zero_share",
        "inactive_tier",
        "ae_disabled",
        "studio_disabled",
        "studio_cap",
        "studio_share",
    ],
)
def test_compatible_configs_export(payload: dict[str, Any], allowed: str) -> None:
    enrollment = payload["enrollment"]
    if allowed == "equal_cap":
        enrollment["match_magnet"]["max_deferral_rate"] = 0.06
    elif allowed == "zero_share":
        enrollment["below_default"]["share_tiers"] = [
            {"max_auto_enroll_default_rate": None, "share": 0.0}
        ]
    elif allowed == "inactive_tier":
        enrollment["auto_enrollment"]["default_deferral_rate"] = 0.03
        payload["plan_design_parameters"] = {"default": _design(0.03)}
    elif allowed == "ae_disabled":
        enrollment["auto_enrollment"]["enabled"] = False
    elif allowed == "studio_disabled":
        payload["dc_plan"] = {"auto_enroll": False}
    elif allowed == "studio_cap":
        payload["dc_plan"] = {"max_voluntary_deferral_percent": 0.08}
    else:
        payload["dc_plan"] = {
            "below_default_share_tiers": [
                {"max_auto_enroll_default_rate": None, "share": 0.0}
            ]
        }
    assert to_dbt_vars(SimulationConfig.model_validate(payload))
