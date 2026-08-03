"""Scenario-pool execution for isolated seed ensemble members."""

from __future__ import annotations

import logging
from hashlib import sha256
from collections.abc import Callable
from pathlib import Path
from typing import Any

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import (
    ConstructionSpec,
    InitializationPolicy,
    build_orchestrator,
)
from planalign_orchestrator.run_metadata import compute_config_fingerprint
from planalign_orchestrator.run_pool import (
    JobResult,
    PoolEvent,
    ScenarioJob,
    ScenarioRunPool,
    resolve_worker_count,
)

from .aggregate import aggregate_ensemble, write_ensemble_results
from .extract import extract_completed_outcomes
from .models import AttributionShare, EnsembleResult, SeedPlan, SeedRunOutcome
from .provenance import write_ensemble_provenance
from .risk import evaluate_thresholds


logger = logging.getLogger(__name__)


def run_ensemble(
    plan: SeedPlan,
    *,
    parallel: int | None = None,
    config: Any | None = None,
    on_event: Callable[[PoolEvent], None] | None = None,
) -> EnsembleResult:
    """Run all planned seed worlds, then aggregate only immutable successes.

    Every job is fully resolved before entering ``ScenarioRunPool``. A
    KeyboardInterrupt propagates from the pool before aggregation, so an
    interrupted ensemble cannot leave a complete-looking aggregate behind.
    """
    resolved_config = _resolve_config(plan, config)
    effective_plan = _with_config_fingerprint(plan, resolved_config)
    outcomes = execute_seed_runs(
        effective_plan,
        resolved_config,
        parallel=parallel,
        on_event=on_event,
    )
    successful = [outcome for outcome in outcomes if outcome.succeeded]
    if not successful:
        return EnsembleResult(plan=effective_plan, outcomes=tuple(outcomes))

    seed_values = extract_completed_outcomes(
        successful,
        ensemble_id=effective_plan.ensemble_id,
        scenario_id=effective_plan.scenario_id,
    )
    distributions = aggregate_ensemble(
        seed_values,
        min_seeds=effective_plan.spec.min_seeds,
        n_seeds_requested=len(effective_plan.seeds),
    )
    risk_statements = evaluate_thresholds(
        distributions,
        seed_values,
        effective_plan.spec.thresholds,
    )
    write_ensemble_results(effective_plan.ensemble_db_path, distributions, seed_values)
    write_ensemble_provenance(effective_plan)
    attribution: tuple[AttributionShare, ...] = ()
    if effective_plan.spec.attribution:
        from .attribution import attribute_variance

        attribution = tuple(
            attribute_variance(
                effective_plan,
                outcomes,
                config=resolved_config,
                parallel=parallel,
            )
        )
    if effective_plan.spec.discard_seed_dbs:
        _discard_seed_databases(effective_plan)
    return EnsembleResult(
        plan=effective_plan,
        outcomes=tuple(outcomes),
        distributions=tuple(distributions),
        risk_statements=tuple(risk_statements),
        attribution=attribution,
    )


def execute_seed_runs(
    plan: SeedPlan,
    config: Any,
    *,
    parallel: int | None = None,
    on_event: Callable[[PoolEvent], None] | None = None,
    job_prefix: str = "seed",
) -> tuple[SeedRunOutcome, ...]:
    """Submit one resolved, isolated job per seed and retain all outcomes."""
    jobs = _build_seed_jobs(plan, config, job_prefix=job_prefix)
    budget = resolve_worker_count(parallel, len(jobs))
    results = ScenarioRunPool(budget.workers).run(
        run_seed_worker, jobs, on_event=on_event
    )
    return tuple(_to_outcomes(plan, results, job_prefix=job_prefix))


def run_seed_worker(job: ScenarioJob) -> dict[str, Any]:
    """Execute one fully-resolved seed job in a process-pool worker.

    This must remain module-level: ``ScenarioRunPool`` sends it across a
    process boundary when parallel execution is enabled.
    """
    if job.config is None:
        raise ValueError("seed worker received no resolved simulation configuration")
    database_path = job.db_path.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_dir = (
        job.dbt_artifacts_dir or database_path.parent / f"{job.name}_artifacts"
    ).resolve()
    reports_dir = (database_path.parent / "reports" / job.name).resolve()
    project_dir = job.payload.get("dbt_project_dir")
    resolved_project_dir = Path(project_dir).resolve() if project_dir else None
    built = build_orchestrator(
        ConstructionSpec(
            config=job.config,
            database=database_path,
            threads=job.threads,
            dbt_project_dir=resolved_project_dir,
            dbt_artifacts_dir=artifacts_dir,
            reports_dir=reports_dir,
            initialization=InitializationPolicy.SELF_HEALING,
            initialization_lock_name=_seed_initialization_lock_name(database_path),
            entry_point="cli.simulate",
            validation_mode=True,
            verbose=False,
        )
    )
    built.orchestrator.execute_multi_year_simulation(
        start_year=int(job.payload["start_year"]),
        end_year=int(job.payload["end_year"]),
        fail_on_validation_error=True,
    )
    return {"config_fingerprint": compute_config_fingerprint(job.config)}


