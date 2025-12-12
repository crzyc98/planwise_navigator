"""
Mock WorkspaceStorage for testing DatabasePathResolver.

Feature: 005-database-path-resolver
"""

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

from planalign_api.services.database_path_resolver import WorkspaceStorageProtocol


class MockWorkspaceStorage:
    """
    Mock implementation of WorkspaceStorage for testing.

    Allows full control over returned paths without filesystem access.
    """

    def __init__(
        self,
        workspaces_root: Optional[Path] = None,
        workspace_path_override: Optional[Path] = None,
        scenario_path_override: Optional[Path] = None,
    ):
        """
        Initialize mock storage.

        Args:
            workspaces_root: Base path for workspaces (default: /tmp/workspaces)
            workspace_path_override: If set, _workspace_path always returns this
            scenario_path_override: If set, _scenario_path always returns this
        """
        self.workspaces_root = workspaces_root or Path("/tmp/workspaces")
        self._workspace_path_override = workspace_path_override
        self._scenario_path_override = scenario_path_override

    def _workspace_path(self, workspace_id: str) -> Path:
        """Get workspace directory path."""
        if self._workspace_path_override:
            return self._workspace_path_override
        return self.workspaces_root / workspace_id

    def _scenario_path(self, workspace_id: str, scenario_id: str) -> Path:
        """Get scenario directory path."""
        if self._scenario_path_override:
            return self._scenario_path_override
        return self._workspace_path(workspace_id) / "scenarios" / scenario_id


def create_mock_storage(**kwargs) -> MagicMock:
    """
    Create a MagicMock that conforms to WorkspaceStorageProtocol.

    This is useful for tests that need to verify method calls.

    Usage:
        mock_storage = create_mock_storage()
        mock_storage._scenario_path.return_value = Path("/custom/path")
        resolver = DatabasePathResolver(mock_storage)
    """
    mock = MagicMock(spec=WorkspaceStorageProtocol)
    return mock
