"""Batch must use canonical no-implicit-initialization construction."""

from pathlib import Path

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import (
    ConstructionSpec,
    InitializationPolicy,
    build_orchestrator,
)


def test_fresh_batch_construction_uses_none_and_no_initializer_hook(tmp_path):
    config = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
    result = build_orchestrator(
        ConstructionSpec(
            config=config,
            database=tmp_path / "batch.duckdb",
            initialization=InitializationPolicy.NONE,
            entry_point="batch",
            validation_mode=True,
        )
    )

    assert result.signature.initialization_policy == "none"
    assert "self_healing_initializer" not in result.signature.installed_hook_names
    assert not (tmp_path / "batch.duckdb").exists()
