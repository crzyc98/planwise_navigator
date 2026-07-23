"""Optional and legacy stage execution strategies for :mod:`year_executor`."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from planalign_core.constants import MODEL_FCT_YEARLY_EVENTS
from planalign_orchestrator.dbt_runner import DbtResult

from .workflow import StageDefinition, WorkflowStage

logger = logging.getLogger(__name__)

try:
    from planalign_orchestrator.parallel_execution_engine import ExecutionContext
except ImportError:  # pragma: no cover - optional runtime capability
    ExecutionContext = None  # type: ignore[assignment,misc]


class PipelineStageError(RuntimeError):
    """Raised when a stage execution strategy cannot complete."""


def execute_tagged_stage(
    executor: Any, stage: StageDefinition, year: int
) -> list[DbtResult]:
    """Execute a non-sharded stage through its broad dbt execution tag."""
    tag_name = stage.name.value.upper()
    if executor.verbose:
        logger.info("Executing tag:%s with %d threads", tag_name, executor.dbt_threads)
    result = executor.dbt_runner.execute_command(
        ["run", "--select", f"tag:{tag_name}"],
        simulation_year=year,
        dbt_vars=executor._dbt_vars,
        stream_output=True,
    )
    if not result.success:
        raise PipelineStageError(
            f"Parallel stage {stage.name.value} failed with code {result.return_code}"
        )
    return [result]


def execute_sharded_events(executor: Any, year: int) -> list[DbtResult]:
    """Run optional event shards followed by the single event publisher."""
    results: list[DbtResult] = []
    if executor.verbose:
        logger.debug("Executing event generation with %d shards", executor.event_shards)
    for shard_id in range(executor.event_shards):
        shard_vars = {
            **executor._dbt_vars,
            "shard_id": shard_id,
            "total_shards": executor.event_shards,
        }
        result = executor.dbt_runner.execute_command(
            ["run", "--select", f"events_y{year}_shard{shard_id}"],
            simulation_year=year,
            dbt_vars=shard_vars,
            stream_output=True,
        )
        results.append(result)
        if not result.success:
            raise PipelineStageError(
                f"Event shard {shard_id} failed with code {result.return_code}"
            )

    union_result = executor.dbt_runner.execute_command(
        ["run", "--select", MODEL_FCT_YEARLY_EVENTS],
        simulation_year=year,
        dbt_vars=executor._dbt_vars,
        stream_output=True,
    )
    results.append(union_result)
    if not union_result.success:
        raise PipelineStageError(
            f"Event union writer failed with code {union_result.return_code}"
        )
    return results


def should_use_model_parallelization(executor: Any, stage: StageDefinition) -> bool:
    """Apply conservative safety gates to optional model parallelization."""
    try:
        db_path = getattr(executor.db_manager, "db_path", None)
        if db_path and str(db_path).endswith(".duckdb"):
            return False
    except Exception:
        pass

    if stage.name in {WorkflowStage.EVENT_GENERATION, WorkflowStage.STATE_ACCUMULATION}:
        config = executor.parallelization_config
        engine = executor.parallel_execution_engine
        if config and hasattr(config, "safety"):
            if config.safety.validate_execution_safety and engine is not None:
                validation = engine.validate_stage_parallelization(stage.models)
                return (
                    validation.get("parallelizable", False)
                    and validation.get("safety_score", 0) > 80
                )
        return False
    return len(stage.models) > 1


def execute_model_parallelization(
    executor: Any, stage: StageDefinition, year: int
) -> None:
    """Delegate an eligible stage to the optional parallel execution engine."""
    if ExecutionContext is None:
        raise PipelineStageError("Model-level parallelization is unavailable")
    if executor.verbose:
        logger.info("Using model-level parallelization for stage %s", stage.name.value)
    context = ExecutionContext(
        simulation_year=year,
        dbt_vars=executor._dbt_vars,
        stage_name=stage.name.value,
        execution_id=str(uuid.uuid4())[:8],
    )
    engine = executor.parallel_execution_engine
    config = executor.parallelization_config
    assert engine is not None
    assert config is not None
    result = engine.execute_stage_with_parallelization(
        stage.models,
        context,
        enable_conditional_parallelization=config.enable_conditional_parallelization,
    )
    if executor.verbose:
        logger.info(
            "Parallelization success=%s models=%d time=%.1fs factor=%sx",
            result.success,
            len(result.model_results),
            result.execution_time,
            result.parallelism_achieved,
        )
        for error in result.errors[:3]:
            logger.error("Parallelization error: %s", error)
    if result.success:
        return
    detail = f": {'; '.join(result.errors[:2])}" if result.errors else ""
    raise PipelineStageError(
        f"Model-level parallelization failed in stage {stage.name.value}{detail}"
    )
