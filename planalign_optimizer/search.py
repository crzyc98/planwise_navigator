"""Deterministic, hard-budgeted optimizer search over isolated scenarios."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from planalign_ensemble.runner import run_seed_worker
from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.run_pool import (
    JobResult,
    PoolEvent,
    ScenarioJob,
    ScenarioRunPool,
    WorkerBudget,
    resolve_worker_count,
)

from .baseline import fingerprint_baseline
from .design_space import candidate_identity, refine_candidates, sample_candidates
from .evaluate import (
    candidate_from_job_result,
    classify_candidate,
    resolve_candidate_config,
)
from .models import (
    Candidate,
    LeverValue,
    ObjectiveConstraintSpec,
    OptimizerRun,
    OptimizerSpec,
)
from .pareto import pareto_frontier

SEED_PHASE_FRACTION = 0.6


def seed_phase_count(max_runs: int) -> int:
    """Return how many candidates the deterministic seed phase requests.

    Shared between the real search loop and the CLI's ``--dry-run`` preview
    so the two never drift out of sync on what "the seed phase" means.
    """
    return max(1, math.ceil(max_runs * SEED_PHASE_FRACTION))


def run_optimizer(
    spec: OptimizerSpec,
    baseline: SimulationConfig,
    *,
    max_runs: int,
    search_seed: int,
    database_dir: Path,
    parallel: int | None = None,
    on_event: Callable[[PoolEvent], None] | None = None,
    pool_factory: Callable[[int], ScenarioRunPool] = ScenarioRunPool,
) -> tuple[OptimizerRun, WorkerBudget]:
    """Evaluate at most ``max_runs`` exact-unique designs and summarize them."""
    if max_runs < 1:
        raise ValueError("max_runs must be >= 1")
    database_dir.mkdir(parents=True, exist_ok=True)
    budget = resolve_worker_count(parallel, max_runs)
    seed_count = seed_phase_count(max_runs)
    seed_values = sample_candidates(spec.design_space, seed_count, seed=search_seed)
    candidates = _evaluate_values(
        seed_values,
        spec,
        baseline,
        database_dir,
        max_runs,
        budget,
        pool_factory,
        on_event,
    )
    evaluated = sum(candidate.is_duplicate_of is None for candidate in candidates)
    remaining = max_runs - evaluated
    if remaining > 0 and candidates:
        anchor = _refinement_anchor(candidates, spec.objective)
        excluded = {
            candidate_identity(candidate.lever_values) for candidate in candidates
        }
        refinement_values = refine_candidates(
            spec.design_space,
            anchor.lever_values,
            remaining,
            seed=search_seed + 1,
            exclude=excluded,
        )
        candidates += _evaluate_values(
            refinement_values,
            spec,
            baseline,
            database_dir,
            remaining,
            budget,
            pool_factory,
            on_event,
            start_index=len(candidates),
        )
    run = _build_run(spec, baseline, max_runs, search_seed, candidates)
    return run, budget


def rank_feasible(
    candidates: Sequence[Candidate], spec: ObjectiveConstraintSpec
) -> tuple[str, ...]:
    """Rank feasible candidates for a single objective with stable tie-breaking."""
    if len(spec.objectives) != 1:
        return ()
    objective = spec.objectives[0]
    feasible = [
        candidate
        for candidate in candidates
        if candidate.status == "feasible"
        and candidate.objective_values.get(objective.metric) is not None
    ]
    direction = 1 if objective.direction == "minimize" else -1
    feasible.sort(
        key=lambda candidate: (
            direction * _objective_value(candidate, objective.metric),
            candidate.candidate_id,
        )
    )
    return tuple(candidate.candidate_id for candidate in feasible)


def _objective_value(candidate: Candidate, metric: str) -> float:
    value = candidate.objective_values[metric]
    if value is None:  # guarded by rank_feasible's filter
        raise ValueError(
            f"candidate {candidate.candidate_id} has no value for {metric}"
        )
    return float(value)


def binding_constraints(candidates: Sequence[Candidate]) -> tuple[str, ...]:
    """Name constraints no evaluated candidate ever satisfied."""
    metrics = sorted(
        {
            result.metric
            for candidate in candidates
            for result in candidate.constraint_results
        }
    )
    return tuple(
        metric
        for metric in metrics
        if not any(
            result.metric == metric and result.satisfied is True
            for candidate in candidates
            for result in candidate.constraint_results
        )
    )


def _evaluate_values(
    values: Sequence[dict[str, LeverValue]],
    spec: OptimizerSpec,
    baseline: SimulationConfig,
    database_dir: Path,
    budget_limit: int,
    worker_budget: WorkerBudget,
    pool_factory: Callable[[int], ScenarioRunPool],
    on_event: Callable[[PoolEvent], None] | None,
    *,
    start_index: int = 0,
) -> tuple[Candidate, ...]:
    jobs, metadata = _build_jobs(
        values, baseline, database_dir, budget_limit, start_index=start_index
    )
    results = (
        pool_factory(worker_budget.workers).run(
            run_seed_worker, jobs, on_event=on_event
        )
        if jobs
        else {}
    )
    return _collect_candidates(metadata, results, spec)


def _refinement_anchor(
    candidates: Sequence[Candidate], spec: ObjectiveConstraintSpec
) -> Candidate:
    ranked = rank_feasible(candidates, spec)
    if ranked:
        return next(item for item in candidates if item.candidate_id == ranked[0])
    frontier = pareto_frontier(candidates, spec.objectives)
    if frontier:
        return next(item for item in candidates if item.candidate_id == frontier[0])
    return min(candidates, key=_constraint_penalty)


def _constraint_penalty(candidate: Candidate) -> tuple[int, int, int, str]:
    status_penalty = 1 if candidate.status == "failed" else 0
    missing = sum(result.satisfied is None for result in candidate.constraint_results)
    failed = sum(result.satisfied is False for result in candidate.constraint_results)
    return status_penalty, missing, failed, candidate.candidate_id


def _build_jobs(
    values: Sequence[dict[str, LeverValue]],
    baseline: SimulationConfig,
    database_dir: Path,
    max_runs: int,
    *,
    start_index: int = 0,
) -> tuple[
    list[ScenarioJob],
    list[tuple[str, dict[str, LeverValue], Path, str | None, bool]],
]:
    """Resolve each candidate's config, isolating resolution failures.

    A candidate whose declared-lever overlay cannot resolve against the
    baseline (an out-of-range value, an incompatible config shape) is
    recorded as a failed candidate rather than raising — one bad candidate
    must never discard every other candidate's already-completed work
    (FR-016's "failed" status exists for exactly this).
    """
    jobs: list[ScenarioJob] = []
    metadata: list[tuple[str, dict[str, LeverValue], Path, str | None, bool]] = []
    seen: dict[object, str] = {}
    evaluated = 0
    for offset, lever_values in enumerate(values):
        identity = candidate_identity(lever_values)
        candidate_id = f"candidate-{start_index + offset:04d}"
        duplicate_of = seen.get(identity)
        db_path = database_dir / "candidates" / candidate_id / "scenario.duckdb"
        if duplicate_of is not None:
            metadata.append((candidate_id, lever_values, db_path, duplicate_of, False))
            continue
        if evaluated >= max_runs:
            break
        seen[identity] = candidate_id
        evaluated += 1
        try:
            config, _ = resolve_candidate_config(baseline, lever_values)
        except (ValueError, ValidationError):
            metadata.append((candidate_id, lever_values, db_path, None, True))
            continue
        jobs.append(_scenario_job(candidate_id, config, db_path))
        metadata.append((candidate_id, lever_values, db_path, None, False))
    return jobs, metadata


def _scenario_job(
    candidate_id: str, config: SimulationConfig, db_path: Path
) -> ScenarioJob:
    seed = int(config.simulation.random_seed)
    return ScenarioJob(
        name=candidate_id,
        config=config,
        db_path=db_path,
        seed=seed,
        threads=1,
        dbt_artifacts_dir=db_path.parent / "dbt_artifacts",
        payload={
            "start_year": int(config.simulation.start_year),
            "end_year": int(config.simulation.end_year),
        },
    )


def _collect_candidates(
    metadata: Sequence[tuple[str, dict[str, LeverValue], Path, str | None, bool]],
    results: dict[str, JobResult],
    spec: OptimizerSpec,
) -> tuple[Candidate, ...]:
    collected: list[Candidate] = []
    by_id: dict[str, Candidate] = {}
    for candidate_id, values, db_path, duplicate_of, resolution_failed in metadata:
        if duplicate_of is not None:
            original = by_id[duplicate_of]
            candidate = original.model_copy(
                update={
                    "candidate_id": candidate_id,
                    "lever_values": values,
                    "is_duplicate_of": duplicate_of,
                    "duration_seconds": 0.0,
                }
            )
        elif resolution_failed:
            candidate = classify_candidate(
                candidate_id, values, None, spec.objective, {}, failed=True
            )
        else:
            result = results[candidate_id]
            candidate = candidate_from_job_result(
                candidate_id,
                values,
                db_path,
                spec.objective,
                result,
                ensemble_database=spec.baseline.ensemble_database,
            )
        collected.append(candidate)
        by_id[candidate_id] = candidate
    return tuple(collected)


def _build_run(
    spec: OptimizerSpec,
    baseline: SimulationConfig,
    max_runs: int,
    search_seed: int,
    candidates: tuple[Candidate, ...],
) -> OptimizerRun:
    ranked = rank_feasible(candidates, spec.objective)
    frontier = (
        pareto_frontier(candidates, spec.objective.objectives)
        if len(spec.objective.objectives) == 2
        else None
    )
    binding = binding_constraints(candidates) if not ranked and not frontier else None
    return OptimizerRun(
        run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"),
        design_space=spec.design_space,
        objective_constraint_spec=spec.objective,
        max_runs=max_runs,
        search_seed=search_seed,
        baseline_config_fingerprint=fingerprint_baseline(baseline),
        candidates=candidates,
        ranked_feasible=ranked,
        pareto_frontier=frontier,
        binding_infeasible_constraints=binding,
    )
