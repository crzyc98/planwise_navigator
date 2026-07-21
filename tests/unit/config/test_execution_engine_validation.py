"""Execution-engine configuration is validated before construction."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from planalign_cli.integration.orchestrator_wrapper import OrchestratorWrapper
from planalign_orchestrator.config import OptimizationSettings, load_simulation_config
from planalign_orchestrator.construction import ConstructionSpec, build_orchestrator


def _config_data() -> dict:
    return yaml.safe_load(Path("tests/fixtures/invariant_config.yaml").read_text())


def test_unset_and_supported_execution_engine_resolve_to_dbt(tmp_path):
    unset = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
    data = _config_data()
    data.setdefault("optimization", {})["execution_engine"] = "dbt"
    supported_path = tmp_path / "supported.yaml"
    supported_path.write_text(yaml.safe_dump(data))
    supported = load_simulation_config(supported_path)

    assert unset.optimization.execution_engine == "dbt"
    assert supported.optimization.execution_engine == "dbt"


def test_unsupported_execution_engine_names_option(tmp_path):
    with pytest.raises(ValidationError, match="optimization.execution_engine"):
        OptimizationSettings(execution_engine="compiled")


def test_cli_adapter_rejects_unsupported_engine_before_construction(tmp_path):
    data = _config_data()
    data.setdefault("optimization", {})["execution_engine"] = "compiled"
    path = tmp_path / "unsupported.yaml"
    path.write_text(yaml.safe_dump(data))

    wrapper = OrchestratorWrapper(path, tmp_path / "run.duckdb")
    with pytest.raises(ValueError, match="optimization.execution_engine"):
        wrapper.create_orchestrator()

    assert not (tmp_path / "run.duckdb").exists()


@pytest.mark.parametrize("entry_point", ["cli.simulate", "batch", "studio"])
def test_supported_engine_reaches_canonical_preflight(entry_point, tmp_path):
    config = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
    result = build_orchestrator(
        ConstructionSpec(
            config=config,
            database=tmp_path / f"{entry_point}.duckdb",
            entry_point=entry_point,
            validation_mode=True,
        )
    )

    assert result.signature.execution_engine == "dbt"
