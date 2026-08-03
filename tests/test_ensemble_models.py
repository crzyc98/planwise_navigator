"""Fast validation tests for seed-ensemble request and result entities."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from planalign_ensemble.models import EnsembleSpec


def _spec(**overrides: object) -> EnsembleSpec:
    """Build a minimal valid ensemble request for validation tests."""
    values: dict[str, object] = {
        "scenario_id": "baseline",
        "seed_count": 3,
        "start_year": 2025,
        "end_year": 2027,
    }
    values.update(overrides)
    return EnsembleSpec(**values)


@pytest.mark.fast
def test_duplicate_explicit_seeds_are_rejected_with_repeated_values() -> None:
    """Duplicate worlds must be rejected rather than silently de-duplicated."""
    with pytest.raises(ValidationError, match="42"):
        _spec(seed_list=[42, 1043, 42])


@pytest.mark.fast
def test_attribution_seed_count_cannot_exceed_headline_seed_count() -> None:
    """Attribution must remain a paired subset of the headline ensemble."""
    with pytest.raises(ValidationError, match="attribution_seed_count"):
        _spec(attribution=True, attribution_seed_count=4)


@pytest.mark.fast
def test_seed_count_must_be_at_least_one() -> None:
    """An ensemble always contains at least one resolved seed."""
    with pytest.raises(ValidationError, match="seed_count"):
        _spec(seed_count=0)


@pytest.mark.fast
def test_minimum_sample_must_be_at_least_one() -> None:
    """A non-positive sufficiency threshold would make output misleading."""
    with pytest.raises(ValidationError, match="min_seeds"):
        _spec(min_seeds=0)
