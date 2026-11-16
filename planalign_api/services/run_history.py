"""Find a scenario's previous retained run from run files alone (#1186).

Managed runs live in ``<scenario>/runs/<run_id>/``, each with a
``run_metadata.json`` written when the run is archived. The previous run of a
selected result is the most recently started run that completed and started
before the selected one. Only small JSON files are read; no database opens.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from planalign_core.constants import STATUS_COMPLETED

from .current_result import RUN_METADATA_FILENAME

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviousRun:
    """A retained, completed run that started before the selected result."""

    run_id: str
    path: Path
    started_at: datetime


def read_run_metadata(run_dir: Path) -> Optional[dict[str, Any]]:
    """A run's ``run_metadata.json``; ``None`` when absent or unreadable."""
    path = run_dir / RUN_METADATA_FILENAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.info("Run metadata unreadable in %s: %s", run_dir.name, exc)
        return None
    return payload if isinstance(payload, dict) else None


def run_started_at(metadata: Optional[dict[str, Any]]) -> Optional[datetime]:
    """Aware start time; archived runs record a naive local ``started_at``."""
    value = metadata.get("started_at") if metadata else None
    if not isinstance(value, str):
        return None
    try:
        started_at = datetime.fromisoformat(value)
    except ValueError:
        return None
    return started_at if started_at.tzinfo else started_at.astimezone()


def _completed_run(run_dir: Path) -> Optional[PreviousRun]:
    if run_dir.is_symlink() or not run_dir.is_dir() or not _is_uuid(run_dir.name):
        return None
    metadata = read_run_metadata(run_dir)
    started_at = run_started_at(metadata)
    if (
        metadata is None
        or started_at is None
        or metadata.get("run_id") != run_dir.name
        or metadata.get("status") != STATUS_COMPLETED
    ):
        return None
    return PreviousRun(run_id=run_dir.name, path=run_dir, started_at=started_at)


def _is_uuid(name: str) -> bool:
    try:
        return str(uuid.UUID(name)) == name
    except ValueError:
        return False


def find_previous_run(selected_run_dir: Path) -> Optional[PreviousRun]:
    """The latest completed sibling run that started before the selected one."""
    selected_start = run_started_at(read_run_metadata(selected_run_dir))
    if selected_start is None:
        return None
    candidates = (
        _completed_run(run_dir)
        for run_dir in selected_run_dir.parent.iterdir()
        if run_dir.name != selected_run_dir.name
    )
    earlier = [
        run for run in candidates if run is not None and run.started_at < selected_start
    ]
    return max(earlier, key=lambda run: run.started_at, default=None)


__all__ = ["PreviousRun", "find_previous_run", "read_run_metadata", "run_started_at"]
