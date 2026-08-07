"""Optimizer export tests."""

from pathlib import Path

import pandas as pd
import pytest

from planalign_optimizer.export import write_exports
from planalign_optimizer.models import (
    Candidate,
    DesignSpaceSpec,
    ObjectiveConstraintSpec,
    ObjectiveTerm,
    OptimizerRun,
)

pytestmark = pytest.mark.fast


def test_export_contains_every_status_and_conditional_pareto_sheet(
    tmp_path: Path,
) -> None:
    candidates = tuple(
        Candidate(candidate_id=f"candidate-{index:04d}", lever_values={}, status=status)
        for index, status in enumerate(
            ("feasible", "infeasible", "non_evaluable", "failed")
        )
    )
    run = OptimizerRun(
        run_id="run",
        design_space=DesignSpaceSpec(),
        objective_constraint_spec=ObjectiveConstraintSpec(
            objectives=(ObjectiveTerm(metric="active_headcount", direction="maximize"),)
        ),
        max_runs=4,
        search_seed=42,
        baseline_config_fingerprint="abc",
        candidates=candidates,
    )
    write_exports(run, tmp_path)
    assert len(pd.read_csv(tmp_path / "candidates.csv")) == 4
    assert pd.ExcelFile(tmp_path / "optimizer_results.xlsx").sheet_names == [
        "Candidates"
    ]

    two_objectives = run.model_copy(
        update={
            "objective_constraint_spec": ObjectiveConstraintSpec(
                objectives=(
                    ObjectiveTerm(metric="active_headcount", direction="maximize"),
                    ObjectiveTerm(metric="participation_rate", direction="maximize"),
                )
            ),
            "pareto_frontier": ("candidate-0000",),
        }
    )
    write_exports(two_objectives, tmp_path / "pareto")
    assert pd.ExcelFile(tmp_path / "pareto" / "optimizer_results.xlsx").sheet_names == [
        "Candidates",
        "Pareto Frontier",
    ]
