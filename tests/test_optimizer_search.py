"""Optimizer bounded-search tests."""

from pathlib import Path

import pytest

from planalign_optimizer.models import (
    BaselineSpec,
    Candidate,
    ConstraintResult,
    DesignSpaceSpec,
    LeverSpec,
    ObjectiveConstraintSpec,
    ObjectiveTerm,
    OptimizerSpec,
)
from planalign_optimizer.search import binding_constraints, rank_feasible, run_optimizer
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.run_pool import JobResult

pytestmark = pytest.mark.fast


def _candidate(identifier: str, value: float, status: str = "feasible") -> Candidate:
    return Candidate(
        candidate_id=identifier,
        lever_values={"x": value},
        db_path=Path(f"{identifier}.duckdb"),
        status=status,
        objective_values={"cost": value},
    )


def test_feasible_candidates_are_ranked_by_direction() -> None:
    spec = ObjectiveConstraintSpec(
        objectives=(ObjectiveTerm(metric="cost", direction="minimize"),)
    )
    assert rank_feasible(
        (_candidate("b", 2), _candidate("a", 1), _candidate("x", 0, "infeasible")), spec
    ) == ("a", "b")


def test_binding_constraints_name_never_satisfied_metric() -> None:
    candidates = (
        _candidate("a", 1, "infeasible").model_copy(
            update={
                "constraint_results": (
                    ConstraintResult(
                        metric="participation_rate",
                        evaluation_mode="point_estimate",
                        evaluated_value=0.5,
                        satisfied=False,
                    ),
                )
            }
        ),
        _candidate("b", 2, "infeasible").model_copy(
            update={
                "constraint_results": (
                    ConstraintResult(
                        metric="participation_rate",
                        evaluation_mode="point_estimate",
                        evaluated_value=0.6,
                        satisfied=False,
                    ),
                )
            }
        ),
    )
    assert binding_constraints(candidates) == ("participation_rate",)


class _FailedPool:
    submitted: list[object] = []

    def __init__(self, workers: int) -> None:
        self.workers = workers

    def run(self, worker, jobs, *, on_event=None):
        type(self).submitted = list(jobs)
        return {job.name: JobResult(name=job.name, status="failed") for job in jobs}


def _optimizer_spec() -> OptimizerSpec:
    return OptimizerSpec(
        design_space=DesignSpaceSpec(
            levers=(
                LeverSpec(
                    name="auto_enrollment.default_deferral_rate",
                    kind="continuous",
                    bounds=(0.03, 0.08),
                ),
            )
        ),
        objective=ObjectiveConstraintSpec(
            objectives=(
                ObjectiveTerm(metric="participation_rate", direction="maximize"),
            )
        ),
        baseline=BaselineSpec(config_path=Path("config/simulation_config.yaml")),
    )


def test_budget_and_search_seed_are_deterministic(tmp_path: Path) -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    first, _ = run_optimizer(
        _optimizer_spec(),
        baseline,
        max_runs=4,
        search_seed=77,
        database_dir=tmp_path / "first",
        pool_factory=_FailedPool,
    )
    second, _ = run_optimizer(
        _optimizer_spec(),
        baseline,
        max_runs=4,
        search_seed=77,
        database_dir=tmp_path / "second",
        pool_factory=_FailedPool,
    )
    assert len([item for item in first.candidates if item.is_duplicate_of is None]) <= 4
    assert [item.lever_values for item in first.candidates] == [
        item.lever_values for item in second.candidates
    ]
    assert all(item.status == "failed" for item in first.candidates)


def test_unresolvable_candidate_is_recorded_failed_not_fatal(
    monkeypatch, tmp_path: Path
) -> None:
    """One bad candidate must not discard every other candidate's results."""
    values = [
        {"auto_enrollment.default_deferral_rate": 0.03},
        {"auto_enrollment.default_deferral_rate": 0.9999},
    ]
    monkeypatch.setattr(
        "planalign_optimizer.search.sample_candidates", lambda *args, **kwargs: values
    )

    def _boom(baseline, lever_values):
        if lever_values["auto_enrollment.default_deferral_rate"] > 0.5:
            raise ValueError("simulated unresolvable overlay")
        return baseline, {}

    monkeypatch.setattr("planalign_optimizer.search.resolve_candidate_config", _boom)
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    run, _ = run_optimizer(
        _optimizer_spec(),
        baseline,
        max_runs=2,
        search_seed=1,
        database_dir=tmp_path,
        pool_factory=_FailedPool,
    )
    statuses = {
        candidate.candidate_id: candidate.status for candidate in run.candidates
    }
    assert statuses["candidate-0000"] == "failed"  # from the pool, per _FailedPool
    assert statuses["candidate-0001"] == "failed"  # from the resolution error
    assert len(run.candidates) == 2


def test_exact_duplicates_do_not_consume_budget(monkeypatch, tmp_path: Path) -> None:
    values = [
        {"auto_enrollment.default_deferral_rate": 0.03},
        {"auto_enrollment.default_deferral_rate": 0.03},
        {"auto_enrollment.default_deferral_rate": 0.030000000000000002},
    ]
    monkeypatch.setattr(
        "planalign_optimizer.search.sample_candidates", lambda *args, **kwargs: values
    )
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    run, _ = run_optimizer(
        _optimizer_spec(),
        baseline,
        max_runs=2,
        search_seed=1,
        database_dir=tmp_path,
        pool_factory=_FailedPool,
    )
    assert len(_FailedPool.submitted) == 2
    assert run.candidates[1].is_duplicate_of == "candidate-0000"
    assert run.candidates[2].is_duplicate_of is None
