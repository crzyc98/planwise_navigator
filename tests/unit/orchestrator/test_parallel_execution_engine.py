"""Tests for planalign_orchestrator.parallel_execution_engine module.

Covers LegacyResourceMonitor resource pressure logic, effective-worker
determination (legacy + advanced resource-manager paths), single-model
execution with deterministic var injection and the double-execution guard,
and parallelization recommendation generation.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from planalign_orchestrator import parallel_execution_engine as pee
from planalign_orchestrator.parallel_execution_engine import (
    ExecutionContext,
    ExecutionResult,
    LegacyResourceMonitor,
    ParallelExecutionEngine,
)

pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _context(**overrides) -> ExecutionContext:
    base = dict(
        simulation_year=2025,
        dbt_vars={"random_seed": 42},
        stage_name="EVENT_GENERATION",
        execution_id="run-1",
    )
    base.update(overrides)
    return ExecutionContext(**base)


def _engine(**kwargs) -> ParallelExecutionEngine:
    # A logger must be supplied: the __init__ `logger` parameter shadows the
    # module-level logger, so __init__ calls logger.debug(...) on it.
    kwargs.setdefault("logger", MagicMock(name="logger"))
    return ParallelExecutionEngine(
        dbt_runner=MagicMock(name="dbt_runner"),
        dependency_analyzer=MagicMock(name="dependency_analyzer"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# LegacyResourceMonitor
# ---------------------------------------------------------------------------


def test_legacy_monitor_reports_safe_when_below_thresholds():
    monitor = LegacyResourceMonitor(memory_threshold_mb=4000.0, cpu_threshold_pct=90.0)
    with patch.object(
        pee.psutil,
        "virtual_memory",
        return_value=SimpleNamespace(used=1000 * 1024 * 1024),
    ), patch.object(pee.psutil, "cpu_percent", return_value=10.0):
        result = monitor.check_resources()

    assert result["memory_pressure"] is False
    assert result["cpu_pressure"] is False
    assert result["safe_for_parallelization"] is True


def test_legacy_monitor_detects_memory_pressure():
    monitor = LegacyResourceMonitor(memory_threshold_mb=4000.0, cpu_threshold_pct=90.0)
    with patch.object(
        pee.psutil,
        "virtual_memory",
        return_value=SimpleNamespace(used=5000 * 1024 * 1024),
    ), patch.object(pee.psutil, "cpu_percent", return_value=10.0):
        result = monitor.check_resources()

    assert result["memory_pressure"] is True
    assert result["safe_for_parallelization"] is False


# ---------------------------------------------------------------------------
# ExecutionResult dataclass
# ---------------------------------------------------------------------------


def test_execution_result_defaults_empty_errors():
    res = ExecutionResult(
        success=True,
        model_results={},
        execution_time=1.0,
        parallelism_achieved=2,
        resource_usage={},
    )
    assert res.errors == []


# ---------------------------------------------------------------------------
# _determine_effective_workers
# ---------------------------------------------------------------------------


def test_effective_workers_legacy_safe_returns_max_workers():
    engine = _engine(max_workers=4, resource_monitoring=True)
    with patch.object(
        engine.legacy_resource_monitor,
        "check_resources",
        return_value={"safe_for_parallelization": True},
    ):
        assert engine._determine_effective_workers(["a", "b"], _context()) == 4


def test_effective_workers_legacy_unsafe_returns_none():
    engine = _engine(max_workers=4, resource_monitoring=True)
    with patch.object(
        engine.legacy_resource_monitor,
        "check_resources",
        return_value={"safe_for_parallelization": False},
    ):
        assert engine._determine_effective_workers(["a"], _context()) is None


def test_effective_workers_no_monitoring_returns_max_workers():
    engine = _engine(max_workers=6, resource_monitoring=False)
    assert engine._determine_effective_workers(["a"], _context()) == 6


def test_effective_workers_resource_manager_unhealthy_returns_none():
    rm = MagicMock()
    rm.check_resource_health.return_value = False
    engine = _engine(resource_manager=rm)
    assert engine._determine_effective_workers(["a"], _context()) is None


def test_effective_workers_resource_manager_adapts_thread_count():
    rm = MagicMock()
    rm.check_resource_health.return_value = True
    rm.optimize_thread_count.return_value = (2, "memory pressure easing")
    engine = _engine(resource_manager=rm, max_workers=4, enable_adaptive_scaling=True)

    workers = engine._determine_effective_workers(["a", "b"], _context())

    assert workers == 2
    assert engine._current_thread_count == 2


# ---------------------------------------------------------------------------
# _execute_single_model
# ---------------------------------------------------------------------------


def test_execute_single_model_injects_deterministic_vars():
    engine = _engine(resource_monitoring=False, deterministic_execution=True)
    engine.dbt_runner.execute_command.return_value = SimpleNamespace(success=True)

    engine._execute_single_model("int_hiring_events", _context())

    kwargs = engine.dbt_runner.execute_command.call_args.kwargs
    assert "thread_local_seed" in kwargs["dbt_vars"]
    assert kwargs["dbt_vars"]["model_execution_id"] == "run-1:int_hiring_events"
    # original context dbt_vars must not be mutated
    assert "thread_local_seed" not in _context().dbt_vars


def test_execute_single_model_clears_active_set_after_run():
    engine = _engine(resource_monitoring=False)
    engine.dbt_runner.execute_command.return_value = SimpleNamespace(success=True)

    engine._execute_single_model("model_a", _context())

    assert engine._active_executions == set()


def test_execute_single_model_rejects_concurrent_duplicate():
    engine = _engine(resource_monitoring=False)
    ctx = _context()
    # Simulate the model already being in-flight.
    engine._active_executions.add(f"{ctx.execution_id}:model_a")

    with pytest.raises(RuntimeError, match="already being executed"):
        engine._execute_single_model("model_a", ctx)


# ---------------------------------------------------------------------------
# _generate_parallelization_recommendations
# ---------------------------------------------------------------------------


def _opportunity(safety_level, parallel_models, estimated_speedup=2.0):
    return SimpleNamespace(
        safety_level=safety_level,
        parallel_models=parallel_models,
        estimated_speedup=estimated_speedup,
    )


def test_recommendations_for_high_safety_models():
    engine = _engine()
    ops = [_opportunity("high", ["a", "b"], estimated_speedup=3.0)]
    recs = engine._generate_parallelization_recommendations(ops)
    assert any("high-safety" in r and "3.0x" in r for r in recs)


def test_recommendations_for_medium_safety_models():
    engine = _engine()
    ops = [_opportunity("medium", ["a"])]
    recs = engine._generate_parallelization_recommendations(ops)
    assert any("conditional parallelization" in r for r in recs)


def test_recommendations_when_no_opportunities():
    engine = _engine()
    recs = engine._generate_parallelization_recommendations([])
    assert recs == [
        "No parallelization opportunities found - all models require sequential execution"
    ]
