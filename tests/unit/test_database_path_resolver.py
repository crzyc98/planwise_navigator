"""
Unit tests for DatabasePathResolver.

Feature: 005-database-path-resolver
Test coverage target: 95%+ (SC-006)
Performance target: <100ms for all unit tests (SC-003)
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

from planalign_api.services.database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
    IsolationMode,
    WorkspaceStorageProtocol,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def mock_storage():
    """Create a mock WorkspaceStorage that conforms to WorkspaceStorageProtocol."""
    storage = MagicMock(spec=WorkspaceStorageProtocol)
    return storage


@pytest.fixture
def temp_project_root(tmp_path):
    """Create a temporary project root with dbt directory."""
    dbt_dir = tmp_path / "dbt"
    dbt_dir.mkdir()
    return tmp_path


@pytest.fixture
def resolver_with_mock(mock_storage, temp_project_root):
    """Create a resolver with mock storage and temporary project root."""
    return DatabasePathResolver(
        storage=mock_storage,
        project_root=temp_project_root,
    )


# ==============================================================================
# T011: Unit test - scenario-level resolution
# ==============================================================================


@pytest.mark.fast
class TestScenarioLevelResolution:
    """Tests for scenario-level database resolution (highest priority in fallback chain)."""

    def test_scenario_db_exists_returns_scenario_path(self, mock_storage, tmp_path):
        """Given scenario db exists, resolver returns scenario path with source='scenario'."""
        # Setup: Create scenario directory with database
        scenario_path = tmp_path / "workspaces" / "ws1" / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        db_file = scenario_path / "simulation.duckdb"
        db_file.touch()

        # Configure mock
        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = tmp_path / "workspaces" / "ws1"

        # Create resolver
        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)

        # Execute
        result = resolver.resolve("ws1", "sc1")

        # Assert
        assert result.exists is True
        assert result.path == db_file
        assert result.source == "scenario"
        assert result.warning is None

    def test_scenario_db_not_found_falls_through(self, mock_storage, tmp_path):
        """Given scenario db does NOT exist, resolver continues to workspace level."""
        # Setup: Create scenario directory WITHOUT database
        scenario_path = tmp_path / "workspaces" / "ws1" / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        workspace_path = tmp_path / "workspaces" / "ws1"

        # Configure mock
        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = workspace_path

        # Create resolver
        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)

        # Execute
        result = resolver.resolve("ws1", "sc1")

        # Assert - should fall through to return None (no db at any level)
        assert result.exists is False
        assert result.source is None


# ==============================================================================
# T012: Unit test - workspace-level fallback
# ==============================================================================


@pytest.mark.fast
class TestWorkspaceLevelFallback:
    """Tests for workspace-level database fallback."""

    def test_workspace_db_exists_after_scenario_miss(self, mock_storage, tmp_path):
        """Given scenario db missing but workspace db exists, returns workspace path."""
        # Setup
        scenario_path = tmp_path / "workspaces" / "ws1" / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        workspace_path = tmp_path / "workspaces" / "ws1"
        workspace_db = workspace_path / "simulation.duckdb"
        workspace_db.touch()

        # Configure mock
        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = workspace_path

        # Create resolver
        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)

        # Execute
        result = resolver.resolve("ws1", "sc1")

        # Assert
        assert result.exists is True
        assert result.path == workspace_db
        assert result.source == "workspace"
        assert result.warning is None


# ==============================================================================
# T013: Unit test - project-level fallback with warning
# ==============================================================================


@pytest.mark.fast
class TestProjectLevelFallback:
    """Tests for project-level database fallback (SINGLE_TENANT mode only)."""

    def test_project_db_fallback_with_warning(self, mock_storage, tmp_path):
        """Given no scenario/workspace db, falls back to project db with warning."""
        # Setup: Create empty paths for scenario/workspace, project db exists
        scenario_path = tmp_path / "workspaces" / "ws1" / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        workspace_path = tmp_path / "workspaces" / "ws1"

        dbt_path = tmp_path / "dbt"
        dbt_path.mkdir()
        project_db = dbt_path / "simulation.duckdb"
        project_db.touch()

        # Configure mock
        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = workspace_path

        # Create resolver in SINGLE_TENANT mode (default)
        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)

        # Execute
        result = resolver.resolve("ws1", "sc1")

        # Assert
        assert result.exists is True
        assert result.path == project_db
        assert result.source == "project"
        assert result.warning is not None
        assert "global" in result.warning.lower() or "project" in result.warning.lower()


# ==============================================================================
# T014: Unit test - path traversal rejection
# ==============================================================================


@pytest.mark.fast
class TestPathTraversalRejection:
    """Tests for path traversal prevention (security)."""

    @pytest.mark.parametrize(
        "workspace_id,scenario_id",
        [
            ("../etc", "passwd"),  # Parent traversal
            ("workspace", "../../../etc/passwd"),  # Deep traversal
            ("workspace/nested", "scenario"),  # Path separator
            ("workspace\\nested", "scenario"),  # Windows path separator
            ("workspace", "scenario\x00evil"),  # Null byte
            ("..", "scenario"),  # Relative parent
            (".", "scenario"),  # Current directory
            (".hidden", "scenario"),  # Hidden file prefix
        ],
    )
    def test_path_traversal_rejected(
        self, mock_storage, tmp_path, workspace_id, scenario_id
    ):
        """Given path traversal characters, resolver returns None with warning."""
        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)

        result = resolver.resolve(workspace_id, scenario_id)

        assert result.exists is False
        assert result.path is None
        assert result.warning is not None
        assert "traversal" in result.warning.lower()

    def test_valid_identifiers_pass_validation(self, mock_storage, tmp_path):
        """Given valid identifiers, validation passes and resolution proceeds."""
        scenario_path = tmp_path / "workspaces" / "valid-ws" / "scenarios" / "valid-sc"
        scenario_path.mkdir(parents=True)
        db_file = scenario_path / "simulation.duckdb"
        db_file.touch()

        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = tmp_path / "workspaces" / "valid-ws"

        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)

        # Valid identifiers with allowed characters
        result = resolver.resolve("valid-ws-123", "valid-sc_456")

        # If mock returns a valid path, resolution should succeed
        assert result.exists is True


# ==============================================================================
# T015: Unit test - not found returns None
# ==============================================================================


@pytest.mark.fast
class TestNotFoundReturnsNone:
    """Tests for handling when no database is found at any level."""

    def test_no_database_at_any_level(self, mock_storage, tmp_path):
        """Given no database at scenario/workspace/project, returns None."""
        # Setup: Create directories but no database files
        scenario_path = tmp_path / "workspaces" / "ws1" / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        workspace_path = tmp_path / "workspaces" / "ws1"
        dbt_path = tmp_path / "dbt"
        dbt_path.mkdir()

        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = workspace_path

        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)

        result = resolver.resolve("ws1", "sc1")

        assert result.exists is False
        assert result.path is None
        assert result.source is None
        # No warning for "not found" - only for fallback to project

    def test_empty_workspace_id_rejected(self, mock_storage, tmp_path):
        """Given empty workspace_id, returns None with warning."""
        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)

        result = resolver.resolve("", "sc1")

        assert result.exists is False
        assert result.warning is not None

    def test_empty_scenario_id_rejected(self, mock_storage, tmp_path):
        """Given empty scenario_id, returns None with warning."""
        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)

        result = resolver.resolve("ws1", "")

        assert result.exists is False
        assert result.warning is not None


# ==============================================================================
# T023-T026: User Story 2 - Mock-based testing
# ==============================================================================


@pytest.mark.fast
class TestMockBasedResolution:
    """Tests using mock storage without real filesystem I/O."""

    def test_mock_storage_scenario_path(self, tmp_path):
        """Test resolver with mock storage returning scenario path."""
        mock_storage = MagicMock()

        # Create a temporary scenario db
        scenario_path = tmp_path / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        db_file = scenario_path / "simulation.duckdb"
        db_file.touch()

        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = tmp_path

        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)
        result = resolver.resolve("ws1", "sc1")

        assert result.source == "scenario"
        mock_storage._scenario_path.assert_called_once_with("ws1", "sc1")

    def test_mock_storage_workspace_fallback(self, tmp_path):
        """Test resolver with mock storage falling back to workspace."""
        mock_storage = MagicMock()

        # Setup: scenario path without db, workspace path with db
        scenario_path = tmp_path / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        workspace_db = workspace_path / "simulation.duckdb"
        workspace_db.touch()

        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = workspace_path

        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)
        result = resolver.resolve("ws1", "sc1")

        assert result.source == "workspace"
        mock_storage._workspace_path.assert_called_once_with("ws1")

    def test_mock_storage_project_fallback(self, tmp_path):
        """Test resolver with mock storage falling back to project."""
        mock_storage = MagicMock()

        # Setup: empty scenario/workspace paths, project db exists
        scenario_path = tmp_path / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        dbt_path = tmp_path / "dbt"
        dbt_path.mkdir()
        project_db = dbt_path / "simulation.duckdb"
        project_db.touch()

        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = workspace_path

        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)
        result = resolver.resolve("ws1", "sc1")

        assert result.source == "project"
        assert result.warning is not None

    def test_configurable_project_root(self, tmp_path):
        """Test resolver with custom project_root override."""
        mock_storage = MagicMock()

        # Create custom project root with dbt
        custom_root = tmp_path / "custom_project"
        dbt_path = custom_root / "dbt"
        dbt_path.mkdir(parents=True)
        project_db = dbt_path / "simulation.duckdb"
        project_db.touch()

        # Empty scenario/workspace paths
        mock_storage._scenario_path.return_value = tmp_path / "empty_scenario"
        mock_storage._workspace_path.return_value = tmp_path / "empty_workspace"
        (tmp_path / "empty_scenario").mkdir()
        (tmp_path / "empty_workspace").mkdir()

        resolver = DatabasePathResolver(
            storage=mock_storage, project_root=custom_root
        )
        result = resolver.resolve("ws1", "sc1")

        assert result.path == project_db
        assert result.source == "project"


# ==============================================================================
# T031-T033: User Story 3 - Multi-tenant isolation
# ==============================================================================


@pytest.mark.fast
class TestMultiTenantIsolation:
    """Tests for multi-tenant isolation mode."""

    def test_multi_tenant_stops_at_workspace_level(self, mock_storage, tmp_path):
        """Given MULTI_TENANT mode, resolver does NOT fall back to project."""
        # Setup: No scenario/workspace dbs, project db exists
        scenario_path = tmp_path / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        dbt_path = tmp_path / "dbt"
        dbt_path.mkdir()
        project_db = dbt_path / "simulation.duckdb"
        project_db.touch()

        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = workspace_path

        resolver = DatabasePathResolver(
            storage=mock_storage,
            project_root=tmp_path,
            isolation_mode=IsolationMode.MULTI_TENANT,
        )
        result = resolver.resolve("ws1", "sc1")

        # Should return None even though project db exists
        assert result.exists is False
        assert result.path is None
        assert result.source is None

    def test_single_tenant_allows_project_fallback(self, mock_storage, tmp_path):
        """Given SINGLE_TENANT mode (default), resolver falls back to project."""
        # Setup: No scenario/workspace dbs, project db exists
        scenario_path = tmp_path / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        dbt_path = tmp_path / "dbt"
        dbt_path.mkdir()
        project_db = dbt_path / "simulation.duckdb"
        project_db.touch()

        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = workspace_path

        resolver = DatabasePathResolver(
            storage=mock_storage,
            project_root=tmp_path,
            isolation_mode=IsolationMode.SINGLE_TENANT,
        )
        result = resolver.resolve("ws1", "sc1")

        assert result.exists is True
        assert result.source == "project"

    def test_isolation_mode_enum_values(self):
        """Test IsolationMode enum has expected values."""
        assert IsolationMode.SINGLE_TENANT.value == "single-tenant"
        assert IsolationMode.MULTI_TENANT.value == "multi-tenant"

    def test_default_isolation_mode_is_single_tenant(self, mock_storage, tmp_path):
        """Test default isolation mode is SINGLE_TENANT."""
        resolver = DatabasePathResolver(storage=mock_storage, project_root=tmp_path)
        assert resolver._isolation_mode == IsolationMode.SINGLE_TENANT


# ==============================================================================
# Additional edge case tests
# ==============================================================================


@pytest.mark.fast
class TestEdgeCases:
    """Additional edge case tests for comprehensive coverage."""

    def test_resolved_database_path_exists_property(self):
        """Test ResolvedDatabasePath.exists property."""
        with_path = ResolvedDatabasePath(path=Path("/some/path"), source="scenario")
        without_path = ResolvedDatabasePath(path=None, source=None)

        assert with_path.exists is True
        assert without_path.exists is False

    def test_resolved_database_path_is_immutable(self):
        """Test ResolvedDatabasePath is frozen (immutable)."""
        result = ResolvedDatabasePath(path=Path("/test"), source="scenario")

        with pytest.raises(Exception):  # ValidationError in Pydantic
            result.path = Path("/different")

    def test_custom_database_filename(self, mock_storage, tmp_path):
        """Test resolver with custom database filename."""
        scenario_path = tmp_path / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        custom_db = scenario_path / "custom.duckdb"
        custom_db.touch()

        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = tmp_path

        resolver = DatabasePathResolver(
            storage=mock_storage,
            project_root=tmp_path,
            database_filename="custom.duckdb",
        )
        result = resolver.resolve("ws1", "sc1")

        assert result.exists is True
        assert result.path == custom_db
