"""Workspace service - thin wrapper around storage."""

from typing import Any, Dict, List, Optional

from ..models.workspace import (
    Workspace,
    WorkspaceCreate,
    WorkspaceSummary,
    WorkspaceUpdate,
)
from ..storage.workspace_storage import WorkspaceStorage

# Built-in defaults mirroring routers/workspaces.py:get_default_config, used when
# no default_config is supplied to create_workspace().
_BUILTIN_DEFAULT_CONFIG: Dict[str, Any] = {
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
    "employer_match": {
        "active_formula": "simple_match",
        "formulas": {
            "simple_match": {
                "name": "Simple Match",
                "type": "simple",
                "match_rate": 0.50,
                "max_match_percentage": 0.06,
            },
        },
        "tenure_match_tiers": [],
        "points_match_tiers": [],
        "tenure_graded_bands": [],
    },
    "employer_core_contribution": {
        "enabled": True,
        "status": "flat",
        "contribution_rate": 0.03,
    },
}


class WorkspaceService:
    """Service for workspace operations."""

    def __init__(self, storage: WorkspaceStorage):
        self.storage = storage

    def list_workspaces(self) -> List[WorkspaceSummary]:
        """List all workspaces."""
        return self.storage.list_workspaces()

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get a workspace by ID."""
        return self.storage.get_workspace(workspace_id)

    def create_workspace(
        self, data: WorkspaceCreate, default_config: Optional[Dict[str, Any]] = None
    ) -> Workspace:
        """Create a new workspace."""
        return self.storage.create_workspace(
            data, default_config or _BUILTIN_DEFAULT_CONFIG
        )

    def update_workspace(
        self, workspace_id: str, data: WorkspaceUpdate
    ) -> Optional[Workspace]:
        """Update an existing workspace."""
        return self.storage.update_workspace(
            workspace_id,
            name=data.name,
            description=data.description,
            base_config=data.base_config,
        )

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace and all its scenarios."""
        return self.storage.delete_workspace(workspace_id)

    def get_base_config(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get base configuration for a workspace."""
        workspace = self.storage.get_workspace(workspace_id)
        if workspace:
            return workspace.base_config
        return None

    def update_base_config(
        self, workspace_id: str, config: Dict[str, Any]
    ) -> Optional[Workspace]:
        """Update base configuration for a workspace."""
        return self.storage.update_workspace(workspace_id, base_config=config)
