"""Fast worker-isolation coverage for seed ensembles."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from planalign_ensemble.models import EnsembleSpec
from planalign_ensemble.planner import plan_ensemble
from planalign_ensemble.runner import run_ensemble, run_seed_worker
from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.construction import InitializationPolicy
from planalign_orchestrator.pipeline_orchestrator import PipelineStageError
from planalign_orchestrator.run_pool import ScenarioJob
from tests.test_ensemble_end_to_end import _write_seed_snapshot


@pytest.mark.fast
def test_seed_worker_leaves_initialization_to_the_pipeline(
    tmp_path, monkeypatch
) -> None:
    """Seed workers must not pre-build what the pipeline rebuilds (#967)."""
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
        assert spec.initialization is InitializationPolicy.NONE
        return SimpleNamespace(orchestrator=FakeOrchestrator())

    monkeypatch.setattr("planalign_ensemble.runner.build_orchestrator", fake_build)

    run_seed_worker(job)

    assert Path.cwd() == original_directory


@pytest.mark.fast
def test_pipeline_failure_after_construction_excludes_only_that_seed(
    tmp_path, monkeypatch
) -> None:
    """Without a pre-flight initializer, setup failures surface from the pipeline.

    A seed whose pipeline fails after successful construction must be reported
    as failed and kept out of aggregation, while the other seeds still count.
    """
    plan = plan_ensemble(
        EnsembleSpec(
            scenario_id="failing-seed",
            seed_count=3,
            start_year=2027,
            end_year=2027,
            min_seeds=2,
        ),
        output_root=tmp_path,
    )
    failing_seed = plan.seeds[1]
    config = SimulationConfig(
        simulation={"start_year": 2027, "end_year": 2027, "random_seed": 1},
        compensation={},
    )

    def fake_build(spec):
        assert spec.initialization is InitializationPolicy.NONE
        seed = spec.config.simulation.random_seed

        def execute_multi_year_simulation(**_kwargs) -> None:
            if seed == failing_seed:
                raise PipelineStageError("Dbt seed failed with code 1")
            _write_seed_snapshot(spec.database, seed)

        return SimpleNamespace(
            orchestrator=SimpleNamespace(
                execute_multi_year_simulation=execute_multi_year_simulation
            )
        )

    monkeypatch.setattr("planalign_ensemble.runner.build_orchestrator", fake_build)

    result = run_ensemble(plan, parallel=1, config=config)

    statuses = {outcome.seed: outcome.status for outcome in result.outcomes}
    assert statuses.pop(failing_seed) == "failed"
    assert set(statuses.values()) == {"completed"}
    failed = next(o for o in result.outcomes if o.seed == failing_seed)
    assert "Dbt seed failed" in (failed.error or "")
    with duckdb.connect(str(plan.ensemble_db_path), read_only=True) as conn:
        aggregated = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT seed FROM fct_metric_seed_values"
            ).fetchall()
        }
    assert aggregated == set(statuses)
