"""FastAPI router for vesting analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..models.vesting import (
    VestingAnalysisRequest,
    VestingAnalysisResponse,
    VestingScheduleListResponse,
)
from ..services.vesting_service import VestingService, get_schedule_list
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


def get_workspace_storage() -> WorkspaceStorage:
    """Get workspace storage instance."""
    from ..config import get_settings
    settings = get_settings()
    return WorkspaceStorage(settings.workspaces_root)


def get_vesting_service(
    storage: WorkspaceStorage = Depends(get_workspace_storage),
) -> VestingService:
    """Dependency to get VestingService instance (T032)."""
    return VestingService(storage)


@router.get("/vesting/schedules", response_model=VestingScheduleListResponse)
async def list_vesting_schedules() -> VestingScheduleListResponse:
    """
    List all pre-defined vesting schedules (T030).

    Returns all available vesting schedule types with their
    percentage progressions and descriptions.
    """
    return get_schedule_list()


@router.post(
    "/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting",
    response_model=VestingAnalysisResponse
)
async def analyze_vesting(
    workspace_id: str,
    scenario_id: str,
    request: VestingAnalysisRequest,
    vesting_service: VestingService = Depends(get_vesting_service)
) -> VestingAnalysisResponse:
    """
    Run vesting analysis comparing two schedules (T031).

    Compares current vs proposed vesting schedules and projects
    forfeiture differences for terminated employees in the
    specified simulation year.
    """
    # Get scenario name from workspace storage
    storage = vesting_service.storage
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    scenario = storage.get_scenario(workspace_id, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario_name = scenario.get("name", scenario_id)

    result = vesting_service.analyze_vesting(
        workspace_id, scenario_id, scenario_name, request
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Simulation data not found. Ensure the scenario has completed simulation."
        )

    return result
