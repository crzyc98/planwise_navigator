"""Run one seed ensemble as a cancellable ``planalign simulate`` subprocess.

The job waits for a simulation slot like any Studio run and holds it for every
seed. Seeds run one at a time (``--parallel 1``), so one slot is always one
simulation and ``max_concurrent_simulations`` caps ensembles too (#1086). The
CLI prints one ``PLANALIGN_ENSEMBLE_PROGRESS|`` record per seed event
(``planalign_ensemble.progress``), which becomes the job's progress.

Every process the job starts carries its id in the environment
(``processes.JOB_ENV_MARKER``), so cancel, shutdown and restart recovery can
stop seed workers even after the CLI parent is gone.
"""

from __future__ import annotations

import asyncio
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

from planalign_ensemble.progress import ENV_FLAG, parse_progress_line

from ...errors import sanitize_job_error
from ...models.ensemble_job import (
    MIN_SEED_COUNT,
    EnsembleError,
    EnsembleJob,
    EnsembleOutput,
)
from ..simulation.run_execution import build_env
from ..simulation.run_slots import simulation_slot
from ..simulation.subprocess_utils import create_subprocess
from .processes import JOB_ENV_MARKER, signal_job, stop_job
from .store import LOG_FILENAME, EnsembleJobStore

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOG_TAIL_LINES = 400
OUTPUT_DRAIN_SECONDS = 2.0
EXIT_POLL_SECONDS = 0.2

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
    """Which ensemble jobs this API process owns, and their cancel state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owned: set[str] = set()
        self._started: set[str] = set()
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

    def begin(self, job_id: str) -> bool:
        """Take the slot for real; False if the job was cancelled while queued."""
        with self._lock:
            if job_id in self._cancelled:
                return False
            self._started.add(job_id)
            return True

    def attach(self, job_id: str) -> None:
        """The child is running; stop it at once if a cancel got here first."""
        with self._lock:
            cancelled = job_id in self._cancelled
        if cancelled:
            signal_job(job_id)

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
        if not started:
            return "queued", done
        signal_job(job_id)
        return "running", done

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
        # One slot is one simulation: never fan seeds out inside it.
        "--parallel",
        "1",
        "--min-seeds",
        str(MIN_SEED_COUNT),
    ]


def build_job_env(job: EnsembleJob, paths: JobPaths) -> dict[str, str]:
    env = build_env(PROJECT_ROOT, database_path=paths.work_dir / "guard.duckdb")
    env.pop("PLANALIGN_STRUCTURED_TELEMETRY", None)
    env[ENV_FLAG] = "1"
    env[JOB_ENV_MARKER] = job.job_id
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
        return_code: Optional[int] = None
        error: Optional[str] = None
        try:
            return_code = await self._execute(job, paths, tail)
        except asyncio.CancelledError:
            # The API is stopping. Stop the child too, and leave the record
            # and work/ for restart recovery to finish off.
            signal_job(job.job_id)
            raise
        except Exception:  # noqa: BLE001 -- surfaced on the job record
            error = sanitize_job_error(logger, job.job_id, event="Ensemble failed")
        # Waiting for the process tree and deleting work/ can take a while.
        await asyncio.to_thread(self.settle, job, paths, return_code, error, tail)

    async def _execute(
        self, job: EnsembleJob, paths: JobPaths, tail: deque[str]
    ) -> int:
        self.store.update(job.workspace_id, job.job_id, _mark_running)
        process, lines = await create_subprocess(
            self.command_factory(job, paths),
            str(PROJECT_ROOT),
            build_job_env(job, paths),
        )
        self.registry.attach(job.job_id)
        reader = asyncio.create_task(self._read(job, lines, tail))
        try:
            return_code = await _wait_exit(process)
            # Surviving seed workers inherit stdout and would hold the pipe
            # open; stop reading shortly after the CLI exits.
            await asyncio.wait({reader}, timeout=OUTPUT_DRAIN_SECONDS)
            return return_code
        finally:
            reader.cancel()

    async def _read(self, job: EnsembleJob, lines: Any, tail: deque[str]) -> None:
        async for raw in lines:
            line = raw.decode("utf-8", errors="replace")
            record = parse_progress_line(line)
            if record is not None:
                self.store.update(
                    job.workspace_id, job.job_id, lambda t: _apply_record(t, record)
                )
            elif line.strip():
                tail.append(line.rstrip())

    def settle(
        self,
        job: EnsembleJob,
        paths: JobPaths,
        return_code: Optional[int],
        error: Optional[str],
        tail: deque[str],
    ) -> None:
        """Wait for the job's processes, record the outcome, then clean up."""
        try:
            stop_job(job.job_id)
            self._finalize(job, paths, return_code, error, tail)
        except Exception:  # noqa: BLE001 -- surfaced on the job record
            message = sanitize_job_error(logger, job.job_id, event="Ensemble failed")
            for suffix in ("", ".wal"):
                Path(str(paths.database) + suffix).unlink(missing_ok=True)
            self._finalize(job, paths, None, message, tail)
        finally:
            self._write_log(job, tail)
            self.store.remove_work(job.workspace_id, job.job_id)

    def _finalize(
        self,
        job: EnsembleJob,
        paths: JobPaths,
        return_code: Optional[int],
        error: Optional[str],
        tail: deque[str],
    ) -> None:
        if self.registry.begin_finalize(job.job_id):
            self._set_terminal(job, "cancelled")
            return
        if error is not None:
            self._fail(job, EnsembleError(kind="unexpected", message=error))
            return
        if return_code in (0, 2):
            output = collect_output(paths)
            if output is not None:
                self._succeed(job, output, partial=return_code == 2)
                return
            tail.append("The ensemble finished without a readable aggregate database.")
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


async def _wait_exit(process: Any) -> int:
    """The CLI's exit code, as soon as it exits.

    ``asyncio`` ``Process.wait()`` also waits for stdout to close, which a
    surviving seed worker can hold open; the return code is set on exit.
    """
    while True:
        code = process.poll() if hasattr(process, "poll") else process.returncode
        if code is not None:
            return int(code)
        await asyncio.sleep(EXIT_POLL_SECONDS)


def collect_output(paths: JobPaths) -> Optional[EnsembleOutput]:
    """Validate the aggregate in place, then keep it beside the job record."""
    candidates = sorted(paths.output_root.glob("*/ensemble.duckdb"))
    if len(candidates) != 1:
        return None
    source = candidates[0]
    try:
        with duckdb.connect(str(source), read_only=True) as connection:
            rows = connection.execute(
                "SELECT DISTINCT ensemble_id, scenario_id FROM fct_metric_distributions"
            ).fetchall()
    except duckdb.Error as exc:
        logger.warning("Unreadable ensemble database %s: %s", source, exc)
        return None
    if len(rows) != 1:
        return None
    for suffix in ("", ".wal"):
        candidate = source.with_name(source.name + suffix)
        if candidate.exists():
            shutil.move(str(candidate), str(paths.database) + suffix)
    ensemble_id, scenario_id = rows[0]
    return EnsembleOutput(
        database_path=str(paths.database.resolve()),
        ensemble_id=str(ensemble_id),
        ensemble_scenario_id=str(scenario_id),
    )


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
    job: EnsembleJob, return_code: Optional[int], tail: deque[str], paths: JobPaths
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
