"""Cached filesystem storage accounting for workspaces.

Byte totals require a recursive walk of a workspace tree, and workspace trees
grow without bound as simulation runs accumulate (16 GB / 6.5k files is a
normal working set). Walking synchronously on navigation requests made
``/api/workspaces``, ``/api/system/status`` and ``/api/health`` the slowest
endpoints in the API — seconds each whenever a simulation had evicted the OS
dentry cache.

Two things make that cheap here:

1. ``os.scandir`` instead of ``Path.rglob`` + ``Path.stat`` — the directory
   entry is reused for the type check and the size, roughly 2.5x fewer
   syscalls.
2. A short TTL cache. These totals only feed a display figure and a soft
   ">90% of limit" warning, so a value up to ``_TTL_SECONDS`` old is fine.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

# Storage figures are advisory (display + soft warning), so a minute of
# staleness is acceptable and keeps navigation off the filesystem.
_TTL_SECONDS = 60.0

# workspace directory -> (expires_at, size in bytes)
_size_cache: Dict[Path, Tuple[float, int]] = {}


@dataclass(frozen=True)
class WorkspaceTotals:
    """Aggregate storage accounting across all workspaces."""

    total_bytes: int
    workspace_count: int
    scenario_count: int

    @property
    def total_mb(self) -> float:
        return self.total_bytes / (1024 * 1024)


def _scan_directory_bytes(path: Path) -> int:
    """Sum the sizes of every regular file under `path`.

    Symlinks are counted as links, not followed: a workspace can symlink into
    a parameter-pack overlay, and following those would double-count bytes
    that live outside the workspace.
    """
    total = 0
    stack = [str(path)]

    while stack:
        try:
            entries = os.scandir(stack.pop())
        except OSError:
            continue  # Raced deletion or unreadable directory; skip it.

        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue  # Entry vanished mid-walk.

    return total


def directory_bytes(path: Path, *, allow_scan: bool = True) -> Optional[int]:
    """Return the cached recursive size of `path` in bytes.

    With `allow_scan=False` a cache miss returns None instead of walking the
    tree, so latency-sensitive callers never block on the filesystem.
    """
    now = time.monotonic()
    cached = _size_cache.get(path)
    if cached is not None and cached[0] > now:
        return cached[1]

    if not allow_scan:
        return None

    size = _scan_directory_bytes(path)
    _size_cache[path] = (now + _TTL_SECONDS, size)
    return size


def iter_workspace_dirs(workspaces_root: Path):
    """Yield each workspace directory under the root, skipping dotfiles."""
    if not workspaces_root.exists():
        return
    for workspace_dir in sorted(workspaces_root.iterdir()):
        if workspace_dir.is_dir() and not workspace_dir.name.startswith("."):
            yield workspace_dir


def workspace_totals(
    workspaces_root: Path, *, allow_scan: bool = True
) -> Optional[WorkspaceTotals]:
    """Aggregate storage usage and counts across all workspaces.

    Returns None only when `allow_scan=False` and any workspace size is
    missing from the cache, so callers get an all-or-nothing answer rather
    than a total that silently omits workspaces.
    """
    total_bytes = 0
    workspace_count = 0
    scenario_count = 0

    for workspace_dir in iter_workspace_dirs(workspaces_root):
        workspace_count += 1

        scenarios_dir = workspace_dir / "scenarios"
        if scenarios_dir.exists():
            scenario_count += sum(
                1 for entry in scenarios_dir.iterdir() if entry.is_dir()
            )

        size = directory_bytes(workspace_dir, allow_scan=allow_scan)
        if size is None:
            return None
        total_bytes += size

    return WorkspaceTotals(total_bytes, workspace_count, scenario_count)


def invalidate(path: Optional[Path] = None) -> None:
    """Drop cached sizes for one workspace, or all of them."""
    if path is None:
        _size_cache.clear()
    else:
        _size_cache.pop(path, None)
