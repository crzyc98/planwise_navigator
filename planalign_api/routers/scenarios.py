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
from ..services.seed_config_validator import validate_seed_configs
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
    Validates seed config sections (promotion_hazard, age_bands, tenure_bands)
    atomically — if any section is invalid, the entire update is rejected.
    """
    # Validate seed config sections in config_overrides if present
    if data.config_overrides:
        errors = validate_seed_configs(data.config_overrides)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Validation failed",
                    "errors": [
                        {"section": e.section, "field": e.field, "message": e.message}
                        for e in errors
                    ],
                },
            )

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

    # Helper function to find results file in a directory
    def find_results_file(search_dir: Path) -> Path | None:
        if not search_dir.exists():
            return None
        # First try: {scenario_name}_results.xlsx
        candidate = search_dir / f"{scenario.name}_results.{ext}"
        if candidate.exists():
            return candidate
        # Second try: results.xlsx
        candidate = search_dir / f"results.{ext}"
        if candidate.exists():
            return candidate
        # Third try: any *_results.xlsx file
        for f in search_dir.glob(f"*_results.{ext}"):
            return f
        return None

    results_file = None

    # Check 1: Look in legacy results/ directory
    results_file = find_results_file(scenario_path / "results")

    # Check 2: Look in most recent run directory (runs/{run_id}/)
    if not results_file:
        runs_dir = scenario_path / "runs"
        if runs_dir.exists():
            # Get most recent run directory by modification time
            run_dirs = sorted(
                [d for d in runs_dir.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            for run_dir in run_dirs:
                results_file = find_results_file(run_dir)
                if results_file:
                    break

    if results_file and results_file.exists():
        # Build descriptive filename: {workspace}_{scenario}_results_{date}.xlsx
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        # Sanitize names for filename (replace spaces with underscores)
        ws_name = workspace.name.replace(" ", "_")
        sc_name = scenario.name.replace(" ", "_")
        download_filename = f"{ws_name}_{sc_name}_results_{date_str}.{ext}"
        return FileResponse(
            path=results_file,
            media_type=media_type,
            filename=download_filename,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Export file not found for scenario {scenario_id}. Run the simulation first to generate results.",
    )
