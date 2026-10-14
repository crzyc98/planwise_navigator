"""Sample benchmark process-tree RSS without changing simulation workers."""

from __future__ import annotations

from threading import Event, Thread
from types import TracebackType

import psutil


class ProcessResources:
    """Sample aggregate RSS every 100 ms, including dbt subprocesses.

    RSS can double count shared pages and miss short peaks; this is a sampled
    process-tree measurement, not an OS high-water mark or per-worker budget.
    """

    def __init__(self) -> None:
        self.peak_rss_mib = 0.0
        self._stop = Event()
        self._thread = Thread(target=self._sample, daemon=True)

    def __enter__(self) -> ProcessResources:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        self._thread.join()

    def _sample(self) -> None:
        parent = psutil.Process()
        while not self._stop.is_set():
            total = 0
            for process in [parent, *parent.children(recursive=True)]:
                try:
                    total += process.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            self.peak_rss_mib = max(self.peak_rss_mib, total / (1024 * 1024))
            self._stop.wait(0.1)
