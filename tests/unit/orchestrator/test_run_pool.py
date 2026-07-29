"""Unit tests for the parallel scenario fan-out pool (#457).

Covers the three properties the pool exists to guarantee: concurrency sized
from measured budgets, failure containment, and results that do not depend on
whether a job ran inline or on a worker process.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from planalign_orchestrator.run_pool import (
    WORKER_MEMORY_BUDGET_MIB,
    EventKind,
    ScenarioJob,
    ScenarioRunPool,
    resolve_worker_count,
)

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def _job(name: str, **payload) -> ScenarioJob:
    return ScenarioJob(
        name=name,
        config=None,
        db_path=f"/tmp/{name}.duckdb",
        seed=42,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Worker-count budgeting
# ---------------------------------------------------------------------------


class TestResolveWorkerCount:
    def test_memory_caps_concurrency_below_cpu_count(self):
        """The point of #457: a 16-core laptop with 3 GiB free gets 2 workers."""
        budget = resolve_worker_count(
            None, 8, available_memory_mib=3 * WORKER_MEMORY_BUDGET_MIB, cpu_count=16
        )
        assert budget.workers == 3
        assert "memory" in budget.reason

    def test_cpu_caps_concurrency_when_memory_is_plentiful(self):
        budget = resolve_worker_count(
            None, 8, available_memory_mib=256_000, cpu_count=4
        )
        assert budget.workers == 3  # cpu_count - 1 reserved
        assert "CPU" in budget.reason

    def test_never_exceeds_job_count(self):
        budget = resolve_worker_count(
            None, 2, available_memory_mib=256_000, cpu_count=64
        )
        assert budget.workers == 2

    def test_explicit_request_is_honored_over_measured_budget(self):
        """An operator on unmeasured hardware must be able to override."""
        budget = resolve_worker_count(
            6, 8, available_memory_mib=WORKER_MEMORY_BUDGET_MIB, cpu_count=2
        )
        assert budget.workers == 6
        assert budget.reason == "explicitly requested"

    def test_explicit_request_still_clamped_to_job_count(self):
        budget = resolve_worker_count(16, 3, available_memory_mib=256_000, cpu_count=64)
        assert budget.workers == 3
        assert "capped" in budget.reason

    def test_rejects_zero_and_negative(self):
        with pytest.raises(ValueError, match="must be >= 1"):
            resolve_worker_count(0, 4)

    def test_falls_back_to_cpu_budget_when_memory_probe_fails(self, monkeypatch):
        monkeypatch.setattr(
            "planalign_orchestrator.run_pool._available_memory_mib", lambda: None
        )
        budget = resolve_worker_count(None, 8, cpu_count=4)
        assert budget.workers == 3
        assert budget.available_memory_mib is None

    def test_no_jobs_means_no_workers(self):
        assert resolve_worker_count(None, 0).workers == 0

    def test_always_allows_at_least_one_worker(self):
        """Even a machine reporting almost no free memory must make progress."""
        budget = resolve_worker_count(None, 4, available_memory_mib=10, cpu_count=1)
        assert budget.workers == 1

    def test_describe_mentions_both_caps(self):
        text = resolve_worker_count(
            None, 4, available_memory_mib=8192, cpu_count=8
        ).describe()
        assert "cpu cap" in text and "memory cap" in text


# ---------------------------------------------------------------------------
# Worker functions must be module-level to survive pickling to a spawned child
# ---------------------------------------------------------------------------


def _echo_worker(job: ScenarioJob) -> dict:
    return {"name": job.name, "seed": job.seed, "pid": os.getpid()}


def _failing_worker(job: ScenarioJob) -> dict:
    if job.payload.get("boom"):
        raise RuntimeError(f"{job.name} exploded")
    return {"name": job.name}


def _slow_worker(job: ScenarioJob) -> dict:
    time.sleep(job.payload.get("sleep", 0.5))
    return {"name": job.name}


def _slow_echo_worker(job: ScenarioJob) -> dict:
    """Slow enough that every worker claims a job before any queue is drained."""
    time.sleep(job.payload.get("sleep", 0.3))
    return {"name": job.name, "seed": job.seed, "pid": os.getpid()}


def _lock_holding_worker(job: ScenarioJob) -> dict:
    """Hold a context manager across a long sleep, so SIGTERM must unwind it."""
    marker = Path(job.payload["marker"])
    marker.write_text("held")
    try:
        time.sleep(job.payload.get("sleep", 30))
    finally:
        marker.unlink(missing_ok=True)
    return {"name": job.name}


# ---------------------------------------------------------------------------
# Execution semantics
# ---------------------------------------------------------------------------


