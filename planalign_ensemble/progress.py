"""Machine-readable seed progress for Studio-launched ensembles.

Studio runs ``planalign simulate --seeds`` as a subprocess and needs per-seed
progress without parsing Rich output. When ``PLANALIGN_ENSEMBLE_PROGRESS=1``
each pool event is also printed as one sentinel-prefixed JSON line, the same
shape as ``planalign_fit.progress``. CLI output is unchanged when unset.

Records: ``{"v": 1, "event": "seed_started" | "seed_completed" |
"seed_failed", "seed": int | null, "duration_seconds": float | null,
"error": str | null}``.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

from planalign_orchestrator.run_pool import EventKind, PoolEvent

SENTINEL = "PLANALIGN_ENSEMBLE_PROGRESS|"
ENV_FLAG = "PLANALIGN_ENSEMBLE_PROGRESS"
PROTOCOL_VERSION = 1

_EVENT_NAMES = {
    EventKind.JOB_STARTED: "seed_started",
    EventKind.JOB_COMPLETED: "seed_completed",
    EventKind.JOB_FAILED: "seed_failed",
}


def emit_pool_event(event: PoolEvent) -> None:
    """Print one progress record for ``event`` when enabled; a no-op otherwise."""
    if os.environ.get(ENV_FLAG) != "1":
        return
    record = {
        "v": PROTOCOL_VERSION,
        "event": _EVENT_NAMES[event.kind],
        "seed": _seed_from_job_name(event.job_name),
        "duration_seconds": event.duration_seconds,
        "error": event.error,
    }
    sys.stdout.write(SENTINEL + json.dumps(record) + "\n")
    sys.stdout.flush()


def parse_progress_line(line: str) -> Optional[dict[str, Any]]:
    """The record carried by ``line``, or ``None`` for any other output."""
    text = line.strip()
    if not text.startswith(SENTINEL):
        return None
    try:
        record = json.loads(text[len(SENTINEL) :])
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict) or record.get("event") not in _EVENT_NAMES.values():
        return None
    return record


def _seed_from_job_name(job_name: str) -> Optional[int]:
    """Headline jobs are named ``seed_<seed>`` (``runner._build_seed_jobs``)."""
    prefix, _, raw = job_name.rpartition("_")
    try:
        return int(raw) if prefix else None
    except ValueError:
        return None


__all__ = ["ENV_FLAG", "SENTINEL", "emit_pool_event", "parse_progress_line"]
