import os
from pathlib import Path

import pytest

from planalign_orchestrator.config import (SimulationConfig,
                                           load_simulation_config, to_dbt_vars)
from tests.fixtures.config import GOLDEN_DBT_VARS_KEYS


def test_load_simulation_config_valid_yaml(tmp_path: Path):
    yaml_text = """
simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 42
compensation:
  cola_rate: 0.01
  merit_budget: 0.02
enrollment:
  auto_enrollment:
    enabled: true
"""
    p = tmp_path / "config.yaml"
    p.write_text(yaml_text)

    cfg = load_simulation_config(p)
    assert isinstance(cfg, SimulationConfig)
    assert cfg.simulation.start_year == 2025
    assert cfg.compensation.cola_rate == 0.01


def test_environment_variable_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    p = tmp_path / "config.yaml"
    p.write_text(
        """
simulation:
  start_year: 2025
  end_year: 2029
compensation:
  cola_rate: 0.01
  merit_budget: 0.02
enrollment:
  auto_enrollment:
    enabled: true
"""
    )

    monkeypatch.setenv("NAV_SIMULATION__START_YEAR", "2030")
    cfg = load_simulation_config(p)
    assert cfg.simulation.start_year == 2030


def test_dbt_var_mapping(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text(
        """
simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 99
compensation:
  cola_rate: 0.005
  merit_budget: 0.025
eligibility:
  waiting_period_days: 30
plan_eligibility:
  minimum_age: 21
enrollment:
  auto_enrollment:
    enabled: true
    window_days: 45
    default_deferral_rate: 0.06
    opt_out_grace_period: 30
  proactive_enrollment:
    enabled: true
    timing_window:
      min_days: 7
      max_days: 35
    probability_by_demographics:
      young: 0.25
      mid_career: 0.45
      mature: 0.65
      senior: 0.75
  timing:
    business_day_adjustment: true
"""
    )

    cfg = load_simulation_config(p)
    vars_dict = to_dbt_vars(cfg)
    # Spot-check a few keys
    assert vars_dict["eligibility_waiting_days"] == 30
    assert vars_dict["random_seed"] == 99
    assert vars_dict["proactive_enrollment_rate_senior"] == 0.75


def test_to_dbt_vars_golden_output(golden_config):
    """
    Golden output test for to_dbt_vars() regression detection.

    This test captures the expected output for critical dbt variables.
    If to_dbt_vars() changes in a way that alters these outputs, this test
    will fail, alerting us to potential regressions.
    """
    result = to_dbt_vars(golden_config)

    # Verify all critical keys exist
    for key in GOLDEN_DBT_VARS_KEYS:
        assert key in result, f"Missing critical dbt_var key: {key}"

    # Verify golden config values are correctly exported
    assert result["random_seed"] == 42
    assert result["target_growth_rate"] == 0.03
    assert result["cola_rate"] == 0.02
    assert result["merit_budget"] == 0.03

    # Enrollment settings from production config
    assert result["auto_enrollment_enabled"] is True
    # Note: Production config uses 0 waiting days (immediate eligibility)
    assert result["eligibility_waiting_days"] == 0

    # Verify proactive enrollment rates exist and are reasonable (0-1 range)
    for rate_key in [
        "proactive_enrollment_rate_young",
        "proactive_enrollment_rate_mid_career",
        "proactive_enrollment_rate_mature",
        "proactive_enrollment_rate_senior",
    ]:
        assert 0 <= result[rate_key] <= 1, f"{rate_key} out of range: {result[rate_key]}"


def test_to_dbt_vars_contains_all_required_keys(minimal_config):
    """Verify to_dbt_vars() exports all keys required by dbt models."""
    result = to_dbt_vars(minimal_config)

    # Required keys for core dbt models
    required_keys = [
        # Core simulation
        "random_seed",
        "target_growth_rate",
        # Compensation
        "cola_rate",
        "merit_budget",
        # Eligibility
        "eligibility_waiting_days",
        "minimum_age",
        # Enrollment
        "auto_enrollment_enabled",
        "auto_enrollment_window_days",
        "auto_enrollment_default_deferral_rate",
        "auto_enrollment_opt_out_grace_period",
        # Proactive enrollment
        "proactive_enrollment_enabled",
        "proactive_enrollment_min_days",
        "proactive_enrollment_max_days",
    ]

    for key in required_keys:
        assert key in result, f"Missing required dbt_var: {key}"


def test_to_dbt_vars_output_types(minimal_config):
    """Verify to_dbt_vars() exports correct types for dbt."""
    result = to_dbt_vars(minimal_config)

    # Integer types
    assert isinstance(result["random_seed"], int)
    assert isinstance(result["eligibility_waiting_days"], int)
    assert isinstance(result["minimum_age"], int)

    # Float types (rates, percentages)
    assert isinstance(result["cola_rate"], (int, float))
    assert isinstance(result["merit_budget"], (int, float))
    assert isinstance(result["target_growth_rate"], (int, float))

    # Boolean types
    assert isinstance(result["auto_enrollment_enabled"], bool)
    assert isinstance(result["proactive_enrollment_enabled"], bool)
