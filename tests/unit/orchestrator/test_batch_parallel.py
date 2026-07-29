"""Batch fan-out wiring for #457.

The pool itself is covered in test_run_pool.py; these tests pin the batch
runner's contract with it — that job preparation is deterministic and happens
in the parent, and that a failure lands in the summary rather than aborting the
batch.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from planalign_orchestrator.run_pool import JobResult
from planalign_orchestrator.scenario_batch_runner import ScenarioBatchRunner

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


@pytest.fixture
def batch_env(tmp_path, monkeypatch):
    """A scenarios dir, an output dir, and a dbt/ dir for scenario databases."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dbt").mkdir()

    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    for name, seed, growth in (("alpha", 111, 0.03), ("beta", 222, 0.08)):
        (scenarios / f"{name}.yaml").write_text(
            yaml.dump(
                {
                    "simulation": {
                        "start_year": 2025,
                        "end_year": 2025,
                        "random_seed": seed,
                        "target_growth_rate": growth,
                    },
                    "scenario_id": name,
                }
            )
        )

    base = Path(__file__).resolve().parents[3] / "config" / "simulation_config.yaml"
    runner = ScenarioBatchRunner(
        scenarios_dir=scenarios,
        output_dir=tmp_path / "out",
        base_config_path=base,
    )
    return runner, tmp_path


class TestJobPreparation:
    def test_job_carries_a_resolved_config_and_seed(self, batch_env):
        runner, _ = batch_env
        job = runner._prepare_job(
            "alpha", runner.scenarios_dir / "alpha.yaml", export_format="csv"
        )

        assert job.name == "alpha"
        assert job.seed == 111
        # The seed must be baked into the config the worker receives, not
        # re-resolved on the far side of the process boundary.
        assert job.config.simulation.random_seed == 111
        assert job.config.simulation.target_growth_rate == 0.03

    def test_scenario_overrides_are_merged_in_the_parent(self, batch_env):
        runner, _ = batch_env
        alpha = runner._prepare_job(
            "alpha", runner.scenarios_dir / "alpha.yaml", export_format="csv"
        )
        beta = runner._prepare_job(
            "beta", runner.scenarios_dir / "beta.yaml", export_format="csv"
        )

        assert alpha.config.simulation.target_growth_rate == 0.03
        assert beta.config.simulation.target_growth_rate == 0.08
        assert alpha.db_path != beta.db_path

    def test_preparation_is_deterministic(self, batch_env):
        """Same inputs, same job — regardless of when or where it is built."""
        runner, _ = batch_env
        first = runner._prepare_job(
            "alpha", runner.scenarios_dir / "alpha.yaml", export_format="csv"
        )
        second = runner._prepare_job(
            "alpha", runner.scenarios_dir / "alpha.yaml", export_format="csv"
        )
        assert first.seed == second.seed
        assert first.config.model_dump() == second.config.model_dump()

    def test_each_scenario_gets_its_own_database(self, batch_env):
        runner, tmp_path = batch_env
        job = runner._prepare_job(
            "alpha", runner.scenarios_dir / "alpha.yaml", export_format="csv"
        )
        assert job.db_path == (tmp_path / "dbt" / "alpha.duckdb").absolute()
        assert job.db_path.exists()

    def test_artifacts_isolated_only_when_fanning_out(self, batch_env):
        """Serial batches must keep writing to dbt/target as they always have."""
        runner, _ = batch_env
        serial = runner._prepare_job(
            "alpha", runner.scenarios_dir / "alpha.yaml", export_format="csv"
        )
        assert serial.dbt_artifacts_dir is None

        parallel = runner._prepare_job(
            "alpha",
            runner.scenarios_dir / "alpha.yaml",
            export_format="csv",
            isolate_dbt_artifacts=True,
        )
        assert parallel.dbt_artifacts_dir is not None
        assert (parallel.dbt_artifacts_dir / "target").is_dir()
        assert (parallel.dbt_artifacts_dir / "logs").is_dir()

    def test_workers_get_disjoint_artifact_dirs(self, batch_env):
        runner, _ = batch_env
        alpha = runner._prepare_job(
            "alpha",
            runner.scenarios_dir / "alpha.yaml",
            export_format="csv",
            isolate_dbt_artifacts=True,
        )
        beta = runner._prepare_job(
            "beta",
            runner.scenarios_dir / "beta.yaml",
            export_format="csv",
            isolate_dbt_artifacts=True,
        )
        assert alpha.dbt_artifacts_dir != beta.dbt_artifacts_dir


class TestRunBatchWiring:
    @staticmethod
    def _patch_pool(monkeypatch, outcomes):
        """Replace pool execution, capturing the jobs it was handed."""
        seen = {}

        def fake_run(self, worker, jobs, *, on_event=None):
            seen["jobs"] = jobs
            seen["max_workers"] = self.max_workers
            return {j.name: outcomes(j) for j in jobs}

        monkeypatch.setattr(
            "planalign_orchestrator.run_pool.ScenarioRunPool.run", fake_run
        )
        return seen

    def test_failed_job_is_reported_not_raised(self, batch_env, monkeypatch):
        runner, _ = batch_env
        self._patch_pool(
            monkeypatch,
            lambda j: (
                JobResult(
                    name=j.name, status="completed", value={"status": "completed"}
                )
                if j.name == "alpha"
                else JobResult(
                    name=j.name, status="failed", error="boom", traceback="tb"
                )
            ),
        )

        results = runner.run_batch(export_format="csv", parallel=2)

        assert results["alpha"]["status"] == "completed"
        assert results["beta"]["status"] == "failed"
        assert results["beta"]["error"] == "boom"

    def test_parallel_one_uses_a_single_worker(self, batch_env, monkeypatch):
        runner, _ = batch_env
        seen = self._patch_pool(
            monkeypatch,
            lambda j: JobResult(j.name, "completed", value={"status": "completed"}),
        )
        runner.run_batch(export_format="csv", parallel=1)
        assert seen["max_workers"] == 1
        assert all(j.dbt_artifacts_dir is None for j in seen["jobs"])

    def test_fan_out_isolates_artifacts(self, batch_env, monkeypatch):
        runner, _ = batch_env
        seen = self._patch_pool(
            monkeypatch,
            lambda j: JobResult(j.name, "completed", value={"status": "completed"}),
        )
        runner.run_batch(export_format="csv", parallel=2)
        assert seen["max_workers"] == 2
        assert all(j.dbt_artifacts_dir is not None for j in seen["jobs"])

    def test_worker_budget_is_exposed_for_reporting(self, batch_env, monkeypatch):
        runner, _ = batch_env
        self._patch_pool(
            monkeypatch,
            lambda j: JobResult(j.name, "completed", value={"status": "completed"}),
        )
        runner.run_batch(export_format="csv", parallel=2)
        assert runner.worker_budget is not None
        assert runner.worker_budget.workers == 2
        assert "worker(s)" in runner.worker_budget.describe()

    def test_setup_failure_does_not_abort_the_batch(self, batch_env, monkeypatch):
        """A bad scenario config must fail alone, mirroring serial behavior."""
        runner, _ = batch_env
        (runner.scenarios_dir / "beta.yaml").write_text(
            yaml.dump({"simulation": {"start_year": 2030, "end_year": 2025}})
        )
        seen = self._patch_pool(
            monkeypatch,
            lambda j: JobResult(j.name, "completed", value={"status": "completed"}),
        )

        results = runner.run_batch(export_format="csv", parallel=2)

        assert results["alpha"]["status"] == "completed"
        assert results["beta"]["status"] == "failed"
        assert [j.name for j in seen["jobs"]] == ["alpha"]
