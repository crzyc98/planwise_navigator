"""Batch processing endpoints."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ..config import APISettings, get_settings
from ..errors import sanitize_job_error
from ..models.batch import BatchCreate, BatchJob, BatchScenario
from ..models.scenario import Scenario
from ..services.simulation_service import SimulationService
from ..storage.workspace_storage import WorkspaceStorage
from ..websocket.manager import ConnectionManager, get_connection_manager
from ..services.telemetry_service import get_telemetry_service

logger = logging.getLogger(__name__)

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


# In-memory store for batch jobs (would use Redis in production)
_batch_jobs: Dict[str, BatchJob] = {}


def get_batch_job(batch_id: str) -> Optional[BatchJob]:
    """Return the in-memory job used to seed a batch WebSocket snapshot."""
    return _batch_jobs.get(batch_id)


def serialize_batch_update(batch_job: BatchJob, event: str) -> dict:
    """Build the documented batch WebSocket envelope from the current job."""
    scenario_payload = [scenario.model_dump() for scenario in batch_job.scenarios]
    overall_progress = round(
        sum(scenario.progress for scenario in batch_job.scenarios)
        / max(len(batch_job.scenarios), 1)
    )
    return {
        "type": "batch_update",
        "event": event,
        "batch_id": batch_job.id,
        "status": batch_job.status,
        "scenarios": scenario_payload,
        "overall_progress": overall_progress,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _broadcast_batch(
    batch_job: BatchJob,
    event: str,
    manager: Optional[ConnectionManager] = None,
) -> None:
    """Publish the current batch state to all subscribers."""
    channel_manager = manager or get_connection_manager()
    await channel_manager.broadcast_json(
        f"batch_{batch_job.id}", serialize_batch_update(batch_job, event)
    )


@router.post("/workspaces/{workspace_id}/run-all", response_model=BatchJob)
async def run_all_scenarios(
    workspace_id: str,
    data: BatchCreate = BatchCreate(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    storage: WorkspaceStorage = Depends(get_storage),
) -> BatchJob:
    """
    Run all (or selected) scenarios in a workspace as a batch.

    Returns a batch job ID that can be used to monitor progress.
    """
    # Debug logging for batch request
    logger.info("=== BATCH REQUEST RECEIVED ===")
    logger.info(f"  workspace_id: {workspace_id}")
    logger.info(f"  data.name: {data.name}")
    logger.info(f"  data.scenario_ids: {data.scenario_ids}")
    logger.info(
        f"  data.parallel: {data.parallel} (type: {type(data.parallel).__name__})"
    )
    logger.info(f"  data.export_format: {data.export_format}")

    # Verify workspace exists
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    # Get scenarios to run
    all_scenarios = storage.list_scenarios(workspace_id)
    if not all_scenarios:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workspace {workspace_id} has no scenarios",
        )

    # Filter to selected scenarios if specified
    if data.scenario_ids:
        scenario_ids_set = set(data.scenario_ids)
        scenarios_to_run = [s for s in all_scenarios if s.id in scenario_ids_set]
        if not scenarios_to_run:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="None of the specified scenarios were found",
            )
    else:
        scenarios_to_run = all_scenarios

    # Create batch job
    batch_id = str(uuid.uuid4())
    batch_name = (
        data.name or f"Batch {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
    )

    batch_scenarios = [
        BatchScenario(
            scenario_id=s.id,
            name=s.name,
            status="pending",
            progress=0,
        )
        for s in scenarios_to_run
    ]

    batch_job = BatchJob(
        id=batch_id,
        name=batch_name,
        workspace_id=workspace_id,
        status="pending",
        submitted_at=datetime.now(timezone.utc),
        scenarios=batch_scenarios,
        parallel=data.parallel,
        export_format=data.export_format,
    )

    _batch_jobs[batch_id] = batch_job
    await _broadcast_batch(batch_job, "pending")

    # Start batch processing in background
    background_tasks.add_task(
        _execute_batch,
        storage,
        workspace_id,
        batch_id,
        scenarios_to_run,
        data.parallel,
        data.export_format,
        get_connection_manager(),
    )

    return batch_job


@router.get("/batches/{batch_id}/status", response_model=BatchJob)
async def get_batch_status(batch_id: str) -> BatchJob:
    """
    Get the status of a batch job.
    """
    if batch_id not in _batch_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch job {batch_id} not found",
        )

    return _batch_jobs[batch_id]


@router.get("/workspaces/{workspace_id}/batches", response_model=List[BatchJob])
async def list_batch_jobs(
    workspace_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> List[BatchJob]:
    """
    List all batch jobs for a workspace.
    """
    # Verify workspace exists
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    return [job for job in _batch_jobs.values() if job.workspace_id == workspace_id]


async def _execute_batch(
    storage: WorkspaceStorage,
    workspace_id: str,
    batch_id: str,
    scenarios: List[Scenario],
    parallel: bool,
    _export_format: Optional[str],
    manager: Optional[ConnectionManager] = None,
) -> None:
    """Execute batch scenarios (background task)."""
    logger.info("=== BATCH EXECUTION STARTED ===")
    logger.info(f"  batch_id: {batch_id}")
    logger.info(f"  parallel: {parallel} (type: {type(parallel).__name__})")
    logger.info(f"  num_scenarios: {len(scenarios)}")
    logger.info(f"  scenario_names: {[s.name for s in scenarios]}")

    batch_job = _batch_jobs[batch_id]
    batch_job.status = "running"
    await _broadcast_batch(batch_job, "running", manager)

    # Create simulation service
    simulation_service = SimulationService(storage)

    async def run_scenario(index: int, scenario: Scenario) -> None:
        """Run a single scenario and update batch status."""
        run_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)
        logger.info(
            f"  [{start_time.strftime('%H:%M:%S.%f')}] [Scenario {index}] STARTED: {scenario.name}"
        )
        batch_job.scenarios[index].status = "running"
        await _broadcast_batch(batch_job, "running", manager)

        async def publish_progress() -> None:
            """Forward the scenario's existing simulation telemetry to batch clients."""
            while True:
                telemetry = get_telemetry_service().get_snapshot(run_id)
                if telemetry is not None:
                    next_progress = telemetry.progress
                    if batch_job.scenarios[index].progress != next_progress:
                        batch_job.scenarios[index].progress = next_progress
                        await _broadcast_batch(batch_job, "progress", manager)
                await asyncio.sleep(0.25)

        progress_task = asyncio.create_task(publish_progress())

        try:
            # Get merged config for this scenario
            merged_config = storage.get_merged_config(workspace_id, scenario.id)
            if merged_config is None:
                raise ValueError(
                    f"No merged config available for scenario {scenario.id}"
                )

            # Execute the simulation
            await simulation_service.execute_simulation(
                workspace_id=workspace_id,
                scenario_id=scenario.id,
                run_id=run_id,
                config=merged_config,
                resume_from_checkpoint=False,
            )

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            stored_scenario = storage.get_scenario(workspace_id, scenario.id)
            outcome: Literal["completed", "failed", "cancelled"]
            if stored_scenario and stored_scenario.status in {
                "completed",
                "failed",
                "cancelled",
            }:
                outcome = cast(
                    Literal["completed", "failed", "cancelled"],
                    stored_scenario.status,
                )
            else:
                outcome = "failed"
            batch_job.scenarios[index].status = outcome
            if outcome == "completed":
                batch_job.scenarios[index].progress = 100
            else:
                batch_job.scenarios[
                    index
                ].error_message = f"Simulation finished with terminal status {outcome}"
            await _broadcast_batch(batch_job, outcome, manager)
            logger.info(
                f"  [{end_time.strftime('%H:%M:%S.%f')}] [Scenario {index}] "
                f"{outcome.upper()}: {scenario.name} (took {duration:.1f}s)"
            )

        except Exception:
            end_time = datetime.now(timezone.utc)
            batch_job.scenarios[index].status = "failed"
            batch_job.scenarios[index].error_message = sanitize_job_error(
                logger,
                f"scenario {index} ({scenario.name})",
                event="Batch scenario failed",
            )
            await _broadcast_batch(batch_job, "failed", manager)
        finally:
            progress_task.cancel()
            await asyncio.gather(progress_task, return_exceptions=True)

    try:
        if parallel:
            # Run all scenarios in parallel
            logger.info("=== EXECUTING IN PARALLEL MODE ===")
            logger.info(f"  Creating {len(scenarios)} concurrent tasks...")
            tasks = [run_scenario(i, scenario) for i, scenario in enumerate(scenarios)]
            logger.info("  Launching asyncio.gather for all tasks...")
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("  All parallel tasks completed")
        else:
            # Run sequentially
            logger.info("=== EXECUTING IN SEQUENTIAL MODE ===")
            for i, scenario in enumerate(scenarios):
                logger.info(
                    f"  Starting scenario {i+1}/{len(scenarios)}: {scenario.name}"
                )
                await run_scenario(i, scenario)
                logger.info(
                    f"  Completed scenario {i+1}/{len(scenarios)}: {scenario.name}"
                )

        # Check if all completed successfully
        all_completed = all(s.status == "completed" for s in batch_job.scenarios)
        any_cancelled = any(s.status == "cancelled" for s in batch_job.scenarios)
        batch_job.status = (
            "completed" if all_completed else "cancelled" if any_cancelled else "failed"
        )
        batch_job.completed_at = datetime.now(timezone.utc)
        batch_job.duration_seconds = (
            batch_job.completed_at - batch_job.submitted_at
        ).total_seconds()
        await _broadcast_batch(batch_job, batch_job.status, manager)

    except Exception:
        batch_job.status = "failed"
        batch_job.completed_at = datetime.now(timezone.utc)
        batch_job.duration_seconds = (
            batch_job.completed_at - batch_job.submitted_at
        ).total_seconds()
        # Mark any pending scenarios as failed
        for batch_scenario in batch_job.scenarios:
            if batch_scenario.status in ("pending", "running"):
                batch_scenario.status = "failed"
                batch_scenario.error_message = sanitize_job_error(
                    logger, batch_job.id, event="Batch execution failed"
                )
        await _broadcast_batch(batch_job, "failed", manager)
