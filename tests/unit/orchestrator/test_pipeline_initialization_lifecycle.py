"""Pipeline-owned fresh-database initialization under ``InitializationPolicy.NONE``.

With no pre-flight initializer (#967), the pipeline alone loads seeds, builds
start-year staging, runs FOUNDATION, and seeds the enrollment registry. These
tests pin that order and its failure/retry/resume behavior without dbt.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import planalign_orchestrator.pipeline_orchestrator as pipeline_module
from planalign_orchestrator.pipeline.workflow import StageDefinition, WorkflowStage
from planalign_orchestrator.pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineStageError,
)

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]

START_YEAR = 2025


def _result(success: bool) -> SimpleNamespace:
    return SimpleNamespace(success=success, return_code=0 if success else 2)


def _registry_orchestrator() -> tuple[PipelineOrchestrator, MagicMock]:
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    calls = MagicMock()
    orchestrator.registry_manager = MagicMock()
    orchestrator.registry_manager.get_enrollment_registry.return_value = (
        calls.enrollment
    )
    orchestrator.registry_manager.get_deferral_registry.return_value = calls.deferral
    orchestrator.config = MagicMock()
    orchestrator.config.simulation.start_year = START_YEAR
    return orchestrator, calls


def _seeding_orchestrator(monkeypatch, *results: bool) -> PipelineOrchestrator:
    monkeypatch.setattr(pipeline_module, "DataCleanupManager", MagicMock())
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._seeded = False
    orchestrator.db_manager = MagicMock()
    orchestrator.verbose = False
    orchestrator.dbt_runner = MagicMock()
    orchestrator.dbt_runner.execute_command.side_effect = [_result(r) for r in results]
    return orchestrator


def test_fresh_run_creates_then_resets_registries() -> None:
    orchestrator, calls = _registry_orchestrator()

    orchestrator._initialize_registries(START_YEAR)

    assert calls.mock_calls == [
        ("enrollment.create_table", (), {}),
        ("deferral.create_table", (), {}),
        ("enrollment.reset", (), {}),
        ("deferral.reset", (), {}),
    ]


def test_resumed_run_preserves_prior_year_registries() -> None:
    orchestrator, calls = _registry_orchestrator()

    orchestrator._initialize_registries(START_YEAR + 1)

    calls.enrollment.reset.assert_not_called()
    calls.deferral.reset.assert_not_called()
    calls.enrollment.create_table.assert_called_once_with()


def test_failed_seed_load_aborts_and_is_retried(monkeypatch) -> None:
    orchestrator = _seeding_orchestrator(monkeypatch, False, True)

    with pytest.raises(PipelineStageError, match="Dbt seed failed"):
        orchestrator._ensure_seeds_loaded()
    assert orchestrator._seeded is False

    orchestrator._ensure_seeds_loaded()
    orchestrator._ensure_seeds_loaded()

    assert orchestrator._seeded is True
    assert orchestrator.dbt_runner.execute_command.call_count == 2


def test_failed_start_year_staging_aborts() -> None:
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._dbt_vars = {}
    orchestrator.dbt_runner = MagicMock()
    orchestrator.dbt_runner.execute_command.return_value = _result(False)

    with pytest.raises(PipelineStageError, match="Staging models failed"):
        orchestrator._run_start_year_setup(START_YEAR)


def _year_orchestrator(monkeypatch, foundation_error: Exception | None):
    """Wire just enough of a start-year workflow to record setup order."""
    monkeypatch.setattr(pipeline_module, "DataCleanupManager", MagicMock())
    order: list[str] = []
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._seeded = False
    orchestrator._dbt_vars = {}
    orchestrator.db_manager = MagicMock()
    orchestrator.verbose = False
    orchestrator.hazard_cache_manager = None
    orchestrator.duckdb_performance_monitor = None
    orchestrator.config = MagicMock()
    orchestrator.config.simulation.start_year = START_YEAR
    orchestrator.state_manager = MagicMock()
    orchestrator.workforce_projection = MagicMock()
    orchestrator.hook_manager = MagicMock()
    orchestrator.stage_validator = MagicMock()
    orchestrator.workflow_builder = MagicMock()
    orchestrator.workflow_builder.build_year_workflow.return_value = [
        StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[],
            models=["int_baseline_workforce"],
            validation_rules=[],
        )
    ]

    def execute_command(args, **_kwargs):
        order.append("seed" if args == ["seed"] else "staging")
        return _result(True)

    def execute_stage(stage, year):
        order.append(stage.name.value)
        if foundation_error is not None:
            raise foundation_error

    def seed_registry(year):
        order.append("registry")

    orchestrator.dbt_runner = MagicMock()
    orchestrator.dbt_runner.execute_command.side_effect = execute_command
    orchestrator._execute_stage_with_monitoring = execute_stage
    orchestrator._seed_start_year_enrollment_registry = seed_registry
    return orchestrator, order


def test_start_year_builds_seeds_staging_foundation_then_registry(monkeypatch) -> None:
    orchestrator, order = _year_orchestrator(monkeypatch, foundation_error=None)

    orchestrator._execute_year_workflow(START_YEAR, fail_on_validation_error=True)

    assert order == ["seed", "staging", WorkflowStage.FOUNDATION.value, "registry"]


def test_foundation_failure_propagates_before_registry_seeding(monkeypatch) -> None:
    orchestrator, order = _year_orchestrator(
        monkeypatch, foundation_error=PipelineStageError("foundation failed")
    )

    with pytest.raises(PipelineStageError, match="foundation failed"):
        orchestrator._execute_year_workflow(START_YEAR, fail_on_validation_error=True)

    assert order == ["seed", "staging", WorkflowStage.FOUNDATION.value]
