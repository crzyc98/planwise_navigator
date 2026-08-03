"""Paired one-factor-at-a-time variance attribution for seed ensembles."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from .models import (
    AttributionShare,
    MetricSeedValue,
    SeedPlan,
    SeedRunOutcome,
    Subsystem,
)


BaselineExecutor = Callable[[SeedPlan], Sequence[SeedRunOutcome]]


@dataclass(frozen=True)
class BaselineResolution:
    """The exact paired baseline set and its transparent reuse accounting."""

    outcomes: tuple[SeedRunOutcome, ...]
    reused_count: int
    executed_count: int


def resolve_baselines(
    plan: SeedPlan,
    headline_outcomes: Sequence[SeedRunOutcome],
    *,
    attribution_seeds: Sequence[int],
    config_fingerprint: str,
    execute: BaselineExecutor,
) -> BaselineResolution:
    """Reuse only completed same-seed results with the expected config identity."""
    seeds = _validated_attribution_seeds(plan, attribution_seeds)
    reusable = _reusable_outcomes(headline_outcomes, seeds, config_fingerprint)
    missing = tuple(seed for seed in seeds if seed not in reusable)
    fresh = (
        tuple(execute(_baseline_plan(plan, missing, config_fingerprint)))
        if missing
        else ()
    )
    by_seed = {outcome.seed: outcome for outcome in (*reusable.values(), *fresh)}
    outcomes = tuple(_outcome_or_failure(seed, by_seed, plan) for seed in seeds)
    return BaselineResolution(
        outcomes=outcomes,
        reused_count=len(reusable),
        executed_count=len(missing),
    )


def calculate_variance_shares(
    baseline_values: Sequence[MetricSeedValue],
    frozen_values: Sequence[MetricSeedValue],
    *,
    subsystem: Subsystem,
    baselines_reused: int,
    baselines_executed: int,
    anchor_seed: int | None = None,
) -> list[AttributionShare]:
    """Measure conditional variance change from values paired by metric, year, seed."""
    baseline = _values_by_metric_and_seed(baseline_values)
    frozen = _values_by_metric_and_seed(frozen_values)
    keys = sorted(set(baseline) | set(frozen))
    return [
        _variance_share(
            key,
            baseline.get(key, {}),
            frozen.get(key, {}),
            subsystem,
            baselines_reused,
            baselines_executed,
            anchor_seed,
        )
        for key in keys
    ]


def not_stochastic_shares(
    baseline_values: Sequence[MetricSeedValue],
    *,
    subsystems: Iterable[Subsystem],
    baselines_reused: int,
    baselines_executed: int,
) -> list[AttributionShare]:
    """Represent known non-random subsystems without fabricating zero shares."""
    grouped = _values_by_metric_and_seed(baseline_values)
    shares: list[AttributionShare] = []
    for subsystem in subsystems:
        for metric, year in sorted(grouped):
            shares.append(
                AttributionShare(
                    metric=metric,
                    simulation_year=year,
                    subsystem=subsystem,
                    n_seeds=len(grouped[(metric, year)]),
                    baselines_reused=baselines_reused,
                    baselines_executed=baselines_executed,
                    stochastic_status="not_stochastic",
                )
            )
    return shares


def _validated_attribution_seeds(
    plan: SeedPlan, seeds: Sequence[int]
) -> tuple[int, ...]:
    """Require a nonempty, duplicate-free subset of the headline seed order."""
    normalized = tuple(seeds)
    if not normalized:
        raise ValueError("attribution requires at least one seed")
    if len(normalized) != len(set(normalized)):
        raise ValueError("attribution seeds must not contain duplicates")
    missing = sorted(set(normalized) - set(plan.seeds))
    if missing:
        raise ValueError(
            f"attribution seeds are not in the headline ensemble: {missing}"
        )
    return normalized


def _reusable_outcomes(
    outcomes: Sequence[SeedRunOutcome],
    seeds: Sequence[int],
    fingerprint: str,
) -> dict[int, SeedRunOutcome]:
    """Select real completed result files that satisfy the exact reuse guard."""
    wanted = set(seeds)
    return {
        outcome.seed: outcome
        for outcome in outcomes
        if outcome.seed in wanted
        and outcome.succeeded
        and outcome.config_fingerprint == fingerprint
        and outcome.db_path.exists()
    }


def _baseline_plan(plan: SeedPlan, seeds: Sequence[int], fingerprint: str) -> SeedPlan:
    """Allocate fresh baseline databases without ever revising headline outputs."""
    paths = {
        seed: plan.ensemble_db_path.parent
        / "attribution"
        / "baselines"
        / f"seed_{seed}.duckdb"
        for seed in seeds
    }
    return plan.model_copy(
        update={
            "seeds": tuple(seeds),
            "seed_db_paths": paths,
            "config_fingerprint": fingerprint,
            "total_run_count": len(seeds),
        }
    )


def _outcome_or_failure(
    seed: int,
    outcomes: dict[int, SeedRunOutcome],
    plan: SeedPlan,
) -> SeedRunOutcome:
    """Preserve an executor omission as an explicit failed baseline outcome."""
    outcome = outcomes.get(seed)
    if outcome is not None:
        return outcome
    return SeedRunOutcome(
        seed=seed,
        db_path=plan.seed_db_paths[seed],
        status="failed",
        error="baseline executor returned no terminal outcome",
    )


def _values_by_metric_and_seed(
    values: Sequence[MetricSeedValue],
) -> dict[tuple[str, int], dict[int, float]]:
    """Index non-null values so every variance calculation is seed-paired."""
    grouped: dict[tuple[str, int], dict[int, float]] = defaultdict(dict)
    for item in values:
        if item.value is None:
            continue
        key = (item.metric, item.simulation_year)
        if item.seed in grouped[key]:
            raise ValueError(
                f"duplicate attribution evidence for {key}, seed {item.seed}"
            )
        grouped[key][item.seed] = float(item.value)
    return grouped


def _variance_share(
    key: tuple[str, int],
    baseline: dict[int, float],
    frozen: dict[int, float],
    subsystem: Subsystem,
    reused: int,
    executed: int,
    anchor_seed: int | None = None,
) -> AttributionShare:
    """Compute one anchored conditional variance change over the shared seed set."""
    paired_seeds = sorted(set(baseline) & set(frozen))
    common = {
        "metric": key[0],
        "simulation_year": key[1],
        "subsystem": subsystem,
        "n_seeds": len(paired_seeds),
        "baselines_reused": reused,
        "baselines_executed": executed,
        "anchor_seed": anchor_seed,
        "stochastic_status": "stochastic",
    }
    if len(paired_seeds) < 2:
        return AttributionShare(**common)
    baseline_variance = float(np.var([baseline[seed] for seed in paired_seeds], ddof=1))
    frozen_variance = float(np.var([frozen[seed] for seed in paired_seeds], ddof=1))
    variance_share = (
        None
        if baseline_variance == 0.0
        else 1.0 - (frozen_variance / baseline_variance)
    )
    return AttributionShare(
        **common,
        baseline_variance=baseline_variance,
        frozen_variance=frozen_variance,
        variance_share=variance_share,
    )


def attribute_variance(
    plan: SeedPlan,
    headline_outcomes: Sequence[SeedRunOutcome],
    *,
    subsystems: Iterable[Subsystem] | None = None,
    config: Any | None = None,
    parallel: int | None = None,
) -> list[AttributionShare]:
    """Execute frozen ensembles and return ranked one-factor-at-a-time shares."""
    if config is None:
        raise ValueError("attribution requires the resolved simulation configuration")
    selected_seeds = _attribution_seed_list(plan)
    baseline_fingerprint = _fingerprint(config, plan)
    resolution = resolve_baselines(
        plan,
        headline_outcomes,
        attribution_seeds=selected_seeds,
        config_fingerprint=baseline_fingerprint,
        execute=lambda fresh_plan: _execute_seed_runs(
            fresh_plan, config, parallel, "baseline"
        ),
    )
    baseline_plan = _outcome_plan(
        plan, selected_seeds, resolution.outcomes, baseline_fingerprint
    )
    _write_provenance(baseline_plan, role="attribution_baseline")
    baseline_values = _extract_values(baseline_plan, resolution.outcomes)
    eligible_baseline_values = _sufficient_baseline_values(
        baseline_values, plan.spec.min_seeds
    )
    if not eligible_baseline_values:
        return []
    selected_subsystems = tuple(subsystems or tuple(Subsystem))
    shares = _frozen_shares(
        plan,
        selected_seeds,
        selected_subsystems,
        eligible_baseline_values,
        resolution,
        config,
        parallel,
    )
    shares.extend(
        not_stochastic_shares(
            eligible_baseline_values,
            subsystems=(
                item for item in selected_subsystems if not item.is_seed_variant
            ),
            baselines_reused=resolution.reused_count,
            baselines_executed=resolution.executed_count,
        )
    )
    ordered = _rank_shares(shares)
    write_attribution_results(plan.ensemble_db_path, plan, ordered)
    return ordered


def write_attribution_results(
    ensemble_db_path: Path,
    plan: SeedPlan,
    shares: Sequence[AttributionShare],
) -> None:
    """Persist attribution results beside distributions in the ensemble database."""
    rows = [
        (
            plan.ensemble_id,
            plan.scenario_id,
            share.metric,
            share.simulation_year,
            share.subsystem.value,
            share.variance_share,
            share.baseline_variance,
            share.frozen_variance,
            share.anchor_seed,
            share.n_seeds,
            share.baselines_reused,
            share.baselines_executed,
            share.stochastic_status,
        )
        for share in shares
    ]
    if not rows:
        return
    ensemble_db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(ensemble_db_path)) as connection:
        connection.execute(_CREATE_ATTRIBUTION_SQL)
        connection.executemany(
            "INSERT INTO fct_variance_attribution VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


_CREATE_ATTRIBUTION_SQL = """
CREATE TABLE IF NOT EXISTS fct_variance_attribution (
    ensemble_id VARCHAR NOT NULL,
    scenario_id VARCHAR NOT NULL,
    metric VARCHAR NOT NULL,
    simulation_year INTEGER NOT NULL,
    subsystem VARCHAR NOT NULL,
    variance_share DOUBLE,
    baseline_variance DOUBLE,
    frozen_variance DOUBLE,
    anchor_seed INTEGER,
    n_seeds INTEGER NOT NULL,
    baselines_reused INTEGER NOT NULL,
    baselines_executed INTEGER NOT NULL,
    stochastic_status VARCHAR NOT NULL,
    PRIMARY KEY (ensemble_id, scenario_id, metric, simulation_year, subsystem)
)
"""


def _attribution_seed_list(plan: SeedPlan) -> tuple[int, ...]:
    """Choose the documented headline subset used by every frozen comparison."""
    count = plan.spec.resolved_attribution_seed_count or len(plan.seeds)
    return _validated_attribution_seeds(plan, plan.seeds[:count])


def _fingerprint(config: Any, plan: SeedPlan) -> str:
    """Use the project's seed-independent identity for reuse safety."""
    if not hasattr(config, "simulation"):
        if plan.config_fingerprint:
            return plan.config_fingerprint
        raise ValueError("attribution configuration has no fingerprintable simulation")
    from planalign_orchestrator.run_metadata import compute_config_fingerprint

    return compute_config_fingerprint(config)


