"""Configuration fixtures for simulation testing."""

import pytest
from pathlib import Path
from navigator_orchestrator.config import (
    SimulationConfig,
    SimulationSettings,
    CompensationSettings,
    load_simulation_config,
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
            assert orchestrator.config.multi_year['optimization']['max_workers'] == 1
    """
    # multi_year is a dict in the loaded config
    if 'optimization' in minimal_config.multi_year:
        minimal_config.multi_year['optimization']['max_workers'] = 1
        minimal_config.multi_year['optimization']['level'] = "medium"
    if 'performance' in minimal_config.multi_year:
        minimal_config.multi_year['performance']['enable_parallel_dbt'] = False
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
            assert orchestrator.config.multi_year['optimization']['max_workers'] == 4
    """
    # multi_year is a dict in the loaded config
    if 'optimization' in minimal_config.multi_year:
        minimal_config.multi_year['optimization']['max_workers'] = 4
        minimal_config.multi_year['optimization']['level'] = "high"
    if 'performance' in minimal_config.multi_year:
        minimal_config.multi_year['performance']['enable_parallel_dbt'] = True
    return minimal_config
