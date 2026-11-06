"""Calibration worker transport, persistence, cancellation, and recovery."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import psutil
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.routers import calibration
from planalign_api.services.calibration_jobs import JobRunner, JobStore
from planalign_api.services.calibration_process import ProcessRegistry
from planalign_orchestrator import calibration_worker as worker
from planalign_orchestrator.calibration_optimizer import (
    AutoCalibrationResult,
    AutoCalibrationSettings,
)
from planalign_orchestrator.calibration_runner import (
    CalibrationRun,
    PerYearCompensationResult,
)
from planalign_orchestrator.exceptions import ConfigurationError

pytestmark = pytest.mark.fast
ROW = PerYearCompensationResult(
    simulation_year=2025, avg_compensation=123.4, headcount=2
)


@pytest.fixture(autouse=True)
def isolate_worker_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct main() tests must not enable in-process dbt for later API tests."""
    monkeypatch.setenv("PLANALIGN_DBT_IN_PROCESS", "0")


def request(kind: str = "run") -> worker.WorkerRequest:
    return worker.WorkerRequest.model_validate(
        {
            "kind": kind,
            "run": {
                "start_year": 2025,
                "end_year": 2026,
                "params": {"cola_rate": 0.031234},
            },
            "settings": {"target_workforce_growth": 0.03, "target_comp_growth": 0.04},
        }
    )


def wait_for(predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 10
    while not predicate():
        assert time.monotonic() < deadline, "Job did not reach expected state"
        time.sleep(0.01)


@pytest.mark.parametrize(
    "failure,status",
    [
        (None, None),
        (ConfigurationError("guard"), 409),
        (RuntimeError("private SQL"), 500),
    ],
)
def test_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception | None,
    status: int | None,
) -> None:
    received = []

    class Engine:
        def __init__(self, run: CalibrationRun, threads: int) -> None:
            received.append((run, threads))

        def run_calibration(self) -> list[PerYearCompensationResult]:
            if failure is not None:
                raise failure
            return [ROW]

    monkeypatch.setattr(worker, "CalibrationRunner", Engine)
    worker.atomic_write_json(
        tmp_path / "request.json", request().model_dump(mode="json")
    )
    assert worker.main(tmp_path) == (0 if status is None else 1)
    assert received == [(request().run, 1)]
    if status is None:
        assert json.loads((tmp_path / "result.json").read_text()) == [
            ROW.model_dump(mode="json")
        ]
    else:
        error = json.loads((tmp_path / "error.json").read_text())
        assert error["error_status"] == status
        assert "private SQL" not in error["error"]
        if status == 409:
            assert error["error"] == str(failure)


def test_worker_optimize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    received = []
    outcome = AutoCalibrationResult(
        converged=True,
        status="converged",
        message="done",
        best_params=request().run.params,
        achieved_comp_growth_pct=4.0,
        target_comp_growth_pct=4.0,
        max_abs_error_pct=0.0,
        start_year=2025,
        end_year=2026,
        iterations=[],
        results=[ROW],
    )

    class Engine:
        def __init__(
            self, run: CalibrationRun, settings: AutoCalibrationSettings, threads: int
        ) -> None:
            received.append((run, settings, threads))

        def optimize(self) -> AutoCalibrationResult:
            return outcome

    monkeypatch.setattr(worker, "AutoCalibrator", Engine)
    value = request("optimize")
    worker.atomic_write_json(tmp_path / "request.json", value.model_dump(mode="json"))
    assert worker.main(tmp_path) == 0
    assert received == [(value.run, value.settings, 1)]
    assert json.loads((tmp_path / "result.json").read_text()) == outcome.model_dump(
        mode="json"
    )


def make_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: Callable[[Path], list[str]],
) -> tuple[TestClient, JobRunner]:
    store = JobStore(tmp_path)
    runner = JobRunner(store, ProcessRegistry(), command)
    monkeypatch.setattr(calibration, "get_job_store", lambda: store)
    monkeypatch.setattr(calibration, "get_job_runner", lambda: runner)
    app = FastAPI()
    app.include_router(calibration.router)
    return TestClient(app), runner


def result_command(directory: Path) -> list[str]:
    payload = json.dumps([ROW.model_dump(mode="json")])
    return [
        sys.executable,
        "-c",
        "from pathlib import Path; "
        f"Path({str(directory / 'result.json')!r}).write_text({payload!r})",
    ]


