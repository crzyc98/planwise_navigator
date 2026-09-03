"""Configuration contracts for per-design contribution formula families."""

from __future__ import annotations

from pathlib import Path

import pytest
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
