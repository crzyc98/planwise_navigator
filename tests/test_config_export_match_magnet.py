"""Feature 102 — match-magnet dial & ceiling fidelity: config export tests.

Covers:
  - US1: always-on `employer_match_max_deferral_rate` (independent of
    deferral_match_response) and that it tracks the active formula ceiling.
  - US2: match-magnet dial vars exported from `enrollment.match_magnet` and
    overridable via dc_plan (UI).
  - US3: `voluntary_max_deferral_rate` exported from config and dc_plan.
"""

import pytest

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.config.export import (
    _compute_match_max_deferral_rate,
    _export_employer_match_vars,
    _export_enrollment_vars,
)

pytestmark = [pytest.mark.fast, pytest.mark.config]


def _make_config():
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.scenario_id = "test_magnet"
    cfg.plan_design_id = "test_plan"
    return cfg


# ---------------------------------------------------------------------------
# US1 — ceiling fidelity (FR-001/002/003)
# ---------------------------------------------------------------------------


class TestAlwaysOnMatchCeiling:
    def test_legacy_formula_is_ignored(self):
        assert (
            _compute_match_max_deferral_rate(
                {
                    "active_match_formula": "simple",
                    "match_formulas": {"simple": {"max_match_percentage": 0.06}},
                }
            )
            is None
        )

    def test_compute_returns_none_when_no_formula(self):
        assert _compute_match_max_deferral_rate({}) is None

    def test_ui_match_tiers_take_precedence(self):
        emv = {
            "match_tiers": [
                {"employee_min": 0.0, "employee_max": 0.04},
                {"employee_min": 0.04, "employee_max": 0.08},
            ],
            "active_match_formula": "simple_match",
            "match_formulas": {
                "simple_match": {"type": "simple", "max_match_percentage": 0.06}
            },
        }
        assert _compute_match_max_deferral_rate(emv) == pytest.approx(0.08)

    def test_ceiling_exported_without_deferral_match_response(self):
        """FR-003: ceiling must be exported by the employer-match exporter,
        independent of whether deferral_match_response is configured."""
        cfg = _make_config()
        # Ensure DMR is not what produces the value.
        cfg.employer_match.active_formula = "simple_match"
        cfg.employer_match.formulas = {
            "simple_match": {"type": "simple", "max_match_percentage": 0.06}
        }
        result = _export_employer_match_vars(cfg)
        assert "employer_match_max_deferral_rate" in result
        assert result["employer_match_max_deferral_rate"] == pytest.approx(0.05)

    def test_ceiling_changes_with_configured_ceiling(self):
        """FR-002: 6% vs 10% ceiling must yield different exported values."""
        cfg = _make_config()
        cfg.dc_plan = {
            "match_tiers": [
                {"employee_min": 0.0, "employee_max": 0.06, "match_rate": 0.5}
            ]
        }
        six = _export_employer_match_vars(cfg)["employer_match_max_deferral_rate"]

        cfg.dc_plan["match_tiers"][0]["employee_max"] = 0.10
        ten = _export_employer_match_vars(cfg)["employer_match_max_deferral_rate"]

        assert six == pytest.approx(0.06)
        assert ten == pytest.approx(0.10)
        assert ten > six


# ---------------------------------------------------------------------------
# US2 — expose the dial (FR-004/005/006)
# ---------------------------------------------------------------------------


