"""Run one seed ensemble as a cancellable ``planalign simulate`` subprocess.

The job waits for a simulation slot like any Studio run, then holds it for
every seed, so an ensemble never runs beside another simulation at the default
``max_concurrent_simulations`` of 1. The CLI is told to run at most that many
seeds at once (``--parallel``) and prints one ``PLANALIGN_ENSEMBLE_PROGRESS|``
record per seed event (``planalign_ensemble.progress``), which becomes the
job's progress.
"""

from __future__ import annotations

import logging
import shutil
import sys
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional

import duckdb
import psutil

from planalign_ensemble.progress import ENV_FLAG, parse_progress_line

from ...errors import sanitize_job_error
from ...models.ensemble_job import EnsembleError, EnsembleJob, EnsembleOutput
from ..simulation.run_execution import build_env
from ..simulation.run_slots import simulation_slot
from ..simulation.subprocess_utils import create_subprocess, wait_subprocess
from .store import LOG_FILENAME, EnsembleJobStore

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CANCEL_GRACE_SECONDS = 5.0
LOG_TAIL_LINES = 400

CancelOutcome = Literal["not_owned", "queued", "running", "finalizing"]


@dataclass(frozen=True)
class JobPaths:
    work_dir: Path
    config: Path
    dbt_project: Path
    output_root: Path
    database: Path


CommandFactory = Callable[[EnsembleJob, JobPaths], list[str]]


