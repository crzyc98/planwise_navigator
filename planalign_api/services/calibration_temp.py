"""Identify disposable calibration databases left by interrupted jobs."""

from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path

import psutil

_OWNED_DATABASE = re.compile(r"^planalign_calibration_(\d+)_(\d+)_.*\.duckdb$")
_LEGACY_GRACE_SECONDS = 86400


def calibration_database_prefix() -> str:
    """Encode the creating process so another process can protect live jobs."""
    started_ms = int(psutil.Process().create_time() * 1000)
    return f"planalign_calibration_{os.getpid()}_{started_ms}_"


def _owner_is_alive(path: Path) -> bool:
    match = _OWNED_DATABASE.fullmatch(path.name)
    if match is None:
        # Older releases did not mark owners; give any pre-upgrade job time to
        # finish before reclaiming its database.
        return time.time() - path.stat().st_mtime < _LEGACY_GRACE_SECONDS
    pid, started_ms = (int(part) for part in match.groups())
    try:
        return int(psutil.Process(pid).create_time() * 1000) == started_ms
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


def find_orphaned_calibration_databases(temp_dir: Path | None = None) -> list[Path]:
    """Find only exact calibration DuckDB copies in the system temp directory."""
    root = temp_dir if temp_dir is not None else Path(tempfile.gettempdir())
    return [
        path
        for path in sorted(root.glob("planalign_calibration_*.duckdb"))
        if path.is_file() and not path.is_symlink() and not _owner_is_alive(path)
    ]
