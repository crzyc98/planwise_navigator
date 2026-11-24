"""Config path rules shared by the scenario diff and the like-for-like check."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models.comparison import ConfigDelta

# Covered by their own checks (census hash, seed, years), so a different census
# path holding the same file is not a difference.
CHECKED_SEPARATELY = frozenset(
    {
        "simulation.random_seed",
        "simulation.start_year",
        "simulation.end_year",
        "setup.census_parquet_path",
        "data_sources.census_parquet_path",
    }
)
# Labels, runtime knobs and housekeeping that cannot change results. Matched
# like CONFIG_GROUP_PREFIXES ("setup.clear" covers "setup.clear_tables").
# Anything that might change results (e.g. "advanced.engine") stays out.
IGNORED_PREFIXES = (
    "simulation.name",
    "advanced.log_level",
    "advanced.memory_limit_gb",
    "advanced.checkpoint_frequency",
    "advanced.enable_multithreading",
    "advanced.strict_validation",
    # Threading, memory and the single supported execution engine.
    "optimization",
    "orchestrator.threading",
    # Archive retention and garbage collection.
    "storage",
    # Which intermediate tables are cleared between runs.
    "setup.clear",
    # Backup, log and database location settings.
    "production_safety",
)
# Lists where an empty list means the same to the engine as no setting, so
# Studio's [] after removing every entry is not a difference.
EMPTY_MEANS_UNSET = frozenset({"compensation.minimum_wage", "workforce.acquisitions"})


def matches(path: str, prefix: str) -> bool:
    """``prefix`` itself, a key under it, or a key it starts (``setup.clear_*``)."""
    return path == prefix or path.startswith((f"{prefix}.", f"{prefix}_"))


def ignored_path(path: str) -> bool:
    return path in CHECKED_SEPARATELY or any(
        matches(path, prefix) for prefix in IGNORED_PREFIXES
    )


def ignored_delta(delta: ConfigDelta) -> bool:
    """An ignored path, or a section against a non-section whose settings are
    all ignored."""
    section = delta.a if isinstance(delta.a, Mapping) else delta.b
    if not isinstance(section, Mapping):
        return ignored_path(delta.path)
    return all(ignored_path(path) for path in _leaf_paths(delta.path, section))


def _leaf_paths(path: str, value: Any) -> list[str]:
    if not isinstance(value, Mapping) or not value:
        return [path]
    return [
        leaf
        for key, child in value.items()
        for leaf in _leaf_paths(f"{path}.{key}", child)
    ]