class EnsembleRegistry:
    """Which ensemble jobs this API process owns, and the child behind each."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owned: set[str] = set()
        self._started: set[str] = set()
        self._cancelled: set[str] = set()
        self._finalizing: set[str] = set()
        self._pids: dict[str, int] = {}
        self._done: dict[str, threading.Event] = {}

    def claim(self, job_id: str) -> None:
        with self._lock:
            self._owned.add(job_id)
            self._done[job_id] = threading.Event()

    def owns(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._owned

    def begin(self, job_id: str) -> bool:
        """Take the slot for real; False if the job was cancelled while queued."""
        with self._lock:
            if job_id in self._cancelled:
                return False
            self._started.add(job_id)
            return True

    def attach(self, job_id: str, pid: int) -> None:
        with self._lock:
            self._pids[job_id] = pid
            cancelled = job_id in self._cancelled
        if cancelled:
            stop_process_tree(pid)

    def cancel(self, job_id: str) -> tuple[CancelOutcome, Optional[threading.Event]]:
        """Request cancellation; the event is set once the job has ended."""
        with self._lock:
            if job_id not in self._owned:
                return "not_owned", None
            done = self._done.get(job_id)
            if job_id in self._finalizing:
                return "finalizing", done
            self._cancelled.add(job_id)
            started = job_id in self._started
            pid = self._pids.get(job_id)
        if pid is not None:
            stop_process_tree(pid)
        return ("running" if started else "queued"), done

    def begin_finalize(self, job_id: str) -> bool:
        """Commit to an outcome; True if the job was cancelled first."""
        with self._lock:
            self._finalizing.add(job_id)
            return job_id in self._cancelled

    def release(self, job_id: str) -> None:
        with self._lock:
            for members in (self._owned, self._started, self._cancelled):
                members.discard(job_id)
            self._finalizing.discard(job_id)
            self._pids.pop(job_id, None)
            done = self._done.pop(job_id, None)
        if done is not None:
            done.set()


default_registry = EnsembleRegistry()


def build_cli_command(job: EnsembleJob, paths: JobPaths) -> list[str]:
    """The ``planalign simulate --seed-list`` invocation for one job."""
    years = (
        f"{job.start_year}-{job.end_year}"
        if job.start_year != job.end_year
        else str(job.start_year)
    )
    return [
        sys.executable,
        "-m",
        "planalign_cli",
        "simulate",
        years,
        "--config",
        str(paths.config),
        "--database",
        str(paths.output_root),
        "--dbt-project-dir",
        str(paths.dbt_project),
        "--seed-list",
        ",".join(str(seed) for seed in job.seeds),
        "--parallel",
        str(job.estimate.workers),
    ]


def build_job_env(paths: JobPaths) -> dict[str, str]:
    env = build_env(PROJECT_ROOT, database_path=paths.work_dir / "guard.duckdb")
    env.pop("PLANALIGN_STRUCTURED_TELEMETRY", None)
    env[ENV_FLAG] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


class EnsembleJobRunner:
    """Wait for a slot, run the CLI, and record the job's outcome."""

    def __init__(
        self,
        store: EnsembleJobStore,
        registry: EnsembleRegistry,
        command_factory: CommandFactory = build_cli_command,
    ):
        self.store = store
        self.registry = registry
        self.command_factory = command_factory

    async def run(self, job: EnsembleJob, paths: JobPaths) -> None:
        """Run ``job``; the caller has already claimed it in the registry."""
        try:
            async with simulation_slot():
                if not self.registry.begin(job.job_id):
                    logger.info("Ensemble %s was cancelled while queued", job.job_id)
                    return
                await self._run_started(job, paths)
        finally:
            self.registry.release(job.job_id)

    async def _run_started(self, job: EnsembleJob, paths: JobPaths) -> None:
        tail: deque[str] = deque(maxlen=LOG_TAIL_LINES)
        try:
            return_code = await self._execute(job, paths, tail)
            self._finalize(job, paths, return_code, tail)
        except Exception:  # noqa: BLE001 -- surfaced on the job record
            pid = self.store.recorded_process(job.workspace_id, job.job_id)
            if pid is not None:
                stop_process_tree(pid)
            message = sanitize_job_error(logger, job.job_id, event="Ensemble failed")
            self._fail(job, EnsembleError(kind="unexpected", message=message))
        finally:
            self._write_log(job, tail)
            self.store.clear_process(job.workspace_id, job.job_id)
            self.store.remove_work(job.workspace_id, job.job_id)

    async def _execute(
        self, job: EnsembleJob, paths: JobPaths, tail: deque[str]
    ) -> int:
        self.store.update(job.workspace_id, job.job_id, _mark_running)
        process, lines = await create_subprocess(
            self.command_factory(job, paths), str(PROJECT_ROOT), build_job_env(paths)
        )
        self.store.record_process(job.workspace_id, job.job_id, process.pid)
        self.registry.attach(job.job_id, process.pid)
        async for raw in lines:
            line = raw.decode("utf-8", errors="replace")
            record = parse_progress_line(line)
            if record is not None:
                self.store.update(
                    job.workspace_id, job.job_id, lambda t: _apply_record(t, record)
                )
            elif line.strip():
                tail.append(line.rstrip())
        return await wait_subprocess(process)

    def _finalize(
        self, job: EnsembleJob, paths: JobPaths, return_code: int, tail: deque[str]
    ) -> None:
        if self.registry.begin_finalize(job.job_id):
            self._set_terminal(job, "cancelled")
            return
        if return_code in (0, 2):
            output = collect_output(paths)
            if output is not None:
                self._succeed(job, output, partial=return_code == 2)
                return
            tail.append("The ensemble finished without an aggregate database.")
        self._fail(job, _classify_failure(job, return_code, tail, paths))

    def _succeed(self, job: EnsembleJob, output: EnsembleOutput, partial: bool) -> None:
        def _mark(target: EnsembleJob) -> None:
            _terminal(target, "partial" if partial else "completed")
            target.output = output
            target.progress.current_seed = None
            if partial:
                total, failed = target.seed_count, len(target.failed_seeds)
                target.error = EnsembleError(
                    kind="seeds_failed",
                    message=(
                        f"{failed} of {total} seeds failed; the results use the "
                        f"{total - failed} that finished."
                    ),
                )

        self.store.update(job.workspace_id, job.job_id, _mark)

    def _set_terminal(self, job: EnsembleJob, status: str) -> None:
        self.store.update(
            job.workspace_id, job.job_id, lambda target: _terminal(target, status)
        )

    def _fail(self, job: EnsembleJob, error: EnsembleError) -> None:
        def _mark(target: EnsembleJob) -> None:
            _terminal(target, "failed")
            target.error = error

        self.store.update(job.workspace_id, job.job_id, _mark)

    def _write_log(self, job: EnsembleJob, tail: deque[str]) -> None:
        directory = self.store.job_dir(job.workspace_id, job.job_id)
        if directory.is_dir():
            (directory / LOG_FILENAME).write_text("\n".join(tail) + "\n", "utf-8")


