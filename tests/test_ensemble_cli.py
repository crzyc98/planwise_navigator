"""Fast CLI option and exit-code tests for seed ensembles."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from planalign_cli.commands.simulate import (
    _ensemble_exit_code,
    _parse_seed_list,
    _parse_threshold,
    default,
    run_simulation,
)
from planalign_cli.main import simulate as main_simulate
from planalign_cli.commands.batch import default as batch_default
from planalign_cli.commands.batch import run_batch
from planalign_cli.main import batch as main_batch
from planalign_ensemble.models import (
    EnsembleResult,
    EnsembleSpec,
    SeedPlan,
    SeedRunOutcome,
)


def _result(statuses: list[str]) -> EnsembleResult:
    """Construct a small result shape solely for exit-status coverage."""
    spec = EnsembleSpec(
        scenario_id="baseline", seed_count=len(statuses), start_year=2025, end_year=2025
    )
    plan = SeedPlan(
        ensemble_id="ens",
        scenario_id="baseline",
        seeds=tuple(range(len(statuses))),
        seed_db_paths={
            index: Path(f"seed_{index}.duckdb") for index in range(len(statuses))
        },
        ensemble_db_path=Path("ensemble.duckdb"),
        total_run_count=len(statuses),
        estimated_disk_mib=1,
        spec=spec,
    )
    outcomes = tuple(
        SeedRunOutcome(seed=index, db_path=plan.seed_db_paths[index], status=status)
        for index, status in enumerate(statuses)
    )
    return EnsembleResult(plan=plan, outcomes=outcomes)


@pytest.mark.fast
def test_seed_options_exist_on_both_simulate_entry_points() -> None:
    """The documented and hidden command variants cannot silently diverge."""
    required = {
        "seeds",
        "seed_list",
        "min_seeds",
        "discard_seed_dbs",
        "threshold",
        "attribution",
        "attribution_seeds",
    }

    assert required <= set(inspect.signature(run_simulation).parameters)
    assert required <= set(inspect.signature(default).parameters)
    assert required <= set(inspect.signature(main_simulate).parameters)


@pytest.mark.fast
def test_explicit_seed_list_parser_is_strict_and_order_preserving() -> None:
    """CLI strings become exact provenance inputs, not a silently repaired set."""
    assert _parse_seed_list("42, 1043,2044") == (42, 1043, 2044)
    with pytest.raises(ValueError, match="integer"):
        _parse_seed_list("42,nope")


@pytest.mark.fast
def test_threshold_parser_requires_metric_and_numeric_value() -> None:
    """Repeatable CLI thresholds are validated before any ensemble starts."""
    threshold = _parse_threshold("total_employer_plan_cost:2400000")

    assert threshold.metric == "total_employer_plan_cost"
    assert threshold.value == 2_400_000
    with pytest.raises(ValueError, match="metric:value"):
        _parse_threshold("not-a-threshold")


@pytest.mark.fast
def test_batch_exposes_the_same_seed_count_option() -> None:
    """Each batch scenario can opt into the same isolated ensemble semantics."""
    required = {
        "seeds",
        "seed_list",
        "min_seeds",
        "discard_seed_dbs",
        "threshold",
        "attribution",
        "attribution_seeds",
    }
    for command in (run_batch, batch_default, main_batch):
        assert required <= set(inspect.signature(command).parameters)


@pytest.mark.fast
def test_ensemble_exit_codes_preserve_success_for_thin_samples() -> None:
    """Partial failures and no-success runs are distinct from withheld bands."""
    assert _ensemble_exit_code(_result(["completed"])) == 0
    assert _ensemble_exit_code(_result(["completed", "failed"])) == 2
    assert _ensemble_exit_code(_result(["failed", "failed"])) == 3
