"""Durable calibration jobs and child-process supervision."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal
from uuid import uuid4

from planalign_orchestrator.calibration_worker import WorkerRequest, atomic_write_json

from ..config import get_settings
from ..errors import sanitize_job_error
from ..models.calibration import CalibrationJob
from .calibration_process import (
    ProcessRegistry,
    _terminate,
    terminate_orphan,
    terminate_orphans_by_command,
    wait_for_group_exit,
)

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MAX_FINISHED_JOBS = 20
TERMINAL = {"completed", "failed", "cancelled"}
CommandFactory = Callable[[Path], list[str]]
_store_lock = threading.RLock()
_db_locks: dict[str, threading.Lock] = {}
registry = ProcessRegistry()


class JobStore:
    """Records under an injectable workspace root; no in-memory result cache."""

    def __init__(self, workspaces_root: Path) -> None:
        self.root = Path(workspaces_root).resolve() / "calibration_jobs"

    def job_dir(self, run_id: str) -> Path:
        if not run_id or not run_id.replace("_", "").isalnum():
            raise ValueError("Invalid calibration job id")
        return self.root / run_id

    def save(self, job: CalibrationJob) -> None:
        with _store_lock:
            directory = self.job_dir(job.run_id)
            directory.mkdir(parents=True, exist_ok=True)
            atomic_write_json(directory / "job.json", job.model_dump(mode="json"))

    def load(self, run_id: str) -> CalibrationJob | None:
        try:
            path = self.job_dir(run_id) / "job.json"
            return CalibrationJob.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            logger.warning("Unreadable calibration record %s", run_id, exc_info=True)
            return None

    def list_jobs(self) -> list[CalibrationJob]:
        return [
            job
            for path in self.root.glob("*/job.json")
            if (job := self.load(path.parent.name)) is not None
        ]

    def create(self, kind: Literal["run", "optimize"]) -> CalibrationJob:
        prefix = "cal" if kind == "run" else "autocal"
        job = CalibrationJob(
            run_id=f"{prefix}_{uuid4().hex[:12]}",
            kind=kind,
            status="queued",
            created_at=datetime.now(),
        )
        self.save(job)
        return job

    def update(self, run_id: str, **updates: object) -> CalibrationJob:
        with _store_lock:
            job = self.load(run_id)
            if job is None:
                raise LookupError(run_id)
            payload = job.model_dump()
            payload.update(updates)
            updated = CalibrationJob.model_validate(payload)
            self.save(updated)
            return updated

    def record_process(self, run_id: str, pid: int) -> None:
        atomic_write_json(self.job_dir(run_id) / "process.json", {"pid": pid})

    def recorded_process(self, run_id: str) -> int | None:
        path = self.job_dir(run_id) / "process.json"
        if not path.exists():
            return None
        pid = json.loads(path.read_text(encoding="utf-8"))["pid"]
        return (
            pid
            if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
            else None
        )

    def prune_finished(self, protect: set[str]) -> None:
        with _store_lock:
            finished = sorted(
                (job for job in self.list_jobs() if job.status in TERMINAL),
                key=lambda job: job.created_at,
                reverse=True,
            )
            for job in finished[_MAX_FINISHED_JOBS:]:
                if job.run_id not in protect:
                    shutil.rmtree(self.job_dir(job.run_id))


def build_worker_command(directory: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "planalign_orchestrator.calibration_worker",
        str(directory),
    ]


def get_job_store() -> JobStore:
    return JobStore(get_settings().workspaces_root)


def get_job_runner() -> JobRunner:
    return JobRunner(get_job_store(), registry, build_worker_command)


def _db_lock_for(database_path: str | None) -> threading.Lock | None:
    if database_path is None:
        return None
    with _store_lock:
        return _db_locks.setdefault(
            str(Path(database_path).resolve()), threading.Lock()
        )


def _cleanup(directory: Path) -> None:
    path = directory / "cleanup.json"
    if not path.exists():
        return
    metadata = json.loads(path.read_text(encoding="utf-8"))
    _remove_temporary(metadata.get("config"), metadata.get("database"))


def _remove_temporary(config: str | Path | None, database: str | Path | None) -> None:
    for key, value in (("config", config), ("database", database)):
        if value is None:
            continue
        try:
            Path(value).unlink(missing_ok=True)
            if key == "database":
                Path(f"{value}.wal").unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove calibration %s", key, exc_info=True)


class JobRunner:
    def __init__(
        self,
        store: JobStore,
        processes: ProcessRegistry,
        command_factory: CommandFactory = build_worker_command,
    ) -> None:
        self.store = store
        self.registry = processes
        self.command_factory = command_factory

    def start(
        self,
        job: CalibrationJob,
        request: WorkerRequest,
        database_path: str | None,
        workspace_config: Path | None,
        calibration_database: Path | None = None,
    ) -> None:
        directory = self.store.job_dir(job.run_id)
        self.registry.claim(job.run_id)
        try:
            atomic_write_json(
                directory / "cleanup.json",
                {
                    "config": str(workspace_config) if workspace_config else None,
                    "database": (
                        str(calibration_database) if calibration_database else None
                    ),
                },
            )
            atomic_write_json(
                directory / "request.json", request.model_dump(mode="json")
            )
            threading.Thread(
                target=self._run,
                args=(job, database_path),
                name=f"calibration-{job.run_id}",
                daemon=True,
            ).start()
        except Exception:
            _remove_temporary(workspace_config, calibration_database)
            try:
                self._fail(job)
            finally:
                self._finish(job)

    def _run(self, job: CalibrationJob, database_path: str | None) -> None:
        lock = _db_lock_for(database_path)
        acquired = False
        try:
            acquired = self._acquire(job.run_id, lock)
            code = None
            if not self.registry.was_cancelled(job.run_id):
                code = self._execute(job)
            self._finalize(job, code)
        except Exception:
            self._fail(job)
        finally:
            try:
                self._finish(job)
            finally:
                if acquired and lock is not None:
                    lock.release()

    def _acquire(self, run_id: str, lock: threading.Lock | None) -> bool:
        if lock is None:
            return False
        while not self.registry.was_cancelled(run_id):
            if lock.acquire(timeout=0.05):
                return True
        return False

    def _execute(self, job: CalibrationJob) -> int:
        directory = self.store.job_dir(job.run_id)
        self.store.update(job.run_id, status="running")
        with (directory / "worker.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                self.command_factory(directory),
                cwd=PROJECT_ROOT,
                env=os.environ.copy(),
                start_new_session=os.name == "posix",
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.registry.attach(job.run_id, process)
            try:
                self.store.record_process(job.run_id, process.pid)
            except Exception:
                _terminate(process)
                raise
            code = process.wait()
            wait_for_group_exit(process.pid)
            return code

    def _finalize(self, job: CalibrationJob, code: int | None) -> None:
        if self.registry.begin_finalize(job.run_id):
            self._terminal(job, status="cancelled")
            return
        directory = self.store.job_dir(job.run_id)
        if code == 0:
            result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
            field = "results" if job.kind == "run" else "outcome"
            self._terminal(job, status="completed", **{field: result})
        else:
            error = json.loads((directory / "error.json").read_text(encoding="utf-8"))
            if error["error_status"] not in (409, 500):
                raise ValueError("Invalid worker error status")
            self._terminal(
                job,
                status="failed",
                error=error["error"],
                error_status=error["error_status"],
            )

    def _terminal(self, job: CalibrationJob, **updates: object) -> None:
        _cleanup(self.store.job_dir(job.run_id))
        self.store.update(job.run_id, completed_at=datetime.now(), **updates)

    def _fail(self, job: CalibrationJob) -> None:
        message = sanitize_job_error(logger, job.run_id, event="Calibration job failed")
        if self.registry.begin_finalize(job.run_id):
            self._terminal(job, status="cancelled")
        else:
            self._terminal(job, status="failed", error=message, error_status=500)

    def _finish(self, job: CalibrationJob) -> None:
        try:
            (self.store.job_dir(job.run_id) / "process.json").unlink(missing_ok=True)
        finally:
            self.registry.release(job.run_id)
        self.store.prune_finished(self.registry.owned())

    def cancel(self, run_id: str) -> None:
        done = self.registry.cancel(run_id)
        if done is not None:
            done.wait()

    def recover(self) -> None:
        for job in self.store.list_jobs():
            if job.status in TERMINAL or self.registry.owns(job.run_id):
                continue
            pid = self.store.recorded_process(job.run_id)
            if pid is not None:
                terminate_orphan(pid, self.store.job_dir(job.run_id))
            else:
                terminate_orphans_by_command(self.store.job_dir(job.run_id))
            self._terminal(
                job,
                status="failed",
                error="API restarted during calibration",
                error_status=500,
            )
            (self.store.job_dir(job.run_id) / "process.json").unlink(missing_ok=True)
        self.store.prune_finished(self.registry.owned())
