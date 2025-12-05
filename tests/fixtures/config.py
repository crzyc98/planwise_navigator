"""Configuration fixtures for simulation testing."""

import pytest
from pathlib import Path
from planalign_orchestrator.config import (
    SimulationConfig,
    SimulationSettings,
    CompensationSettings,
    load_simulation_config,
    to_dbt_vars,
)


@pytest.fixture
def minimal_config() -> SimulationConfig:
    """
    Minimal valid simulation configuration for unit tests.

    Provides a lightweight config suitable for fast unit testing
    without full simulation execution.

    Usage:
        @pytest.mark.fast
        @pytest.mark.unit
        def test_config_validation(minimal_config):
            assert minimal_config.simulation.start_year == 2025
            assert minimal_config.simulation.end_year == 2026
    """
    # Load from the actual config file to get all required structures
    config = load_simulation_config("config/simulation_config.yaml")
    # Override for test isolation
    config.scenario_id = "test_scenario"
    config.plan_design_id = "test_plan"
    config.simulation.start_year = 2025
    config.simulation.end_year = 2026
    config.simulation.random_seed = 42
    return config


@pytest.fixture
def single_threaded_config(minimal_config) -> SimulationConfig:
    """
    Configuration optimized for single-threaded testing.

    Disables parallel execution for deterministic, sequential testing
    on work laptops or CI environments.

    Usage:
        @pytest.mark.integration
        def test_sequential_execution(single_threaded_config):
            orchestrator = PipelineOrchestrator(single_threaded_config)
            assert orchestrator.config.optimization.max_workers == 1
    """
    from planalign_orchestrator.config import OptimizationSettings

    # Use typed OptimizationSettings (top-level attribute, not inside multi_year)
    if minimal_config.optimization is None:
        minimal_config.optimization = OptimizationSettings()
    minimal_config.optimization.max_workers = 1
    minimal_config.optimization.level = "medium"
    return minimal_config


@pytest.fixture
def multi_threaded_config(minimal_config) -> SimulationConfig:
    """
    Configuration with 4-thread parallel execution.

    Enables parallel processing for performance testing on
    multi-core systems.

    Usage:
        @pytest.mark.performance
        def test_parallel_speedup(multi_threaded_config):
            orchestrator = PipelineOrchestrator(multi_threaded_config)
            assert orchestrator.config.optimization.max_workers == 4
    """
    from planalign_orchestrator.config import OptimizationSettings

    # Use typed OptimizationSettings (top-level attribute, not inside multi_year)
    if minimal_config.optimization is None:
        minimal_config.optimization = OptimizationSettings()
    minimal_config.optimization.max_workers = 4
    minimal_config.optimization.level = "high"
    return minimal_config


@pytest.fixture
def golden_config() -> SimulationConfig:
    """
    Configuration with stable, known dbt_vars output for regression testing.

    This fixture provides a configuration where all values are explicitly set
    to enable golden output testing. Changes to to_dbt_vars() that alter the
    output will cause tests using this fixture to fail, catching regressions.

    Usage:
        def test_to_dbt_vars_golden_output(golden_config):
            result = to_dbt_vars(golden_config)
            assert result["random_seed"] == 42
            assert result["cola_rate"] == 0.02
    """
    config = load_simulation_config("config/simulation_config.yaml")
    # Set stable values for testing
    config.scenario_id = "golden_test"
    config.plan_design_id = "golden_plan"
    config.simulation.start_year = 2025
    config.simulation.end_year = 2027
    config.simulation.random_seed = 42
    config.simulation.target_growth_rate = 0.03
    config.compensation.cola_rate = 0.02
    config.compensation.merit_budget = 0.03
    return config


# Critical dbt_vars keys that must be tested for regression
GOLDEN_DBT_VARS_KEYS = [
    # Simulation settings
    "random_seed",
    "target_growth_rate",
    # Compensation settings
    "cola_rate",
    "merit_budget",
    # Enrollment settings
    "auto_enrollment_enabled",
    "auto_enrollment_window_days",
    "auto_enrollment_default_deferral_rate",
    # Eligibility settings
    "eligibility_waiting_days",
    "minimum_age",
    # Proactive enrollment rates
    "proactive_enrollment_rate_young",
    "proactive_enrollment_rate_mid_career",
    "proactive_enrollment_rate_mature",
    "proactive_enrollment_rate_senior",
]
