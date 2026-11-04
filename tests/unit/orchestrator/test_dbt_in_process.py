"""Worker-only dbt execution contracts."""

import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from planalign_orchestrator import calibration_worker
from planalign_orchestrator.dbt_in_process import invoke_dbt
from planalign_orchestrator.dbt_runner import DbtRunner

pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    "outcome,code", [("success", 0), ("failure", 1), ("returned", 2), ("raised", 2)]
)
def test_invoke_restores_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: str, code: int
) -> None:
    from dbt.adapters.duckdb.connections import DuckDBConnectionManager
    from dbt.cli.main import dbtRunner

    monkeypatch.setenv("EXISTING", "original")
    before, cwd = os.environ.copy(), Path.cwd()
    cleanup = Mock()

    def invoke(self: object, args: list[str]) -> SimpleNamespace:
        assert args == ["run", "--threads", "1"]
        assert Path.cwd() == tmp_path
        assert dict(os.environ) == {"EXISTING": "changed", "ADDED": "yes"}
        os.environ["DBT_ADDED"] = "temporary"
        print("diagnostic")
        if outcome == "raised":
            raise RuntimeError("invoke failed")
        return SimpleNamespace(
            success=outcome == "success",
            exception=RuntimeError("invoke failed") if outcome == "returned" else None,
        )

    monkeypatch.setattr(dbtRunner, "invoke", invoke)
    monkeypatch.setattr(DuckDBConnectionManager, "close_all_connections", cleanup)
    result = invoke_dbt(
        ["dbt", "run", "--threads", "1"],
        tmp_path,
        {"EXISTING": "changed", "ADDED": "yes"},
        start_ts=time.perf_counter(),
    )
    assert (result.return_code, result.success) == (code, code == 0)
    assert result.command == ["dbt", "run", "--threads", "1"]
    assert result.execution_time >= 0
    assert "diagnostic" in result.stdout
    assert ("invoke failed" in result.stderr) == (code == 2)
    assert os.environ == before and Path.cwd() == cwd
    cleanup.assert_called_once()


@pytest.mark.parametrize("flag", [None, "0", "true", "1"])
def test_flag_gating(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, flag: str | None
) -> None:
    monkeypatch.delenv("PLANALIGN_DBT_IN_PROCESS", raising=False)
    if flag is not None:
        monkeypatch.setenv("PLANALIGN_DBT_IN_PROCESS", flag)
    runner = DbtRunner(working_dir=tmp_path, db_manager=Mock())
    subprocess_call, in_process = Mock(), Mock()
    monkeypatch.setattr(runner, "_run_subprocess", subprocess_call)
    monkeypatch.setattr("planalign_orchestrator.dbt_in_process.invoke_dbt", in_process)
    runner._execute_once(
        ["run"],
        description=None,
        simulation_year=None,
        dbt_vars=None,
        threads=1,
        stream_output=False,
        on_line=None,
    )
    assert in_process.called == (flag == "1")
    assert subprocess_call.called == (flag != "1")
    runner.db_manager.close_all.assert_called_once()


def test_worker_enables_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PLANALIGN_DBT_IN_PROCESS", "0")
    monkeypatch.setattr(calibration_worker.WorkerRequest, "model_validate_json", Mock())
    (tmp_path / "request.json").write_text("{}")

    def execute(request: object) -> list[object]:
        assert os.environ["PLANALIGN_DBT_IN_PROCESS"] == "1"
        return []

    monkeypatch.setattr(calibration_worker, "execute", execute)
    assert calibration_worker.run_as_worker(tmp_path) == 0


def test_main_does_not_enable_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PLANALIGN_DBT_IN_PROCESS", raising=False)
    (tmp_path / "request.json").write_text("{}")  # invalid: main() fails fast
    assert calibration_worker.main(tmp_path) == 1
    assert "PLANALIGN_DBT_IN_PROCESS" not in os.environ