def _execute_seed_runs(
    plan: SeedPlan, config: Any, parallel: int | None, job_prefix: str
) -> tuple[SeedRunOutcome, ...]:
    """Invoke the canonical pool worker without introducing a second executor."""
    from .runner import execute_seed_runs

    return execute_seed_runs(plan, config, parallel=parallel, job_prefix=job_prefix)


def _outcome_plan(
    plan: SeedPlan,
    seeds: Sequence[int],
    outcomes: Sequence[SeedRunOutcome],
    fingerprint: str,
) -> SeedPlan:
    """Build provenance from the actual reused or freshly executed DB paths."""
    paths = {outcome.seed: outcome.db_path for outcome in outcomes}
    return plan.model_copy(
        update={
            "seeds": tuple(seeds),
            "seed_db_paths": {seed: paths[seed] for seed in seeds},
            "config_fingerprint": fingerprint,
            "total_run_count": len(seeds),
        }
    )


def _extract_values(
    plan: SeedPlan, outcomes: Sequence[SeedRunOutcome]
) -> list[MetricSeedValue]:
    """Read only completed immutable result databases in deterministic order."""
    from .extract import extract_completed_outcomes

    return extract_completed_outcomes(
        outcomes, ensemble_id=plan.ensemble_id, scenario_id=plan.scenario_id
    )


