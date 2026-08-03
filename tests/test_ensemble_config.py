"""Fast configuration validation for ensemble thresholds."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from planalign_orchestrator.config import SimulationConfig, to_dbt_vars
from planalign_orchestrator.run_metadata import compute_config_fingerprint


@pytest.mark.fast
def test_ensemble_thresholds_are_typed_and_available_at_config_load() -> None:
    """Threshold requests are validated before workers can consume resources."""
    config = SimulationConfig(
        simulation={"start_year": 2025, "end_year": 2027},
        compensation={},
        ensemble={
            "thresholds": [
                {
                    "metric": "total_employer_plan_cost",
                    "value": 2_400_000,
                    "label": "Plan cost ceiling",
                }
            ]
        },
    )

    threshold = config.ensemble.thresholds[0]
    assert threshold.metric == "total_employer_plan_cost"
    assert threshold.value == 2_400_000
    assert threshold.label == "Plan cost ceiling"


@pytest.mark.fast
def test_ensemble_threshold_requires_a_metric_name() -> None:
    """Blank metric names cannot become silently unevaluable threshold rows."""
    with pytest.raises(ValidationError, match="metric"):
        SimulationConfig(
            simulation={"start_year": 2025, "end_year": 2027},
            compensation={},
            ensemble={"thresholds": [{"metric": "", "value": 1}]},
        )


@pytest.mark.fast
def test_subsystem_freeze_vars_are_opt_in_and_change_the_fingerprint(
    minimal_config,
) -> None:
    """Ordinary configs retain their historical dbt var set and fingerprint."""
    default_vars = to_dbt_vars(minimal_config)
    default_fingerprint = compute_config_fingerprint(minimal_config)

    assert not any(key.startswith("random_seed_") for key in default_vars)

    frozen_ensemble = minimal_config.ensemble.model_copy(
        update={"frozen_subsystem_seeds": {"termination": 42}}
    )
    frozen_config = minimal_config.model_copy(update={"ensemble": frozen_ensemble})
    frozen_vars = to_dbt_vars(frozen_config)

    assert frozen_vars["random_seed_termination"] == 42
    assert "random_seed_hiring" not in frozen_vars
    assert compute_config_fingerprint(frozen_config) != default_fingerprint