class TestPoolExecution:
    def test_inline_path_runs_in_calling_process(self):
        """max_workers=1 must stay in-process: it is the serial reference."""
        results = ScenarioRunPool(1).run(_echo_worker, [_job("a"), _job("b")])
        assert set(results) == {"a", "b"}
        assert all(r.value["pid"] == os.getpid() for r in results.values())

    def test_empty_job_list_is_a_no_op(self):
        assert ScenarioRunPool(4).run(_echo_worker, []) == {}

    def test_one_failure_does_not_stop_the_pool(self):
        jobs = [_job("ok1"), _job("bad", boom=True), _job("ok2")]
        results = ScenarioRunPool(1).run(_failing_worker, jobs)

        assert results["ok1"].succeeded and results["ok2"].succeeded
        assert not results["bad"].succeeded
        assert "exploded" in results["bad"].error
        assert "RuntimeError" in results["bad"].traceback

    def test_events_are_emitted_for_every_job(self):
        events = []
        jobs = [_job("ok"), _job("bad", boom=True)]
        ScenarioRunPool(1).run(_failing_worker, jobs, on_event=events.append)

        started = [e for e in events if e.kind is EventKind.JOB_STARTED]
        completed = [e for e in events if e.kind is EventKind.JOB_COMPLETED]
        failed = [e for e in events if e.kind is EventKind.JOB_FAILED]
        assert len(started) == 2
        assert [e.job_name for e in completed] == ["ok"]
        assert [e.job_name for e in failed] == ["bad"]

    def test_broken_event_handler_does_not_fail_the_run(self):
        """A display bug must not lose a completed simulation."""

        def explode(_event):
            raise ValueError("bad handler")

        results = ScenarioRunPool(1).run(_echo_worker, [_job("a")], on_event=explode)
        assert results["a"].succeeded

    def test_rejects_zero_workers(self):
        with pytest.raises(ValueError, match="must be >= 1"):
            ScenarioRunPool(0)


@pytest.mark.slow
class TestPoolParallelExecution:
    """Exercises the real process-boundary path (spawn + pickle + queues)."""

    def test_jobs_run_in_worker_processes_not_the_parent(self):
        jobs = [_job(f"s{i}") for i in range(4)]
        results = ScenarioRunPool(4).run(_echo_worker, jobs)

        assert set(results) == {"s0", "s1", "s2", "s3"}
        assert all(r.succeeded for r in results.values())
        assert os.getpid() not in {r.value["pid"] for r in results.values()}

    def test_work_spreads_across_workers(self):
        """Jobs long enough to overlap must land on more than one worker."""
        jobs = [_job(f"s{i}", sleep=0.3) for i in range(4)]
        results = ScenarioRunPool(4).run(_slow_echo_worker, jobs)

        pids = {r.value["pid"] for r in results.values()}
        assert len(pids) > 1, f"all work ran on one worker: {pids}"

    def test_results_match_the_serial_path(self):
        """Exit criterion: parallel output equals serial output."""
        jobs = [_job(f"s{i}") for i in range(4)]
        serial = ScenarioRunPool(1).run(_echo_worker, jobs)
        parallel = ScenarioRunPool(4).run(_echo_worker, jobs)

        strip = lambda rs: {  # noqa: E731 - pid is expected to differ
            n: {k: v for k, v in r.value.items() if k != "pid"} for n, r in rs.items()
        }
        assert strip(serial) == strip(parallel)

    def test_failure_in_one_worker_is_contained(self):
        jobs = [_job("ok1"), _job("bad", boom=True), _job("ok2")]
        results = ScenarioRunPool(3).run(_failing_worker, jobs)

        assert results["ok1"].succeeded and results["ok2"].succeeded
        assert not results["bad"].succeeded
        assert "exploded" in results["bad"].error

    def test_terminate_lets_workers_release_their_resources(self, tmp_path):
        """SIGTERM must unwind, not kill outright.

        A killed worker runs no finally blocks, so it would leak the
        per-scenario ExecutionMutex lock file and a re-run within the hour
        would block on a lock nobody holds.
        """
        marker = tmp_path / "held.marker"
        jobs = [_job("held", marker=str(marker), sleep=30)]
        pool = ScenarioRunPool(2)

        import threading

        done = threading.Event()

        def run():
            try:
                pool.run(
                    _lock_holding_worker,
                    jobs + [_job("second", marker=str(tmp_path / "b"), sleep=30)],
                )
            except BaseException:
                pass
            finally:
                done.set()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        deadline = time.monotonic() + 30
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert marker.exists(), "worker never acquired its resource"

        pool._terminate_workers()
        done.wait(timeout=30)

        assert not marker.exists(), "worker was killed before it could clean up"

    def test_concurrency_actually_overlaps(self):
        """Four 0.5s jobs on four workers must beat the 2.0s serial total."""
        jobs = [_job(f"s{i}", sleep=0.5) for i in range(4)]
        started = time.monotonic()
        results = ScenarioRunPool(4).run(_slow_worker, jobs)
        elapsed = time.monotonic() - started

        assert all(r.succeeded for r in results.values())
        assert elapsed < 2.0, f"no overlap observed: {elapsed:.2f}s"
