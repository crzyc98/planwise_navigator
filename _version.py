"""
Fidelity PlanAlign Engine Version Information

This module provides centralized version management for Fidelity PlanAlign Engine.
Follow Semantic Versioning 2.0.0 (https://semver.org/)

Version format: MAJOR.MINOR.PATCH
- MAJOR: Incompatible API changes or major architectural changes
- MINOR: New features in a backwards-compatible manner (e.g., new epics)
- PATCH: Backwards-compatible bug fixes

Version History:
- 2.0.0: Renamed from PlanWise Navigator to Fidelity PlanAlign Engine
  - Breaking change: CLI command renamed from 'planwise' to 'planalign'
  - Breaking change: Package renamed from 'navigator_orchestrator' to 'planalign_orchestrator'
  - Breaking change: Package renamed from 'planwise_cli' to 'planalign_cli'
- 1.0.0: Initial production release (as PlanWise Navigator)
  - E068: Performance Optimization (2× improvement)
  - E069: Batch Scenario Processing
  - E072: Pipeline Modularization
  - E074: Enhanced Error Handling
  - E075: Testing Infrastructure (256 tests)
  - E078: Cohort Pipeline Integration
  - E080: Validation Model to Test Conversion
"""

from __future__ import annotations

__version__ = "2.0.0"
__version_info__ = tuple(int(x) for x in __version__.split("."))

# Release metadata
__release_date__ = "2025-11-24"
__release_name__ = "PlanAlign Engine"

# Git information (can be populated by CI/CD or build scripts)
__git_sha__ = None
__git_branch__ = None

def get_version() -> str:
    """Get the current version string."""
    return __version__

def get_version_info() -> tuple[int, int, int]:
    """Get version as a tuple of integers (major, minor, patch)."""
    return __version_info__

def get_full_version() -> str:
    """Get full version string including git info if available."""
    version = __version__
    if __git_sha__:
        version += f"+{__git_sha__[:7]}"
    return version

def get_version_dict() -> dict[str, str | tuple[int, int, int] | None]:
    """Get version information as a dictionary."""
    return {
        "version": __version__,
        "version_info": __version_info__,
        "release_date": __release_date__,
        "release_name": __release_name__,
        "git_sha": __git_sha__,
        "git_branch": __git_branch__,
    }
