"""NDT (Non-Discrimination Testing) endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import APISettings, get_settings
from ..services.ndt_service import (
    ACPTestResponse,
    AvailableYearsResponse,
    NDTService,
)
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


def get_ndt_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> NDTService:
    """Dependency to get NDT service."""
    return NDTService(storage)


@router.get(
    "/{workspace_id}/analytics/ndt/available-years",
    response_model=AvailableYearsResponse,
)
async def get_ndt_available_years(
    workspace_id: str,
    scenario_id: str = Query(..., description="Scenario ID"),
    storage: WorkspaceStorage = Depends(get_storage),
    ndt_service: NDTService = Depends(get_ndt_service),
) -> AvailableYearsResponse:
    """Get available simulation years for NDT testing."""
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    scenario = storage.get_scenario(workspace_id, scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    return ndt_service.get_available_years(workspace_id, scenario_id)


@router.get(
    "/{workspace_id}/analytics/ndt/acp",
    response_model=ACPTestResponse,
)
async def run_acp_test(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated scenario IDs"),
    year: int = Query(..., description="Simulation year to analyze"),
    include_employees: bool = Query(False, description="Include per-employee detail"),
    storage: WorkspaceStorage = Depends(get_storage),
    ndt_service: NDTService = Depends(get_ndt_service),
) -> ACPTestResponse:
    """Run ACP non-discrimination test for one or more scenarios."""
    # Validate workspace
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    # Parse scenario IDs
    scenario_ids = [s.strip() for s in scenarios.split(",") if s.strip()]
    if not scenario_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one scenario ID is required",
        )

    # Validate all scenarios exist and are completed
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

    # Run ACP test for each scenario
    results = []
    for scenario_id in scenario_ids:
        result = ndt_service.run_acp_test(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            scenario_name=scenario_names[scenario_id],
            year=year,
            include_employees=include_employees,
        )
        results.append(result)

    return ACPTestResponse(
        test_type="acp",
        year=year,
        results=results,
    )
