"""Make a census file the workspace census, with its as-of date.

Every path that sets ``setup.census_parquet_path`` (import wizard, direct
upload, Use as Census, roll-forward) sets ``setup.census_as_of_date`` with it,
so switching censuses never leaves another file's date behind. A file with no
stored date clears the key, and the engine then infers the date as before.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

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


def is_active_census(
    storage: WorkspaceStorage, workspace_id: str, census_path: str
) -> bool:
    """Whether ``census_path`` is the workspace's configured census."""
    config = storage.merge_overrides(workspace_id, {}) or {}
    configured = (config.get("setup") or {}).get("census_parquet_path")
    return (
        bool(configured)
        and Path(str(configured)).resolve() == Path(census_path).resolve()
    )
