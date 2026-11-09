"""
PlanAlign Engine Version Information

This module provides centralized version management for PlanAlign Engine.
Follow Semantic Versioning 2.0.0 (https://semver.org/)

Version format: MAJOR.MINOR.PATCH
- MAJOR: Incompatible API changes or major architectural changes
- MINOR: New features in a backwards-compatible manner (e.g., new epics)
- PATCH: Backwards-compatible bug fixes

See CHANGELOG.md for detailed version history.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

__version__ = "3.0.0"
_major, _minor, _patch = (int(x) for x in __version__.split("."))
__version_info__: tuple[int, int, int] = (_major, _minor, _patch)

# Release metadata
__release_date__ = "2026-10-14"
__release_name__ = "Plan Design & Evidence"

_REPO_ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def get_git_sha() -> str | None:
    """Return the commit running this code, with ``-dirty`` for uncommitted edits.

    ``PLANALIGN_GIT_SHA`` overrides it for installs without a git checkout.
    Returns None when neither is available.
    """
    override = os.environ.get("PLANALIGN_GIT_SHA")
    if override:
        return override
    try:
        sha = _git("rev-parse", "--short=12", "HEAD")
        dirty = _git("status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{sha}-dirty" if dirty else sha


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    ).stdout.strip()


def get_version() -> str:
    """Get the current version string."""
    return __version__


def get_version_info() -> tuple[int, int, int]:
    """Get version as a tuple of integers (major, minor, patch)."""
    return __version_info__


def get_full_version() -> str:
    """Get full version string including git info if available."""
    sha = get_git_sha()
    return f"{__version__}+{sha}" if sha else __version__


def get_version_dict() -> dict[str, str | tuple[int, int, int] | None]:
    """Get version information as a dictionary."""
    return {
        "version": __version__,
        "version_info": __version_info__,
        "release_date": __release_date__,
        "release_name": __release_name__,
        "git_sha": get_git_sha(),
    }