class TestMatchMagnetDialExport:
    def test_defaults_preserve_current_behavior(self):
        cfg = _make_config()
        result = _export_enrollment_vars(cfg)
        assert result["enrollment_match_magnet_enabled"] is True
        assert result["enrollment_match_magnet_probability"] == pytest.approx(0.45)

    def test_config_values_exported(self):
        cfg = _make_config()
        cfg.enrollment.match_magnet.enabled = False
        cfg.enrollment.match_magnet.snap_probability = 0.80
        result = _export_enrollment_vars(cfg)
        assert result["enrollment_match_magnet_enabled"] is False
        assert result["enrollment_match_magnet_probability"] == pytest.approx(0.80)

    def test_dc_plan_overrides_take_precedence(self):
        cfg = _make_config()
        cfg.enrollment.match_magnet.snap_probability = 0.45
        # Simulate UI-driven dc_plan payload (decimals already divided by 100).
        cfg.dc_plan = {
            "match_magnet_enabled": False,
            "match_magnet_probability": 0.20,
        }
        result = _export_enrollment_vars(cfg)
        assert result["enrollment_match_magnet_enabled"] is False
        assert result["enrollment_match_magnet_probability"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# US3 — configurable deferral cap (FR-009/013)
# ---------------------------------------------------------------------------


class TestVoluntaryMaxDeferralExport:
    def test_default_cap_is_fifteen_percent(self):
        """Issue #652 (D7): raised from 0.10 so the higher demographic cells
        have room to spread. mature/executive and senior/high (0.12) and
        senior/executive (0.15) were previously clamped down to 0.10."""
        cfg = _make_config()
        result = _export_enrollment_vars(cfg)
        assert result["voluntary_max_deferral_rate"] == pytest.approx(0.15)

    def test_config_cap_exported(self):
        cfg = _make_config()
        cfg.enrollment.match_magnet.max_deferral_rate = 0.12
        result = _export_enrollment_vars(cfg)
        assert result["voluntary_max_deferral_rate"] == pytest.approx(0.12)

    def test_dc_plan_cap_override(self):
        cfg = _make_config()
        cfg.dc_plan = {"max_voluntary_deferral_percent": 0.15}
        result = _export_enrollment_vars(cfg)
        assert result["voluntary_max_deferral_rate"] == pytest.approx(0.15)


def test_default_yaml_match_design() -> None:
    from planalign_orchestrator.config import to_dbt_vars

    result = to_dbt_vars(_make_config())
    assert result["match_tiers"] == [
        {"employee_min": 0.0, "employee_max": 0.03, "match_rate": 1.0},
        {"employee_min": 0.03, "employee_max": 0.05, "match_rate": 0.5},
    ]
    assert result["match_cap_percent"] == 0.04
    assert result["employer_match_max_deferral_rate"] == 0.05


def test_legacy_formula_without_supported_match_is_rejected() -> None:
    from planalign_orchestrator.config import to_dbt_vars

    cfg = _make_config()
    cfg.dc_plan = {}
    cfg.employer_match.active_formula = "old"
    cfg.employer_match.formulas = {
        "old": {
            "type": "tiered",
            "tiers": [{"employee_min": 0, "employee_max": 0.06, "match_rate": 0.5}],
            "max_match_percentage": 0.03,
        }
    }
    assert cfg.employer_match.formulas["old"]["tiers"][0]["match_rate"] == 0.5
    with pytest.raises(ValueError, match="dc_plan.match_tiers"):
        to_dbt_vars(cfg)


def test_supported_tiers_override_legacy_formula() -> None:
    from planalign_orchestrator.config import to_dbt_vars

    cfg = _make_config()
    cfg.employer_match.active_formula = "old"
    cfg.dc_plan = {
        "match_tiers": [{"employee_min": 0, "employee_max": 0.06, "match_rate": 0.5}],
        "match_cap_percent": 0.03,
    }
    result = to_dbt_vars(cfg)
    assert result["match_tiers"] == cfg.dc_plan["match_tiers"]
    assert result["match_cap_percent"] == 0.03


@pytest.mark.parametrize("bad_cap", ["bad", {}, []])
def test_invalid_match_cap_cannot_leave_partial_export(bad_cap: object) -> None:
    from planalign_orchestrator.config import to_dbt_vars

    cfg = _make_config()
    cfg.dc_plan = {
        "match_tiers": [{"employee_min": 0, "employee_max": 0.06, "match_rate": 0.5}],
        "match_cap_percent": bad_cap,
    }
    with pytest.raises(ValueError, match="Invalid dc_plan match configuration"):
        to_dbt_vars(cfg)


def test_per_design_match_is_authoritative_over_legacy_global() -> None:
    from planalign_orchestrator.config import to_dbt_vars

    cfg = _make_config()
    cfg.dc_plan = {}
    cfg.employer_match.active_formula = "old"
    cfg.plan_design_id = "baseline"
    cfg.plan_design_parameters = {
        "baseline": {
            "match": {
                "family": "deferral_based",
                "cap_percent": 0.03,
                "tiers": [{"employee_min": 0, "employee_max": 0.06, "match_rate": 0.5}],
            },
            "employer_core": {"contribution_rate": 0.02},
            "auto_enrollment": {
                "default_deferral_rate": 0.06,
                "window_days": 45,
                "scope": "all_eligible_employees",
            },
            "deferral_escalation": {"increment": 0.01, "cap": 0.1},
            "eligibility": {"waiting_period_days": 0},
        }
    }
    result = to_dbt_vars(cfg)
    assert result["plan_design_parameters"]["baseline"]["match"]["cap_percent"] == 0.03
    assert (
        result["plan_design_parameters"]["baseline"]["match"]["tiers"][0]["match_rate"]
        == 0.5
    )


@pytest.mark.parametrize("age", [18, 19, 21])
def test_configured_minimum_age_overrides_project_default(age: int) -> None:
    from pathlib import Path
    import yaml
    from planalign_orchestrator.config import to_dbt_vars

    cfg = _make_config()
    cfg.plan_eligibility.minimum_age = age
    defaults = yaml.safe_load(
        (Path(__file__).parents[1] / "dbt/dbt_project.yml").read_text()
    )["vars"]
    merged = defaults | to_dbt_vars(cfg)
    assert merged["plan_eligibility_minimum_age"] == age
    assert merged["minimum_age"] == age
