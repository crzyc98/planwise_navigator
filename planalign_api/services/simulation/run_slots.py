"""Limit how many Studio simulations run at once.

Every simulation, single or batch, takes a slot before it starts, so the
``max_concurrent_simulations`` setting caps the whole API process. Runs that
cannot get a slot wait in order and stay ``queued`` until one frees up.
"""

import asyncio
import functools
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable
from weakref import WeakKeyDictionary

from ...config import get_settings

logger = logging.getLogger(__name__)

# One semaphore per event loop: an asyncio.Semaphore cannot be shared across
# loops, and tests create a fresh loop per client.
_slots: "WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    WeakKeyDictionary()
)

Execute = Callable[..., Awaitable[None]]


def _loop_slots() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    slots = _slots.get(loop)
    if slots is None:
        slots = asyncio.Semaphore(get_settings().max_concurrent_simulations)
        _slots[loop] = slots
    return slots


@asynccontextmanager
async def simulation_slot() -> AsyncIterator[None]:
    """Hold one simulation slot for the duration of the block."""
    async with _loop_slots():
        yield


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
