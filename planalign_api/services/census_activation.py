"""Make a census file the workspace census, with its as-of date.

The date belongs to the census file: it is stored on the file's Imported Files
record. Every path that sets ``setup.census_parquet_path`` (import wizard,
direct upload, Use as Census, roll-forward) copies it to
``setup.census_as_of_date``, and a Studio run takes it from the record of the
census that run uses, so a scenario on another census, or a census picked in
Configure, never gets another file's date. A file with no stored date clears
the key, and the engine then infers the date as before.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from ..storage.workspace_storage import WorkspaceStorage

CENSUS_PATH_KEY = "setup.census_parquet_path"
CENSUS_AS_OF_KEY = "setup.census_as_of_date"


def activate_census(
    storage: WorkspaceStorage,
    workspace_id: str,
    census_path: str,
    as_of: Optional[date],
) -> bool:
    """Set the workspace census and its as-of date; False if the workspace is missing."""
    if not storage.update_base_config_key(workspace_id, CENSUS_PATH_KEY, census_path):
        return False
    return set_active_census_as_of(storage, workspace_id, as_of)


def set_active_census_as_of(
    storage: WorkspaceStorage, workspace_id: str, as_of: Optional[date]
) -> bool:
    """Set (or clear) the as-of date of the census already in use."""
    value = as_of.isoformat() if as_of is not None else None
    return storage.update_base_config_key(workspace_id, CENSUS_AS_OF_KEY, value)


def _workspace_setup(storage: WorkspaceStorage, workspace_id: str) -> dict[str, Any]:
    config = storage.merge_overrides(workspace_id, {}) or {}
    return config.get("setup") or {}


def is_active_census(
    storage: WorkspaceStorage, workspace_id: str, census_path: str
) -> bool:
    """Whether ``census_path`` is the workspace's configured census."""
    from .simulation.run_execution import resolve_census_path

    configured = _workspace_setup(storage, workspace_id).get("census_parquet_path")
    if not configured:
        return False
    resolved = resolve_census_path(storage, str(configured), workspace_id)
    return resolved is not None and resolved == Path(census_path).resolve()


def census_as_of_for(
    storage: WorkspaceStorage, workspace_id: str, census: Path
) -> Optional[date]:
    """The as-of date stored on the record of ``census``; None if it has none."""
    from .import_service import ImportService

    record = ImportService(storage.workspaces_root).find_parquet_by_path(
        workspace_id, str(census)
    )
    return record.census_as_of_date if record else None


def prefill_as_of(
    storage: WorkspaceStorage, workspace_id: str, inferred: Optional[date]
) -> Optional[date]:
    """The date to prefill: the configured plan-year end, else ``inferred``.

    The engine's fallback honors a configured plan year, so the prompt does too.
    """
    setup = _workspace_setup(storage, workspace_id)
    end, start = setup.get("plan_year_end_date"), setup.get("plan_year_start_date")
    try:
        if end:
            return date.fromisoformat(str(end))
        if start:
            begin = date.fromisoformat(str(start))
            return begin.replace(year=begin.year + 1) - timedelta(days=1)
    except ValueError:
        return inferred
    return inferred
