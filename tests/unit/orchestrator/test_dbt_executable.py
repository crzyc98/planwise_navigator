"""dbt discovery works for virtualenv entry points without shell activation."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from planalign_orchestrator.dbt_executable import find_dbt_executable
from planalign_orchestrator.dbt_runner import DbtExecutionError, DbtRunner
from tests.helpers.dbt_manifest import load_production_manifest

pytestmark = pytest.mark.fast


@pytest.fixture
def unactivated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.symlink_to(sys.executable)
    dbt = bin_dir / "dbt"
    dbt.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "if sys.argv[1] == 'parse':\n"
        "    target = Path(os.environ['DBT_TARGET_PATH'])\n"
        "    target.mkdir(parents=True)\n"
        "    (target / 'manifest.json').write_text(json.dumps({'nodes': {}}))\n"
        "print('dbt command:', ' '.join(sys.argv[1:]))\n"
    )
    dbt.chmod(0o755)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(sys, "executable", str(python))
    return dbt


def test_sibling_discovery_keeps_virtualenv_symlink_location(
    unactivated_environment: Path,
) -> None:
    assert find_dbt_executable() == str(unactivated_environment)


def test_path_takes_precedence(
    unactivated_environment: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path_bin = tmp_path / "path-bin"
    path_bin.mkdir()
    dbt = path_bin / "dbt"
    dbt.write_text("#!/bin/sh\nexit 0\n")
    dbt.chmod(0o755)
    monkeypatch.setenv("PATH", str(path_bin))
    assert find_dbt_executable() == "dbt"


@pytest.mark.parametrize("candidate", ["missing", "directory", "nonexecutable"])
def test_invalid_sibling_fails_clearly(
    unactivated_environment: Path,
    candidate: str,
) -> None:
    if candidate == "nonexecutable":
        unactivated_environment.chmod(0o644)
    else:
        unactivated_environment.unlink()
        if candidate == "directory":
            unactivated_environment.mkdir()
    assert find_dbt_executable() is None
    with pytest.raises(DbtExecutionError, match="not found on PATH or beside"):
        DbtRunner()._build_command(["run"])
    load_production_manifest.cache_clear()
    with pytest.raises(AssertionError, match="dbt executable is required"):
        load_production_manifest()


@pytest.mark.parametrize("streaming", [False, True])
def test_runner_executes_sibling_in_both_modes(
    unactivated_environment: Path,
    streaming: bool,
) -> None:
    runner = DbtRunner(threads=3)
    command = runner._build_command(["run"])
    assert command == [str(unactivated_environment), "run", "--threads", "3"]
    execute = runner._execute_with_streaming if streaming else runner._run_subprocess
    result = execute(command, start_ts=time.perf_counter())
    assert result.success
    assert "dbt command: run --threads 3" in result.stdout


def test_explicit_override_is_preserved(unactivated_environment: Path) -> None:
    runner = DbtRunner(executable="custom-dbt")
    assert runner._build_command(["run"]) == ["custom-dbt", "run"]


def test_manifest_helper_parses_with_sibling(unactivated_environment: Path) -> None:
    load_production_manifest.cache_clear()
    try:
        assert load_production_manifest() == {"nodes": {}}
    finally:
        load_production_manifest.cache_clear()
