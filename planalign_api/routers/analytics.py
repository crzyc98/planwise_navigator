"""DC Plan analytics endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import APISettings, get_settings
from ..constants import MAX_SCENARIO_COMPARISON
from ..models.analytics import DCPlanAnalytics, DCPlanComparisonResponse
from ..services.analytics_service import AnalyticsService
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


def get_analytics_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> AnalyticsService:
    """Dependency to get analytics service."""
    return AnalyticsService(storage)


@router.get(
    "/{workspace_id}/scenarios/{scenario_id}/analytics/dc-plan",
    response_model=DCPlanAnalytics,
)
async def get_dc_plan_analytics(
    workspace_id: str,
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> DCPlanAnalytics:
    """
    Get DC Plan contribution analytics for a single scenario.

    Returns participation rates, contribution totals, deferral distributions,
    and escalation metrics.
    """
    # Verify workspace exists
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    # Verify scenario exists and is completed
    scenario = storage.get_scenario(workspace_id, scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    if scenario.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Scenario {scenario_id} has not completed successfully",
        )

    # Get analytics
    analytics = analytics_service.get_dc_plan_analytics(
        workspace_id, scenario_id, scenario.name
    )

    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate DC plan analytics",
        )

    return analytics


@router.get(
    "/{workspace_id}/analytics/dc-plan/compare",
    response_model=DCPlanComparisonResponse,
)
async def compare_dc_plan_analytics(
    workspace_id: str,
    scenarios: str = Query(..., description=f"Comma-separated scenario IDs (max {MAX_SCENARIO_COMPARISON})"),
    storage: WorkspaceStorage = Depends(get_storage),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> DCPlanComparisonResponse:
    """
    Compare DC Plan analytics across multiple scenarios (max {MAX_SCENARIO_COMPARISON}).

    Returns side-by-side analytics for comparison.
    """
    # Verify workspace exists
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    # Parse and validate scenario IDs
    scenario_ids = [s.strip() for s in scenarios.split(",")]

    if len(scenario_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 scenarios required for comparison",
        )

    if len(scenario_ids) > MAX_SCENARIO_COMPARISON:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_SCENARIO_COMPARISON} scenarios allowed for comparison",
        )

    # Verify all scenarios exist and are completed
    scenario_names = {}
    for scenario_id in scenario_ids:
        scenario = storage.get_scenario(workspace_id, scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )
        if scenario.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scenario {scenario_id} has not completed successfully",
            )
        scenario_names[scenario_id] = scenario.name

    # Get analytics for each scenario
    analytics_list: List[DCPlanAnalytics] = []
    for scenario_id in scenario_ids:
        analytics = analytics_service.get_dc_plan_analytics(
            workspace_id, scenario_id, scenario_names[scenario_id]
        )
        if analytics:
            analytics_list.append(analytics)

    if len(analytics_list) < 2:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate analytics for comparison",
        )

    return DCPlanComparisonResponse(
        scenarios=scenario_ids,
        scenario_names=scenario_names,
        analytics=analytics_list,
    )
