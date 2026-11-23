"""Private calibration scratch directories and orphan discovery.

Each calibration job gets one private temp directory holding its config and
database copy, so DuckDB's ``.wal``/``.tmp`` files and the wage-evidence
parquet written next to the database are removed with it.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from pathlib import Path

import psutil

_OWNED_ENTRY = re.compile(r"^planalign_calibration_(\d+)_(\d+)_")
_LEGACY_GRACE_SECONDS = 86400
CALIBRATION_TEMP_PREFIX = "planalign_calibration_"


def calibration_database_prefix() -> str:
    """Encode the creating process so another process can protect live jobs."""
    started_ms = int(psutil.Process().create_time() * 1000)
    return f"{CALIBRATION_TEMP_PREFIX}{os.getpid()}_{started_ms}_"


def create_calibration_temp_dir() -> Path:
    """Create a private (0o700) per-job directory for calibration scratch."""
    return Path(tempfile.mkdtemp(prefix=calibration_database_prefix()))


def remove_calibration_scratch(path: str | Path) -> None:
    """Remove a calibration temp file, or the whole job directory holding it.

    Files from older releases sat directly in the temp directory; for those
    the database's ``.wal`` and wage-evidence siblings are removed too.
    Raises ``OSError`` when removal fails for a reason other than absence.
    """
    target = Path(path)
    if _OWNED_ENTRY.match(target.parent.name):
        try:
            shutil.rmtree(target.parent)
        except FileNotFoundError:
            pass
        return
    target.unlink(missing_ok=True)
    if target.suffix == ".duckdb":
        Path(f"{target}.wal").unlink(missing_ok=True)
        for evidence in target.parent.glob(f"{target.stem}.wage_evidence*.parquet"):
            evidence.unlink(missing_ok=True)


def _owner_is_alive(path: Path) -> bool:
    match = _OWNED_ENTRY.match(path.name)
    if match is None:
        # Older releases did not mark owners; give any pre-upgrade job time to
        # finish before reclaiming its scratch.
        return time.time() - path.stat().st_mtime < _LEGACY_GRACE_SECONDS
    pid, started_ms = (int(part) for part in match.groups())
    try:
        return int(psutil.Process(pid).create_time() * 1000) == started_ms
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


def _is_calibration_scratch(path: Path) -> bool:
    if path.is_symlink():
        return False
    if path.is_dir():
        return True
    name = path.name
    return path.is_file() and (
        name.endswith((".duckdb", ".duckdb.wal"))
        or (".wage_evidence" in name and name.endswith(".parquet"))
    )


def find_orphaned_calibration_databases(temp_dir: Path | None = None) -> list[Path]:
    """Find orphaned calibration job directories and legacy temp DB files."""
    root = temp_dir if temp_dir is not None else Path(tempfile.gettempdir())
    return [
        path
        for path in sorted(root.glob(f"{CALIBRATION_TEMP_PREFIX}*"))
        if _is_calibration_scratch(path) and not _owner_is_alive(path)
    ]
