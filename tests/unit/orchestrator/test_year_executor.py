"""
Unit tests for YearExecutor.

Covers:
- __init__ and attribute wiring
- execute_workflow_stage success and failure paths
- _dispatch_stage_execution routing (EVENT_GENERATION, STATE_ACCUMULATION, other)
- _execute_parallel_stage with tag-based and sharded execution
- _execute_sharded_event_generation with multiple shards and union writer
- _run_stage_models with and without model parallelization
- _should_use_model_parallelization (DuckDB detection, sequential stages, validation)
- _run_stage_with_model_parallelization success and failure
- _run_stage_models_legacy routing for event vs other stages
- _run_sequential_event_models with full refresh, snapshot clearing
- _is_force_full_refresh
- _clear_snapshot_rows_if_needed
- _append_full_refresh_if_needed / _get_full_refresh_reason
- _run_parallel_or_single (parallel safe vs single selection)
- _should_full_refresh_foundation
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, call

import pytest

from planalign_orchestrator.dbt_runner import DbtResult
from planalign_orchestrator.pipeline.workflow import StageDefinition, WorkflowStage
from planalign_orchestrator.pipeline.year_executor import (
    PipelineStageError,
    YearExecutor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_result(command=None) -> DbtResult:
    return DbtResult(
        success=True, stdout="ok", stderr="", execution_time=0.1,
        return_code=0, command=command or ["dbt", "run"],
    )


def _fail_result(return_code=1, command=None) -> DbtResult:
    return DbtResult(
        success=False, stdout="", stderr="error", execution_time=0.1,
        return_code=return_code, command=command or ["dbt", "run"],
    )


def _make_executor(
    *,
    dbt_vars: Optional[Dict[str, Any]] = None,
    dbt_threads: int = 1,
    start_year: int = 2025,
    event_shards: int = 1,
    verbose: bool = False,
    parallel_execution_engine: Optional[Any] = None,
    model_parallelization_enabled: bool = False,
    parallelization_config: Optional[Any] = None,
    progress_callback: Optional[Any] = None,
    db_path: Optional[str] = None,
    setup: Optional[Any] = None,
    simulation_start_year: int = 2025,
) -> YearExecutor:
    """Build a YearExecutor with mocked dependencies."""
    config = MagicMock()
    config.simulation.start_year = simulation_start_year
    if setup is not None:
        config.setup = setup
    else:
        config.setup = None

    runner = MagicMock()
    runner.execute_command.return_value = _ok_result()
    runner.run_models.return_value = [_ok_result()]

    db_manager = MagicMock()
    if db_path is not None:
        db_manager.db_path = db_path
    else:
        # Default: no db_path attribute
        del db_manager.db_path

    return YearExecutor(
        config=config,
        dbt_runner=runner,
        db_manager=db_manager,
        dbt_vars=dbt_vars or {"simulation_year": 2025},
        dbt_threads=dbt_threads,
        start_year=start_year,
        event_shards=event_shards,
        verbose=verbose,
        parallel_execution_engine=parallel_execution_engine,
        model_parallelization_enabled=model_parallelization_enabled,
        parallelization_config=parallelization_config,
        progress_callback=progress_callback,
    )


def _foundation_stage(models=None):
    return StageDefinition(
        name=WorkflowStage.FOUNDATION,
        dependencies=[],
        models=models or ["model_a", "model_b"],
        validation_rules=[],
        parallel_safe=False,
    )


def _event_stage(models=None):
    return StageDefinition(
        name=WorkflowStage.EVENT_GENERATION,
        dependencies=[],
        models=models or ["int_termination_events", "int_hiring_events"],
        validation_rules=[],
        parallel_safe=False,
    )


def _state_accum_stage(models=None):
    return StageDefinition(
        name=WorkflowStage.STATE_ACCUMULATION,
        dependencies=[],
        models=models or ["fct_yearly_events", "fct_workforce_snapshot"],
        validation_rules=[],
        parallel_safe=False,
    )


def _validation_stage(models=None, parallel_safe=True):
    return StageDefinition(
        name=WorkflowStage.VALIDATION,
        dependencies=[],
        models=models or ["dq_check"],
        validation_rules=[],
        parallel_safe=parallel_safe,
    )


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestYearExecutorInit:
    def test_attributes_wired(self):
        executor = _make_executor(
            dbt_vars={"simulation_year": 2026},
            dbt_threads=4,
            start_year=2025,
            event_shards=3,
            verbose=True,
        )
        assert executor._dbt_vars == {"simulation_year": 2026}
        assert executor.dbt_threads == 4
        assert executor.start_year == 2025
        assert executor.event_shards == 3
        assert executor.verbose is True

    def test_year_validator_created(self):
        executor = _make_executor()
        assert executor._year_validator is not None


# ---------------------------------------------------------------------------
# execute_workflow_stage
# ---------------------------------------------------------------------------

class TestExecuteWorkflowStage:
    def test_success_returns_result_dict(self):
        executor = _make_executor()
        result = executor.execute_workflow_stage(_foundation_stage(), 2025)

        assert result["success"] is True
        assert result["stage"] == "foundation"
        assert result["year"] == 2025
        assert "execution_time" in result
        assert "results" in result

    def test_failure_returns_error_dict(self):
        executor = _make_executor()
        executor.dbt_runner.execute_command.return_value = _fail_result()

        result = executor.execute_workflow_stage(_foundation_stage(["m1"]), 2025)

        assert result["success"] is False
        assert "error" in result
        assert result["stage"] == "foundation"

    def test_progress_callback_update_stage_called(self):
        callback = MagicMock()
        callback.update_stage = MagicMock()
        callback.stage_completed = MagicMock()
        executor = _make_executor(progress_callback=callback)

        executor.execute_workflow_stage(_foundation_stage(), 2025)

        callback.update_stage.assert_called_once_with("foundation")
        callback.stage_completed.assert_called_once()

    def test_progress_callback_not_called_when_none(self):
        executor = _make_executor(progress_callback=None)
        # Should not raise
        result = executor.execute_workflow_stage(_foundation_stage(), 2025)
        assert result["success"] is True

    def test_verbose_prints(self, capsys):
        executor = _make_executor(verbose=True)
        executor.execute_workflow_stage(_foundation_stage(), 2025)
        captured = capsys.readouterr()
        assert "foundation" in captured.out.lower() or "FOUNDATION" in captured.out

    def test_verbose_failure_prints(self, capsys):
        executor = _make_executor(verbose=True)
        executor.dbt_runner.execute_command.return_value = _fail_result()
        executor.execute_workflow_stage(_foundation_stage(["m1"]), 2025)
        captured = capsys.readouterr()
        assert "Failed" in captured.out or "failed" in captured.out.lower()


# ---------------------------------------------------------------------------
# _dispatch_stage_execution
# ---------------------------------------------------------------------------

class TestDispatchStageExecution:
    def test_event_generation_dispatches_to_parallel(self):
        executor = _make_executor()
        stage = _event_stage()
        with patch.object(executor, "_execute_parallel_stage", return_value=[_ok_result()]) as mock:
            executor._dispatch_stage_execution(stage, 2025)
            mock.assert_called_once_with(stage, 2025)

    def test_state_accumulation_validates_then_runs(self):
        executor = _make_executor()
        stage = _state_accum_stage()
        with patch.object(executor._year_validator, "validate_year_dependencies") as mock_val, \
             patch.object(executor, "_run_stage_models") as mock_run:
            executor._dispatch_stage_execution(stage, 2026)
            mock_val.assert_called_once_with(2026)
            mock_run.assert_called_once_with(stage, 2026)

    def test_other_stages_run_directly(self):
        executor = _make_executor()
        stage = _foundation_stage()
        with patch.object(executor, "_run_stage_models") as mock_run:
            result = executor._dispatch_stage_execution(stage, 2025)
            mock_run.assert_called_once_with(stage, 2025)
            assert result == []


# ---------------------------------------------------------------------------
# _execute_parallel_stage
# ---------------------------------------------------------------------------

class TestExecuteParallelStage:
    def test_single_shard_uses_tag(self):
        executor = _make_executor(event_shards=1)
        stage = _event_stage()
        results = executor._execute_parallel_stage(stage, 2025)

        assert len(results) == 1
        cmd_call = executor.dbt_runner.execute_command.call_args
        assert "tag:EVENT_GENERATION" in cmd_call[0][0]

    def test_multi_shard_delegates(self):
        executor = _make_executor(event_shards=3)
        stage = _event_stage()
        with patch.object(executor, "_execute_sharded_event_generation", return_value=[_ok_result()]) as mock:
            executor._execute_parallel_stage(stage, 2025)
            mock.assert_called_once_with(2025)

    def test_tag_failure_raises(self):
        executor = _make_executor(event_shards=1)
        executor.dbt_runner.execute_command.return_value = _fail_result(return_code=2)
        stage = _event_stage()

        with pytest.raises(PipelineStageError, match="Parallel stage"):
            executor._execute_parallel_stage(stage, 2025)

    def test_non_event_stage_uses_tag(self):
        """Non-EVENT_GENERATION stages still use tag-based selection."""
        executor = _make_executor(event_shards=1)
        stage = _validation_stage()
        results = executor._execute_parallel_stage(stage, 2025)
        cmd_call = executor.dbt_runner.execute_command.call_args
        assert "tag:VALIDATION" in cmd_call[0][0]

    def test_verbose_prints_tag_info(self, capsys):
        executor = _make_executor(event_shards=1, verbose=True)
        executor._execute_parallel_stage(_event_stage(), 2025)
        captured = capsys.readouterr()
        assert "EVENT_GENERATION" in captured.out


# ---------------------------------------------------------------------------
# _execute_sharded_event_generation
# ---------------------------------------------------------------------------

class TestExecuteShardedEventGeneration:
    def test_runs_all_shards_plus_union(self):
        executor = _make_executor(event_shards=2)
        results = executor._execute_sharded_event_generation(2025)

        # 2 shards + 1 union
        assert executor.dbt_runner.execute_command.call_count == 3
        assert len(results) == 3

    def test_shard_vars_include_shard_id(self):
        executor = _make_executor(event_shards=2, dbt_vars={"simulation_year": 2025})
        executor._execute_sharded_event_generation(2025)

        calls = executor.dbt_runner.execute_command.call_args_list
        # First shard
        shard_vars_0 = calls[0][1]["dbt_vars"]
        assert shard_vars_0["shard_id"] == 0
        assert shard_vars_0["total_shards"] == 2
        # Second shard
        shard_vars_1 = calls[1][1]["dbt_vars"]
        assert shard_vars_1["shard_id"] == 1

    def test_shard_failure_raises(self):
        executor = _make_executor(event_shards=2)
        executor.dbt_runner.execute_command.side_effect = [
            _ok_result(),
            _fail_result(return_code=1),  # second shard fails
        ]
        with pytest.raises(PipelineStageError, match="Event shard 1 failed"):
            executor._execute_sharded_event_generation(2025)

    def test_union_failure_raises(self):
        executor = _make_executor(event_shards=1)
        executor.dbt_runner.execute_command.side_effect = [
            _ok_result(),   # shard 0
            _fail_result(), # union fails
        ]
        with pytest.raises(PipelineStageError, match="Event union writer failed"):
            executor._execute_sharded_event_generation(2025)

    def test_verbose_prints_shard_info(self, capsys):
        executor = _make_executor(event_shards=2, verbose=True)
        executor._execute_sharded_event_generation(2025)
        captured = capsys.readouterr()
        assert "2 shards" in captured.out


# ---------------------------------------------------------------------------
# _run_stage_models
# ---------------------------------------------------------------------------

class TestRunStageModels:
    def test_empty_models_returns_early(self):
        executor = _make_executor()
        stage = StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[],
            models=[],
            validation_rules=[],
            parallel_safe=False,
        )
        # With no models, dbt_runner should not be invoked at all
        executor._run_stage_models(stage, 2025)
        executor.dbt_runner.execute_command.assert_not_called()
        executor.dbt_runner.run_models.assert_not_called()

    def test_falls_back_to_legacy_when_parallelization_disabled(self):
        executor = _make_executor(model_parallelization_enabled=False)
        stage = _foundation_stage()
        with patch.object(executor, "_run_stage_models_legacy") as mock:
            executor._run_stage_models(stage, 2025)
            mock.assert_called_once()

    def test_uses_parallelization_when_enabled_and_appropriate(self):
        engine = MagicMock()
        p_config = MagicMock()
        executor = _make_executor(
            model_parallelization_enabled=True,
            parallel_execution_engine=engine,
            parallelization_config=p_config,
        )
        stage = _foundation_stage(models=["a", "b"])

        with patch.object(executor, "_should_use_model_parallelization", return_value=True), \
             patch.object(executor, "_run_stage_with_model_parallelization") as mock_par:
            executor._run_stage_models(stage, 2025)
            mock_par.assert_called_once_with(stage, 2025)

    def test_falls_back_when_should_use_returns_false(self):
        engine = MagicMock()
        executor = _make_executor(
            model_parallelization_enabled=True,
            parallel_execution_engine=engine,
        )
        stage = _foundation_stage()
        with patch.object(executor, "_should_use_model_parallelization", return_value=False), \
             patch.object(executor, "_run_stage_models_legacy") as mock_leg:
            executor._run_stage_models(stage, 2025)
            mock_leg.assert_called_once()


# ---------------------------------------------------------------------------
# _should_use_model_parallelization
# ---------------------------------------------------------------------------

class TestShouldUseModelParallelization:
    def test_duckdb_path_returns_false(self):
        executor = _make_executor(db_path="/data/sim.duckdb")
        stage = _foundation_stage(models=["a", "b"])
        assert executor._should_use_model_parallelization(stage) is False

    def test_non_duckdb_path_with_multiple_models(self):
        executor = _make_executor(db_path="/data/sim.sqlite")
        stage = _foundation_stage(models=["a", "b"])
        assert executor._should_use_model_parallelization(stage) is True

    def test_no_db_path_attr_with_multiple_models(self):
        executor = _make_executor()  # db_path deleted in _make_executor
        stage = _foundation_stage(models=["a", "b"])
        # Falls through to model count check
        assert executor._should_use_model_parallelization(stage) is True

    def test_single_model_returns_false(self):
        executor = _make_executor()
        stage = _foundation_stage(models=["single"])
        assert executor._should_use_model_parallelization(stage) is False

    def test_event_generation_without_config_returns_false(self):
        executor = _make_executor()
        stage = _event_stage()
        assert executor._should_use_model_parallelization(stage) is False

    def test_state_accumulation_without_config_returns_false(self):
        executor = _make_executor()
        stage = _state_accum_stage()
        assert executor._should_use_model_parallelization(stage) is False

    def test_sequential_stage_with_safety_validation_passing(self):
        engine = MagicMock()
        engine.validate_stage_parallelization.return_value = {
            "parallelizable": True, "safety_score": 95
        }
        p_config = MagicMock()
        p_config.safety.validate_execution_safety = True

        executor = _make_executor(
            parallel_execution_engine=engine,
            parallelization_config=p_config,
        )
        stage = _event_stage(models=["a", "b"])
        assert executor._should_use_model_parallelization(stage) is True

    def test_sequential_stage_with_safety_validation_failing(self):
        engine = MagicMock()
        engine.validate_stage_parallelization.return_value = {
            "parallelizable": False, "safety_score": 30
        }
        p_config = MagicMock()
        p_config.safety.validate_execution_safety = True

        executor = _make_executor(
            parallel_execution_engine=engine,
            parallelization_config=p_config,
        )
        stage = _event_stage(models=["a", "b"])
        assert executor._should_use_model_parallelization(stage) is False

    def test_db_path_detection_exception_falls_through(self):
        """If db_path raises an exception, we fall through to other checks."""
        executor = _make_executor()
        # Make db_manager.db_path raise when accessed
        type(executor.db_manager).db_path = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        stage = _foundation_stage(models=["a", "b"])
        # Should not raise, falls through
        result = executor._should_use_model_parallelization(stage)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# _run_stage_with_model_parallelization
# ---------------------------------------------------------------------------

class TestRunStageWithModelParallelization:
    def _make_engine_result(self, success=True, errors=None):
        result = MagicMock()
        result.success = success
        result.model_results = [MagicMock()]
        result.execution_time = 1.5
        result.parallelism_achieved = 2.0
        result.errors = errors or []
        return result

    def test_success(self):
        engine = MagicMock()
        engine.execute_stage_with_parallelization.return_value = self._make_engine_result()
        p_config = MagicMock()
        p_config.enable_conditional_parallelization = True

        executor = _make_executor(
            parallel_execution_engine=engine,
            parallelization_config=p_config,
        )
        # Should not raise
        executor._run_stage_with_model_parallelization(_foundation_stage(), 2025)
        engine.execute_stage_with_parallelization.assert_called_once()

    def test_failure_with_errors_raises(self):
        engine = MagicMock()
        engine.execute_stage_with_parallelization.return_value = self._make_engine_result(
            success=False, errors=["model_a failed", "model_b failed", "model_c failed"]
        )
        p_config = MagicMock()
        p_config.enable_conditional_parallelization = True

        executor = _make_executor(
            parallel_execution_engine=engine,
            parallelization_config=p_config,
        )
        with pytest.raises(PipelineStageError, match="model_a failed"):
            executor._run_stage_with_model_parallelization(_foundation_stage(), 2025)

    def test_failure_without_errors_raises_generic(self):
        engine = MagicMock()
        engine.execute_stage_with_parallelization.return_value = self._make_engine_result(
            success=False, errors=[]
        )
        p_config = MagicMock()
        p_config.enable_conditional_parallelization = True

        executor = _make_executor(
            parallel_execution_engine=engine,
            parallelization_config=p_config,
        )
        with pytest.raises(PipelineStageError, match="Model-level parallelization failed"):
            executor._run_stage_with_model_parallelization(_foundation_stage(), 2025)

    def test_verbose_prints_details(self, capsys):
        engine = MagicMock()
        engine.execute_stage_with_parallelization.return_value = self._make_engine_result()
        p_config = MagicMock()
        p_config.enable_conditional_parallelization = True

        executor = _make_executor(
            verbose=True,
            parallel_execution_engine=engine,
            parallelization_config=p_config,
        )
        executor._run_stage_with_model_parallelization(_foundation_stage(), 2025)
        captured = capsys.readouterr()
        assert "parallelization" in captured.out.lower() or "Parallelization" in captured.out

    def test_verbose_failure_shows_errors(self, capsys):
        engine = MagicMock()
        engine.execute_stage_with_parallelization.return_value = self._make_engine_result(
            success=False, errors=["oops"]
        )
        p_config = MagicMock()
        p_config.enable_conditional_parallelization = True

        executor = _make_executor(
            verbose=True,
            parallel_execution_engine=engine,
            parallelization_config=p_config,
        )
        with pytest.raises(PipelineStageError):
            executor._run_stage_with_model_parallelization(_foundation_stage(), 2025)
        captured = capsys.readouterr()
        assert "Errors" in captured.out or "oops" in captured.out


# ---------------------------------------------------------------------------
# _run_stage_models_legacy
# ---------------------------------------------------------------------------

class TestRunStageModelsLegacy:
    def test_event_generation_runs_sequential(self):
        executor = _make_executor()
        stage = _event_stage()
        with patch.object(executor, "_run_sequential_event_models") as mock:
            executor._run_stage_models_legacy(stage, 2025)
            mock.assert_called_once_with(stage, 2025)

    def test_state_accumulation_runs_sequential(self):
        executor = _make_executor()
        stage = _state_accum_stage()
        with patch.object(executor, "_run_sequential_event_models") as mock:
            executor._run_stage_models_legacy(stage, 2025)
            mock.assert_called_once_with(stage, 2025)

    def test_other_stage_runs_parallel_or_single(self):
        executor = _make_executor()
        stage = _foundation_stage()
        with patch.object(executor, "_run_parallel_or_single") as mock:
            executor._run_stage_models_legacy(stage, 2025)
            mock.assert_called_once_with(stage, 2025)


# ---------------------------------------------------------------------------
# _run_sequential_event_models
# ---------------------------------------------------------------------------

class TestRunSequentialEventModels:
    def test_runs_each_model_sequentially(self):
        executor = _make_executor()
        stage = _event_stage(models=["m1", "m2", "m3"])

        executor._run_sequential_event_models(stage, 2025)

        assert executor.dbt_runner.execute_command.call_count == 3

    def test_model_failure_raises(self):
        executor = _make_executor()
        executor.dbt_runner.execute_command.side_effect = [
            _ok_result(),
            _fail_result(return_code=2),
        ]
        stage = _event_stage(models=["m1", "m2"])

        with pytest.raises(PipelineStageError, match="m2"):
            executor._run_sequential_event_models(stage, 2025)

    def test_clears_snapshot_for_fct_workforce_snapshot(self):
        executor = _make_executor()
        stage = _state_accum_stage(models=["fct_workforce_snapshot"])

        with patch.object(executor, "_clear_snapshot_rows_if_needed") as mock_clear:
            executor._run_sequential_event_models(stage, 2025)
            mock_clear.assert_called_once_with("fct_workforce_snapshot", 2025)

    def test_full_refresh_appended_when_forced(self):
        executor = _make_executor(setup={"clear_tables": True, "clear_mode": "all"})
        stage = _event_stage(models=["some_model"])

        executor._run_sequential_event_models(stage, 2025)

        cmd_args = executor.dbt_runner.execute_command.call_args[0][0]
        assert "--full-refresh" in cmd_args

    def test_full_refresh_for_specific_models(self):
        executor = _make_executor()
        stage = _event_stage(models=["int_workforce_snapshot_optimized"])

        executor._run_sequential_event_models(stage, 2025)

        cmd_args = executor.dbt_runner.execute_command.call_args[0][0]
        assert "--full-refresh" in cmd_args

    def test_no_full_refresh_for_normal_model(self):
        executor = _make_executor()
        stage = _event_stage(models=["int_termination_events"])

        executor._run_sequential_event_models(stage, 2025)

        cmd_args = executor.dbt_runner.execute_command.call_args[0][0]
        assert "--full-refresh" not in cmd_args


# ---------------------------------------------------------------------------
# _is_force_full_refresh
# ---------------------------------------------------------------------------

class TestIsForceFullRefresh:
    def test_true_when_clear_tables_and_clear_mode_all(self):
        executor = _make_executor(setup={"clear_tables": True, "clear_mode": "all"})
        assert executor._is_force_full_refresh() is True

    def test_false_when_no_setup(self):
        executor = _make_executor(setup=None)
        assert executor._is_force_full_refresh() is False

    def test_false_when_setup_not_dict(self):
        executor = _make_executor()
        executor.config.setup = "not_a_dict"
        assert executor._is_force_full_refresh() is False

    def test_false_when_clear_tables_false(self):
        executor = _make_executor(setup={"clear_tables": False, "clear_mode": "all"})
        assert executor._is_force_full_refresh() is False

    def test_false_when_clear_mode_not_all(self):
        executor = _make_executor(setup={"clear_tables": True, "clear_mode": "incremental"})
        assert executor._is_force_full_refresh() is False

    def test_true_with_uppercase_clear_mode(self):
        executor = _make_executor(setup={"clear_tables": True, "clear_mode": "ALL"})
        assert executor._is_force_full_refresh() is True


# ---------------------------------------------------------------------------
# _clear_snapshot_rows_if_needed
# ---------------------------------------------------------------------------

class TestClearSnapshotRowsIfNeeded:
    def test_skips_non_snapshot_model(self):
        executor = _make_executor()
        executor._clear_snapshot_rows_if_needed("int_termination_events", 2025)
        executor.db_manager.execute_with_retry.assert_not_called()

    def test_clears_snapshot_model(self):
        executor = _make_executor()
        executor._clear_snapshot_rows_if_needed("fct_workforce_snapshot", 2025)
        executor.db_manager.execute_with_retry.assert_called_once()

    def test_exception_is_non_fatal(self):
        executor = _make_executor()
        executor.db_manager.execute_with_retry.side_effect = RuntimeError("lock")
        # Should not raise
        executor._clear_snapshot_rows_if_needed("fct_workforce_snapshot", 2025)

    def test_verbose_prints_on_success(self, capsys):
        executor = _make_executor(verbose=True)
        executor._clear_snapshot_rows_if_needed("fct_workforce_snapshot", 2025)
        captured = capsys.readouterr()
        assert "fct_workforce_snapshot" in captured.out


# ---------------------------------------------------------------------------
# _append_full_refresh_if_needed / _get_full_refresh_reason
# ---------------------------------------------------------------------------

class TestAppendFullRefreshIfNeeded:
    def test_appends_for_snapshot_optimized(self):
        executor = _make_executor()
        selection = ["run", "--select", "int_workforce_snapshot_optimized"]
        executor._append_full_refresh_if_needed(
            selection, "int_workforce_snapshot_optimized", False, 2025
        )
        assert "--full-refresh" in selection

    def test_appends_for_deferral_escalation(self):
        executor = _make_executor()
        selection = ["run", "--select", "int_deferral_rate_escalation_events"]
        executor._append_full_refresh_if_needed(
            selection, "int_deferral_rate_escalation_events", False, 2025
        )
        assert "--full-refresh" in selection

    def test_appends_when_force_full_refresh(self):
        executor = _make_executor()
        selection = ["run", "--select", "any_model"]
        executor._append_full_refresh_if_needed(selection, "any_model", True, 2025)
        assert "--full-refresh" in selection

    def test_no_append_for_normal_model(self):
        executor = _make_executor()
        selection = ["run", "--select", "int_termination_events"]
        executor._append_full_refresh_if_needed(
            selection, "int_termination_events", False, 2025
        )
        assert "--full-refresh" not in selection

    def test_verbose_prints_reason(self, capsys):
        executor = _make_executor(verbose=True)
        selection = ["run", "--select", "int_workforce_snapshot_optimized"]
        executor._append_full_refresh_if_needed(
            selection, "int_workforce_snapshot_optimized", False, 2025
        )
        captured = capsys.readouterr()
        assert "schema compatibility" in captured.out


class TestGetFullRefreshReason:
    def test_known_model(self):
        executor = _make_executor()
        assert executor._get_full_refresh_reason("int_workforce_snapshot_optimized") == "schema compatibility"

    def test_known_deferral_model(self):
        executor = _make_executor()
        assert executor._get_full_refresh_reason("int_deferral_rate_escalation_events") == "self-reference incremental"

    def test_unknown_model(self):
        executor = _make_executor()
        assert executor._get_full_refresh_reason("random_model") == "clear_mode=all"


# ---------------------------------------------------------------------------
# _run_parallel_or_single
# ---------------------------------------------------------------------------

class TestRunParallelOrSingle:
    def test_parallel_safe_with_multiple_models(self):
        executor = _make_executor()
        stage = StageDefinition(
            name=WorkflowStage.VALIDATION,
            dependencies=[],
            models=["m1", "m2"],
            validation_rules=[],
            parallel_safe=True,
        )
        executor.dbt_runner.run_models.return_value = [_ok_result(), _ok_result()]

        executor._run_parallel_or_single(stage, 2025)

        executor.dbt_runner.run_models.assert_called_once()
        call_kwargs = executor.dbt_runner.run_models.call_args
        assert call_kwargs[1]["parallel"] is True

    def test_parallel_safe_failure_raises(self):
        executor = _make_executor()
        stage = StageDefinition(
            name=WorkflowStage.VALIDATION,
            dependencies=[],
            models=["m1", "m2"],
            validation_rules=[],
            parallel_safe=True,
        )
        executor.dbt_runner.run_models.return_value = [_ok_result(), _fail_result()]

        with pytest.raises(PipelineStageError, match="Some models failed"):
            executor._run_parallel_or_single(stage, 2025)

    def test_single_model_uses_execute_command(self):
        executor = _make_executor()
        stage = _foundation_stage(models=["single_model"])

        executor._run_parallel_or_single(stage, 2025)

        executor.dbt_runner.execute_command.assert_called_once()

    def test_non_parallel_safe_uses_execute_command(self):
        executor = _make_executor()
        stage = StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[],
            models=["m1", "m2"],
            validation_rules=[],
            parallel_safe=False,
        )

        executor._run_parallel_or_single(stage, 2025)

        executor.dbt_runner.execute_command.assert_called_once()
        cmd = executor.dbt_runner.execute_command.call_args[0][0]
        assert "m1 m2" in " ".join(cmd)

    def test_single_execution_failure_raises(self):
        executor = _make_executor()
        executor.dbt_runner.execute_command.return_value = _fail_result(return_code=2)
        stage = _foundation_stage(models=["single_model"])

        with pytest.raises(PipelineStageError, match="Dbt failed"):
            executor._run_parallel_or_single(stage, 2025)

    def test_foundation_full_refresh_appended(self):
        executor = _make_executor(simulation_start_year=2025)
        stage = StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[],
            models=["m1"],
            validation_rules=[],
            parallel_safe=False,
        )

        executor._run_parallel_or_single(stage, 2025)

        cmd = executor.dbt_runner.execute_command.call_args[0][0]
        assert "--full-refresh" in cmd


# ---------------------------------------------------------------------------
# _should_full_refresh_foundation
# ---------------------------------------------------------------------------

class TestShouldFullRefreshFoundation:
    def test_non_foundation_stage_returns_false(self):
        executor = _make_executor()
        stage = _event_stage()
        assert executor._should_full_refresh_foundation(stage, 2025) is False

    def test_first_year_returns_true(self):
        executor = _make_executor(simulation_start_year=2025)
        stage = StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[], models=["m1"], validation_rules=[],
        )
        assert executor._should_full_refresh_foundation(stage, 2025) is True

    def test_non_first_year_with_clear_mode_all_returns_true(self):
        executor = _make_executor(
            simulation_start_year=2025,
            setup={"clear_mode": "all"},
        )
        stage = StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[], models=["m1"], validation_rules=[],
        )
        assert executor._should_full_refresh_foundation(stage, 2026) is True

    def test_non_first_year_with_clear_mode_incremental_returns_false(self):
        executor = _make_executor(
            simulation_start_year=2025,
            setup={"clear_mode": "incremental"},
        )
        stage = StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[], models=["m1"], validation_rules=[],
        )
        assert executor._should_full_refresh_foundation(stage, 2026) is False

    def test_no_setup_defaults_to_all(self):
        executor = _make_executor(simulation_start_year=2025, setup=None)
        stage = StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[], models=["m1"], validation_rules=[],
        )
        # No setup -> clear_mode defaults to "all"
        assert executor._should_full_refresh_foundation(stage, 2026) is True

    def test_verbose_prints_reason(self, capsys):
        executor = _make_executor(simulation_start_year=2025, verbose=True)
        stage = StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[], models=["m1"], validation_rules=[],
        )
        executor._should_full_refresh_foundation(stage, 2025)
        captured = capsys.readouterr()
        assert "full-refresh" in captured.out.lower() or "FOUNDATION" in captured.out


# ---------------------------------------------------------------------------
# PipelineStageError
# ---------------------------------------------------------------------------

class TestPipelineStageError:
    def test_is_runtime_error(self):
        err = PipelineStageError("boom")
        assert isinstance(err, RuntimeError)
        assert str(err) == "boom"
