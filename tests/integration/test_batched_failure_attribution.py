"""Batched-failure attribution for dependency-closed stage selections.

Goal: prove that when a model fails *inside a batched dbt selection*, the surfaced
error still names the failing **model**, **stage**, and **year**.

Tier A's hazard-cache batch is already covered at the unit level in
``tests/unit/test_hazard_cache_batching.py::test_batched_failure_still_names_failing_model``
(a failed batched build routes through ``_build_rebuild_error`` +
``extract_dbt_failure_detail``, which reads per-node ``run_results.json`` and names
the failing model).

This module is the integration home for the same guarantee once Tiers B and C add
their own batched selections (T021, and the STATE_ACCUMULATION collapse). Each case
injects a deliberately broken model into an isolated DB build and asserts the
attribution. They are skipped until wired to an isolated-DB fixture so CI stays green.
"""

from unittest.mock import MagicMock

import duckdb
import pytest

from planalign_orchestrator.dbt_runner import DbtExecutionError
from planalign_orchestrator.pipeline.workflow import StageDefinition, WorkflowStage
from planalign_orchestrator.pipeline.year_executor import YearExecutor


@pytest.mark.skip(
    reason="Tier A attribution covered by unit test; B/C cases pending isolated-DB fixture."
)
def test_batched_hazard_failure_names_model():
    """Placeholder — Tier A covered in test_hazard_cache_batching.py (unit)."""


@pytest.mark.skip(
    reason="Tier B: merged INIT+FOUNDATION selection — implement with T019/T021."
)
def test_merged_foundation_failure_names_model_stage_year():
    """A failure in the merged INITIALIZATION+FOUNDATION selection names model+stage+year."""


def test_collapsed_state_failure_keeps_context_and_partial_outputs(tmp_path):
    """A failed state selection is attributable and leaves its run DB inspectable."""
    database = tmp_path / "failed-run" / "simulation.duckdb"
    database.parent.mkdir()
    with duckdb.connect(str(database)) as connection:
        connection.execute("CREATE TABLE partial_state (simulation_year INTEGER)")
        connection.execute("INSERT INTO partial_state VALUES (2026)")

    config = MagicMock()
    config.simulation.start_year = 2025
    runner = MagicMock()
    runner.execute_command.side_effect = DbtExecutionError(
        "model.fidelity_planalign_engine.int_employee_contributions: injected failure"
    )
    executor = YearExecutor(
        config=config,
        dbt_runner=runner,
        db_manager=MagicMock(db_path=database),
        dbt_vars={"simulation_year": 2026},
        dbt_threads=1,
        start_year=2025,
    )
    executor._year_validator = MagicMock()
    stage = StageDefinition(
        name=WorkflowStage.STATE_ACCUMULATION,
        dependencies=[WorkflowStage.EVENT_GENERATION],
        models=["int_workforce_state_accumulator", "int_employee_contributions"],
        validation_rules=[],
    )

    outcome = executor.execute_workflow_stage(stage, 2026)

    assert outcome["success"] is False
    assert outcome["stage"] == "state_accumulation"
    assert outcome["year"] == 2026
    assert len(outcome["correlation_id"]) == 8
    assert "int_employee_contributions" in outcome["error"]
    assert database.is_file()
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute("SELECT * FROM partial_state").fetchall() == [(2026,)]
