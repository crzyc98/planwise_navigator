"""Run fit/backtest jobs as cancellable CLI subprocesses (#588).

A backtest runs full orchestrator simulations in-process, so a thread cannot
be interrupted mid-run; a child process can. Each job therefore runs
``python -m planalign_cli.main fit|backtest …`` in its own process group, and
a daemon thread streams its stdout, turning ``PLANALIGN_FIT_PROGRESS|`` records
(contracts/progress-protocol.md) into job progress. The CLI stays the single
engine; Studio is just another caller of it.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from planalign_fit.pack import MANIFEST_FILENAME
from planalign_fit.progress import ENV_FLAG, parse_progress_line

from ...errors import sanitize_job_error
from ...models.param_fit import JobError, JobProgress, ParamFitJob
from .jobs import LOG_FILENAME, JobStore

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CANCEL_GRACE_SECONDS = 5.0
LOG_TAIL_LINES = 400
IS_POSIX = os.name == "posix"

# CLI exit codes (planalign_cli/commands/fit.py, backtest.py) -> job error.
_FIT_EXITS = {
    2: ("invalid_input", 422),
    3: ("invalid_history", 422),
    4: ("output_conflict", 409),
}
_BACKTEST_EXITS = {
    2: ("invalid_input", 422),
    3: ("invalid_history", 422),
    4: ("simulation_failure", 500),
}


@dataclass(frozen=True)
class JobPaths:
    history_files: Path
    base_config: Path
    seeds_dir: Path
    pack_dir: Path
    work_dir: Path


CommandFactory = Callable[[ParamFitJob, JobPaths], list[str]]


class ProcessRegistry:
    """Which jobs this API process owns, and the child process behind each."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owned: set[str] = set()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled: set[str] = set()
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
        if self.was_cancelled(job_id):
            _terminate(process)

    def was_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    def cancel(self, job_id: str) -> Optional[threading.Event]:
        """Request cancellation; returns an event set once the job has ended."""
        with self._lock:
            if job_id not in self._owned:
                return None
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
            done = self._done.pop(job_id, None)
        if done is not None:
            done.set()


default_registry = ProcessRegistry()


def build_cli_command(job: ParamFitJob, paths: JobPaths) -> list[str]:
    """The ``planalign fit|backtest`` invocation for one job."""
    base = [sys.executable, "-m", "planalign_cli.main", job.mode]
    common = [str(paths.history_files), *_common_args(job, paths)]
    if job.mode == "fit":
        return [*base, *common]
    request = job.request
    thresholds = request.thresholds
    return [
        *base,
        *common,
        "--holdout",
        str(request.holdout_years),
        "--seed-list",
        ",".join(str(seed) for seed in request.seeds),
        "--workdir",
        str(paths.work_dir),
        *_threshold_args("headcount", thresholds.headcount),
        *_threshold_args("compensation", thresholds.compensation),
        *_threshold_args("flows", thresholds.flows),
        *_threshold_args("plan", thresholds.plan),
    ]


def _common_args(job: ParamFitJob, paths: JobPaths) -> list[str]:
    """Inputs, output, and fit knobs shared by ``fit`` and ``backtest``."""
    options = job.request.fit_options
    return [
        "--config",
        str(paths.base_config),
        "--seeds-dir",
        str(paths.seeds_dir),
        "--output",
        str(paths.pack_dir),
        "--credibility-k",
        repr(options.credibility_k),
        "--min-exposure",
        repr(options.min_exposure),
        "--level-coverage-threshold",
        repr(options.level_coverage_threshold),
        "--separation-exposure-gate",
        repr(options.separation_exposure_gate),
        "--notes",
        job.request.notes,
    ]


def _threshold_args(family: str, pair) -> list[str]:
    return [f"--threshold-{family}", f"{pair.warn!r},{pair.fail!r}"]