def _sufficient_baseline_values(
    values: Sequence[MetricSeedValue], min_seeds: int
) -> list[MetricSeedValue]:
    """Keep attribution out of metric/year groups below the band sample floor."""
    seed_sets: dict[tuple[str, int], set[int]] = defaultdict(set)
    for item in values:
        if item.value is not None:
            seed_sets[(item.metric, item.simulation_year)].add(item.seed)
    eligible = {key for key, seeds in seed_sets.items() if len(seeds) >= min_seeds}
    return [
        item
        for item in values
        if (item.metric, item.simulation_year) in eligible and item.value is not None
    ]


def _frozen_shares(
    plan: SeedPlan,
    seeds: Sequence[int],
    subsystems: Sequence[Subsystem],
    baseline_values: Sequence[MetricSeedValue],
    resolution: BaselineResolution,
    config: Any,
    parallel: int | None,
) -> list[AttributionShare]:
    """Run each independently seed-variant subsystem once with a pinned stream."""
    shares: list[AttributionShare] = []
    for subsystem in (item for item in subsystems if item.is_seed_variant):
        frozen_config = _frozen_config(config, subsystem, seeds[0])
        frozen_plan = _frozen_plan(
            plan, seeds, subsystem, _fingerprint(frozen_config, plan)
        )
        outcomes = _execute_seed_runs(
            frozen_plan, frozen_config, parallel, subsystem.value
        )
        _write_provenance(
            frozen_plan, role="attribution_frozen", frozen_subsystem=subsystem
        )
        calculated = calculate_variance_shares(
            baseline_values,
            _extract_values(frozen_plan, outcomes),
            subsystem=subsystem,
            baselines_reused=resolution.reused_count,
            baselines_executed=resolution.executed_count,
            anchor_seed=seeds[0],
        )
        shares.extend(
            share
            for share in calculated
            if share.n_seeds >= plan.spec.min_seeds
            and (share.metric, share.simulation_year)
            in {(item.metric, item.simulation_year) for item in baseline_values}
        )
    return shares