def _seed_initialization_lock_name(database_path: Path) -> str:
    """Derive a lock namespace that cannot collide with another seed database."""
    digest = sha256(str(database_path).encode("utf-8")).hexdigest()[:16]
    return f"planalign_init_{digest}"


def _resolve_config(plan: SeedPlan, config: Any | None) -> Any:
    """Load the base config once, before any job can be scheduled."""
    if config is not None:
        return config
    if plan.spec.config_path is None:
        raise ValueError("an ensemble run requires config or spec.config_path")
    return load_simulation_config(plan.spec.config_path, env_overrides=False)


def _with_config_fingerprint(plan: SeedPlan, config: Any) -> SeedPlan:
    """Stamp the seed-independent config identity into the immutable plan."""
    if not hasattr(config, "simulation"):
        return plan
    return plan.model_copy(
        update={"config_fingerprint": compute_config_fingerprint(config)}
    )


def _build_seed_jobs(
    plan: SeedPlan, config: Any, *, job_prefix: str = "seed"
) -> list[ScenarioJob]:
    """Build all seed-specific job payloads before invoking the run pool."""
    return [
        ScenarioJob(
            name=f"{job_prefix}_{seed}",
            config=_with_seed(config, seed, plan),
            db_path=plan.seed_db_paths[seed],
            seed=seed,
            threads=1,
            dbt_artifacts_dir=(
                plan.ensemble_db_path.parent / f"{job_prefix}_{seed}_artifacts"
            ),
            payload={
                "start_year": plan.spec.start_year,
                "end_year": plan.spec.end_year,
                "dbt_project_dir": plan.spec.dbt_project_dir,
            },
        )
        for seed in plan.seeds
    ]


def _with_seed(config: Any, seed: int, plan: SeedPlan) -> Any:
    """Copy a Pydantic config with the planned horizon and one random seed."""
    if not hasattr(config, "simulation") or not hasattr(config, "model_copy"):
        return config
    simulation = config.simulation.model_copy(
        update={
            "random_seed": seed,
            "start_year": plan.spec.start_year,
            "end_year": plan.spec.end_year,
        }
    )
    return config.model_copy(update={"simulation": simulation})


def _to_outcomes(
    plan: SeedPlan, results: dict[str, JobResult], *, job_prefix: str = "seed"
) -> list[SeedRunOutcome]:
    """Retain every failure and report terminal outcomes in plan seed order."""
    outcomes: list[SeedRunOutcome] = []
    for seed in plan.seeds:
        result = results[f"{job_prefix}_{seed}"]
        fingerprint = ""
        if result.value is not None:
            fingerprint = str(result.value.get("config_fingerprint", ""))
        outcomes.append(
            SeedRunOutcome(
                seed=seed,
                db_path=plan.seed_db_paths[seed],
                status="completed" if result.succeeded else "failed",
                error=result.error,
                duration_seconds=result.duration_seconds,
                config_fingerprint=fingerprint,
            )
        )
    return outcomes


def _discard_seed_databases(plan: SeedPlan) -> None:
    """Delete this ensemble's seed worlds while retaining its aggregate database."""
    ensemble_dir = plan.ensemble_db_path.parent
    seed_paths = set(plan.seed_db_paths.values())
    attribution_dir = ensemble_dir / "attribution"
    if attribution_dir.exists():
        seed_paths.update(attribution_dir.rglob("seed_*.duckdb"))
    for seed_path in seed_paths:
        for candidate in (seed_path, seed_path.with_name(f"{seed_path.name}.wal")):
            candidate.unlink(missing_ok=True)
    logger.warning(
        "Discarded per-seed databases after aggregation; later attribution cannot "
        "reuse these headline baselines."
    )


__all__ = ["execute_seed_runs", "run_ensemble", "run_seed_worker"]
