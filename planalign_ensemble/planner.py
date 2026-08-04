"""Deterministic seed resolution and isolated ensemble path planning."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import EnsembleSpec, SeedPlan, Subsystem


_DERIVED_SEED_INCREMENT = 1001

# Calibrated against two measured ensembles (issue #544): a 5-year, ~7k-employee
# run produced a ~58 MiB seed database and a ~17.8 MiB dbt artifacts directory
# per run (headline or attribution alike), and a ~2 MiB aggregate database. The
# per-year rate lets the estimate track `--seeds`/horizon changes instead of
# staying flat; the artifacts and aggregate constants keep headroom over the
# measured values rather than matching them exactly.
_SEED_DB_MIB_PER_YEAR = 11.6
_SEED_ARTIFACTS_MIB = 18.0
_ESTIMATED_ENSEMBLE_DB_MIB = 4.0
_UNSAFE_PATH_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")

# Offset well clear of any plausible headline seed range so an anchor seed can
# never collide with a headline seed, keeping the two seed spaces legible in
# logs and output paths.
_ANCHOR_SEED_OFFSET = 9_000_000


def plan_ensemble(
    spec: EnsembleSpec,
    *,
    output_root: Path = Path("var/ensembles"),
    now: datetime | None = None,
    config_fingerprint: str = "",
) -> SeedPlan:
    """Resolve all seed inputs and isolated output paths before execution.

    The plan deliberately has no side effects: workers are the first code to
    create output directories, after the CLI has disclosed the full cost.
    """
    seeds = spec.seed_list or _derive_seeds(spec.base_seed, spec.seed_count)
    timestamp = _resolve_timestamp(now)
    ensemble_dir = output_root / f"{timestamp}-{_safe_component(spec.scenario_id)}"
    paths = {seed: ensemble_dir / f"seed_{seed}.duckdb" for seed in seeds}
    attribution_runs = (
        len(_attributable_subsystems())
        * spec.resolved_attribution_seed_count
        * spec.resolved_attribution_anchor_count
    )
    planned_seed_databases = len(seeds) + attribution_runs
    return SeedPlan(
        ensemble_id=_ensemble_id(spec.scenario_id, seeds, config_fingerprint),
        scenario_id=spec.scenario_id,
        seeds=tuple(seeds),
        seed_db_paths=paths,
        ensemble_db_path=ensemble_dir / "ensemble.duckdb",
        config_fingerprint=config_fingerprint,
        total_run_count=len(seeds) + attribution_runs,
        estimated_disk_mib=_estimate_disk_mib(
            planned_seed_databases, spec.start_year, spec.end_year
        ),
        spec=spec,
    )


def _estimate_disk_mib(
    planned_seed_databases: int, start_year: int, end_year: int
) -> float:
    """Scale the per-run estimate by horizon so shortening it lowers the figure."""
    horizon_years = end_year - start_year + 1
    per_run_mib = (_SEED_DB_MIB_PER_YEAR * horizon_years) + _SEED_ARTIFACTS_MIB
    return (planned_seed_databases * per_run_mib) + _ESTIMATED_ENSEMBLE_DB_MIB


def _derive_seeds(base_seed: int, seed_count: int) -> tuple[int, ...]:
    """Derive a readable, stable sequence without depending on RNG state."""
    return tuple(
        base_seed + (_DERIVED_SEED_INCREMENT * index) for index in range(seed_count)
    )


def _resolve_timestamp(now: datetime | None) -> str:
    """Render a UTC path component that is stable when supplied by tests."""
    resolved = now or datetime.now(timezone.utc)
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_component(value: str) -> str:
    """Keep scenario names usable in a platform-independent path."""
    cleaned = _UNSAFE_PATH_COMPONENT.sub("-", value).strip(".-")
    return cleaned or "scenario"


def _ensemble_id(
    scenario_id: str, seeds: tuple[int, ...], config_fingerprint: str
) -> str:
    """Produce a reproducible identifier for the aggregate's logical inputs."""
    payload = json.dumps(
        {
            "scenario_id": scenario_id,
            "seeds": seeds,
            "config_fingerprint": config_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _attributable_subsystems() -> tuple[Subsystem, ...]:
    """Return only production subsystems with independently seedable draws."""
    return tuple(subsystem for subsystem in Subsystem if subsystem.is_seed_variant)


def resolve_attribution_anchor_seeds(spec: EnsembleSpec) -> tuple[int, ...]:
    """Derive the deterministic anchor seeds averaged over for attribution.

    Averaging the frozen arm's conditional variance over several anchors,
    rather than pinning to one, is what makes the estimate approximate the
    subsystem's first-order Sobol index instead of an arbitrary single-anchor
    value (#543). Anchors live in a disjoint numeric range from headline seeds
    so the two spaces never collide and stay legible in logs and output paths.
    """
    count = spec.resolved_attribution_anchor_count
    if count == 0:
        return ()
    return tuple(
        spec.base_seed + _ANCHOR_SEED_OFFSET + (_DERIVED_SEED_INCREMENT * index)
        for index in range(count)
    )


__all__ = ["plan_ensemble", "resolve_attribution_anchor_seeds"]
