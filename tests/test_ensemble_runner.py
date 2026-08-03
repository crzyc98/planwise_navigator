"""Fast worker-isolation coverage for seed ensembles."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from planalign_ensemble.runner import run_seed_worker
from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.run_pool import ScenarioJob


@pytest.mark.fast
def test_seed_worker_uses_a_per_seed_working_directory_for_initialization(
    tmp_path, monkeypatch
) -> None:
    """Parallel cold starts must not contend on a repository-global lock file."""
    database = tmp_path / "seed_42.duckdb"
    project_dir = tmp_path / "project"
    config = SimulationConfig(
        simulation={"start_year": 2025, "end_year": 2025, "random_seed": 42},
        compensation={},
    )
    job = ScenarioJob(
        name="seed_42",
        config=config,
        db_path=database,
        seed=42,
        threads=1,
        dbt_artifacts_dir=tmp_path / "artifacts",
        payload={
            "start_year": 2025,
            "end_year": 2025,
            "dbt_project_dir": str(project_dir),
        },
    )
    original_directory = Path.cwd()

    class FakeOrchestrator:
        def execute_multi_year_simulation(self, **kwargs) -> None:
            assert kwargs["start_year"] == 2025
            assert kwargs["end_year"] == 2025

    def fake_build(spec):
        assert spec.database == database.resolve()
        assert spec.dbt_project_dir == project_dir.resolve()
        assert spec.initialization_lock_name != "planalign_init"
        return SimpleNamespace(orchestrator=FakeOrchestrator())

    monkeypatch.setattr("planalign_ensemble.runner.build_orchestrator", fake_build)

    run_seed_worker(job)

    assert Path.cwd() == original_directory
