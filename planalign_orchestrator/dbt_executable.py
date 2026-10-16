"""Locate dbt without requiring shell activation of the Python environment."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def find_dbt_executable() -> str | None:
    """Preserve PATH lookup, falling back to an executable beside Python."""
    if shutil.which("dbt") is not None:
        return "dbt"
    # Do not resolve Python's symlink: its target can be outside the virtualenv.
    name = "dbt.exe" if os.name == "nt" else "dbt"
    candidate = Path(sys.executable).parent / name
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None
