"""Contract tests for canonical construction inputs."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction.spec import (
    ConstructionSpec,
    ExecutionEngineOption,
    InitializationPolicy,
)


@pytest.fixture
def simulation_config():
    return load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))


def test_construction_spec_is_pydantic_and_defaults_to_safe_policy(
    simulation_config,
    tmp_path,
):
    spec = ConstructionSpec(config=simulation_config, database=tmp_path / "run.duckdb")

    assert spec.threads == 1
    assert spec.initialization is InitializationPolicy.NONE
    assert spec.execution_engine.engine == "dbt"
    assert spec.entry_point == "cli.simulate"
    assert spec.validation_mode is False


@pytest.mark.parametrize("threads", [0, 17])
def test_construction_spec_rejects_invalid_thread_count(
    simulation_config,
    tmp_path,
    threads,
):
    with pytest.raises(ValidationError, match="threads"):
        ConstructionSpec(
            config=simulation_config,
            database=tmp_path / "run.duckdb",
            threads=threads,
        )


def test_construction_spec_rejects_unknown_entry_point(simulation_config, tmp_path):
    with pytest.raises(ValidationError, match="entry_point"):
        ConstructionSpec(
            config=simulation_config,
            database=tmp_path / "run.duckdb",
            entry_point="unknown",
        )


def test_execution_engine_rejects_unsupported_value():
    with pytest.raises(ValidationError, match="execution_engine.*dbt"):
        ExecutionEngineOption(engine="compiled")


def test_initialization_policy_values_are_explicit():
    assert InitializationPolicy.NONE.value == "none"
    assert InitializationPolicy.SELF_HEALING.value == "self_healing"
