"""
Test: Auto-Enrollment Disabled Config Export

Verifies that when auto_enrollment.enabled is set to False in SimulationConfig,
the exported dbt vars correctly set auto_enrollment_enabled to False.

This is a unit-level verification that the Python config layer correctly
exports the disabled flag, complementing the dbt-level test that verifies
the SQL models respect it.
"""

import pytest

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.config.export import _export_enrollment_vars


def _make_config_with_auto_enrollment(enabled: bool):
    """Load real config and set auto_enrollment.enabled."""
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.enrollment.auto_enrollment.enabled = enabled
    return cfg


class TestAutoEnrollmentDisabledExport:
    """Tests that disabled auto-enrollment is correctly exported to dbt vars."""

    def test_disabled_auto_enrollment_exports_false(self):
        """When auto_enrollment.enabled=False, dbt var must be False."""
        cfg = _make_config_with_auto_enrollment(enabled=False)
        result = _export_enrollment_vars(cfg)
        assert result["auto_enrollment_enabled"] is False

    def test_enabled_auto_enrollment_exports_true(self):
        """When auto_enrollment.enabled=True, dbt var must be True."""
        cfg = _make_config_with_auto_enrollment(enabled=True)
        result = _export_enrollment_vars(cfg)
        assert result["auto_enrollment_enabled"] is True

    def test_dc_plan_override_disables_auto_enrollment(self):
        """When dc_plan config sets auto_enroll=False, it overrides to disabled."""
        cfg = _make_config_with_auto_enrollment(enabled=True)
        cfg.dc_plan = {"auto_enroll": False}
        result = _export_enrollment_vars(cfg)
        assert result["auto_enrollment_enabled"] is False


class TestAutoEnrollmentMultiYear:
    """Tests that disabled auto-enrollment persists across multi-year config."""

    def test_disabled_flag_consistent_across_years(self):
        """auto_enrollment_enabled=False must export the same for any year."""
        from planalign_orchestrator.config import to_dbt_vars

        cfg = _make_config_with_auto_enrollment(enabled=False)
        for year in [2025, 2026, 2027]:
            cfg.simulation.start_year = year
            result = to_dbt_vars(cfg)
            assert result["auto_enrollment_enabled"] is False, (
                f"auto_enrollment_enabled should be False for year {year}"
            )
