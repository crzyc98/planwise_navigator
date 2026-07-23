"""Scenario comparison endpoints."""


from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import APISettings, get_settings
from ..models.comparison import (
    ComparisonResponse,
    ConfigDiffResponse,
)
from ..storage.workspace_storage import WorkspaceStorage
from ..models.scenario import Scenario
from ..services.comparison_service import ComparisonService
from ..services.config_diff_service import ConfigDiffService
from ..services.scenario_read_warning import has_selected_result

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


def get_comparison_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> ComparisonService:
    """Dependency to get comparison service."""
    return ComparisonService(storage)


def get_config_diff_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> ConfigDiffService:
    """Dependency to get the effective configuration diff service."""
    return ConfigDiffService(storage)


def _require_completed_scenario(
    storage: WorkspaceStorage, workspace_id: str, scenario_id: str
) -> Scenario:
    """Fetch a scenario, 404 if missing, 400 if not completed."""
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
    return scenario


def _validate_scenario_pair(
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario_a: str,
    scenario_b: str,
) -> dict[str, str]:
    if scenario_a == scenario_b:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select two distinct scenarios",
        )
    return {
        scenario_id: _require_completed_scenario(
            storage, workspace_id, scenario_id
        ).name
        for scenario_id in (scenario_a, scenario_b)
    }


@router.get(
    "/{workspace_id}/comparison/config-diff",
    response_model=ConfigDiffResponse,
)
async def compare_scenario_configs(
    workspace_id: str,
    scenario_a: str = Query(...),
    scenario_b: str = Query(...),
    storage: WorkspaceStorage = Depends(get_storage),
    service: ConfigDiffService = Depends(get_config_diff_service),
) -> ConfigDiffResponse:
    """Compare effective configuration and provenance for two scenarios."""
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    names = _validate_scenario_pair(storage, workspace_id, scenario_a, scenario_b)
    try:
        return service.compare(
            workspace_id, scenario_a, scenario_b, names, workspace=workspace
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/{workspace_id}/comparison", response_model=ComparisonResponse)
async def compare_scenarios(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated scenario IDs"),
    baseline: str = Query(..., description="Baseline scenario ID"),
    storage: WorkspaceStorage = Depends(get_storage),
    comparison_service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonResponse:
    """
    Compare multiple scenarios against a baseline.

    Returns pre-calculated deltas for workforce metrics and events.
    """
    # Verify workspace exists
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    # Parse scenario IDs
    scenario_ids = [s.strip() for s in scenarios.split(",")]

    # Verify baseline is in the list
    if baseline not in scenario_ids:
        scenario_ids.insert(0, baseline)

    # Verify all scenarios exist and are completed
    scenario_names = {
        scenario_id: _require_completed_scenario(
            storage, workspace_id, scenario_id
        ).name
        for scenario_id in scenario_ids
    }

    # Generate comparison
    comparison = comparison_service.compare_scenarios(
        workspace_id, scenario_ids, baseline
    )

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate comparison",
        )

    comparison.scenario_names = scenario_names
    return comparison
