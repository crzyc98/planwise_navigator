"""On-disk records for Studio seed-ensemble jobs.

Each job owns ``workspaces/<ws>/ensembles/<job_id>/``::

    job.json         the EnsembleJob record (atomic temp-file + rename writes)
    work/            config, seeds, dbt overlay and per-seed databases;
                     removed when the job ends
    ensemble.duckdb  the aggregate, kept for completed/partial jobs
    job.log          tail of the CLI output, for support
"""

from __future__ import annotations

import logging
import re
import shutil
import threading
from pathlib import Path
from typing import Callable, Optional

from pydantic import ValidationError

from ...models.ensemble_job import EnsembleJob
from ..param_fit.jobs import atomic_write_json

logger = logging.getLogger(__name__)

JOBS_DIRNAME = "ensembles"
JOB_FILENAME = "job.json"
WORK_DIRNAME = "work"
LOG_FILENAME = "job.log"
ENSEMBLE_DB_FILENAME = "ensemble.duckdb"
JOB_ID_PATTERN = re.compile(r"^ens_[0-9a-f]{12}$")

_write_lock = threading.RLock()


def is_job_id(value: str) -> bool:
    """Job ids are generated tokens; anything else never reaches the disk."""
    return bool(JOB_ID_PATTERN.match(value))


class EnsembleJobStore:
    """Read and write ensemble job records under one workspaces root."""

    def __init__(self, workspaces_root: Path):
        self.workspaces_root = Path(workspaces_root)

    def jobs_root(self, workspace_id: str) -> Path:
        return self.workspaces_root / workspace_id / JOBS_DIRNAME

    def job_dir(self, workspace_id: str, job_id: str) -> Path:
        return self.jobs_root(workspace_id) / job_id

    def work_dir(self, workspace_id: str, job_id: str) -> Path:
        return self.job_dir(workspace_id, job_id) / WORK_DIRNAME

    def save(self, job: EnsembleJob) -> None:
        directory = self.job_dir(job.workspace_id, job.job_id)
        directory.mkdir(parents=True, exist_ok=True)
        with _write_lock:
            atomic_write_json(directory / JOB_FILENAME, job.model_dump(mode="json"))

    def load(self, workspace_id: str, job_id: str) -> Optional[EnsembleJob]:
        if not is_job_id(job_id):
            return None
        path = self.job_dir(workspace_id, job_id) / JOB_FILENAME
        if not path.is_file():
            return None
        try:
            return EnsembleJob.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            logger.warning("Unreadable ensemble job record: %s", path)
            return None

    def list_jobs(self, workspace_id: str) -> list[EnsembleJob]:
        root = self.jobs_root(workspace_id)
        if not root.is_dir():
            return []
        jobs = [self.load(workspace_id, entry.name) for entry in root.iterdir()]
        found = [job for job in jobs if job is not None]
        return sorted(found, key=lambda job: job.created_at, reverse=True)

    def update(
        self, workspace_id: str, job_id: str, mutate: Callable[[EnsembleJob], None]
    ) -> Optional[EnsembleJob]:
        """Read-modify-write one record under the store lock."""
        with _write_lock:
            job = self.load(workspace_id, job_id)
            if job is None:
                return None
            mutate(job)
            self.save(job)
            return job

    def remove_work(self, workspace_id: str, job_id: str) -> None:
        shutil.rmtree(self.work_dir(workspace_id, job_id), ignore_errors=True)
