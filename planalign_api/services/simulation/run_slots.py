"""Limit how many heavy Studio jobs run at once across the API process.

Every simulation, batch step, ensemble, census roll-forward, calibration,
parameter fit/backtest, and optimizer run takes a slot before it starts, so
``max_concurrent_simulations`` caps the whole API process across both asyncio
tasks and worker threads. Jobs that cannot get a slot wait in FIFO order and
stay ``queued`` until one frees up.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import threading
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Iterator, Optional

from ...config import get_settings

logger = logging.getLogger(__name__)

Execute = Callable[..., Awaitable[None]]


@dataclass
class _AsyncWaiter:
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[None]
    granted: bool = False
    cancelled: bool = False

    def notify(self) -> bool:
        if self.loop.is_closed():
            return False
        try:
            self.loop.call_soon_threadsafe(_resolve_future, self.future)
        except RuntimeError:
            return False
        return True


@dataclass
class _ThreadWaiter:
    event: threading.Event = field(default_factory=threading.Event)
    granted: bool = False
    cancelled: bool = False

    def notify(self) -> bool:
        self.event.set()
        return True


_Waiter = _AsyncWaiter | _ThreadWaiter

_lock = threading.Lock()
_in_use = 0
_waiters: deque[_Waiter] = deque()


def _resolve_future(future: asyncio.Future[None]) -> None:
    if not future.done():
        future.set_result(None)


def _limit() -> int:
    return get_settings().max_concurrent_simulations


def available_slots() -> int:
    """Return how many simulation slots are currently free."""
    with _lock:
        return max(0, _limit() - _in_use)


def queue_capacity_exceeded(queued_count: int) -> bool:
    """Whether admitting another job of one type would exceed its queue cap.

    Free simulation slots can start an incoming job immediately rather than
    leaving it queued, so up to ``max_queued_jobs_per_type + available_slots``
    unstarted jobs are accepted before rejecting with 429.
    """
    return queued_count >= get_settings().max_queued_jobs_per_type + available_slots()


def _discard_waiter_locked(waiter: _Waiter) -> None:
    try:
        _waiters.remove(waiter)
    except ValueError:
        pass


def _grant_waiters_locked() -> None:
    global _in_use
    limit = _limit()
    while _in_use < limit and _waiters:
        waiter = _waiters.popleft()
        if waiter.cancelled:
            continue
        if waiter.notify():
            waiter.granted = True
            _in_use += 1


def _release_locked() -> None:
    global _in_use
    if _in_use > 0:
        _in_use -= 1
    _grant_waiters_locked()


def _release() -> None:
    with _lock:
        _release_locked()


async def _acquire_async() -> None:
    global _in_use
    loop = asyncio.get_running_loop()
    with _lock:
        _grant_waiters_locked()
        if _in_use < _limit() and not _waiters:
            _in_use += 1
            return
        waiter = _AsyncWaiter(loop=loop, future=loop.create_future())
        _waiters.append(waiter)
    try:
        await waiter.future
    except BaseException:
        with _lock:
            if waiter.granted:
                _release_locked()
            else:
                waiter.cancelled = True
                _discard_waiter_locked(waiter)
        raise


def _claim_or_cancel_locked(
    waiter: _ThreadWaiter,
    is_cancelled: Optional[Callable[[], bool]],
) -> bool:
    with _lock:
        if not waiter.granted:
            return False
        if is_cancelled is not None and is_cancelled():
            _release_locked()
            return False
        return True


def _abort_thread_waiter(waiter: _ThreadWaiter) -> bool:
    with _lock:
        if waiter.granted:
            _release_locked()
        else:
            waiter.cancelled = True
            _discard_waiter_locked(waiter)
    return False


def _wait_for_thread_slot(
    waiter: _ThreadWaiter,
    is_cancelled: Optional[Callable[[], bool]],
    poll_interval: float,
) -> bool:
    timeout = poll_interval if is_cancelled is not None else None
    try:
        while True:
            if waiter.event.wait(timeout=timeout):
                return _claim_or_cancel_locked(waiter, is_cancelled)
            if is_cancelled is not None and is_cancelled():
                return _abort_thread_waiter(waiter)
    except BaseException:
        _abort_thread_waiter(waiter)
        raise


def _acquire_sync(
    *,
    is_cancelled: Optional[Callable[[], bool]] = None,
    poll_interval: float = 0.02,
) -> bool:
    global _in_use
    if is_cancelled is not None and is_cancelled():
        return False
    with _lock:
        _grant_waiters_locked()
        if _in_use < _limit() and not _waiters:
            _in_use += 1
            return True
        waiter = _ThreadWaiter()
        _waiters.append(waiter)
    return _wait_for_thread_slot(waiter, is_cancelled, poll_interval)


@asynccontextmanager
async def simulation_slot() -> AsyncIterator[None]:
    """Hold one simulation slot for the duration of an async block."""
    await _acquire_async()
    try:
        yield
    finally:
        _release()


@contextmanager
def simulation_slot_sync(
    *,
    is_cancelled: Optional[Callable[[], bool]] = None,
    poll_interval: float = 0.02,
) -> Iterator[bool]:
    """Hold one simulation slot from a synchronous worker thread.

    Yields ``True`` once a slot is held, or ``False`` if ``is_cancelled`` became
    true before a slot was taken. Releases any acquired slot on exit.
    """
    acquired = _acquire_sync(is_cancelled=is_cancelled, poll_interval=poll_interval)
    try:
        yield acquired
    finally:
        if acquired:
            _release()


def runs_in_simulation_slot(execute: Execute) -> Execute:
    """Wait for a slot before ``execute`` runs; skip it if cancelled meanwhile.

    Wraps ``SimulationService.execute_simulation``. Callers register the run
    first (``routers.simulations.reserve_run``); cancelling a queued run
    evicts it, so a run no longer registered once the slot frees is skipped.
    Nothing awaits between that check and the run marking itself running, so
    a cancel request cannot slip in between.
    """

    @functools.wraps(execute)
    async def wrapper(
        self: Any,
        workspace_id: str,
        scenario_id: str,
        run_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        from ...routers.simulations import is_run_registered

        async with simulation_slot():
            if not is_run_registered(run_id):
                logger.info("Run %s was cancelled before it started", run_id)
                return
            await execute(self, workspace_id, scenario_id, run_id, *args, **kwargs)

    return wrapper
