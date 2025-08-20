import os
from pathlib import Path

import pytest

from navigator_orchestrator.config import (SimulationConfig,
                                           load_simulation_config, to_dbt_vars)


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
