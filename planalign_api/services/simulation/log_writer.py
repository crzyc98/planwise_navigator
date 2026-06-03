"""Incremental log writer for simulation run output."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Optional

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {"error": "ERROR", "warning": "WARNING", "debug": "INFO"}


class SimulationLogWriter:
    """Writes simulation subprocess output to a persistent log file.

    Opens ``{run_dir}/simulation.log`` on construction and appends one
    formatted line per ``write_line()`` call.  The file handle is held open
    for the duration of the run so that partial logs survive a crash.

    Usage::

        writer = SimulationLogWriter(run_dir)
        try:
            writer.write_line("info", "Simulation started")
        finally:
            writer.close()
    """

    FILENAME = "simulation.log"

    def __init__(self, run_dir: Path) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = run_dir / self.FILENAME
        self._sequence = 0
        self._file: Optional[IO[str]] = None
        try:
            self._file = open(self._log_path, "a", encoding="utf-8", buffering=1)
        except OSError as exc:
            logger.error("SimulationLogWriter: cannot open %s — %s", self._log_path, exc)

    def write_line(self, severity: str, message: str) -> None:
        """Append one formatted log line and flush immediately."""
        if self._file is None or self._file.closed:
            return
        self._sequence += 1
        level = _SEVERITY_MAP.get(severity, "INFO")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        try:
            self._file.write(f"{ts} [{level}] {message}\n")
            self._file.flush()
        except OSError as exc:
            logger.warning("SimulationLogWriter: write failed — %s", exc)

    def close(self) -> None:
        """Close the log file handle (idempotent)."""
        if self._file is not None and not self._file.closed:
            try:
                self._file.close()
            except OSError as exc:
                logger.warning("SimulationLogWriter: close failed — %s", exc)

    @property
    def log_path(self) -> Path:
        return self._log_path
