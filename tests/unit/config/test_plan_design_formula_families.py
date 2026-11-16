"""Configuration contracts for per-design contribution formula families."""

from __future__ import annotations

from pathlib import Path

import pytest

from planalign_orchestrator.config.plan_design import validate_points_min_service
from pydantic import ValidationError

from tests.fixtures.invariant_simulation import _simulation_config
from tests.fixtures.plan_design_formula_families.config import (
    CORE_FAMILIES,
    MATCH_FAMILIES,
    apply_single_design_formula,
    relation_contract_payload,
)

pytestmark = [pytest.mark.fast, pytest.mark.config]


def _config():
    return _simulation_config(Path("/tmp/feature_633_census.parquet"))


@pytest.mark.parametrize("family", MATCH_FAMILIES)
def test_accepts_each_per_design_match_family(family: str) -> None:
    configured = apply_single_design_formula(_config(), family, "flat")
    parameters = configured.validated_plan_design_parameters()
    assert parameters.root[configured.plan_design_id].match.family == family


@pytest.mark.parametrize("family", CORE_FAMILIES)
def test_accepts_each_per_design_core_family(family: str) -> None:
    configured = apply_single_design_formula(_config(), "deferral_based", family)
    parameters = configured.validated_plan_design_parameters()
    assert parameters.root[configured.plan_design_id].employer_core.family == family


def test_match_and_core_families_are_independent() -> None:
    configured = apply_single_design_formula(_config(), "points_based", "age_banded")
    design = configured.validated_plan_design_parameters().root[
        configured.plan_design_id
    ]
    assert (design.match.family, design.employer_core.family) == (
        "points_based",
        "age_banded",
    )


def test_legacy_alias_normalizes_to_tenure_graded() -> None:
    payload = relation_contract_payload()["age_design"]
    payload["match"]["family"] = "tenure_based"
    payload["match"]["tenure_graded_bands"] = [
        {
            "min_years": 0,
            "max_years": None,
            "tiers": [{"employee_min": 0.0, "employee_max": 0.06, "match_rate": 0.5}],
        }
    ]
    configured = _config()
    configured.plan_design_parameters = {configured.plan_design_id: payload}
    design = configured.validated_plan_design_parameters().root[
        configured.plan_design_id
    ]
    assert design.match.family == "tenure_graded"


def test_omitted_families_inherit_run_global_defaults() -> None:
    configured = _config()
    configured.employer_core_contribution = {
        "enabled": True,
        "status": "flat",
        "contribution_rate": 0.02,
    }
    configured.plan_design_parameters = {
        configured.plan_design_id: {
            "match": {
                "cap_percent": 0.04,
                "tiers": [
                    {"employee_min": 0.0, "employee_max": 0.06, "match_rate": 0.5}
                ],
            },
            "employer_core": {"contribution_rate": 0.02},
            "auto_enrollment": {
                "default_deferral_rate": 0.04,
                "window_days": 45,
                "scope": "all_eligible_employees",
            },
            "deferral_escalation": {"increment": 0.01, "cap": 0.06},
            "eligibility": {"waiting_period_days": 0},
        }
    }
    design = configured.validated_plan_design_parameters().root[
        configured.plan_design_id
    ]
    assert design.match.family == "deferral_based"
    assert design.employer_core.family == "flat"


@pytest.mark.parametrize(
    ("family", "field", "schedule"),
    [
        (
            "age_banded",
            "age_schedule",
            [{"min_age": 0, "max_age": None, "contribution_rate": 0.03}],
        ),
        (
            "points_based",
            "points_schedule",
            [
                {
                    "min_points": 0,
                    "max_points": None,
                    "contribution_rate": 0.04,
                }
            ],
        ),
    ],
)
def test_omitted_core_schedule_inherits_run_global_default(
    family: str, field: str, schedule: list[dict]
) -> None:
    configured = apply_single_design_formula(_config(), "deferral_based", "flat")
    configured.employer_core_contribution = {
        "enabled": True,
        "status": family,
        "contribution_rate": 0.02,
        field: schedule,
    }
    core = configured.plan_design_parameters.root[
        configured.plan_design_id
    ].employer_core
    core.family = None
    setattr(core, field, [])

    inherited = (
        configured.validated_plan_design_parameters()
        .root[configured.plan_design_id]
        .employer_core
    )

    assert inherited.family == family
    assert getattr(inherited, field)[0].rate == pytest.approx(
        schedule[0]["contribution_rate"] * 100
    )


@pytest.mark.parametrize(
    ("side", "family", "field"),
    [
        ("match", "points_based", "points_tiers"),
        ("match", "tenure_graded", "tenure_graded_bands"),
        ("employer_core", "age_banded", "age_schedule"),
        ("employer_core", "points_based", "points_schedule"),
    ],
)
def test_selected_family_requires_its_design_schedule(
    side: str, family: str, field: str
) -> None:
    payload = relation_contract_payload()["age_design"]
    payload[side]["family"] = family
    payload[side][field] = []
    configured = _config()
    configured.plan_design_parameters = {configured.plan_design_id: payload}
    with pytest.raises(
        ValueError, match=rf"{configured.plan_design_id}.*{side}.{field}"
    ):
        configured.validated_plan_design_parameters()


