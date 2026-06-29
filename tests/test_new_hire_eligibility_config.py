"""Feature 103 — new-hire eligibility rate + census eligibility override: config tests.

Covers:
  - FR-001/FR-011: ``new_hire_ineligible_pct`` validation (0.0-1.0, default 0.0).
  - US3: ``new_hire_eligibility_match_census`` defaults to False.
  - to_dbt_vars exports both vars with no-op defaults (FR-013 backward compatibility).
"""

import pytest
from pydantic import ValidationError

from planalign_orchestrator.config import load_simulation_config, to_dbt_vars
from planalign_orchestrator.config.workforce import EligibilitySettings

pytestmark = [pytest.mark.fast, pytest.mark.config]


class TestEligibilitySettingsValidation:
    def test_defaults_are_no_op(self):
        settings = EligibilitySettings()
        assert settings.new_hire_ineligible_pct == 0.0
        assert settings.new_hire_eligibility_match_census is False

    def test_pct_accepts_in_range(self):
        assert (
            EligibilitySettings(new_hire_ineligible_pct=0.10).new_hire_ineligible_pct
            == 0.10
        )
        assert (
            EligibilitySettings(new_hire_ineligible_pct=0.0).new_hire_ineligible_pct
            == 0.0
        )
        assert (
            EligibilitySettings(new_hire_ineligible_pct=1.0).new_hire_ineligible_pct
            == 1.0
        )

    @pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0, -1.0])
    def test_pct_rejects_out_of_range(self, bad):
        with pytest.raises(ValidationError):
            EligibilitySettings(new_hire_ineligible_pct=bad)


class TestToDbtVarsExport:
    def test_exports_no_op_defaults(self):
        cfg = load_simulation_config("config/simulation_config.yaml")
        dbt_vars = to_dbt_vars(cfg)
        assert dbt_vars["new_hire_ineligible_pct"] == 0.0
        assert dbt_vars["new_hire_eligibility_match_census"] is False

    def test_exports_configured_values(self):
        cfg = load_simulation_config("config/simulation_config.yaml")
        cfg.eligibility.new_hire_ineligible_pct = 0.10
        cfg.eligibility.new_hire_eligibility_match_census = True
        dbt_vars = to_dbt_vars(cfg)
        assert dbt_vars["new_hire_ineligible_pct"] == pytest.approx(0.10)
        assert dbt_vars["new_hire_eligibility_match_census"] is True
