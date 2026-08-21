"""FastAPI router for vesting analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..constants import MAX_SCENARIO_COMPARISON
from ..models.employer_cost import ForfeiturePolicy
from ..models.vesting import (
    ForfeitureProjectionResponse,
    ScenarioYearsResponse,
    VestingAnalysisRequest,
    VestingAnalysisResponse,
    VestingScheduleConfig,
    VestingScheduleListResponse,
    VestingScheduleType,
)
from ..services.scenario_read_warning import has_selected_result
from ..services.vesting_service import (
    SCHEDULE_INFO,
    VestingService,
    get_schedule_list,
)
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


@router.get(
    "/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting/years",
    response_model=ScenarioYearsResponse,
)
async def get_vesting_years(
    workspace_id: str,
    scenario_id: str,
    vesting_service: VestingService = Depends(get_vesting_service),
) -> ScenarioYearsResponse:
    """
    Get available simulation years for vesting analysis.

    Returns the list of simulation years present in the scenario's
    database, sorted ascending, with the default (final) year.
    """
    storage = vesting_service.storage
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    scenario = storage.get_scenario(workspace_id, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    result = vesting_service.get_available_years(workspace_id, scenario_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Simulation data not found. Ensure the scenario has completed simulation.",
        )

    return result


def _resolve_selected_scenarios(
    storage: WorkspaceStorage, workspace_id: str, scenarios: str
) -> list[tuple[str, str]]:
    """Parse and validate the comma-separated scenario selection.

    Unlike the DC-plan comparison endpoint, a single scenario is valid here:
    reporting one scenario's forfeitures across all years is the primary use
    case, not a degenerate comparison.
    """
    scenario_ids = [item.strip() for item in scenarios.split(",") if item.strip()]
    if not scenario_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one scenario is required",
        )
    if len(set(scenario_ids)) != len(scenario_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate scenario IDs are not allowed",
        )
    if len(scenario_ids) > MAX_SCENARIO_COMPARISON:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_SCENARIO_COMPARISON} scenarios allowed",
        )

    resolved: list[tuple[str, str]] = []
    for scenario_id in scenario_ids:
        scenario = storage.get_scenario(workspace_id, scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )
        if not has_selected_result(storage, workspace_id, scenario_id, scenario.status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scenario {scenario_id} has not completed successfully",
            )
        resolved.append((scenario_id, scenario.name or scenario_id))
    return resolved


@router.get(
    "/workspaces/{workspace_id}/analytics/vesting/forfeitures",
    response_model=ForfeitureProjectionResponse,
)
async def project_vesting_forfeitures(
    workspace_id: str,
    scenarios: str = Query(
        ...,
        description=(
            "Comma-separated scenario IDs "
            f"(1-{MAX_SCENARIO_COMPARISON}, all must be completed)"
        ),
    ),
    schedule_type: VestingScheduleType = Query(
        ..., description="The single vesting schedule to report under"
    ),
    require_hours_credit: bool = Query(
        False, description="Require the hours threshold for vesting credit"
    ),
    hours_threshold: int = Query(
        1000, ge=0, le=2080, description="Minimum annual hours for vesting credit"
    ),
    forfeiture_policy: ForfeiturePolicy = Query(
        ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
        description=(
            "What the plan does with forfeited money. Determines whether the "
            "returned employer cost offsets reduce sponsor outlay at all."
        ),
    ),
    vesting_service: VestingService = Depends(get_vesting_service),
) -> ForfeitureProjectionResponse:
    """
    Report annual forfeitures under one vesting schedule, for every simulation
    year, across a selected set of scenarios (issue #489).

    This is a reporting view, not the current-vs-proposed comparison served by
    POST .../analytics/vesting. A scenario's first simulation year has no prior
    year to source employer contributions from, so its row is flagged
    `has_prior_year_basis: false` rather than reported as a measured zero.

    Each series also carries `employer_cost_offsets` (issue #444): the per-year
    reduction to employer cost implied by `forfeiture_policy`, with year N
    terminations offsetting year N+1 cost. The Cost Comparison page joins these
    onto gross cost rather than re-deriving the policy semantics client-side.
    """
    storage = vesting_service.storage
    if not storage.get_workspace(workspace_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    selected = _resolve_selected_scenarios(storage, workspace_id, scenarios)
    schedule = VestingScheduleConfig(
        schedule_type=schedule_type,
        name=SCHEDULE_INFO[schedule_type].name,
        require_hours_credit=require_hours_credit,
        hours_threshold=hours_threshold,
    )
    return vesting_service.project_forfeitures(
        workspace_id, selected, schedule, forfeiture_policy
    )


@router.post(
    "/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting",
    response_model=VestingAnalysisResponse,
)
async def analyze_vesting(
    workspace_id: str,
    scenario_id: str,
    request: VestingAnalysisRequest,
    vesting_service: VestingService = Depends(get_vesting_service),
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

    scenario_name = scenario.name or scenario_id

    result = vesting_service.analyze_vesting(
        workspace_id, scenario_id, scenario_name, request
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Simulation data not found. Ensure the scenario has completed simulation.",
        )

    return result
