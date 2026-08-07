"""Optimizer isolated end-to-end tests."""

from pathlib import Path

import duckdb
import pytest

from planalign_optimizer.models import (
    BaselineSpec,
    ConstraintSpec,
    DesignSpaceSpec,
    LeverSpec,
    ObjectiveConstraintSpec,
    ObjectiveTerm,
    OptimizerSpec,
)
from planalign_optimizer.search import run_optimizer
from planalign_orchestrator.config import load_simulation_config, to_dbt_vars
from planalign_orchestrator.run_pool import JobResult

pytestmark = pytest.mark.integration


class _SnapshotPool:
    def __init__(self, workers: int) -> None:
        self.workers = workers

    def run(self, worker, jobs, *, on_event=None):
        results = {}
        for job in jobs:
            job.db_path.parent.mkdir(parents=True, exist_ok=True)
            rate = to_dbt_vars(job.config)["auto_enrollment_default_deferral_rate"]
            with duckdb.connect(str(job.db_path)) as connection:
                connection.execute(
                    "CREATE TABLE fct_workforce_snapshot AS SELECT 2025 AS simulation_year, "
                    "'active' AS employment_status, 100.0 AS prorated_annual_compensation, "
                    "5.0 AS employer_match_amount, ?::DOUBLE AS total_employer_contributions, "
                    "'participating' AS participation_status, ?::DOUBLE AS current_deferral_rate",
                    [rate * 100.0, rate],
                )
            results[job.name] = JobResult(name=job.name, status="completed")
        return results


def test_two_lever_run_is_isolated_and_constraints_recheck(
    tmp_path: Path, monkeypatch
) -> None:
    isolated = tmp_path / "optimizer" / "isolated.duckdb"
    monkeypatch.setenv("DATABASE_PATH", str(isolated))
    spec = OptimizerSpec(
        design_space=DesignSpaceSpec(
            levers=(
                LeverSpec(
                    name="auto_enrollment.default_deferral_rate",
                    kind="continuous",
                    bounds=(0.03, 0.08),
                ),
                LeverSpec(
                    name="auto_enrollment.scope",
                    kind="discrete",
                    choices=("new_hires_only", "all_eligible_employees"),
                ),
            )
        ),
        objective=ObjectiveConstraintSpec(
            objectives=(
                ObjectiveTerm(metric="total_employer_plan_cost", direction="minimize"),
            ),
            constraints=(
                ConstraintSpec(
                    metric="participation_rate", operator=">=", threshold=1.0
                ),
            ),
        ),
        baseline=BaselineSpec(config_path=Path("config/simulation_config.yaml")),
    )
    baseline = load_simulation_config(spec.baseline.config_path, env_overrides=False)
    run, _ = run_optimizer(
        spec,
        baseline,
        max_runs=4,
        search_seed=42,
        database_dir=isolated.parent,
        pool_factory=_SnapshotPool,
    )
    assert run.ranked_feasible
    for candidate in run.candidates:
        assert candidate.db_path is not None and candidate.db_path.exists()
        assert candidate.db_path != Path("dbt/simulation.duckdb")
        with duckdb.connect(str(candidate.db_path), read_only=True) as connection:
            participants = connection.execute(
                "SELECT AVG(CASE WHEN participation_status = 'participating' THEN 1.0 ELSE 0.0 END) FROM fct_workforce_snapshot"
            ).fetchone()[0]
        assert participants >= 1.0