def collect_output(paths: JobPaths) -> Optional[EnsembleOutput]:
    """Keep the aggregate beside the job record and read its identity."""
    candidates = sorted(paths.output_root.glob("*/ensemble.duckdb"))
    if len(candidates) != 1:
        return None
    for suffix in ("", ".wal"):
        source = candidates[0].with_name(candidates[0].name + suffix)
        if source.exists():
            shutil.move(str(source), str(paths.database) + suffix)
    with duckdb.connect(str(paths.database), read_only=True) as connection:
        rows = connection.execute(
            "SELECT DISTINCT ensemble_id, scenario_id FROM fct_metric_distributions"
        ).fetchall()
    if len(rows) != 1:
        return None
    ensemble_id, scenario_id = rows[0]
    return EnsembleOutput(
        database_path=str(paths.database.resolve()),
        ensemble_id=str(ensemble_id),
        ensemble_scenario_id=str(scenario_id),
    )


def stop_process_tree(pid: int) -> None:
    """SIGTERM the CLI and every descendant (seed workers run in their own
    sessions), then SIGKILL whatever is left after a grace period."""
    try:
        root = psutil.Process(pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error as exc:
        logger.debug("Ensemble process %s already gone: %s", pid, exc)
        return
    for process in processes:
        _signal(process, "terminate")

    def _escalate() -> None:
        _, alive = psutil.wait_procs(processes, timeout=CANCEL_GRACE_SECONDS)
        for process in alive:
            _signal(process, "kill")

    threading.Thread(target=_escalate, daemon=True).start()


def terminate_orphan(pid: int, job_id: str) -> None:
    """Stop an ensemble left running by a dead API process.

    Only a process whose command line names this job is touched, so a
    recycled PID can never take an unrelated process down.
    """
    try:
        if not any(job_id in part for part in psutil.Process(pid).cmdline()):
            return
    except psutil.Error as exc:
        logger.debug("Orphaned ensemble %s (pid %s) not found: %s", job_id, pid, exc)
        return
    stop_process_tree(pid)


def _signal(process: psutil.Process, action: str) -> None:
    try:
        getattr(process, action)()
    except psutil.Error as exc:
        logger.debug("Could not %s ensemble process %s: %s", action, process.pid, exc)


def _mark_running(job: EnsembleJob) -> None:
    job.status = "running"
    job.started_at = _now()
    job.progress.updated_at = job.started_at


def _apply_record(job: EnsembleJob, record: dict[str, Any]) -> None:
    seed = record.get("seed")
    seed = seed if isinstance(seed, int) and not isinstance(seed, bool) else None
    event = record["event"]
    progress = job.progress
    if event == "seed_started":
        progress.current_seed = seed
    elif event == "seed_completed":
        progress.seeds_completed += 1
    else:
        progress.seeds_failed += 1
        if seed is not None:
            job.failed_seeds.append(seed)
    if event != "seed_started" and progress.current_seed == seed:
        progress.current_seed = None
    progress.updated_at = _now()


def _classify_failure(
    job: EnsembleJob, return_code: int, tail: deque[str], paths: JobPaths
) -> EnsembleError:
    last = _redact(_last_message(tail), paths)
    if return_code == 3:
        return EnsembleError(
            kind="no_seeds",
            message=f"Every seed failed, so no ensemble was written. Last output: {last}",
        )
    logger.warning(
        "Ensemble %s exited with %s; last output: %s",
        job.job_id,
        return_code,
        " | ".join(list(tail)[-5:]),
    )
    return EnsembleError(
        kind="unexpected",
        message=f"The ensemble stopped (exit code {return_code}): {last}",
    )


def _last_message(tail: deque[str]) -> str:
    for line in reversed(tail):
        if line.strip():
            return line.strip()
    return "no output"


def _redact(message: str, paths: JobPaths) -> str:
    """Keep server paths out of messages that reach a client."""
    job_dir = paths.work_dir.parent
    for path in (job_dir.resolve(), job_dir):
        message = message.replace(str(path), "<ensemble>")
    return message


def _terminal(job: EnsembleJob, status: str) -> None:
    job.status = status  # type: ignore[assignment]
    job.completed_at = _now()


def _now() -> datetime:
    return datetime.now(timezone.utc)
