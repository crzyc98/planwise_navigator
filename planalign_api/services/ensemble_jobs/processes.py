"""Find and stop every process an ensemble job started.

Seed workers run in their own sessions and outlive a crashed CLI parent, so
neither the parent pid nor its process group reaches them all. Instead each
job's CLI is started with ``PLANALIGN_ENSEMBLE_JOB=<job_id>`` in its
environment, which every descendant inherits. Matching on that unique id means
a recycled pid can never take an unrelated process down.
"""

from __future__ import annotations

import logging
import os

import psutil

logger = logging.getLogger(__name__)

JOB_ENV_MARKER = "PLANALIGN_ENSEMBLE_JOB"
CANCEL_GRACE_SECONDS = 5.0


def job_processes(job_id: str) -> list[psutil.Process]:
    """Live processes started for ``job_id`` (readable ones of this user)."""
    found: list[psutil.Process] = []
    for process in psutil.process_iter():
        if process.pid == os.getpid():
            continue
        try:
            if process.environ().get(JOB_ENV_MARKER) == job_id:
                found.append(process)
        except psutil.Error:
            continue  # gone, a zombie, or another user's process
    return found


def signal_job(job_id: str) -> None:
    """Ask every process of the job to stop; does not wait."""
    for process in job_processes(job_id):
        _signal(process, "terminate")


def stop_job(job_id: str) -> bool:
    """SIGTERM the job's processes, SIGKILL survivors after a grace period,
    and wait (bounded) for them to go. True when none are left."""
    processes = job_processes(job_id)
    if not processes:
        return True
    for process in processes:
        _signal(process, "terminate")
    _, alive = psutil.wait_procs(processes, timeout=CANCEL_GRACE_SECONDS)
    for process in alive:
        _signal(process, "kill")
    _, alive = psutil.wait_procs(alive, timeout=CANCEL_GRACE_SECONDS)
    if alive:
        logger.warning(
            "Ensemble %s: processes %s did not exit",
            job_id,
            [process.pid for process in alive],
        )
    return not alive


def _signal(process: psutil.Process, action: str) -> None:
    try:
        getattr(process, action)()
    except psutil.Error as exc:
        logger.debug("Could not %s ensemble process %s: %s", action, process.pid, exc)
