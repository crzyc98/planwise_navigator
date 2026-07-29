"""dbt artifact isolation for parallel scenario workers (#457).

Concurrent workers share one dbt project dir, so without redirection they all
write ``dbt/target/run_results.json`` and would attribute each other's
failures. These tests pin the redirection and, critically, that it stays off by
default for every serial caller.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from planalign_orchestrator.dbt_runner import DbtRunner, extract_dbt_failure_detail

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator, pytest.mark.dbt]


class TestArtifactPaths:
    def test_defaults_to_the_project_dir(self):
        runner = DbtRunner(working_dir=Path("dbt"))
        assert runner.target_path == Path("dbt") / "target"
        assert runner.log_path == Path("dbt") / "logs"

    def test_redirects_under_an_explicit_artifacts_dir(self, tmp_path):
        runner = DbtRunner(working_dir=Path("dbt"), dbt_artifacts_dir=tmp_path)
        assert runner.target_path == tmp_path / "target"
        assert runner.log_path == tmp_path / "logs"

    def test_artifacts_dir_is_absolute(self, tmp_path, monkeypatch):
        """dbt runs with cwd=dbt/, so a relative path would resolve wrongly."""
        monkeypatch.chdir(tmp_path)
        runner = DbtRunner(working_dir=Path("dbt"), dbt_artifacts_dir=Path("scratch"))
        assert runner.dbt_artifacts_dir.is_absolute()

    def test_two_workers_get_disjoint_target_paths(self, tmp_path):
        a = DbtRunner(dbt_artifacts_dir=tmp_path / "a")
        b = DbtRunner(dbt_artifacts_dir=tmp_path / "b")
        assert a.target_path != b.target_path


class TestSubprocessEnv:
    def test_no_dbt_path_vars_by_default(self):
        """Serial runs must keep dbt's own defaults untouched."""
        env = DbtRunner(database_path="dbt/simulation.duckdb")._build_subprocess_env()
        assert "DBT_TARGET_PATH" not in env
        assert "DBT_LOG_PATH" not in env

    def test_sets_dbt_path_vars_when_isolated(self, tmp_path):
        runner = DbtRunner(dbt_artifacts_dir=tmp_path)
        env = runner._build_subprocess_env()
        assert env["DBT_TARGET_PATH"] == str(tmp_path / "target")
        assert env["DBT_LOG_PATH"] == str(tmp_path / "logs")

    def test_database_path_and_artifacts_dir_coexist(self, tmp_path):
        """Regression: the DATABASE_PATH branch used to re-copy os.environ,
        silently dropping the artifact redirection set just above it."""
        runner = DbtRunner(
            working_dir=Path("dbt"),
            database_path="dbt/simulation.duckdb",
            dbt_artifacts_dir=tmp_path,
        )
        env = runner._build_subprocess_env()
        assert env["DBT_TARGET_PATH"] == str(tmp_path / "target")
        assert env["DATABASE_PATH"] == "simulation.duckdb"


class TestFailureDetailAttribution:
    @staticmethod
    def _write_results(target_dir: Path, node: str, message: str) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "run_results.json").write_text(
            json.dumps(
                {
                    "results": [
                        {"status": "error", "unique_id": node, "message": message}
                    ]
                }
            )
        )

    def test_reads_the_explicit_target_path(self, tmp_path):
        self._write_results(tmp_path / "target", "model.p.dim_x", "boom")
        detail = extract_dbt_failure_detail(tmp_path, target_path=tmp_path / "target")
        assert "model.p.dim_x: boom" == detail

    def test_isolated_worker_ignores_the_shared_project_target(self, tmp_path):
        """The failure a worker reports must be its own, not a neighbour's."""
        project = tmp_path / "dbt"
        self._write_results(project / "target", "model.p.other_scenario", "not mine")
        worker = tmp_path / "worker_a"
        self._write_results(worker / "target", "model.p.mine", "my failure")

        detail = extract_dbt_failure_detail(project, target_path=worker / "target")
        assert "my failure" in detail
        assert "other_scenario" not in detail

    def test_missing_target_path_is_not_an_error(self, tmp_path):
        assert extract_dbt_failure_detail(tmp_path, target_path=tmp_path / "nope") == ""

    def test_legacy_call_without_target_path_still_works(self, tmp_path):
        self._write_results(tmp_path / "target", "model.p.dim_y", "legacy")
        assert "model.p.dim_y: legacy" == extract_dbt_failure_detail(tmp_path)

    def test_runner_reports_its_own_target(self, tmp_path):
        """End-to-end: the runner hands its resolved target to the extractor."""
        runner = DbtRunner(
            working_dir=tmp_path / "dbt", dbt_artifacts_dir=tmp_path / "w"
        )
        self._write_results(tmp_path / "w" / "target", "model.p.dim_z", "isolated")
        detail = extract_dbt_failure_detail(
            runner.working_dir, target_path=runner.target_path
        )
        assert "isolated" in detail
