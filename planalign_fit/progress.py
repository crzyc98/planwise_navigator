"""Structured progress for ``planalign fit`` / ``planalign backtest`` (#588).

Studio runs both commands as subprocesses and needs to know what they are
doing without regex-guessing from log text. When ``PLANALIGN_FIT_PROGRESS=1``
each milestone is printed as one sentinel-prefixed JSON line, mirroring the
simulator's ``PLANALIGN_TELEMETRY|`` protocol. Plain CLI output is unchanged
when the variable is unset.

Contract: specs/588-studio-fit-backtest/contracts/progress-protocol.md
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

SENTINEL = "PLANALIGN_FIT_PROGRESS|"
ENV_FLAG = "PLANALIGN_FIT_PROGRESS"
PROTOCOL_VERSION = 1


def enabled() -> bool:
    return os.environ.get(ENV_FLAG) == "1"


def emit(event: str, **fields: Any) -> None:
    """Print one progress record when enabled; a no-op otherwise."""
    if not enabled():
        return
    record = {"v": PROTOCOL_VERSION, "event": event, **fields}
    sys.stdout.write(SENTINEL + json.dumps(record, default=str) + "\n")
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
    if not isinstance(record, dict) or not isinstance(record.get("event"), str):
        return None
    return record
