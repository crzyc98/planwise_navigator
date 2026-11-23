"""Background jobs get no API credentials and stop with all their descendants."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import psutil
import pytest

from planalign_api.services import child_env
from planalign_api.services.ensemble_jobs import runner as ensemble_runner
from planalign_api.services.param_fit import runner as fit_runner
from planalign_api.services.process_groups import group_alive, new_session_kwargs
from planalign_api.services.simulation import excel_export_worker, run_execution
from planalign_api.services.simulation.subprocess_utils import create_subprocess
from planalign_core.process_security import is_child_env_denied, scrub_child_env

pytestmark = [pytest.mark.fast]

TOKEN = "PLANALIGN_API_TOKEN"
POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="process groups")
CHECK_ENV = (
    "import os, sys; "
    "sys.exit(1 if any(k.startswith('PLANALIGN_API_') and 'TOKEN' in k "
    "for k in os.environ) else 0)"
)


@pytest.fixture
def secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN, "t" * 40)
    monkeypatch.setenv("PLANALIGN_API_OTHER_TOKEN", "x")
    monkeypatch.setenv("NAV_FOO", "keep")
    monkeypatch.setenv("DATABASE_PATH", "/tmp/keep.duckdb")


def _assert_clean(env: dict[str, str]) -> None:
    assert TOKEN not in env
    assert "PLANALIGN_API_OTHER_TOKEN" not in env


# -- environment ---------------------------------------------------------------


@pytest.mark.parametrize(
    "name,denied",
    [
        (TOKEN, True),
        ("planalign_api_token", True),
        ("PLANALIGN_API_SESSION_SECRET", True),
        ("PLANALIGN_API_DB_PASSWORD", True),
        ("PLANALIGN_API_PORT", False),
        ("PLANALIGN_TOKEN_CACHE", False),
        ("NAV_FOO", False),
        ("DATABASE_PATH", False),
    ],
)
def test_denylist(name: str, denied: bool) -> None:
    assert is_child_env_denied(name) is denied


def test_build_child_env_strips_token_and_keeps_engine_vars(secret_env: None) -> None:
    env = child_env.build_child_env({"EXTRA": "1", "PLANALIGN_API_X_SECRET": "s"})
    _assert_clean(env)
    assert "PLANALIGN_API_X_SECRET" not in env
    assert env["NAV_FOO"] == "keep"
    assert env["DATABASE_PATH"] == "/tmp/keep.duckdb"
    assert env["EXTRA"] == "1"


def test_simulation_and_ensemble_env(secret_env: None, tmp_path: Path) -> None:
    sim = run_execution.build_env(tmp_path, "run-1", tmp_path / "db.duckdb")
    _assert_clean(sim)
    assert sim["DATABASE_PATH"] == str(tmp_path / "db.duckdb")
    assert sim["NAV_FOO"] == "keep"
    paths = ensemble_runner.JobPaths(
        config=tmp_path / "c.yaml",
        output_root=tmp_path,
        dbt_project=tmp_path,
        work_dir=tmp_path,
        database=tmp_path / "db.duckdb",
    )

    class Job:
        job_id = "job-1"

    _assert_clean(ensemble_runner.build_job_env(Job(), paths))  # type: ignore[arg-type]


def test_param_fit_env(secret_env: None, tmp_path: Path) -> None:
    env = fit_runner.build_env(tmp_path)
    _assert_clean(env)
    assert env["NAV_FOO"] == "keep"


def test_dbt_runner_env(secret_env: None, tmp_path: Path) -> None:
    from planalign_orchestrator.dbt_runner import DbtRunner

    env = DbtRunner(working_dir=tmp_path)._build_subprocess_env()
    _assert_clean(env)
    assert env["NAV_FOO"] == "keep"


def test_simulation_child_sees_no_token(secret_env: None, tmp_path: Path) -> None:
    async def run() -> int:
        process, lines = await create_subprocess(
            [sys.executable, "-c", CHECK_ENV],
            str(tmp_path),
            run_execution.build_env(tmp_path),
            new_session=True,
        )
        async for _ in lines:
            pass
        return await process.wait()

    assert asyncio.run(run()) == 0


def test_census_rollforward_child_sees_no_token(
    secret_env: None, tmp_path: Path
) -> None:
    from planalign_api.services import census_rollforward_jobs

    env = run_execution.build_env(tmp_path)
    asyncio.run(census_rollforward_jobs.run_cli([sys.executable, "-c", CHECK_ENV], env))


def test_calibration_child_sees_no_token(
    secret_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.api.test_calibration_jobs import make_client, request, wait_for

    marker = tmp_path / "env-checked"
    script = (
        "import os; from pathlib import Path; "
        f"tmp = Path({str(marker)!r} + '.tmp'); "
        f"tmp.write_text(str(os.environ.get({TOKEN!r}))); "
        f"tmp.replace({str(marker)!r})"
    )
    _client, runner = make_client(
        tmp_path, monkeypatch, lambda _: [sys.executable, "-c", script]
    )
    job = runner.store.create("run")
    runner.start(job, request(), None, None)
    wait_for(marker.exists)
    assert marker.read_text() == "None"


def test_excel_export_worker_drops_token(secret_env: None) -> None:
    try:
        executor = excel_export_worker._get_executor()
        assert executor.submit(os.getenv, TOKEN).result(timeout=60) is None
        assert executor.submit(os.getenv, "NAV_FOO").result(timeout=60) == "keep"
    finally:
        excel_export_worker.shutdown_excel_export_executor()


def test_scrub_child_env_is_a_copy() -> None:
    source = {TOKEN: "x", "A": "1"}
    assert scrub_child_env(source) == {"A": "1"}
    assert TOKEN in source


# -- stopping process trees ----------------------------------------------------


def _parent_script(child_pid_file: Path) -> str:
    """A parent that starts a SIGTERM-ignoring sleeper and records its PID."""
    child = (
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(120)"
    )
    return (
        "import subprocess, sys, time; from pathlib import Path; "
        f"c = subprocess.Popen([sys.executable, '-c', {child!r}]); "
        f"Path({str(child_pid_file)!r}).write_text(str(c.pid)); "
        "time.sleep(120)"
    )


def _wait_until(condition: Callable[[], bool], timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.05)


def _gone(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


@POSIX_ONLY
def test_simulation_cancel_kills_grandchild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_execution, "CANCEL_GRACE_SECONDS", 0.5)
    child_pid_file = tmp_path / "child.pid"
    registry = run_execution.ActiveProcessRegistry()

    async def run() -> tuple[int, int, bool]:
        process, _lines = await create_subprocess(
            [sys.executable, "-c", _parent_script(child_pid_file)],
            str(tmp_path),
            dict(os.environ),
            new_session=True,
        )
        registry.register("run-1", process)
        while not child_pid_file.exists() or not child_pid_file.read_text():
            await asyncio.sleep(0.05)
        cancelled = await registry.cancel("run-1")
        return process.pid, int(child_pid_file.read_text()), cancelled

    leader, child, cancelled = asyncio.run(run())
    assert cancelled
    assert _gone(leader)
    assert _gone(child)
    assert registry.is_cancelled("run-1")


@POSIX_ONLY
def test_registry_stop_all_kills_tracked_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_execution, "CANCEL_GRACE_SECONDS", 0.5)
    child_pid_file = tmp_path / "child.pid"
    registry = run_execution.ActiveProcessRegistry()

    async def run() -> tuple[int, int]:
        process, _lines = await create_subprocess(
            [sys.executable, "-c", _parent_script(child_pid_file)],
            str(tmp_path),
            dict(os.environ),
            new_session=True,
        )
        registry.register("run-1", process)
        while not child_pid_file.exists() or not child_pid_file.read_text():
            await asyncio.sleep(0.05)
        await registry.stop_all()
        return process.pid, int(child_pid_file.read_text())

    leader, child = asyncio.run(run())
    assert _gone(leader)
    assert _gone(child)
    assert not registry.processes


@POSIX_ONLY
def test_param_fit_terminate_kills_grandchild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fit_runner, "CANCEL_GRACE_SECONDS", 0.5)
    child_pid_file = tmp_path / "child.pid"
    process = subprocess.Popen(
        [sys.executable, "-c", _parent_script(child_pid_file)],
        text=True,
        **new_session_kwargs(),
    )
    try:
        _wait_until(lambda: child_pid_file.exists() and child_pid_file.read_text())
        child = int(child_pid_file.read_text())
        fit_runner._terminate(process)
        _wait_until(lambda: _gone(process.pid) and _gone(child))
        # The runner reaps the leader on its own thread; the group only reads
        # as empty once that has happened.
        _wait_until(lambda: not group_alive(process.pid))
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