def _frozen_config(config: Any, subsystem: Subsystem, frozen_seed: int) -> Any:
    """Copy the typed config with exactly one attribution stream pinned."""
    if not hasattr(config, "ensemble") or not hasattr(config, "model_copy"):
        raise ValueError("attribution requires a typed SimulationConfig")
    ensemble = config.ensemble.model_copy(
        update={"frozen_subsystem_seeds": {subsystem.value: frozen_seed}}
    )
    return config.model_copy(update={"ensemble": ensemble})


def _frozen_plan(
    plan: SeedPlan,
    seeds: Sequence[int],
    subsystem: Subsystem,
    fingerprint: str,
) -> SeedPlan:
    """Allocate a dedicated immutable result DB for every frozen seed world."""
    paths = {
        seed: plan.ensemble_db_path.parent
        / "attribution"
        / subsystem.value
        / f"seed_{seed}.duckdb"
        for seed in seeds
    }
    return plan.model_copy(
        update={
            "seeds": tuple(seeds),
            "seed_db_paths": paths,
            "config_fingerprint": fingerprint,
            "total_run_count": len(seeds),
        }
    )


def _write_provenance(
    plan: SeedPlan,
    *,
    role: str,
    frozen_subsystem: Subsystem | None = None,
) -> None:
    """Record the attribution role using the existing additive metadata table."""
    from .provenance import write_ensemble_provenance

    write_ensemble_provenance(
        plan,
        role=role,  # type: ignore[arg-type]
        frozen_subsystem=frozen_subsystem,
    )


def _rank_shares(shares: Sequence[AttributionShare]) -> list[AttributionShare]:
    """Return stable metric/year rankings while structural absences stay last."""
    return sorted(
        shares,
        key=lambda item: (
            item.metric,
            item.simulation_year,
            item.stochastic_status == "not_stochastic",
            -(
                item.variance_share
                if item.variance_share is not None
                else float("-inf")
            ),
            item.subsystem.value,
        ),
    )


__all__ = [
    "BaselineResolution",
    "attribute_variance",
    "calculate_variance_shares",
    "not_stochastic_shares",
    "resolve_baselines",
    "write_attribution_results",
]
