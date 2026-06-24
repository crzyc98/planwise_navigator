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
    def test_compute_simple_formula_uses_max_match_percentage(self):
        emv = {
            "active_match_formula": "simple_match",
            "match_formulas": {
                "simple_match": {"type": "simple", "max_match_percentage": 0.06}
            },
        }
        assert _compute_match_max_deferral_rate(emv) == pytest.approx(0.06)

    def test_compute_tiered_formula_uses_top_tier_employee_max(self):
        emv = {
            "active_match_formula": "stretch_match",
            "match_formulas": {
                "stretch_match": {
                    "type": "tiered",
                    "tiers": [{"employee_min": 0.0, "employee_max": 0.10}],
                }
            },
        }
        assert _compute_match_max_deferral_rate(emv) == pytest.approx(0.10)

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
        assert result["employer_match_max_deferral_rate"] == pytest.approx(0.06)

    def test_ceiling_changes_with_configured_ceiling(self):
        """FR-002: 6% vs 10% ceiling must yield different exported values."""
        cfg = _make_config()
        cfg.employer_match.active_formula = "stretch_match"
        cfg.employer_match.formulas = {
            "stretch_match": {
                "type": "tiered",
                "tiers": [{"employee_min": 0.0, "employee_max": 0.06}],
            }
        }
        six = _export_employer_match_vars(cfg)["employer_match_max_deferral_rate"]

        cfg.employer_match.formulas["stretch_match"]["tiers"][0]["employee_max"] = 0.10
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
    def test_default_cap_is_ten_percent(self):
        cfg = _make_config()
        result = _export_enrollment_vars(cfg)
        assert result["voluntary_max_deferral_rate"] == pytest.approx(0.10)

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