def build_env(work_dir: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "PLANALIGN_STRUCTURED_TELEMETRY"
    }
    # The backtest invokes dbt; find it beside this interpreter even when the
    # API was started without an activated virtualenv.
    interpreter_bin = str(Path(sys.executable).parent)
    env["PATH"] = os.pathsep.join(filter(None, [interpreter_bin, env.get("PATH")]))
    env.update(
        {
            ENV_FLAG: "1",
            "PYTHONPATH": str(PROJECT_ROOT),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            # Anything that falls back to get_database_path() lands in the
            # job's scratch, never the shared dev database.
            "DATABASE_PATH": str(work_dir / "guard.duckdb"),
            "PLANALIGN_ENTRY_POINT": "studio_param_fit",
            "TERM": "dumb",
            "NO_COLOR": "1",
            # Wide enough that Rich never wraps a one-line error message.
            "COLUMNS": "4000",
        }
    )
    return env


class JobRunner:
    """Launch one job's subprocess on a worker thread and record its outcome."""

    def __init__(
        self,
        store: JobStore,
        registry: ProcessRegistry,
        command_factory: CommandFactory = build_cli_command,
        on_finished: Optional[Callable[[str], None]] = None,
    ):
        self.store = store
        self.registry = registry
        self.command_factory = command_factory
        self.on_finished = on_finished

    def start(self, job: ParamFitJob, paths: JobPaths) -> None:
        """Run ``job`` on a worker thread; the caller has already claimed it."""
        threading.Thread(
            target=self._run,
            args=(job, paths),
            name=f"param-fit-{job.job_id}",
            daemon=True,
        ).start()

    def _run(self, job: ParamFitJob, paths: JobPaths) -> None:
        tail: deque[str] = deque(maxlen=LOG_TAIL_LINES)
        failure: dict[str, object] = {}
        return_code: Optional[int] = None
        try:
            if not self.registry.was_cancelled(job.job_id):
                return_code = self._execute(job, paths, tail, failure)
            self._finalize(job, paths, return_code, tail, failure)
        except Exception:  # noqa: BLE001 -- surfaced on the job record
            message = sanitize_job_error(
                logger, job.job_id, event="Parameter fit job failed"
            )
            self._fail(job, JobError(kind="unexpected", message=message, status=500))
        finally:
            self._write_log(job, tail)
            self.registry.release(job.job_id)
            if self.on_finished is not None:
                self.on_finished(job.workspace_id)

    def _execute(
        self,
        job: ParamFitJob,
        paths: JobPaths,
        tail: deque[str],
        failure: dict[str, object],
    ) -> int:
        paths.work_dir.mkdir(parents=True, exist_ok=True)
        self.store.update(job.workspace_id, job.job_id, _mark_running)
        process = subprocess.Popen(
            self.command_factory(job, paths),
            cwd=str(PROJECT_ROOT),
            env=build_env(paths.work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=IS_POSIX,
        )
        self.registry.attach(job.job_id, process)
        assert process.stdout is not None  # PIPE was requested above
        for line in process.stdout:
            record = parse_progress_line(line)
            if record is None:
                if line.strip():
                    tail.append(line.rstrip())
                continue
            self._apply_record(job, record, failure)
        return process.wait()

    def _apply_record(
        self, job: ParamFitJob, record: dict, failure: dict[str, object]
    ) -> None:
        event = record.get("event")
        if event == "simulation_failed":
            failure.update(record)
            return
        progress = _progress_from(record)
        if progress is None:
            return

        def _set(target: ParamFitJob) -> None:
            target.progress = progress

        self.store.update(job.workspace_id, job.job_id, _set)

    def _finalize(
        self,
        job: ParamFitJob,
        paths: JobPaths,
        return_code: Optional[int],
        tail: deque[str],
        failure: dict[str, object],
    ) -> None:
        if self.registry.was_cancelled(job.job_id):
            self.store.remove_artifacts(job.workspace_id, job.job_id)
            self._set_terminal(job, "cancelled")
            return
        has_pack = (paths.pack_dir / MANIFEST_FILENAME).is_file()
        if return_code == 0 and has_pack:
            shutil.rmtree(paths.work_dir, ignore_errors=True)
            self._set_terminal(job, "completed")
            return
        self.store.remove_artifacts(job.workspace_id, job.job_id)
        self._fail(job, _classify_failure(job, return_code, tail, failure, paths))

    def _set_terminal(self, job: ParamFitJob, status: str) -> None:
        def _mark(target: ParamFitJob) -> None:
            target.status = status  # type: ignore[assignment]
            target.completed_at = datetime.now(timezone.utc)

        self.store.update(job.workspace_id, job.job_id, _mark)

    def _fail(self, job: ParamFitJob, error: JobError) -> None:
        def _mark(target: ParamFitJob) -> None:
            target.status = "failed"
            target.error = error
            target.completed_at = datetime.now(timezone.utc)

        self.store.update(job.workspace_id, job.job_id, _mark)

    def _write_log(self, job: ParamFitJob, tail: deque[str]) -> None:
        directory = self.store.job_dir(job.workspace_id, job.job_id)
        if directory.is_dir():
            (directory / LOG_FILENAME).write_text("\n".join(tail) + "\n", "utf-8")


def _mark_running(job: ParamFitJob) -> None:
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    job.progress = JobProgress(stage="loading_history", updated_at=_now())


def _progress_from(record: dict) -> Optional[JobProgress]:
    event = record.get("event")
    if event == "stage":
        stage = record.get("stage")
        if stage in ("loading_history", "fitting", "scoring", "writing_pack"):
            return JobProgress(stage=stage, updated_at=_now())
        return None
    if event in ("seed_started", "seed_completed"):
        return JobProgress(
            stage="simulating",
            seed=_as_int(record.get("seed")),
            index=_as_int(record.get("index")),
            total=_as_int(record.get("total")),
            updated_at=_now(),
        )
    return None


def _classify_failure(
    job: ParamFitJob,
    return_code: Optional[int],
    tail: deque[str],
    failure: dict[str, object],
    paths: JobPaths,
) -> JobError:
    exits = _FIT_EXITS if job.mode == "fit" else _BACKTEST_EXITS
    known = exits.get(return_code) if return_code is not None else None
    if known is None:
        logger.warning(
            "Parameter fit job %s exited with %s; last output: %s",
            job.job_id,
            return_code,
            " | ".join(list(tail)[-5:]),
        )
        return JobError(
            kind="unexpected",
            message=(
                f"The {job.mode} job stopped unexpectedly (exit code {return_code}). "
                "See the server log for details."
            ),
            status=500,
        )
    kind, status = known
    raw = str(failure.get("message") or _last_message(tail))
    return JobError(
        kind=kind,  # type: ignore[arg-type]
        message=_redact(raw, paths),
        status=status,
        failed_seed=_as_int(failure.get("seed")),
        failed_year=_as_int(failure.get("year")),
    )


def _last_message(tail: deque[str]) -> str:
    for line in reversed(tail):
        if line.strip():
            return line.strip()
    return "The job failed without an error message."


def _redact(message: str, paths: JobPaths) -> str:
    """Replace server paths with neutral labels before they reach a client."""
    replacements = (
        (paths.history_files, "history"),
        (paths.pack_dir, "pack"),
        (paths.work_dir, "work"),
        (paths.base_config, "base_config.yaml"),
        (paths.seeds_dir, "seeds"),
    )
    for path, label in replacements:
        message = message.replace(str(path.resolve()), label).replace(str(path), label)
    return message


def _terminate(process: subprocess.Popen[str]) -> None:
    """SIGTERM the job's process group, then SIGKILL after a grace period."""
    if process.poll() is not None:
        return
    _signal(process, signal.SIGTERM)

    def _escalate() -> None:
        try:
            process.wait(timeout=CANCEL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _signal(process, signal.SIGKILL if IS_POSIX else signal.SIGTERM)

    threading.Thread(target=_escalate, daemon=True).start()


def _signal(process: subprocess.Popen[str], sig: int) -> None:
    try:
        if IS_POSIX:
            os.killpg(process.pid, sig)
        elif sig == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except (ProcessLookupError, PermissionError) as exc:
        logger.debug("Signal %s to job process %s failed: %s", sig, process.pid, exc)


def _as_int(value: object) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _now() -> datetime:
    return datetime.now(timezone.utc)
