"""On-disk job records for Studio fit/backtest jobs (#588).

Each job owns ``workspaces/<ws>/param_fits/<job_id>/``::

    job.json   the ParamFitJob record (atomic temp-file + rename writes)
    inputs/    base config + seeds snapshotted from the base scenario
    pack/      the parameter pack the CLI wrote (completed jobs only)
    work/      backtest scratch (removed when the job ends)
    job.log    tail of the subprocess output, for support

Records outlive the API process: packs are evidence an analyst may review for
days before applying, so a restart must not lose them (unlike the in-memory
calibration/optimizer registries).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from pydantic import ValidationError

from ...models.param_fit import TERMINAL_STATUSES, ParamFitJob

logger = logging.getLogger(__name__)

JOBS_DIRNAME = "param_fits"
JOB_FILENAME = "job.json"
INPUTS_DIRNAME = "inputs"
PACK_DIRNAME = "pack"
WORK_DIRNAME = "work"
LOG_FILENAME = "job.log"
PROCESS_FILENAME = "process.json"

_write_lock = threading.RLock()


class JobStore:
    """Read and write job records under one workspaces root."""

    def __init__(self, workspaces_root: Path):
        self.workspaces_root = Path(workspaces_root)

    # -- paths ---------------------------------------------------------------

    def jobs_root(self, workspace_id: str) -> Path:
        return self.workspaces_root / workspace_id / JOBS_DIRNAME

    def job_dir(self, workspace_id: str, job_id: str) -> Path:
        return self.jobs_root(workspace_id) / job_id

    def pack_dir(self, workspace_id: str, job_id: str) -> Path:
        return self.job_dir(workspace_id, job_id) / PACK_DIRNAME

    def work_dir(self, workspace_id: str, job_id: str) -> Path:
        return self.job_dir(workspace_id, job_id) / WORK_DIRNAME

    def inputs_dir(self, workspace_id: str, job_id: str) -> Path:
        return self.job_dir(workspace_id, job_id) / INPUTS_DIRNAME

    # -- records -------------------------------------------------------------

    def save(self, job: ParamFitJob) -> None:
        """Atomically write ``job`` (without any computed result)."""
        directory = self.job_dir(job.workspace_id, job.job_id)
        directory.mkdir(parents=True, exist_ok=True)
        payload = job.model_dump(mode="json", exclude={"result"})
        with _write_lock:
            _atomic_write_json(directory / JOB_FILENAME, payload)

    def load(self, workspace_id: str, job_id: str) -> Optional[ParamFitJob]:
        if not _is_safe_id(job_id):
            return None
        path = self.job_dir(workspace_id, job_id) / JOB_FILENAME
        if not path.is_file():
            return None
        try:
            return ParamFitJob.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            logger.warning("Unreadable param-fit job record: %s", path)
            return None

    def list_jobs(self, workspace_id: str) -> list[ParamFitJob]:
        root = self.jobs_root(workspace_id)
        if not root.is_dir():
            return []
        jobs = [self.load(workspace_id, entry.name) for entry in root.iterdir()]
        found = [job for job in jobs if job is not None]
        return sorted(found, key=lambda job: job.created_at, reverse=True)

    def update(
        self, workspace_id: str, job_id: str, mutate: Callable[[ParamFitJob], None]
    ) -> Optional[ParamFitJob]:
        """Read-modify-write one record under the store lock."""
        with _write_lock:
            job = self.load(workspace_id, job_id)
            if job is None:
                return None
            mutate(job)
            self.save(job)
            return job

    # -- child process -------------------------------------------------------

    def record_process(self, workspace_id: str, job_id: str, pid: int) -> None:
        """Remember the child's pid so a restarted API can stop an orphan."""
        path = self.job_dir(workspace_id, job_id) / PROCESS_FILENAME
        _atomic_write_json(path, {"pid": pid})

    def recorded_process(self, workspace_id: str, job_id: str) -> Optional[int]:
        path = self.job_dir(workspace_id, job_id) / PROCESS_FILENAME
        try:
            pid = json.loads(path.read_text(encoding="utf-8")).get("pid")
        except (OSError, ValueError):
            return None
        return pid if isinstance(pid, int) else None

    def clear_process(self, workspace_id: str, job_id: str) -> None:
        path = self.job_dir(workspace_id, job_id) / PROCESS_FILENAME
        path.unlink(missing_ok=True)

    # -- cleanup -------------------------------------------------------------

    def remove_artifacts(self, workspace_id: str, job_id: str) -> None:
        """Drop a job's pack and scratch but keep its record."""
        for path in (
            self.pack_dir(workspace_id, job_id),
            self.work_dir(workspace_id, job_id),
        ):
            shutil.rmtree(path, ignore_errors=True)

    def remove_scratch(self, workspace_id: str, job_id: str) -> None:
        for path in (
            self.work_dir(workspace_id, job_id),
            self.inputs_dir(workspace_id, job_id),
        ):
            shutil.rmtree(path, ignore_errors=True)

    def prune_finished(
        self, workspace_id: str, max_jobs: int, protect: Iterable[str] = ()
    ) -> list[str]:
        """Delete the oldest finished jobs beyond ``max_jobs``; never active ones."""
        protected = set(protect)
        finished = [
            job
            for job in self.list_jobs(workspace_id)
            if job.status in TERMINAL_STATUSES and job.job_id not in protected
        ]
        removed = [job.job_id for job in finished[max_jobs:]]
        for job_id in removed:
            shutil.rmtree(self.job_dir(workspace_id, job_id), ignore_errors=True)
        return removed


def _atomic_write_json(path: Path, payload: Any) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".job-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _is_safe_id(value: str) -> bool:
    """Job and history ids are generated tokens; reject anything path-like."""
    return bool(value) and value.replace("_", "").isalnum()
