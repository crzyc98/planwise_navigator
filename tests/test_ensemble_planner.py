"""Fast tests for deterministic ensemble seed and output planning."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from planalign_ensemble.models import EnsembleSpec
from planalign_ensemble.planner import plan_ensemble


_PLANNED_AT = datetime(2026, 8, 3, 14, 15, 22, tzinfo=timezone.utc)


def _spec(**overrides: object) -> EnsembleSpec:
    """Return a minimal deterministic ensemble request."""
    values: dict[str, object] = {
        "scenario_id": "baseline",
        "seed_count": 3,
        "base_seed": 42,
        "start_year": 2025,
        "end_year": 2027,
    }
    values.update(overrides)
    return EnsembleSpec(**values)


@pytest.mark.fast
def test_derived_seeds_are_deterministic_from_base_seed_and_count(tmp_path) -> None:
    """A base seed produces the documented evenly-spaced sequence every time."""
    spec = _spec()

    first = plan_ensemble(spec, output_root=tmp_path, now=_PLANNED_AT)
    repeated = plan_ensemble(spec, output_root=tmp_path, now=_PLANNED_AT)

    assert first.seeds == (42, 1043, 2044)
    assert repeated.seeds == first.seeds
    assert first.ensemble_db_path.name == "ensemble.duckdb"
    assert tuple(path.name for path in first.seed_db_paths.values()) == (
        "seed_42.duckdb",
        "seed_1043.duckdb",
        "seed_2044.duckdb",
    )


@pytest.mark.fast
def test_explicit_seed_list_is_honored_in_its_declared_order(tmp_path) -> None:
    """Explicit inputs are provenance and must not be re-derived or reordered."""
    plan = plan_ensemble(
        _spec(seed_list=[9, 1, 88]), output_root=tmp_path, now=_PLANNED_AT
    )

    assert plan.seeds == (9, 1, 88)


@pytest.mark.fast
def test_duplicate_explicit_seed_list_is_rejected() -> None:
    """Planner requests preserve model-level duplicate rejection."""
    with pytest.raises(ValidationError, match="5"):
        _spec(seed_list=[5, 5, 8])


@pytest.mark.fast
def test_run_count_discloses_headline_and_attribution_work(tmp_path) -> None:
    """Planning reports the full OFAT multiplier before any worker starts."""
    plan = plan_ensemble(
        _spec(seed_count=5, attribution=True, attribution_seed_count=2),
        output_root=tmp_path,
        now=_PLANNED_AT,
    )

    assert plan.total_run_count == 11  # 5 headline + 3 subsystems × 2 seeds
    assert plan.estimated_disk_mib > 0


@pytest.mark.fast
def test_attribution_disk_estimate_includes_its_frozen_seed_worlds(tmp_path) -> None:
    """Pre-execution storage disclosure must include every planned frozen run."""
    bands_only = plan_ensemble(
        _spec(seed_count=5), output_root=tmp_path, now=_PLANNED_AT
    )
    attribution = plan_ensemble(
        _spec(seed_count=5, attribution=True, attribution_seed_count=2),
        output_root=tmp_path,
        now=_PLANNED_AT,
    )

    assert attribution.estimated_disk_mib > bands_only.estimated_disk_mib
