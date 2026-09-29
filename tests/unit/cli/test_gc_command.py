"""Tests for `planalign gc` disk reclaim (#660)."""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from planalign_cli.commands import gc
from planalign_cli.main import app

pytestmark = pytest.mark.fast
runner = CliRunner()

OLD = time.time() - 30 * 86400


def _touch(path: Path, size: int = 16, mtime: float = OLD) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size)
    os.utime(path, (mtime, mtime))
    return path


def _make_var_tree(var: Path) -> dict[str, Path]:
    paths = {
        "perf_db": _touch(var / "perf_profile" / "c1" / "db" / "run.duckdb"),
        "perf_wal": _touch(var / "perf_profile" / "c1" / "db" / "run.duckdb.wal"),
        "perf_fresh": _touch(
            var / "perf_profile" / "c2" / "db" / "run.duckdb", mtime=time.time()
        ),
        "campaign": _touch(var / "perf_profile" / "c1" / "campaign.json"),
        "census": _touch(var / "perf_profile" / "census_60k.parquet"),
        "seed_db": _touch(var / "ensembles" / "e1" / "seed_42.duckdb"),
        "seed_artifacts": _touch(
            var / "ensembles" / "e1" / "seed_42_artifacts" / "target" / "x.json"
        ).parent.parent,
        "aggregate": _touch(var / "ensembles" / "e1" / "ensemble.duckdb"),
        "report": _touch(var / "ensembles" / "e1" / "reports" / "summary.csv"),
        "compiled": _touch(
            var / "compiled_execution" / "abc" / "staging" / "f.bin"
        ).parent.parent,
        "backup": _touch(var / "backups" / "simulation.duckdb.pre-refresh"),
    }
    os.utime(paths["seed_artifacts"], (OLD, OLD))
    os.utime(paths["compiled"], (OLD, OLD))
    return paths


def test_find_stale_artifacts_keeps_durable_outputs(tmp_path: Path):
    paths = _make_var_tree(tmp_path)

    found = {item.path for item in gc.find_stale_artifacts(tmp_path, 14)}

    reclaimable = {"perf_db", "perf_wal", "seed_db", "seed_artifacts", "compiled"}
    assert found == {paths[key] for key in reclaimable}


def test_find_stale_artifacts_skips_symlinks_out_of_var(tmp_path: Path):
    var = tmp_path / "var"
    outside = _touch(tmp_path / "precious" / "keep.duckdb")
    link = var / "perf_profile" / "link.duckdb"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    assert gc.find_stale_artifacts(var, 0) == []


def _make_scenario_runs(root: Path, count: int) -> Path:
    runs = root / "ws-1" / "scenarios" / "sc-1" / "runs"
    now = datetime.now()
    for index in range(count):
        run = runs / f"run-{index}"
        run.mkdir(parents=True)
        started = (now - timedelta(days=count - index)).isoformat()
        (run / "run_metadata.json").write_text(json.dumps({"started_at": started}))
    return runs


def test_cli_dry_run_then_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = tmp_path / "project"
    paths = _make_var_tree(project / "var")
    workspaces = tmp_path / "workspaces"
    runs = _make_scenario_runs(workspaces, 5)
    monkeypatch.setattr(gc, "PROJECT_ROOT", project)
    args = ["gc", "--workspaces-root", str(workspaces)]

    dry = runner.invoke(app, args)
    assert dry.exit_code == 0, dry.output
    assert "Would remove 2 Studio run(s)" in dry.output
    assert "Would remove 5 var/ artifact(s)" in dry.output
    assert paths["perf_db"].exists()
    assert len(list(runs.iterdir())) == 5

    real = runner.invoke(app, [*args, "--yes"])
    assert real.exit_code == 0, real.output
    assert sorted(p.name for p in runs.iterdir()) == ["run-2", "run-3", "run-4"]
    for key in ("perf_db", "perf_wal", "seed_db", "seed_artifacts", "compiled"):
        assert not paths[key].exists()
    for key in ("perf_fresh", "campaign", "census", "aggregate", "report", "backup"):
        assert paths[key].exists()


def test_config_age_and_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    (project / "config" / "simulation_config.yaml").write_text(
        "storage:\n  max_runs_per_scenario: 3\n  artifact_max_age_days: 60\n"
    )
    _make_var_tree(project / "var")
    monkeypatch.setattr(gc, "PROJECT_ROOT", project)
    args = ["gc", "--workspaces-root", str(tmp_path / "none")]

    assert "Would remove 0 var/ artifact(s)" in runner.invoke(app, args).output
    overridden = runner.invoke(app, [*args, "--older-than-days", "7"])
    assert "Would remove 5 var/ artifact(s)" in overridden.output


def _make_param_fit_jobs(workspaces: Path) -> dict[str, Path]:
    jobs = workspaces / "ws" / "param_fits"
    paths = {
        "stale_work": _touch(jobs / "fit_old" / "work" / "seed_42.duckdb").parent,
        "fresh_work": _touch(
            jobs / "fit_new" / "work" / "seed_42.duckdb", mtime=time.time()
        ).parent,
        "pack": _touch(jobs / "fit_old" / "pack" / "manifest.json"),
        "record": _touch(jobs / "fit_old" / "job.json"),
    }
    os.utime(paths["stale_work"], (OLD, OLD))
    return paths


def test_param_fit_scratch_is_reclaimed_but_packs_are_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    workspaces = tmp_path / "workspaces"
    paths = _make_param_fit_jobs(workspaces)
    monkeypatch.setattr(gc, "PROJECT_ROOT", tmp_path / "project")
    args = ["gc", "--workspaces-root", str(workspaces)]

    assert {item.path for item in gc.find_stale_param_fit_scratch(workspaces, 14)} == {
        paths["stale_work"]
    }
    dry = runner.invoke(app, args)
    assert "Would remove 1 fit/backtest scratch tree(s)" in dry.output
    assert paths["stale_work"].exists()

    real = runner.invoke(app, [*args, "--yes"])
    assert real.exit_code == 0, real.output
    assert not paths["stale_work"].exists()
    for key in ("fresh_work", "pack", "record"):
        assert paths[key].exists()


def test_param_fit_scratch_of_a_running_job_is_never_reclaimed(tmp_path: Path):
    workspaces = tmp_path / "workspaces"
    work = _touch(workspaces / "ws" / "param_fits" / "fit_live" / "work" / "s.duckdb")
    os.utime(work.parent, (OLD, OLD))
    (work.parent.parent / "job.json").write_text(json.dumps({"status": "running"}))

    assert gc.find_stale_param_fit_scratch(workspaces, 0) == []
