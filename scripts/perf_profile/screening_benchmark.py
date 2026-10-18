"""Paired, isolated first-year/full-horizon screening feasibility experiment."""

from __future__ import annotations

import statistics
import time
import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.run_pool import PoolEvent, ScenarioRunPool, WorkerBudget

from planalign_optimizer.baseline import fingerprint_baseline
from planalign_optimizer.design_space import sample_candidates
from planalign_optimizer.evaluate import validate_levers_against_baseline
from planalign_optimizer.models import Candidate, LeverValue, OptimizerSpec
from planalign_optimizer.pareto import pareto_frontier
from .screening import ScreeningPolicy, select_for_validation
from planalign_optimizer.search import _evaluate_candidate_values, rank_feasible
from .screening_resources import ProcessResources
from planalign_optimizer.spec_io import validate_spec


class BenchmarkSettings(BaseModel):
    """Prespecified cost and quality gates; all runs count toward the cap."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int = Field(default=8, ge=2)
    repetitions: int = Field(default=3, ge=1)
    max_simulations: int = Field(ge=1)
    search_seed: int = 42
    minimum_speedup: float = Field(default=1.5, gt=1, allow_inf_nan=False)
    policy: ScreeningPolicy = Field(default_factory=ScreeningPolicy)


class EvaluationStage(BaseModel):
    """Measured pool wall time includes startup and metric extraction."""

    model_config = ConfigDict(frozen=True)

    fidelity: Literal["first_year", "full_horizon", "selected_full_horizon"]
    start_year: int
    end_year: int
    config_fingerprint: str
    wall_seconds: float
    sampled_peak_rss_mib: float
    candidates: tuple[Candidate, ...]


class QualityResult(BaseModel):
    """Truth is the full-horizon ledger, including rejected candidates."""

    missed_feasible: tuple[str, ...]
    frontier_retention: float | None
    objective_loss_fraction: float | None
    evidence_complete: bool
    replay_matches: bool


class BenchmarkTrial(BaseModel):
    reference: EvaluationStage
    screening: EvaluationStage
    validation: EvaluationStage
    selection: dict[str, str]
    selection_seconds: float
    speedup: float | None
    quality: QualityResult
    single_objective_quality: QualityResult


class ScreeningBenchmark(BaseModel):
    """A research artifact, deliberately separate from promotable OptimizerRun."""

    settings: BenchmarkSettings
    spec: OptimizerSpec
    worker_limit: int
    simulation_seed: int
    trials: tuple[BenchmarkTrial, ...]
    simulation_count: int
    median_speedup: float | None
    decision: Literal["NO_GO", "INSUFFICIENT_EVIDENCE", "GO_FOR_EXPANDED_BENCHMARK"]
    reasons: tuple[str, ...]


def run_screening_benchmark(
    spec: OptimizerSpec,
    baseline: SimulationConfig,
    settings: BenchmarkSettings,
    database_dir: Path,
    budget: WorkerBudget,
    *,
    pool_factory: Callable[[int], ScenarioRunPool] = ScenarioRunPool,
    on_event: Callable[[PoolEvent], None] | None = None,
) -> ScreeningBenchmark:
    """Run fixed paired designs, then actually time retained full evaluations.

    Reserve the worst-case 3*N budget before any writes. Fresh output roots
    prevent accidental evidence reuse; screening never enters normal search.
    """
    _validate_request(spec, baseline, settings, database_dir, budget)
    values = sample_candidates(
        spec.design_space, settings.candidate_count, seed=settings.search_seed
    )
    if len(values) < 2:
        raise ValueError("benchmark requires at least two unique designs")
    low_payload = baseline.model_dump(mode="python")
    low_payload["simulation"]["end_year"] = baseline.simulation.start_year
    low = SimulationConfig.model_validate(low_payload)
    database_dir.mkdir(parents=True, exist_ok=False)
    (database_dir / "settings.json").write_text(settings.model_dump_json(indent=2))
    (database_dir / "spec.json").write_text(spec.model_dump_json(indent=2))
    (database_dir / "baseline.json").write_text(baseline.model_dump_json(indent=2))
    trials = tuple(
        _run_trial(
            spec,
            baseline,
            low,
            values,
            settings,
            database_dir / f"trial-{index:02d}",
            budget,
            pool_factory,
            on_event,
        )
        for index in range(settings.repetitions)
    )
    return summarize_benchmark(spec, baseline, settings, budget, trials)


def _validate_request(
    spec: OptimizerSpec,
    baseline: SimulationConfig,
    settings: BenchmarkSettings,
    database_dir: Path,
    budget: WorkerBudget,
) -> None:
    validate_spec(spec)
    validate_levers_against_baseline(baseline, spec.design_space.levers)
    if any(
        not math.isfinite(constraint.threshold)
        for constraint in spec.objective.constraints
    ):
        raise ValueError("benchmark constraint thresholds must be finite")
    if baseline.simulation.end_year <= baseline.simulation.start_year:
        raise ValueError("screening benchmark requires a multi-year baseline")
    if spec.baseline.ensemble_database or any(
        constraint.percentile is not None for constraint in spec.objective.constraints
    ):
        raise ValueError("benchmark supports candidate point estimates only")
    required = 3 * settings.candidate_count * settings.repetitions
    if settings.max_simulations < required:
        raise ValueError(
            f"max_simulations must reserve at least {required} evaluations"
        )
    if budget.workers < 1:
        raise ValueError("benchmark requires at least one worker")
    if database_dir.exists():
        raise ValueError("benchmark output directory must be fresh")


def _run_trial(
    spec: OptimizerSpec,
    baseline: SimulationConfig,
    low: SimulationConfig,
    values: Sequence[dict[str, LeverValue]],
    settings: BenchmarkSettings,
    directory: Path,
    budget: WorkerBudget,
    pool_factory: Callable[[int], ScenarioRunPool],
    on_event: Callable[[PoolEvent], None] | None,
) -> BenchmarkTrial:
    # Alternate order across trials to reduce systematic warm-cache bias.
    index = int(directory.name.split("-")[-1])
    stages = (("full_horizon", baseline), ("first_year", low))
    measured = {
        fidelity: _measure_stage(
            fidelity,
            spec,
            config,
            values,
            directory / fidelity,
            budget,
            pool_factory,
            on_event,
        )
        for fidelity, config in (stages if index % 2 == 0 else stages[::-1])
    }
    reference, screening = measured["full_horizon"], measured["first_year"]
    started = time.perf_counter()
    selection = select_for_validation(
        screening.candidates, spec.objective, settings.policy, seed=settings.search_seed
    )
    selection_seconds = time.perf_counter() - started
    retained = [
        candidate
        for candidate in screening.candidates
        if candidate.candidate_id in selection
    ]
    validation = _measure_stage(
        "selected_full_horizon",
        spec,
        baseline,
        [candidate.lever_values for candidate in retained],
        directory / "validation",
        budget,
        pool_factory,
        on_event,
    )
    # The normal evaluator numbers its input from zero; preserve paired IDs.
    validation = validation.model_copy(
        update={
            "candidates": tuple(
                candidate.model_copy(update={"candidate_id": source.candidate_id})
                for source, candidate in zip(
                    retained, validation.candidates, strict=True
                )
            )
        }
    )
    staged_seconds = (
        screening.wall_seconds + selection_seconds + validation.wall_seconds
    )
    return BenchmarkTrial(
        reference=reference,
        screening=screening,
        validation=validation,
        selection=selection,
        selection_seconds=selection_seconds,
        speedup=reference.wall_seconds / staged_seconds if staged_seconds > 0 else None,
        quality=compare_quality(reference.candidates, validation.candidates, spec),
        single_objective_quality=compare_quality(
            reference.candidates,
            validation.candidates,
            spec.model_copy(
                update={
                    "objective": spec.objective.model_copy(
                        update={"objectives": spec.objective.objectives[:1]}
                    )
                }
            ),
        ),
    )


def _measure_stage(
    fidelity: str,
    spec: OptimizerSpec,
    config: SimulationConfig,
    values: Sequence[dict[str, LeverValue]],
    directory: Path,
    budget: WorkerBudget,
    pool_factory: Callable[[int], ScenarioRunPool],
    on_event: Callable[[PoolEvent], None] | None,
) -> EvaluationStage:
    started = time.perf_counter()
    with ProcessResources() as resources:
        candidates = _evaluate_candidate_values(
            values, spec, config, directory, len(values), budget, pool_factory, on_event
        )
    return EvaluationStage(
        fidelity=fidelity,
        start_year=config.simulation.start_year,
        end_year=config.simulation.end_year,
        config_fingerprint=fingerprint_baseline(config),
        wall_seconds=time.perf_counter() - started,
        sampled_peak_rss_mib=resources.peak_rss_mib,
        candidates=candidates,
    )


def compare_quality(
    reference: Sequence[Candidate], retained: Sequence[Candidate], spec: OptimizerSpec
) -> QualityResult:
    """Compare full-result feasibility, frontier recall, and objective loss."""
    retained_ids = {candidate.candidate_id for candidate in retained}
    validated_ids = {
        candidate.candidate_id
        for candidate in retained
        if candidate.status == "feasible" and _complete_candidate(candidate)
    }
    feasible = [candidate for candidate in reference if candidate.status == "feasible"]
    frontier = pareto_frontier(reference, spec.objective.objectives)
    truth = {candidate.candidate_id: candidate for candidate in reference}
    replay = all(
        _same_evidence(truth[candidate.candidate_id], candidate)
        for candidate in retained
    )
    return QualityResult(
        missed_feasible=tuple(
            sorted(
                candidate.candidate_id
                for candidate in feasible
                if candidate.candidate_id not in retained_ids
            )
        ),
        frontier_retention=(
            len(set(frontier) & validated_ids) / len(frontier) if frontier else None
        ),
        objective_loss_fraction=_objective_loss(reference, retained, spec),
        evidence_complete=bool(feasible)
        and all(
            _complete_candidate(candidate) for candidate in (*reference, *retained)
        ),
        replay_matches=replay,
    )


def _complete_candidate(candidate: Candidate) -> bool:
    return (
        candidate.status in {"feasible", "infeasible"}
        and all(
            value is not None and math.isfinite(value)
            for value in candidate.objective_values.values()
        )
        and all(
            result.evaluated_value is not None
            and math.isfinite(result.evaluated_value)
            and result.satisfied is not None
            for result in candidate.constraint_results
        )
    )


def _same_evidence(first: Candidate, second: Candidate) -> bool:
    return (first.status, first.objective_values, first.constraint_results) == (
        second.status,
        second.objective_values,
        second.constraint_results,
    )


def _objective_loss(
    reference: Sequence[Candidate], retained: Sequence[Candidate], spec: OptimizerSpec
) -> float | None:
    if len(spec.objective.objectives) != 1:
        return None
    full_rank, selected_rank = rank_feasible(reference, spec.objective), rank_feasible(
        retained, spec.objective
    )
    if not full_rank or not selected_rank:
        return None
    metric = spec.objective.objectives[0].metric
    full = next(
        candidate.objective_values[metric]
        for candidate in reference
        if candidate.candidate_id == full_rank[0]
    )
    selected = next(
        candidate.objective_values[metric]
        for candidate in retained
        if candidate.candidate_id == selected_rank[0]
    )
    if full is None or selected is None:
        return None
    difference = abs(selected - full)
    return difference / abs(full) if full else (0.0 if difference == 0 else None)


def summarize_benchmark(
    spec: OptimizerSpec,
    baseline: SimulationConfig,
    settings: BenchmarkSettings,
    budget: WorkerBudget,
    trials: Sequence[BenchmarkTrial],
) -> ScreeningBenchmark:
    """Require zero observed selection/replay loss and the prespecified speedup."""
    speedups = [trial.speedup for trial in trials if trial.speedup is not None]
    median = statistics.median(speedups) if speedups else None
    reasons: list[str] = []
    if any(trial.quality.missed_feasible for trial in trials):
        reasons.append("screening rejected full-horizon feasible designs")
    complete = all(trial.quality.evidence_complete for trial in trials)
    if complete and any(not trial.quality.replay_matches for trial in trials):
        reasons.append("retained full-horizon evidence did not replay exactly")
    if complete and median is not None and median < settings.minimum_speedup:
        reasons.append("measured savings missed the prespecified speedup gate")
    decision = "NO_GO" if reasons else "GO_FOR_EXPANDED_BENCHMARK"
    if not complete or settings.repetitions < 3 or median is None:
        reasons.append("three complete repetitions with feasible evidence are required")
        if decision != "NO_GO":
            decision = "INSUFFICIENT_EVIDENCE"
    return ScreeningBenchmark(
        settings=settings,
        spec=spec,
        worker_limit=budget.workers,
        simulation_seed=baseline.simulation.random_seed,
        trials=tuple(trials),
        simulation_count=sum(
            len(stage.candidates)
            for trial in trials
            for stage in (trial.reference, trial.screening, trial.validation)
        ),
        median_speedup=median,
        decision=decision,
        reasons=tuple(reasons),
    )
