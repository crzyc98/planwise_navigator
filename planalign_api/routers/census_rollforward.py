"""Census status and roll-forward endpoints (#1078)."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ..config import APISettings, get_settings
from ..models.census_rollforward import CensusStatus, RollForwardJob
from ..services import census_rollforward_jobs as jobs
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    return WorkspaceStorage(settings.workspaces_root)


def _require_workspace(storage: WorkspaceStorage, workspace_id: str) -> None:
    if storage.get_workspace(workspace_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )


@router.get(
    "/{workspace_id}/census/status",
    response_model=CensusStatus,
    summary="Compare the census year with the simulation start year",
)
def get_census_status(
    workspace_id: str, storage: WorkspaceStorage = Depends(get_storage)
) -> CensusStatus:
    _require_workspace(storage, workspace_id)
    return jobs.census_status(storage, workspace_id)


@router.post(
    "/{workspace_id}/census/roll-forward",
    response_model=RollForwardJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Roll an old census forward to the year before the start year",
)
def start_census_roll_forward(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    storage: WorkspaceStorage = Depends(get_storage),
) -> RollForwardJob:
    _require_workspace(storage, workspace_id)
    try:
        job = jobs.start_job(storage, workspace_id)
    except jobs.RollForwardUnavailable as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    background_tasks.add_task(jobs.run_job, storage, job.id)
    return job


@router.get(
    "/{workspace_id}/census/roll-forward/{job_id}",
    response_model=RollForwardJob,
    summary="Status of a census roll-forward",
)
def get_census_roll_forward(workspace_id: str, job_id: str) -> RollForwardJob:
    job = jobs.get_job(workspace_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Roll-forward {job_id} not found",
        )
    return job
