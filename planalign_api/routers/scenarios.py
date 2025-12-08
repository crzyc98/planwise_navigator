"""Scenario management endpoints."""

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from ..config import APISettings, get_settings
from ..models.scenario import (
    Scenario,
    ScenarioConfig,
    ScenarioCreate,
    ScenarioUpdate,
)
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


@router.get("/{workspace_id}/scenarios", response_model=List[Scenario])
async def list_scenarios(
    workspace_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> List[Scenario]:
    """
    List all scenarios in a workspace.
    """
    # Verify workspace exists
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    return storage.list_scenarios(workspace_id)


@router.post(
    "/{workspace_id}/scenarios",
    response_model=Scenario,
    status_code=status.HTTP_201_CREATED,
)
async def create_scenario(
    workspace_id: str,
    data: ScenarioCreate,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Scenario:
    """
    Create a new scenario in a workspace.

    The scenario will inherit the workspace's base configuration,
    with config_overrides applied on top.
    """
    scenario = storage.create_scenario(workspace_id, data)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return scenario


@router.get("/{workspace_id}/scenarios/{scenario_id}", response_model=Scenario)
async def get_scenario(
    workspace_id: str,
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Scenario:
    """
    Get a scenario by ID.
    """
    scenario = storage.get_scenario(workspace_id, scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found in workspace {workspace_id}",
        )
    return scenario


@router.get(
    "/{workspace_id}/scenarios/{scenario_id}/config",
    response_model=Dict[str, Any],
)
async def get_scenario_config(
    workspace_id: str,
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Dict[str, Any]:
    """
    Get the fully merged configuration for a scenario.

    This returns the workspace's base configuration with the scenario's
    config_overrides applied.
    """
    config = storage.get_merged_config(workspace_id, scenario_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found in workspace {workspace_id}",
        )
    return config


@router.put("/{workspace_id}/scenarios/{scenario_id}", response_model=Scenario)
async def update_scenario(
    workspace_id: str,
    scenario_id: str,
    data: ScenarioUpdate,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Scenario:
    """
    Update a scenario.

    Allows updating name, description, and config_overrides.
    """
    scenario = storage.update_scenario(
        workspace_id,
        scenario_id,
        name=data.name,
        description=data.description,
        config_overrides=data.config_overrides,
    )
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found in workspace {workspace_id}",
        )
    return scenario


@router.delete("/{workspace_id}/scenarios/{scenario_id}")
async def delete_scenario(
    workspace_id: str,
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Dict[str, bool]:
    """
    Delete a scenario.

    WARNING: This deletes all simulation results for this scenario.
    """
    success = storage.delete_scenario(workspace_id, scenario_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found in workspace {workspace_id}",
        )
    return {"success": True}


@router.get("/{workspace_id}/scenarios/{scenario_id}/results/export")
async def export_scenario_results(
    workspace_id: str,
    scenario_id: str,
    format: str = "excel",
    storage: WorkspaceStorage = Depends(get_storage),
) -> FileResponse:
    """
    Export simulation results as Excel or CSV (workspace-scoped endpoint).

    E087: This endpoint eliminates ambiguity in multi-workspace environments
    by requiring the workspace_id, avoiding the need to search all workspaces.
    """
    # Verify workspace and scenario exist
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
            detail=f"Scenario {scenario_id} not found in workspace {workspace_id}",
        )

    # Determine file format
    if format == "excel":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        media_type = "text/csv"
        ext = "csv"

    # Get scenario path and look for results
    scenario_path = storage._scenario_path(workspace_id, scenario_id)
    results_dir = scenario_path / "results"

    # Try to find the results file (check multiple naming patterns)
    results_file = None
    if results_dir.exists():
        # First try: {scenario_name}_results.xlsx
        candidate = results_dir / f"{scenario.name}_results.{ext}"
        if candidate.exists():
            results_file = candidate
        else:
            # Second try: results.xlsx
            candidate = results_dir / f"results.{ext}"
            if candidate.exists():
                results_file = candidate
            else:
                # Third try: any *_results.xlsx file
                for f in results_dir.glob(f"*_results.{ext}"):
                    results_file = f
                    break

    if results_file and results_file.exists():
        return FileResponse(
            path=results_file,
            media_type=media_type,
            filename=f"{scenario.name}_results.{ext}",
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Export file not found for scenario {scenario_id}. Run the simulation first to generate results.",
    )
