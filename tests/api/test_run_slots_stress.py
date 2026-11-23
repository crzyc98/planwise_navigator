"""Concurrency invariants of the process-wide simulation slot pool."""

from __future__ import annotations

import asyncio
import random
import threading
import time
from typing import Callable

import pytest

from planalign_api.config import APISettings
from planalign_api.services.calibration_process import ProcessRegistry
from planalign_api.services.simulation import run_slots

pytestmark = [pytest.mark.fast]


def _set_limit(monkeypatch: pytest.MonkeyPatch, limit: int) -> None:
    settings = APISettings(max_concurrent_simulations=limit)
    monkeypatch.setattr(run_slots, "get_settings", lambda: settings)


def _assert_idle(timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with run_slots._lock:
            if run_slots._in_use == 0 and not run_slots._waiters:
                return
        time.sleep(0.01)
    raise AssertionError(
        f"slot pool not idle: in_use={run_slots._in_use} "
        f"waiters={len(run_slots._waiters)}"
    )


class _Probe:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.entered = 0

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.entered += 1
            self.peak = max(self.peak, self.active)

    def leave(self) -> None:
        with self._lock:
            self.active -= 1


def _thread_worker(
    probe: _Probe, registry: ProcessRegistry, seed: int, rounds: int
) -> Callable[[], None]:
    def _run() -> None:
        rng = random.Random(seed)
        for i in range(rounds):
            job_id = f"t{seed}-{i}"
            registry.claim(job_id)
            if rng.random() < 0.3:
                threading.Timer(rng.random() * 0.004, registry.cancel, [job_id]).start()
            with run_slots.simulation_slot_sync(
                is_cancelled=lambda: registry.was_cancelled(job_id),
                poll_interval=0.001,
            ) as acquired:
                if acquired:
                    probe.enter()
                    time.sleep(rng.random() * 0.002)
                    probe.leave()
            registry.release(job_id)

    return _run


def _loop_worker(probe: _Probe, seed: int, tasks: int) -> Callable[[], None]:
    async def _one(rng: random.Random) -> None:
        async with run_slots.simulation_slot():
            probe.enter()
            try:
                await asyncio.sleep(rng.random() * 0.002)
            finally:  # a cancel can land while the slot is held
                probe.leave()

    async def _main() -> None:
        rng = random.Random(seed)
        pending = [asyncio.create_task(_one(rng)) for _ in range(tasks)]
        for task in pending:
            if rng.random() < 0.3:
                asyncio.get_running_loop().call_later(rng.random() * 0.01, task.cancel)
        await asyncio.gather(*pending, return_exceptions=True)

    return lambda: asyncio.run(_main())


def _claim_hammer(registry: ProcessRegistry, stop: threading.Event) -> None:
    # What the job services do: count queued jobs under the registry lock.
    i = 0
    while not stop.is_set():
        job_id = f"h{i}"
        if registry.try_claim(
            job_id, lambda q: not run_slots.queue_capacity_exceeded(q)
        ):
            registry.release(job_id)
        i += 1


@pytest.mark.parametrize("limit", [1, 2])
def test_threads_and_loops_never_exceed_limit_or_leak(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    _set_limit(monkeypatch, limit)
    _assert_idle()
    probe = _Probe()
    registry = ProcessRegistry()
    stop = threading.Event()
    workers = [
        threading.Thread(target=_thread_worker(probe, registry, s, 25), daemon=True)
        for s in range(6)
    ] + [
        threading.Thread(target=_loop_worker(probe, 100 + s, 25), daemon=True)
        for s in range(3)
    ]
    hammer = threading.Thread(target=_claim_hammer, args=(registry, stop), daemon=True)
    hammer.start()
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30.0)
    stop.set()
    hammer.join(timeout=5.0)

    assert not any(w.is_alive() for w in workers), "worker deadlocked or starved"
    assert not hammer.is_alive()
    assert probe.peak <= limit
    assert probe.entered > 0
    _assert_idle()


def test_is_cancelled_holding_registry_lock_does_not_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A woken waiter checks cancellation while another thread is in try_claim."""
    _set_limit(monkeypatch, 1)
    registry = ProcessRegistry()
    registry.claim("waiting")
    holder_release = threading.Event()
    checking = threading.Event()

    def _is_cancelled() -> bool:
        checking.set()
        return registry.was_cancelled("waiting")

    def _holder() -> None:
        with run_slots.simulation_slot_sync():
            holder_release.wait(5.0)

    def _waiter() -> None:
        with run_slots.simulation_slot_sync(is_cancelled=_is_cancelled):
            pass

    holder = threading.Thread(target=_holder, daemon=True)
    holder.start()
    while run_slots.available_slots():
        time.sleep(0.005)
    waiter = threading.Thread(target=_waiter, daemon=True)
    waiter.start()
    while not run_slots._waiters:
        time.sleep(0.005)
    checking.clear()

    def _can_queue(queued: int) -> bool:
        holder_release.set()
        # The granted waiter is now blocked on the registry lock we hold.
        assert checking.wait(5.0)
        time.sleep(0.05)
        return not run_slots.queue_capacity_exceeded(queued)

    claimer = threading.Thread(
        target=registry.try_claim, args=("new", _can_queue), daemon=True
    )
    claimer.start()
    claimer.join(timeout=5.0)
    assert not claimer.is_alive(), "try_claim deadlocked against a slot waiter"
    waiter.join(timeout=5.0)
    holder.join(timeout=5.0)
    _assert_idle()


@pytest.mark.parametrize("resolve_first", [False, True])
def test_async_waiter_cancelled_after_grant_releases_slot(
    monkeypatch: pytest.MonkeyPatch, resolve_first: bool
) -> None:
    """Cancel lands after the slot was handed over but before the waiter resumed."""
    _set_limit(monkeypatch, 1)
    _assert_idle()

    async def _main() -> None:
        async def _waiter() -> None:
            async with run_slots.simulation_slot():
                raise AssertionError("cancelled waiter must not run")

        async with run_slots.simulation_slot():
            task = asyncio.create_task(_waiter())
            await asyncio.sleep(0.01)
            assert len(run_slots._waiters) == 1
        # Released with no await since: the slot is granted to ``task``.
        assert run_slots._in_use == 1
        if resolve_first:
            await asyncio.sleep(0)  # resolve callback runs; task not resumed yet
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_main())
    _assert_idle()
