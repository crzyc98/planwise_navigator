"""Workspace service - thin wrapper around storage."""

from typing import Any, Dict, List, Optional

from ..models.workspace import Workspace, WorkspaceCreate, WorkspaceUpdate
from ..storage.workspace_storage import WorkspaceStorage


class WorkspaceService:
    """Service for workspace operations."""

    def __init__(self, storage: WorkspaceStorage):
        self.storage = storage

    def list_workspaces(self) -> List[Workspace]:
        """List all workspaces."""
        return self.storage.list_workspaces()

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get a workspace by ID."""
        return self.storage.get_workspace(workspace_id)

    def create_workspace(self, data: WorkspaceCreate) -> Workspace:
        """Create a new workspace."""
        return self.storage.create_workspace(data)

    def update_workspace(
        self, workspace_id: str, data: WorkspaceUpdate
    ) -> Optional[Workspace]:
        """Update an existing workspace."""
        return self.storage.update_workspace(workspace_id, data)

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
        return self.storage.update_workspace(
            workspace_id,
            WorkspaceUpdate(base_config=config)
        )
