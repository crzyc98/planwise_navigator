"""Read-only employee discovery and storyline endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import APISettings, get_settings
from ..models.timeline import EmployeeSearchResponse, EmployeeTimelineResponse
from ..services.timeline_service import TimelineDatabaseNotFoundError, TimelineService
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    return WorkspaceStorage(settings.workspaces_root)


def get_timeline_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> TimelineService:
    return TimelineService(storage)


def _validate_scope(
    storage: WorkspaceStorage, workspace_id: str, scenario_id: str
) -> None:
    if not storage.get_workspace(workspace_id):
        raise HTTPException(
            status_code=404, detail=f"Workspace {workspace_id} not found"
        )
    if not storage.get_scenario(workspace_id, scenario_id):
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")


@router.get(
    "/{workspace_id}/scenarios/{scenario_id}/employees",
    response_model=EmployeeSearchResponse,
)
def search_employees(
    workspace_id: str,
    scenario_id: str,
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    level: int | None = Query(None, ge=1),
    year: int | None = None,
    enrolled: bool | None = None,
    has_escalations: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    storage: WorkspaceStorage = Depends(get_storage),
    service: TimelineService = Depends(get_timeline_service),
) -> EmployeeSearchResponse:
    _validate_scope(storage, workspace_id, scenario_id)
    try:
        return service.search_employees(
            workspace_id,
            scenario_id,
            q,
            status_filter,
            level,
            year,
            enrolled,
            has_escalations,
            page,
            page_size,
        )
    except TimelineDatabaseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.get(
    "/{workspace_id}/scenarios/{scenario_id}/employees/{employee_id}/timeline",
    response_model=EmployeeTimelineResponse,
)
def get_employee_timeline(
    workspace_id: str,
    scenario_id: str,
    employee_id: str,
    start_year: int | None = None,
    years: int = Query(3, ge=1, le=20),
    storage: WorkspaceStorage = Depends(get_storage),
    service: TimelineService = Depends(get_timeline_service),
) -> EmployeeTimelineResponse:
    _validate_scope(storage, workspace_id, scenario_id)
    try:
        return service.get_timeline(
            workspace_id, scenario_id, employee_id, start_year, years
        )
    except TimelineDatabaseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
