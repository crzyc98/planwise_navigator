"""Analytics endpoints: DC Plan and Winners & Losers."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import APISettings, get_settings
from ..constants import MAX_SCENARIO_COMPARISON
from ..models.analytics import DCPlanAnalytics, DCPlanComparisonResponse
from ..models.winners_losers import WinnersLosersResponse
from ..services.analytics_service import AnalyticsService
from ..services.winners_losers_service import WinnersLosersService
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
    active_only: bool = Query(False, description="If true, include only active employees in participation metrics"),
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
        workspace_id, scenario_id, scenario.name, active_only=active_only
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
    active_only: bool = Query(False, description="If true, include only active employees in participation metrics"),
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
            workspace_id, scenario_id, scenario_names[scenario_id],
            active_only=active_only,
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


# ---------------------------------------------------------------------------
# Winners & Losers
# ---------------------------------------------------------------------------


def get_winners_losers_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> WinnersLosersService:
    """Dependency to get winners/losers service."""
    return WinnersLosersService(storage)


@router.get(
    "/{workspace_id}/analytics/winners-losers",
    response_model=WinnersLosersResponse,
)
async def get_winners_losers(
    workspace_id: str,
    plan_a: str = Query(..., description="Scenario ID for Plan A (reference)"),
    plan_b: str = Query(..., description="Scenario ID for Plan B (alternative)"),
    storage: WorkspaceStorage = Depends(get_storage),
    service: WinnersLosersService = Depends(get_winners_losers_service),
) -> WinnersLosersResponse:
    """
    Compare two scenarios and classify employees as winners, losers, or
    neutral based on total employer contributions (match + core).
    """
    # Validate workspace
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    # Validate both scenarios exist and are completed
    for label, sid in [("Plan A", plan_a), ("Plan B", plan_b)]:
        scenario = storage.get_scenario(workspace_id, sid)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{label} scenario {sid} not found",
            )
        if scenario.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{label} scenario {sid} has not completed successfully",
            )

    result = service.analyze(workspace_id, plan_a, plan_b)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate winners/losers analysis",
        )

    return result