@pytest.mark.parametrize("failure", [False, True])
def test_router_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    def command(directory: Path) -> list[str]:
        if not failure:
            return result_command(directory)
        return [
            sys.executable,
            "-c",
            "from pathlib import Path; "
            f"Path({str(directory / 'error.json')!r}).write_text("
            '\'{"error": "guard", "error_status": 409}\'); raise SystemExit(1)',
        ]

    client, runner = make_client(tmp_path, monkeypatch, command)
    response = client.post(
        "/calibration/run", json={"start_year": 2025, "end_year": 2026}
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    wait_for(lambda: not runner.registry.owns(run_id))
    job = client.get(f"/calibration/runs/{run_id}").json()
    assert job["status"] == ("failed" if failure else "completed")
    assert (
        (job["error_status"] == 409)
        if failure
        else (job["results"] == [ROW.model_dump(mode="json")])
    )
    assert JobStore(tmp_path).load(run_id).model_dump(mode="json") == job
    assert client.post(f"/calibration/runs/{run_id}/cancel").json() == job
    assert client.post("/calibration/runs/unknown/cancel").status_code == 404


def test_cancel_sleeping_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, runner = make_client(
        tmp_path,
        monkeypatch,
        lambda _: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    database, config = tmp_path / "temp.duckdb", tmp_path / "temp.yaml"
    database.touch()
    Path(f"{database}.wal").touch()
    config.touch()
    job = runner.store.create("run")
    runner.start(job, request(), str(database), config, database)
    wait_for(lambda: runner.store.recorded_process(job.run_id) is not None)
    pid = runner.store.recorded_process(job.run_id)
    response = client.post(f"/calibration/runs/{job.run_id}/cancel")
    assert response.json()["status"] == "cancelled"
    assert not psutil.pid_exists(pid)
    assert not database.exists() and not config.exists()
    assert not Path(f"{database}.wal").exists()


def test_cancel_queued_job(tmp_path: Path) -> None:
    runner = JobRunner(JobStore(tmp_path), ProcessRegistry(), result_command)
    from planalign_api.services.calibration_jobs import _db_lock_for

    lock = _db_lock_for(str(tmp_path / "shared.duckdb"))
    lock.acquire()
    try:
        job = runner.store.create("run")
        runner.start(job, request(), str(tmp_path / "shared.duckdb"), None)
        runner.cancel(job.run_id)
        assert runner.store.load(job.run_id).status == "cancelled"
        assert runner.store.recorded_process(job.run_id) is None
    finally:
        lock.release()


def test_recovery(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job = store.create("run")
    database = tmp_path / "temp.duckdb"
    database.touch()
    worker.atomic_write_json(
        store.job_dir(job.run_id) / "cleanup.json", {"database": str(database)}
    )
    store.record_process(job.run_id, os.getpid())  # Reused/unrelated PID must survive.
    runner = JobRunner(JobStore(tmp_path), ProcessRegistry())
    runner.recover()
    restored = store.load(job.run_id)
    assert restored.status == "failed"
    assert restored.error == "API restarted during calibration"
    assert restored.error_status == 500
    assert not database.exists()


def test_cancel_after_finalization_reports_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = JobRunner(JobStore(tmp_path), ProcessRegistry(), result_command)
    job = runner.store.create("run")
    finalizing, proceed, finished = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    terminal = runner._terminal

    def delayed_terminal(job: calibration.CalibrationJob, **updates: object) -> None:
        finalizing.set()
        assert proceed.wait(5)
        terminal(job, **updates)

    monkeypatch.setattr(runner, "_terminal", delayed_terminal)
    runner.start(job, request(), None, None)
    assert finalizing.wait(5)

    def cancel() -> None:
        runner.cancel(job.run_id)
        finished.set()

    thread = threading.Thread(target=cancel)
    thread.start()
    assert not finished.wait(0.05)
    proceed.set()
    thread.join(timeout=5)
    assert finished.is_set()
    assert runner.store.load(job.run_id).status == "completed"


def test_retention(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    active = store.create("run")
    for _ in range(23):
        job = store.create("run")
        store.update(job.run_id, status="cancelled")
    store.prune_finished(set())
    assert len(store.list_jobs()) == 21
    assert store.load(active.run_id).status == "queued"
    assert len(list(store.root.iterdir())) == 21


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group escalation")
def test_cancel_escalates_to_sigkill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from planalign_api.services import calibration_process

    monkeypatch.setattr(calibration_process, "CANCEL_GRACE_SECONDS", 0.1)
    ready = tmp_path / "ready"
    script = (
        "import signal, time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(ready)!r}).touch(); time.sleep(60)"
    )
    client, runner = make_client(
        tmp_path, monkeypatch, lambda _: [sys.executable, "-c", script]
    )
    job = runner.store.create("run")
    runner.start(job, request(), None, None)
    wait_for(ready.exists)
    pid = runner.store.recorded_process(job.run_id)
    assert os.getpgid(pid) == pid
    response = client.post(f"/calibration/runs/{job.run_id}/cancel")
    assert response.json()["status"] == "cancelled"
    assert not psutil.pid_exists(pid)


@pytest.mark.parametrize("matching", [True, False])
def test_orphan_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, matching: bool
) -> None:
    from planalign_api.services import calibration_process

    stopped = []

    class Process:
        def cmdline(self) -> list[str]:
            module = (
                "planalign_orchestrator.calibration_worker" if matching else "other"
            )
            return [sys.executable, "-m", module, str(tmp_path)]

        def kill(self) -> None:
            stopped.append("killed")

        def wait(self, timeout: float) -> None:
            stopped.append("waited")

    monkeypatch.setattr(calibration_process.psutil, "Process", lambda pid: Process())
    monkeypatch.setattr(
        calibration_process.os, "killpg", lambda pid, sig: stopped.append("killed")
    )
    calibration_process.terminate_orphan(12345, tmp_path)
    assert stopped == (["killed", "waited"] if matching else [])


def test_lifespan_recovers_only_unowned_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from planalign_api import config
    from planalign_api.main import create_app
    from planalign_api.services import calibration_jobs

    monkeypatch.setattr(
        config, "settings", config.APISettings(workspaces_root=tmp_path)
    )
    monkeypatch.setattr(calibration_jobs, "registry", ProcessRegistry())
    store = JobStore(tmp_path)
    abandoned, owned, completed = (store.create("run") for _ in range(3))
    store.update(completed.run_id, status="completed", results=[ROW])
    calibration_jobs.registry.claim(owned.run_id)
    with TestClient(create_app()):
        assert store.load(abandoned.run_id).error == "API restarted during calibration"
        assert store.load(owned.run_id).status == "queued"
        assert store.load(completed.run_id).status == "completed"
    calibration_jobs.registry.release(owned.run_id)


@pytest.mark.parametrize(
    "script", ["raise SystemExit(2)", "print('exited without result')"]
)
def test_missing_worker_output_is_safe_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script: str,
) -> None:
    client, runner = make_client(
        tmp_path, monkeypatch, lambda _: [sys.executable, "-c", script]
    )
    response = client.post(
        "/calibration/run", json={"start_year": 2025, "end_year": 2026}
    )
    run_id = response.json()["run_id"]
    wait_for(lambda: not runner.registry.owns(run_id))
    job = client.get(f"/calibration/runs/{run_id}").json()
    assert job["status"] == "failed" and job["error_status"] == 500
    assert str(tmp_path) not in job["error"]


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")
def test_wait_for_group_exit_outlives_leader() -> None:
    """A descendant that survives the leader keeps the group alive until it exits."""
    import subprocess

    from planalign_api.services import calibration_process

    script = (
        "import subprocess, sys; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.5)'])"
    )
    leader = subprocess.Popen([sys.executable, "-c", script], start_new_session=True)
    leader.wait()
    started = time.monotonic()
    calibration_process.wait_for_group_exit(leader.pid)
    assert time.monotonic() - started > 0.2
    with pytest.raises(ProcessLookupError):
        os.killpg(leader.pid, 0)


def test_recovery_without_recorded_pid_finds_worker_by_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from planalign_api.services import calibration_process

    store = JobStore(tmp_path)
    job = store.create("run")
    found = []
    monkeypatch.setattr(
        calibration_process,
        "terminate_orphan",
        lambda pid, directory: found.append((pid, directory)),
    )

    class Proc:
        pid = 4242
        info = {
            "cmdline": [
                sys.executable,
                "-m",
                calibration_process.WORKER_MODULE,
                str(store.job_dir(job.run_id)),
            ]
        }

    class Other:
        pid = 1
        info = {"cmdline": None}

    monkeypatch.setattr(
        calibration_process.psutil, "process_iter", lambda attrs: [Other(), Proc()]
    )
    JobRunner(JobStore(tmp_path), ProcessRegistry()).recover()
    assert found == [(4242, store.job_dir(job.run_id))]
    assert store.load(job.run_id).status == "failed"


def test_enqueue_failure_removes_temp_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file, database = tmp_path / "cfg.yaml", tmp_path / "temp.duckdb"
    config_file.touch()
    database.touch()

    class FailingStore:
        def create(self, kind: str) -> None:
            raise OSError("disk full")

    monkeypatch.setattr(calibration, "get_job_store", lambda: FailingStore())
    target = calibration._ResolvedTarget.__new__(calibration._ResolvedTarget)
    object.__setattr__(target, "database_path", database)
    with pytest.raises(OSError):
        calibration._enqueue(request(), target, str(database), config_file)
    assert not config_file.exists()
    assert not database.exists()
