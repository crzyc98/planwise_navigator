"""Batch processing endpoints."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ..config import APISettings, get_settings
from ..models.batch import BatchCreate, BatchJob, BatchScenario
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


# In-memory store for batch jobs (would use Redis in production)
_batch_jobs: Dict[str, BatchJob] = {}


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
    batch_name = data.name or f"Batch {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

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
        submitted_at=datetime.utcnow(),
        scenarios=batch_scenarios,
        parallel=data.parallel,
        export_format=data.export_format,
    )

    _batch_jobs[batch_id] = batch_job

    # Start batch processing in background
    background_tasks.add_task(
        _execute_batch,
        storage,
        workspace_id,
        batch_id,
        scenarios_to_run,
        data.parallel,
        data.export_format,
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
    scenarios: List,
    parallel: bool,
    export_format: Optional[str],
):
    """Execute batch scenarios (background task)."""
    batch_job = _batch_jobs[batch_id]
    batch_job.status = "running"

    try:
        # For now, run sequentially (parallel would use asyncio.gather)
        for i, scenario in enumerate(scenarios):
            # Update batch scenario status
            batch_job.scenarios[i].status = "running"

            # TODO: Actually run the simulation
            # For now, just simulate progress
            import asyncio

            for progress in range(0, 101, 10):
                batch_job.scenarios[i].progress = progress
                await asyncio.sleep(0.1)  # Simulate work

            batch_job.scenarios[i].status = "completed"
            batch_job.scenarios[i].progress = 100

            # Update scenario in storage
            storage.update_scenario_status(
                workspace_id, scenario.id, "completed", run_id=f"batch_{batch_id}"
            )

        batch_job.status = "completed"
        batch_job.completed_at = datetime.utcnow()
        batch_job.duration_seconds = (
            batch_job.completed_at - batch_job.submitted_at
        ).total_seconds()

    except Exception as e:
        batch_job.status = "failed"
        batch_job.completed_at = datetime.utcnow()
        # Mark any pending scenarios as failed
        for batch_scenario in batch_job.scenarios:
            if batch_scenario.status in ("pending", "running"):
                batch_scenario.status = "failed"
                batch_scenario.error_message = str(e)
