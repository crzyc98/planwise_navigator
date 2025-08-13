#!/usr/bin/env python3
"""
Tests for opt-out rate configuration in Navigator Orchestrator.

Validates that opt-out rate settings are properly extracted from configuration
and passed to dbt models within reasonable bounds.
"""

import pytest
from pathlib import Path

from navigator_orchestrator.config import (
    SimulationConfig,
    load_simulation_config,
    to_dbt_vars,
    OptOutRatesSettings,
    OptOutRatesByAge,
    OptOutRatesByIncome,
)


class TestOptOutConfiguration:
    """Test opt-out rate configuration extraction and validation."""

    def test_opt_out_rates_default_values(self):
        """Test that default opt-out rates are within reasonable industry ranges."""
        age_rates = OptOutRatesByAge()
        income_rates = OptOutRatesByIncome()

        # Age-based rates should be between 1% and 15%
        assert 0.01 <= age_rates.young <= 0.15
        assert 0.01 <= age_rates.mid_career <= 0.15
        assert 0.01 <= age_rates.mature <= 0.15
        assert 0.01 <= age_rates.senior <= 0.15

        # Age progression: young >= mid_career >= mature >= senior
        assert age_rates.young >= age_rates.mid_career
        assert age_rates.mid_career >= age_rates.mature
        assert age_rates.mature >= age_rates.senior

        # Income multipliers should be reasonable (0.3x to 2.0x)
        assert 0.3 <= income_rates.low_income <= 2.0
        assert income_rates.moderate == 1.0  # Base rate
        assert 0.3 <= income_rates.high <= 1.0
        assert 0.3 <= income_rates.executive <= 1.0

    def test_opt_out_rates_validation_bounds(self):
        """Test that Pydantic validation enforces reasonable bounds."""
        # Test that rates above 100% are rejected
        with pytest.raises(ValueError):
            OptOutRatesByAge(young=1.5)  # 150% is invalid

        # Test that negative rates are rejected
        with pytest.raises(ValueError):
            OptOutRatesByAge(senior=-0.01)

        # Test that extreme multipliers are rejected
        with pytest.raises(ValueError):
            OptOutRatesByIncome(low_income=10.0)  # 10x multiplier is excessive

    def test_dbt_vars_extraction(self):
        """Test that opt-out rates are properly extracted to dbt vars."""
        # Create a minimal config with opt-out settings
        config_data = {
            "simulation": {"start_year": 2025, "end_year": 2027},
            "compensation": {"cola_rate": 0.02, "merit_budget": 0.03},
            "workforce": {"total_termination_rate": 0.12},
            "enrollment": {
                "auto_enrollment": {
                    "opt_out_rates": {
                        "by_age": {
                            "young": 0.08,
                            "mid_career": 0.06,
                            "mature": 0.04,
                            "senior": 0.02
                        },
                        "by_income": {
                            "low_income": 1.25,
                            "moderate": 1.00,
                            "high": 0.75,
                            "executive": 0.50
                        }
                    }
                }
            }
        }

        config = SimulationConfig(**config_data)
        dbt_vars = to_dbt_vars(config)

        # Verify age-based rates are extracted
        assert dbt_vars["opt_out_rate_young"] == 0.08
        assert dbt_vars["opt_out_rate_mid"] == 0.06
        assert dbt_vars["opt_out_rate_mature"] == 0.04
        assert dbt_vars["opt_out_rate_senior"] == 0.02

        # Verify income-based rates are calculated correctly
        # Base rate is young * moderate multiplier = 0.08 * 1.00 = 0.08
        expected_base = 0.08
        assert dbt_vars["opt_out_rate_low_income"] == expected_base * 1.25  # 0.10
        assert dbt_vars["opt_out_rate_moderate"] == expected_base * 1.00    # 0.08
        assert dbt_vars["opt_out_rate_high"] == expected_base * 0.75       # 0.06
        assert dbt_vars["opt_out_rate_executive"] == expected_base * 0.50   # 0.04

    def test_industry_benchmarks_compliance(self):
        """Test that calculated rates comply with industry benchmarks."""
        config_data = {
            "simulation": {"start_year": 2025, "end_year": 2027},
            "compensation": {"cola_rate": 0.02, "merit_budget": 0.03},
            "workforce": {"total_termination_rate": 0.12},
            "enrollment": {
                "auto_enrollment": {
                    "opt_out_rates": {
                        "by_age": {
                            "young": 0.12,      # 12%
                            "mid_career": 0.08, # 8%
                            "mature": 0.06,     # 6%
                            "senior": 0.04      # 4%
                        },
                        "by_income": {
                            "low_income": 1.20,  # 20% higher
                            "moderate": 1.00,    # Base
                            "high": 0.70,        # 30% lower
                            "executive": 0.50    # 50% lower
                        }
                    }
                }
            }
        }

        config = SimulationConfig(**config_data)
        dbt_vars = to_dbt_vars(config)

        # Industry benchmarks: well-designed auto-enrollment should have 5-15% opt-out
        # Most extreme case: young + low_income = 0.12 * 1.20 = 14.4% (within range)
        max_rate = dbt_vars["opt_out_rate_low_income"]  # Young * low_income
        assert max_rate <= 0.15, f"Max opt-out rate {max_rate:.1%} exceeds 15% industry benchmark"

        # Most favorable case: senior + executive should be quite low
        min_base = dbt_vars["opt_out_rate_senior"]  # 4%
        min_multiplier_rate = min_base * config.enrollment.auto_enrollment.opt_out_rates.by_income.executive
        assert min_multiplier_rate >= 0.01, f"Min opt-out rate {min_multiplier_rate:.1%} too low to be realistic"

    def test_config_yaml_loading(self, tmp_path):
        """Test loading opt-out configuration from YAML file."""
        yaml_content = """
simulation:
  start_year: 2025
  end_year: 2027

compensation:
  cola_rate: 0.02
  merit_budget: 0.03

workforce:
  total_termination_rate: 0.12

enrollment:
  auto_enrollment:
    enabled: true
    opt_out_rates:
      by_age:
        young: 0.09
        mid_career: 0.07
        mature: 0.05
        senior: 0.03
      by_income:
        low_income: 1.15
        moderate: 1.00
        high: 0.80
        executive: 0.60
"""

        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(yaml_content)

        config = load_simulation_config(config_file)

        # Verify configuration loaded correctly
        assert config.enrollment.auto_enrollment.opt_out_rates.by_age.young == 0.09
        assert config.enrollment.auto_enrollment.opt_out_rates.by_income.low_income == 1.15

        # Verify dbt vars are generated correctly
        dbt_vars = to_dbt_vars(config)
        assert "opt_out_rate_young" in dbt_vars
        assert "opt_out_rate_low_income" in dbt_vars


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
