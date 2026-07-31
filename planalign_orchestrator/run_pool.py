#!/usr/bin/env python3
"""Bounded-concurrency process pool for whole-scenario simulation runs.

Scenario runs are embarrassingly parallel: E069 already guarantees one
``.duckdb`` file per scenario, so N scenarios share no state and can occupy N
cores. This module provides the small pool that ``planalign batch`` uses today
and that the seed-ensemble runner and optimizer submit to later.

The API is deliberately tiny: build :class:`ScenarioJob` values, hand them to
:meth:`ScenarioRunPool.run` with a worker callable, stream
:class:`PoolEvent` updates, collect :class:`JobResult` values.

Two properties matter to callers:

* **Process isolation.** Workers are processes, not threads — each one drives
  its own dbt subprocesses and DuckDB connections. Each worker is placed in its
  own session (``setsid``) so the pool can signal a worker *and its dbt
  children* as a unit, which is what makes Ctrl+C leave no orphans.
* **Failure containment.** One job raising does not stop the pool; it lands as
  a ``failed`` :class:`JobResult` alongside the successes.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import queue
import signal
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

# Measured single-run peak RSS for a 5-year production-path run, from the #455
# baseline in docs/perf/run_cost_profile_production.md (reference config
# 1296 MiB, studio config 1284 MiB). Worker sizing is derived from this rather
# than from CPU count alone, per #457.
MEASURED_PEAK_RSS_MIB = 1296

# Per-worker memory budget: measured peak plus ~18% headroom for census size
# variation and allocator slack. Concurrency is capped so that
# workers * this value fits in available memory.
WORKER_MEMORY_BUDGET_MIB = 1536

# Leave one core for the parent process, the OS, and the user's machine.
RESERVED_CPUS = 1

# Grace period between SIGTERM and SIGKILL when tearing down a worker session.
_TERMINATE_GRACE_SECONDS = 10.0

# How long the parent waits on the event queue before re-checking worker health.
_EVENT_POLL_SECONDS = 0.2


class EventKind(str, Enum):
    """Lifecycle events streamed from the pool to the caller."""

    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"


@dataclass(frozen=True)
class PoolEvent:
    """A single status update about one job."""

    kind: EventKind
    job_name: str
    worker_pid: Optional[int] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class ScenarioJob:
    """One unit of parallel work: a fully-resolved scenario run.

    The job carries everything the worker needs, because it is pickled to a
    process that shares no memory with the parent. In particular ``config``
    must already have its seed pinned and its overrides merged — resolving
    those in the worker would make runs depend on worker scheduling.
    """

    name: str
    config: Any
    db_path: Path
    seed: int
    threads: int = 1
    dbt_artifacts_dir: Optional[Path] = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class JobResult:
    """Outcome of one job, successful or not."""

    name: str
    status: str
    value: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    traceback: Optional[str] = None
    duration_seconds: float = 0.0
    worker_pid: Optional[int] = None

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"


@dataclass(frozen=True)
class WorkerBudget:
    """Resolved concurrency and the reasoning behind it.

    Surfaced to the CLI so an operator can see *why* the pool chose N workers
    — an unexplained cap looks like a bug on a 16-core laptop.
    """

    workers: int
    reason: str
    cpu_limit: int
    memory_limit: int
    available_memory_mib: Optional[int]

    def describe(self) -> str:
        mem = (
            f"{self.available_memory_mib} MiB available"
            if self.available_memory_mib is not None
            else "memory probe unavailable"
        )
        return (
            f"{self.workers} worker(s) — {self.reason} "
            f"(cpu cap {self.cpu_limit}, memory cap {self.memory_limit} @ "
            f"{WORKER_MEMORY_BUDGET_MIB} MiB/worker, {mem})"
        )


def _available_memory_mib() -> Optional[int]:
    """Best-effort available (not merely free) system memory, in MiB."""
    try:
        import psutil

        return int(psutil.virtual_memory().available / (1024 * 1024))
    except Exception as exc:  # pragma: no cover - platform dependent
        logger.debug("Memory probe unavailable, falling back to CPU sizing: %s", exc)
        return None


def resolve_worker_count(
    requested: Optional[int],
    job_count: int,
    *,
    available_memory_mib: Optional[int] = None,
    cpu_count: Optional[int] = None,
) -> WorkerBudget:
    """Choose a worker count from measured memory and CPU budgets.

    An explicit ``requested`` value is honored (still clamped to the job count,
    since idle workers help nobody) so an operator can override the default on
    hardware we have not measured. Otherwise concurrency is the minimum of the
    job count, the CPU budget, and what memory can actually hold — N concurrent
    DuckDB instances at ~1.3 GiB each is the real constraint on a work laptop,
    and sizing on CPU alone is how you swap.
    """
    if job_count <= 0:
        return WorkerBudget(0, "no jobs to run", 0, 0, available_memory_mib)

    cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 1)
    cpu_limit = max(1, cpus - RESERVED_CPUS)

    if available_memory_mib is None:
        available_memory_mib = _available_memory_mib()
    if available_memory_mib is None:
        memory_limit = cpu_limit
        memory_known = False
    else:
        memory_limit = max(1, available_memory_mib // WORKER_MEMORY_BUDGET_MIB)
        memory_known = True

    if requested is not None:
        if requested < 1:
            raise ValueError(f"--parallel must be >= 1, got {requested}")
        workers = min(requested, job_count)
        reason = (
            "explicitly requested"
            if workers == requested
            else f"requested {requested}, capped to {job_count} job(s)"
        )
        if memory_known and requested > memory_limit:
            logger.warning(
                "Requested %d workers exceeds the memory budget for %d "
                "(%d MiB available, ~%d MiB per worker). Proceeding as "
                "requested; expect memory pressure.",
                requested,
                memory_limit,
                available_memory_mib,
                WORKER_MEMORY_BUDGET_MIB,
            )
        return WorkerBudget(
            workers, reason, cpu_limit, memory_limit, available_memory_mib
        )

    workers = max(1, min(job_count, cpu_limit, memory_limit))
    if workers == job_count:
        reason = "one worker per scenario"
    elif workers == memory_limit and memory_known and memory_limit <= cpu_limit:
        reason = "limited by available memory"
    else:
        reason = "limited by available CPUs"
    return WorkerBudget(workers, reason, cpu_limit, memory_limit, available_memory_mib)


def _raise_shutdown(signum: int, frame: Any) -> None:
    """Turn the pool's SIGTERM into an orderly unwind.

    Default SIGTERM kills the process outright, running neither ``finally``
    blocks nor ``atexit`` hooks — which would leak the per-scenario
    ExecutionMutex lock file and leave DuckDB connections open. Raising here
    lets context managers release before the process exits.
    """
    raise SystemExit(128 + signum)


def _worker_loop(
    job_queue: Any,
    event_queue: Any,
    worker: Callable[[ScenarioJob], Dict[str, Any]],
) -> None:
    """Consume jobs until the sentinel; report every outcome as an event.

    Runs in a child process. The worker detaches into its own session so the
    parent can signal this process together with the dbt subprocesses it
    spawns, and ignores SIGINT so that a terminal Ctrl+C does not race the
    parent's orchestrated shutdown.
    """
    if hasattr(os, "setsid"):
        try:
            os.setsid()
        except OSError as exc:  # pragma: no cover - already a session leader
            logger.debug("setsid failed in worker %d: %s", os.getpid(), exc)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, _raise_shutdown)

    pid = os.getpid()
    while True:
        job = job_queue.get()
        if job is None:
            return

        event_queue.put(PoolEvent(EventKind.JOB_STARTED, job.name, worker_pid=pid))
        started = time.monotonic()
        try:
            value = worker(job)
            elapsed = time.monotonic() - started
            event_queue.put(
                (
                    PoolEvent(
                        EventKind.JOB_COMPLETED,
                        job.name,
                        worker_pid=pid,
                        duration_seconds=elapsed,
                    ),
                    JobResult(
                        name=job.name,
                        status="completed",
                        value=value,
                        duration_seconds=elapsed,
                        worker_pid=pid,
                    ),
                )
            )
        except (SystemExit, KeyboardInterrupt):
            # Shutdown, not a job failure. Propagate so the ExecutionMutex and
            # DuckDB connections unwind; the parent fills in the missing result.
            raise
        except Exception as exc:  # noqa: BLE001 - a job must never kill the pool
            elapsed = time.monotonic() - started
            event_queue.put(
                (
                    PoolEvent(
                        EventKind.JOB_FAILED,
                        job.name,
                        worker_pid=pid,
                        duration_seconds=elapsed,
                        error=str(exc),
                    ),
                    JobResult(
                        name=job.name,
                        status="failed",
                        error=str(exc),
                        traceback=traceback.format_exc(),
                        duration_seconds=elapsed,
                        worker_pid=pid,
                    ),
                )
            )


class ScenarioRunPool:
    """Run scenario jobs across worker processes with bounded concurrency.

    ``max_workers <= 1`` runs jobs inline in the calling process. That is not
    just an optimization: it keeps the serial path free of any pickling or
    process-boundary semantics, so ``--parallel 1`` is the untouched behavior
    that parallel output is validated against.
    """

    def __init__(self, max_workers: int) -> None:
        if max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {max_workers}")
        self.max_workers = max_workers
        self._workers: List[Any] = []

    def run(
        self,
        worker: Callable[[ScenarioJob], Dict[str, Any]],
        jobs: Sequence[ScenarioJob],
        *,
        on_event: Optional[Callable[[PoolEvent], None]] = None,
    ) -> Dict[str, JobResult]:
        """Execute ``jobs``, returning one :class:`JobResult` per job name.

        ``worker`` must be importable by name (a module-level function): jobs
        cross a process boundary by pickle. Events are delivered on the calling
        thread as results arrive, so ``on_event`` can drive a progress display
        without interleaving output from the workers themselves.
        """
        if not jobs:
            return {}
        if self.max_workers == 1 or len(jobs) == 1:
            return self._run_inline(worker, jobs, on_event)
        return self._run_parallel(worker, jobs, on_event)

    def _run_inline(
        self,
        worker: Callable[[ScenarioJob], Dict[str, Any]],
        jobs: Sequence[ScenarioJob],
        on_event: Optional[Callable[[PoolEvent], None]],
    ) -> Dict[str, JobResult]:
        results: Dict[str, JobResult] = {}
        pid = os.getpid()
        for job in jobs:
            _emit(on_event, PoolEvent(EventKind.JOB_STARTED, job.name, worker_pid=pid))
            started = time.monotonic()
            try:
                value = worker(job)
                elapsed = time.monotonic() - started
                results[job.name] = JobResult(
                    name=job.name,
                    status="completed",
                    value=value,
                    duration_seconds=elapsed,
                    worker_pid=pid,
                )
                _emit(
                    on_event,
                    PoolEvent(
                        EventKind.JOB_COMPLETED,
                        job.name,
                        worker_pid=pid,
                        duration_seconds=elapsed,
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - contained per job
                elapsed = time.monotonic() - started
                results[job.name] = JobResult(
                    name=job.name,
                    status="failed",
                    error=str(exc),
                    traceback=traceback.format_exc(),
                    duration_seconds=elapsed,
                    worker_pid=pid,
                )
                _emit(
                    on_event,
                    PoolEvent(
                        EventKind.JOB_FAILED,
                        job.name,
                        worker_pid=pid,
                        duration_seconds=elapsed,
                        error=str(exc),
                    ),
                )
        return results

    def _run_parallel(
        self,
        worker: Callable[[ScenarioJob], Dict[str, Any]],
        jobs: Sequence[ScenarioJob],
        on_event: Optional[Callable[[PoolEvent], None]],
    ) -> Dict[str, JobResult]:
        # 'spawn' rather than 'fork': the parent may already hold DuckDB
        # connections and threads, and forking those into a child that then
        # runs dbt is exactly the kind of shared-state hazard process
        # isolation is meant to remove.
        ctx = mp.get_context("spawn")
        workers = min(self.max_workers, len(jobs))
        job_queue = ctx.Queue()
        event_queue = ctx.Queue()

        for job in jobs:
            job_queue.put(job)
        for _ in range(workers):
            job_queue.put(None)

        self._workers = [
            ctx.Process(
                target=_worker_loop,
                args=(job_queue, event_queue, worker),
                name=f"planalign-worker-{i}",
                daemon=False,
            )
            for i in range(workers)
        ]
        for process in self._workers:
            process.start()

        results: Dict[str, JobResult] = {}
        try:
            self._collect(results, event_queue, len(jobs), on_event)
            for process in self._workers:
                process.join()
        except KeyboardInterrupt:
            logger.warning("Interrupted — terminating %d worker(s)", len(self._workers))
            self._terminate_workers()
            self._record_interrupted(results, jobs)
            raise
        finally:
            _drain_queue(job_queue)
            _drain_queue(event_queue)
            job_queue.close()
            event_queue.close()

        # A worker that died mid-job (OOM kill, segfault) never published a
        # result. Surface that as a failure rather than silently returning a
        # short dict the caller would read as success.
        self._record_missing(results, jobs)
        return results

    def _collect(
        self,
        results: Dict[str, JobResult],
        event_queue: Any,
        expected: int,
        on_event: Optional[Callable[[PoolEvent], None]],
    ) -> None:
        """Drain events until every job reports, or every worker is gone."""
        while len(results) < expected:
            try:
                item = event_queue.get(timeout=_EVENT_POLL_SECONDS)
            except queue.Empty:
                if not any(p.is_alive() for p in self._workers):
                    return
                continue

            if isinstance(item, PoolEvent):
                _emit(on_event, item)
                continue
            event, result = item
            results[result.name] = result
            _emit(on_event, event)

    def _terminate_workers(self) -> None:
        """Signal each worker's whole session so no dbt subprocess is orphaned.

        Workers call ``setsid``, so the worker pid is also its session and
        process-group id and its dbt children inherit it. Signalling the group
        reaches those children; signalling only the worker would leave dbt
        running against a database nobody is waiting on.
        """
        for process in self._workers:
            _signal_session(process, signal.SIGTERM)

        deadline = time.monotonic() + _TERMINATE_GRACE_SECONDS
        for process in self._workers:
            remaining = max(0.0, deadline - time.monotonic())
            process.join(timeout=remaining)

        for process in self._workers:
            if process.is_alive():
                logger.warning(
                    "Worker %s did not exit within %.0fs; killing session",
                    process.pid,
                    _TERMINATE_GRACE_SECONDS,
                )
                _signal_session(process, signal.SIGKILL)
                process.join(timeout=5)

    @staticmethod
    def _record_interrupted(
        results: Dict[str, JobResult], jobs: Sequence[ScenarioJob]
    ) -> None:
        for job in jobs:
            results.setdefault(
                job.name,
                JobResult(name=job.name, status="failed", error="interrupted"),
            )

    @staticmethod
    def _record_missing(
        results: Dict[str, JobResult], jobs: Sequence[ScenarioJob]
    ) -> None:
        for job in jobs:
            if job.name in results:
                continue
            logger.error(
                "Worker died without reporting a result for scenario %s", job.name
            )
            results[job.name] = JobResult(
                name=job.name,
                status="failed",
                error=(
                    "worker process died without reporting a result "
                    "(most likely killed for memory use; lower --parallel)"
                ),
            )


def _signal_session(process: Any, sig: int) -> None:
    """Send ``sig`` to a worker's process group, falling back to the process."""
    pid = process.pid
    if pid is None or not process.is_alive():
        return
    try:
        if hasattr(os, "killpg"):
            # Only signal the GROUP when the worker leads its own session.
            # `setsid` runs inside the worker after fork (and may fail), so
            # there is a window where getpgid(pid) still returns OUR group --
            # signalling it would take down the whole pool's process group:
            # the parent, its siblings, and on a terminal the user's shell.
            # Observed as "The runner has received a shutdown signal" killing
            # a CI job outright. Signal just the process until it has setsid.
            pgid = os.getpgid(pid)
            if pgid == pid:
                os.killpg(pgid, sig)
            else:
                os.kill(pid, sig)
        else:  # pragma: no cover - platforms without process groups
            process.terminate()
    except (ProcessLookupError, PermissionError):
        pass
    except OSError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to signal worker %s: %s", pid, exc)


def _drain_queue(q: Any) -> None:
    """Empty a queue so its feeder thread can shut down without blocking."""
    try:
        while True:
            q.get_nowait()
    except (queue.Empty, OSError, ValueError):
        pass


def _emit(on_event: Optional[Callable[[PoolEvent], None]], event: PoolEvent) -> None:
    """Deliver an event without letting a display bug fail the run."""
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception as exc:  # noqa: BLE001 - telemetry must not break execution
        logger.warning("Pool event handler raised: %s", exc)


__all__ = [
    "EventKind",
    "JobResult",
    "MEASURED_PEAK_RSS_MIB",
    "PoolEvent",
    "ScenarioJob",
    "ScenarioRunPool",
    "WORKER_MEMORY_BUDGET_MIB",
    "WorkerBudget",
    "resolve_worker_count",
]
