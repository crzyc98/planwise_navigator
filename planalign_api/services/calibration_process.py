"""Process ownership and cancellation races for calibration workers."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger(__name__)
CANCEL_GRACE_SECONDS = 5.0
IS_POSIX = os.name == "posix"


class ProcessRegistry:
    """Which jobs this API process owns, and the child process behind each."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owned: set[str] = set()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled: set[str] = set()
        self._finalizing: set[str] = set()
        self._done: dict[str, threading.Event] = {}

    def claim(self, job_id: str) -> None:
        with self._lock:
            self._owned.add(job_id)
            self._done[job_id] = threading.Event()

    def owns(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._owned

    def owned(self) -> set[str]:
        with self._lock:
            return set(self._owned)

    def attach(self, job_id: str, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes[job_id] = process
            cancelled = job_id in self._cancelled
        if cancelled:
            _terminate(process)

    def was_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    def begin_finalize(self, job_id: str) -> bool:
        """Commit to an outcome; True if the job was cancelled first.

        After this, a cancel request can no longer change the outcome, so a
        job never reports "cancelled" to one caller and finishes anyway.
        """
        with self._lock:
            self._finalizing.add(job_id)
            return job_id in self._cancelled

    def cancel(self, job_id: str) -> Optional[threading.Event]:
        """Request cancellation; returns an event set once the job has ended."""
        with self._lock:
            if job_id not in self._owned:
                return None
            if job_id in self._finalizing:
                return self._done.get(job_id)  # too late: report the real outcome
            self._cancelled.add(job_id)
            process = self._processes.get(job_id)
            done = self._done.get(job_id)
        if process is not None:
            _terminate(process)
        return done

    def release(self, job_id: str) -> None:
        with self._lock:
            self._owned.discard(job_id)
            self._processes.pop(job_id, None)
            self._cancelled.discard(job_id)
            self._finalizing.discard(job_id)
            done = self._done.pop(job_id, None)
        if done is not None:
            done.set()


def _terminate(process: subprocess.Popen[str]) -> None:
    """Terminate the entire session, including children surviving the leader."""
    try:
        if not IS_POSIX:
            process.terminate()
            try:
                process.wait(timeout=CANCEL_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
            process.wait()
            return
        os.killpg(process.pid, signal.SIGTERM)
        deadline = time.monotonic() + CANCEL_GRACE_SECONDS
        while time.monotonic() < deadline:
            process.poll()  # Reap the leader before checking its process group.
            os.killpg(process.pid, 0)
            time.sleep(0.05)
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    except ProcessLookupError:
        process.wait()
    except PermissionError:
        logger.exception("Could not terminate calibration process %s", process.pid)
        raise


def terminate_orphan(pid: int, directory: Path) -> None:
    """Verify both module and job directory before touching a recorded PID."""
    try:
        process = psutil.Process(pid)
        command = process.cmdline()
        module = "planalign_orchestrator.calibration_worker"
        if command[1:4] != ["-m", module, str(directory)]:
            return
        if IS_POSIX:
            os.killpg(pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=CANCEL_GRACE_SECONDS)
    except (psutil.NoSuchProcess, ProcessLookupError):
        logger.debug("Calibration orphan %s already exited", pid)
