"""Safety and failure-evidence contracts for the CLI hash campaign."""

from pathlib import Path
import json
from types import SimpleNamespace

import pytest

from planalign_orchestrator.dbt_runner import DbtRunner
from scripts.perf_profile import hash_ab


def test_campaign_rejects_unrelated_project_differences(tmp_path: Path) -> None:
    baseline, candidate = tmp_path / "baseline", tmp_path / "candidate"
    for project in (baseline, candidate):
        project.mkdir()
        (project / "dbt_project.yml").write_text("name: test\n")
    (candidate / "unrelated.sql").write_text("SELECT 1")
    args = SimpleNamespace(baseline_project=baseline, candidate_project=candidate)
    with pytest.raises(ValueError, match="differ only"):
        hash_ab.prepare(args)


def test_measure_rejects_existing_output_directory(tmp_path: Path) -> None:
    with pytest.raises(FileExistsError):
        hash_ab.measure(tmp_path, tmp_path, tmp_path / "config.json", "2025-2029")


def test_cli_capture_records_reused_runner_and_restores_method(
    tmp_path: Path, monkeypatch
) -> None:
    calls = []

    def execute(runner, command_args, **kwargs):
        calls.append(command_args)
        target = tmp_path / "target"
        target.mkdir(exist_ok=True)
        (target / "run_results.json").write_text(
            json.dumps(
                {
                    "metadata": {"invocation_id": str(len(calls))},
                    "results": [
                        {
                            "unique_id": f"node-{len(calls)}",
                            "status": "success",
                            "timing": [],
                        }
                    ],
                }
            )
        )
        return "success"

    monkeypatch.setattr(DbtRunner, "execute_command", execute)
    runner = DbtRunner.__new__(DbtRunner)
    runner.working_dir, runner.project_dir, runner.dbt_artifacts_dir = (
        tmp_path,
        None,
        None,
    )
    with hash_ab.record_invocations() as recorders:
        assert runner.execute_command(["seed"]) == "success"
        assert runner.execute_command(["run"]) == "success"
    assert len(recorders) == 1
    assert [item.models[0].unique_id for item in recorders[0].invocations] == [
        "node-1",
        "node-2",
    ]
    assert DbtRunner.execute_command is execute
    assert runner.execute_command.__func__ is execute


def test_failed_cli_retains_evidence_and_restores_environment(
    tmp_path: Path, monkeypatch
) -> None:
    from planalign_cli import main

    source = tmp_path / "source"
    source.mkdir()
    (source / "target").mkdir()
    (source / "target/stale.json").write_text("stale")
    (source / "simulation.duckdb").write_bytes(b"shared sentinel")
    monkeypatch.setenv("DATABASE_PATH", "original-database")
    original = DbtRunner.execute_command

    def fail(*, args: list[str], standalone_mode: bool) -> None:
        import os

        assert "--fail-on-validation-error" in args
        assert args[args.index("--threads") + 1] == "1"
        assert os.environ["DATABASE_PATH"] == str(tmp_path / "sample/simulation.duckdb")
        project = Path(args[args.index("--dbt-project-dir") + 1])
        assert not (project / "target").exists()
        assert not (project / "simulation.duckdb").exists()
        raise RuntimeError("expected validation failure")

    monkeypatch.setattr(main, "app", fail)
    with pytest.raises(RuntimeError, match="Failed sample"):
        hash_ab.measure(
            tmp_path / "sample", source, tmp_path / "config.json", "2025-2029"
        )
    sample = json.loads((tmp_path / "sample/measurement.json").read_text())
    assert "expected validation failure" in sample["error"]
    assert sample["wall_s"] >= 0
    assert DbtRunner.execute_command is original
    import os

    assert os.environ["DATABASE_PATH"] == "original-database"
    assert (source / "simulation.duckdb").read_bytes() == b"shared sentinel"
