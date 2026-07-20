"""Feature 119: factory wires the runner class from optimization.execution_engine."""

from pathlib import Path

import pytest

from planalign_orchestrator import create_orchestrator
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.dbt_runner import DbtRunner
from planalign_orchestrator.engine import CompiledRunner

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]

CONFIG_YAML = Path("config/simulation_config.yaml")


def _orchestrator(tmp_path, engine):
    config = load_simulation_config(CONFIG_YAML, env_overrides=False)
    config.optimization.execution_engine = engine
    return create_orchestrator(
        config,
        db_path=tmp_path / "engine_test.duckdb",
        threads=1,
        auto_initialize=False,
    )


def test_default_engine_uses_dbt_runner(tmp_path):
    orchestrator = _orchestrator(tmp_path, "dbt")
    assert type(orchestrator.dbt_runner) is DbtRunner


def test_compiled_engine_uses_compiled_runner(tmp_path):
    orchestrator = _orchestrator(tmp_path, "compiled")
    assert isinstance(orchestrator.dbt_runner, CompiledRunner)
    assert isinstance(orchestrator.dbt_runner, DbtRunner)  # drop-in contract
    assert orchestrator.dbt_runner.record_log.fallback_count == 0