@pytest.mark.parametrize(
    ("side", "family"),
    [("match", "age_weighted"), ("employer_core", "integrated_flat")],
)
def test_rejects_unsupported_family(side: str, family: str) -> None:
    payload = relation_contract_payload()["age_design"]
    payload[side]["family"] = family
    configured = _config()
    configured.plan_design_parameters = {configured.plan_design_id: payload}
    with pytest.raises(ValidationError, match="family"):
        configured.validated_plan_design_parameters()


def test_explicit_integration_requires_a_level_value() -> None:
    payload = relation_contract_payload()["age_design"]
    core = payload["employer_core"]
    core.update(
        integration_enabled=True,
        integration_level_mode="explicit",
        integration_level_value=None,
    )
    configured = _config()
    configured.plan_design_parameters = {configured.plan_design_id: payload}
    with pytest.raises(ValueError, match=r"integration_level_value.*explicit"):
        configured.validated_plan_design_parameters()


def _points_core_payload(**core_fields: object) -> dict:
    payload = relation_contract_payload()["age_design"]
    payload["employer_core"].update(
        family="points_based",
        points_schedule=[{"min_points": 0, "max_points": None, "rate": 3.0}],
        **core_fields,
    )
    return payload


def test_points_min_service_round_trips_to_dbt_payload() -> None:
    configured = _config()
    configured.plan_design_parameters = {
        configured.plan_design_id: _points_core_payload(
            points_min_service_years=3, points_pre_service_rate=1.0
        )
    }
    payload = configured.validated_plan_design_parameters().to_dbt_payload()
    core = payload[configured.plan_design_id]["employer_core"]
    assert core["points_min_service_years"] == 3
    assert core["points_pre_service_rate"] == pytest.approx(1.0)


def test_unset_points_min_service_is_omitted_from_dbt_payload() -> None:
    configured = _config()
    configured.plan_design_parameters = {
        configured.plan_design_id: _points_core_payload()
    }
    payload = configured.validated_plan_design_parameters().to_dbt_payload()
    core = payload[configured.plan_design_id]["employer_core"]
    assert "points_min_service_years" not in core
    assert "points_pre_service_rate" not in core


@pytest.mark.parametrize(
    "fields",
    [{"points_min_service_years": 3}, {"points_pre_service_rate": 1.0}],
)
def test_points_min_service_requires_both_fields(fields: dict) -> None:
    configured = _config()
    configured.plan_design_parameters = {
        configured.plan_design_id: _points_core_payload(**fields)
    }
    with pytest.raises(ValueError, match="must be set together"):
        configured.validated_plan_design_parameters()


@pytest.mark.parametrize(
    ("min_years", "rate", "message"),
    [
        (0, 1.0, "whole number"),
        (2.5, 1.0, "whole number"),
        ("three", 1.0, "whole number"),
        (3, 150, "percent from 0 to 100"),
        (3, "1", "percent from 0 to 100"),
    ],
)
def test_points_min_service_rejects_out_of_range_values(
    min_years: object, rate: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_points_min_service("points_based", min_years, rate)


def test_points_min_service_rejected_for_other_core_families() -> None:
    payload = relation_contract_payload()["age_design"]
    payload["employer_core"].update(
        points_min_service_years=3, points_pre_service_rate=1.0
    )
    configured = _config()
    configured.plan_design_parameters = {configured.plan_design_id: payload}
    with pytest.raises(ValueError, match="only allowed with the points_based"):
        configured.validated_plan_design_parameters()


def test_points_min_service_inherits_from_studio_dc_plan() -> None:
    configured = apply_single_design_formula(_config(), "deferral_based", "flat")
    configured.dc_plan = {
        "core_integration_enabled": False,
        "core_status": "points_based",
        "core_points_schedule": [
            {"min_points": 0, "max_points": None, "contribution_rate": 0.03}
        ],
        "core_points_min_service_years": 3,
        "core_points_pre_service_rate": 1.0,
    }
    core = configured.plan_design_parameters.root[
        configured.plan_design_id
    ].employer_core
    core.family = None
    core.points_schedule = []

    inherited = (
        configured.validated_plan_design_parameters()
        .root[configured.plan_design_id]
        .employer_core
    )
    assert inherited.family == "points_based"
    assert inherited.points_min_service_years == 3
    assert inherited.points_pre_service_rate == pytest.approx(1.0)


def test_studio_dc_plan_rejects_half_set_points_min_service() -> None:
    from planalign_orchestrator.config import SimulationConfig

    raw = _config().model_dump(mode="json")
    raw["dc_plan"] = {
        "core_status": "points_based",
        "core_points_min_service_years": 3,
        "core_points_pre_service_rate": None,
    }
    with pytest.raises(ValidationError, match="must be set together"):
        SimulationConfig.model_validate(raw)
