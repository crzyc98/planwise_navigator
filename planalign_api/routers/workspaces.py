"""Workspace management endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import APISettings, get_settings
from ..models.workspace import (
    Workspace,
    WorkspaceCreate,
    WorkspaceSummary,
    WorkspaceUpdate,
)
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


async def get_default_config(
    settings: APISettings = Depends(get_settings),
) -> Dict[str, Any]:
    """Get default configuration for new workspaces."""
    import yaml

    if settings.default_config_path.exists():
        with open(settings.default_config_path) as f:
            return yaml.safe_load(f)

    # Built-in defaults
    return {
        "simulation": {
            "start_year": 2025,
            "end_year": 2027,
            "random_seed": 42,
            "target_growth_rate": 0.03,
        },
        "compensation": {
            "cola_rate": 0.02,
            "merit_budget": 0.035,
        },
        "workforce": {
            "total_termination_rate": 0.12,
        },
        "enrollment": {
            "auto_enrollment": {"enabled": True},
        },
    }


@router.get("", response_model=List[WorkspaceSummary])
async def list_workspaces(
    storage: WorkspaceStorage = Depends(get_storage),
) -> List[WorkspaceSummary]:
    """
    List all workspaces.

    Returns summary information for each workspace including scenario count
    and storage usage.
    """
    return storage.list_workspaces()


@router.post("", response_model=Workspace, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    data: WorkspaceCreate,
    storage: WorkspaceStorage = Depends(get_storage),
    default_config: Dict[str, Any] = Depends(get_default_config),
) -> Workspace:
    """
    Create a new workspace.

    If no base_config is provided, uses the system default configuration.
    """
    return storage.create_workspace(data, default_config)


@router.get("/{workspace_id}", response_model=Workspace)
async def get_workspace(
    workspace_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Workspace:
    """
    Get a workspace by ID.

    Returns the full workspace including base configuration.
    """
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return workspace


@router.put("/{workspace_id}", response_model=Workspace)
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdate,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Workspace:
    """
    Update a workspace.

    Allows updating name, description, and base configuration.
    """
    workspace = storage.update_workspace(
        workspace_id,
        name=data.name,
        description=data.description,
        base_config=data.base_config,
    )
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return workspace


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Dict[str, bool]:
    """
    Delete a workspace.

    WARNING: This deletes all scenarios and results in the workspace.
    """
    success = storage.delete_workspace(workspace_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return {"success": True}
