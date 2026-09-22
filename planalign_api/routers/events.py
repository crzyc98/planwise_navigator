"""Read-only global event audit explorer endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import APISettings, get_settings
from ..models.events import EventListResponse
from ..services.events_service import (
    EventExplorerDatabaseNotFoundError,
    EventExplorerService,
)
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    return WorkspaceStorage(settings.workspaces_root)


def get_events_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> EventExplorerService:
    return EventExplorerService(storage)


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
    "/{workspace_id}/scenarios/{scenario_id}/events",
    response_model=EventListResponse,
)
def list_events(
    workspace_id: str,
    scenario_id: str,
    simulation_year: int | None = Query(None),
    event_type: str | None = Query(None),
    event_category: str | None = Query(None),
    employee_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    storage: WorkspaceStorage = Depends(get_storage),
    service: EventExplorerService = Depends(get_events_service),
) -> EventListResponse:
    _validate_scope(storage, workspace_id, scenario_id)
    try:
        return service.list_events(
            workspace_id,
            scenario_id,
            simulation_year=simulation_year,
            event_type=event_type,
            event_category=event_category,
            employee_id=employee_id,
            page=page,
            page_size=page_size,
        )
    except EventExplorerDatabaseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
