"""Run CPU-bound Excel exports outside the API process."""

from __future__ import annotations

import asyncio
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from .run_archiver import export_run_excel

_executor: Optional[ProcessPoolExecutor] = None
_executor_lock = Lock()


def _get_executor() -> ProcessPoolExecutor:
    """Return the lazily-created, memory-bounded Excel export process pool."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
            )
        return _executor


async def export_run_excel_in_process(
    *,
    scenario_path: Path,
    scenario_name: str,
    config: Dict[str, Any],
    seed: int,
    run_dir: Path,
) -> Optional[Path]:
    """Generate a workbook without sharing the API process's GIL."""
    export = partial(
        export_run_excel,
        scenario_path=scenario_path,
        scenario_name=scenario_name,
        config=config,
        seed=seed,
        run_dir=run_dir,
    )
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_executor(), export)


def shutdown_excel_export_executor() -> None:
    """Release the export worker during API shutdown."""
    global _executor
    with _executor_lock:
        executor = _executor
        _executor = None
    if executor is not None:
        executor.shutdown(wait=True, cancel_futures=False)
