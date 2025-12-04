"""
Tests for the SyncService (E083 - Workspace Cloud Synchronization).

These tests verify the Git-based workspace synchronization functionality.
"""

from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Check if GitPython is available
try:
    import git
    from git import Repo
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    git = None
    Repo = None


# Skip all tests if GitPython is not installed
pytestmark = pytest.mark.skipif(
    not GIT_AVAILABLE,
    reason="GitPython is required for sync tests"
)


@pytest.fixture
def temp_workspaces_dir():
    """Create a temporary directory for workspaces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_workspace(temp_workspaces_dir):
    """Create a sample workspace structure."""
    workspace_id = "test-workspace-123"
    workspace_dir = temp_workspaces_dir / workspace_id
    workspace_dir.mkdir(parents=True)

    # Create workspace.json
    workspace_json = workspace_dir / "workspace.json"
    workspace_json.write_text(json.dumps({
        "id": workspace_id,
        "name": "Test Workspace",
        "description": "A test workspace",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }))

    # Create base_config.yaml
    base_config = workspace_dir / "base_config.yaml"
    base_config.write_text("simulation:\n  years: [2025, 2026]\n")

    # Create scenarios directory with a scenario
    scenarios_dir = workspace_dir / "scenarios"
    scenarios_dir.mkdir()

    scenario_id = "test-scenario-456"
    scenario_dir = scenarios_dir / scenario_id
    scenario_dir.mkdir()

    scenario_json = scenario_dir / "scenario.json"
    scenario_json.write_text(json.dumps({
        "id": scenario_id,
        "workspace_id": workspace_id,
        "name": "Test Scenario",
        "created_at": datetime.utcnow().isoformat(),
    }))

    return workspace_dir


@pytest.fixture
def sync_service(temp_workspaces_dir):
    """Create a SyncService with a temporary workspaces directory."""
    from planalign_api.services.sync_service import SyncService
    return SyncService(workspaces_root=temp_workspaces_dir)


class TestSyncModels:
    """Test sync model creation and validation."""

    def test_sync_config_defaults(self):
        """Test SyncConfig default values."""
        from planalign_api.models.sync import SyncConfig

        config = SyncConfig()
        assert config.version == 1
        assert config.enabled is False
        assert config.remote is None
        assert config.branch == "main"
        assert config.auto_sync is False
        assert config.conflict_strategy == "last-write-wins"

    def test_sync_config_custom_values(self):
        """Test SyncConfig with custom values."""
        from planalign_api.models.sync import SyncConfig

        config = SyncConfig(
            enabled=True,
            remote="git@github.com:user/repo.git",
            branch="develop",
            auto_sync=True,
            conflict_strategy="keep-local",
        )
        assert config.enabled is True
        assert config.remote == "git@github.com:user/repo.git"
        assert config.branch == "develop"
        assert config.auto_sync is True
        assert config.conflict_strategy == "keep-local"

    def test_sync_status_model(self):
        """Test SyncStatus model."""
        from planalign_api.models.sync import SyncStatus

        status = SyncStatus(
            is_initialized=True,
            remote_url="git@github.com:user/repo.git",
            branch="main",
            local_changes=5,
            ahead=2,
            behind=1,
        )
        assert status.is_initialized is True
        assert status.local_changes == 5
        assert status.ahead == 2
        assert status.behind == 1

    def test_sync_log_entry_model(self):
        """Test SyncLogEntry model."""
        from planalign_api.models.sync import SyncLogEntry

        entry = SyncLogEntry(
            timestamp=datetime.utcnow(),
            operation="push",
            workspaces_affected=3,
            scenarios_affected=10,
            message="Pushed changes",
            commit_sha="abc1234",
        )
        assert entry.operation == "push"
        assert entry.workspaces_affected == 3
        assert entry.success is True

    def test_sync_push_result_model(self):
        """Test SyncPushResult model."""
        from planalign_api.models.sync import SyncPushResult

        result = SyncPushResult(
            success=True,
            commit_sha="abc1234",
            files_pushed=15,
            message="Push successful",
        )
        assert result.success is True
        assert result.files_pushed == 15

    def test_sync_pull_result_model(self):
        """Test SyncPullResult model."""
        from planalign_api.models.sync import SyncPullResult

        result = SyncPullResult(
            success=True,
            files_updated=5,
            files_added=3,
            files_removed=1,
            message="Pull successful",
        )
        assert result.success is True
        assert result.files_updated == 5
        assert len(result.conflicts) == 0


class TestSyncServiceInitialization:
    """Test SyncService initialization."""

    def test_service_creation(self, sync_service, temp_workspaces_dir):
        """Test SyncService can be created."""
        assert sync_service.workspaces_root == temp_workspaces_dir
        assert sync_service.workspaces_root.exists()

    def test_not_initialized_by_default(self, sync_service):
        """Test sync is not initialized by default."""
        assert sync_service.is_initialized() is False

    def test_get_status_not_initialized(self, sync_service):
        """Test getting status when not initialized."""
        status = sync_service.get_status()
        assert status.is_initialized is False
        assert status.remote_url is None


class TestSyncServiceConfig:
    """Test sync configuration management."""

    def test_get_default_config(self, sync_service):
        """Test getting default config when none exists."""
        config = sync_service.get_sync_config()
        assert config.enabled is False
        assert config.remote is None

    def test_save_and_load_config(self, sync_service):
        """Test saving and loading sync config."""
        from planalign_api.models.sync import SyncConfig

        config = SyncConfig(
            enabled=True,
            remote="git@github.com:user/repo.git",
            branch="develop",
        )
        sync_service.save_sync_config(config)

        loaded = sync_service.get_sync_config()
        assert loaded.enabled is True
        assert loaded.remote == "git@github.com:user/repo.git"
        assert loaded.branch == "develop"


class TestSyncServiceOperations:
    """Test sync operations (init, push, pull)."""

    def test_init_creates_git_repo(self, sync_service, temp_workspaces_dir):
        """Test that init creates a Git repository."""
        # Mock the remote operations
        with patch.object(sync_service, '_create_initial_commit') as mock_commit:
            # Init will fail on remote operations, but should create local repo
            try:
                sync_service.init(
                    remote_url="git@github.com:user/test-repo.git",
                    branch="main",
                )
            except Exception:
                pass  # Expected to fail on remote operations

            # Check if git repo was created
            git_dir = temp_workspaces_dir / ".git"
            # The repo should have been initialized
            assert sync_service.repo is not None or git_dir.exists()

    def test_push_without_init_fails(self, sync_service):
        """Test that push fails when sync is not initialized."""
        result = sync_service.push()
        assert result.success is False
        assert "not initialized" in result.message.lower()

    def test_pull_without_init_fails(self, sync_service):
        """Test that pull fails when sync is not initialized."""
        result = sync_service.pull()
        assert result.success is False
        assert "not initialized" in result.message.lower()


class TestSyncServiceLogging:
    """Test sync operation logging."""

    def test_log_operation(self, sync_service):
        """Test logging a sync operation."""
        sync_service._log_operation(
            operation="push",
            message="Test push",
            workspaces_affected=2,
            scenarios_affected=5,
            commit_sha="abc1234",
        )

        logs = sync_service.get_sync_log(limit=10)
        assert len(logs) == 1
        assert logs[0].operation == "push"
        assert logs[0].message == "Test push"
        assert logs[0].workspaces_affected == 2

    def test_log_limit(self, sync_service):
        """Test log limit is respected."""
        # Create 10 log entries
        for i in range(10):
            sync_service._log_operation(
                operation="push",
                message=f"Push {i}",
            )

        logs = sync_service.get_sync_log(limit=5)
        assert len(logs) == 5

    def test_empty_log(self, sync_service):
        """Test getting empty log."""
        logs = sync_service.get_sync_log()
        assert len(logs) == 0


class TestSyncServiceWorkspaceInfo:
    """Test workspace sync information."""

    def test_get_workspace_info_empty(self, sync_service):
        """Test getting workspace info when no workspaces exist."""
        infos = sync_service.get_workspace_sync_info()
        assert len(infos) == 0

    def test_get_workspace_info_with_workspace(self, sync_service, sample_workspace):
        """Test getting workspace info with a sample workspace."""
        infos = sync_service.get_workspace_sync_info()
        assert len(infos) == 1
        assert infos[0].workspace_name == "Test Workspace"
        assert infos[0].scenario_count == 1

    def test_count_content(self, sync_service, sample_workspace):
        """Test counting workspaces and scenarios."""
        workspaces, scenarios = sync_service._count_content()
        assert workspaces == 1
        assert scenarios == 1


class TestGitignoreTemplate:
    """Test .gitignore template."""

    def test_gitignore_excludes_duckdb(self):
        """Test .gitignore template excludes DuckDB files."""
        from planalign_api.services.sync_service import GITIGNORE_TEMPLATE

        assert "*.duckdb" in GITIGNORE_TEMPLATE

    def test_gitignore_excludes_xlsx(self):
        """Test .gitignore template excludes Excel files."""
        from planalign_api.services.sync_service import GITIGNORE_TEMPLATE

        assert "*.xlsx" in GITIGNORE_TEMPLATE

    def test_gitignore_keeps_json(self):
        """Test .gitignore template keeps JSON files."""
        from planalign_api.services.sync_service import GITIGNORE_TEMPLATE

        # The template should have negation patterns for JSON
        assert "!**/workspace.json" in GITIGNORE_TEMPLATE
        assert "!**/scenario.json" in GITIGNORE_TEMPLATE


class TestSyncExceptions:
    """Test sync exception classes."""

    def test_sync_error(self):
        """Test SyncError exception."""
        from planalign_api.services.sync_service import SyncError

        error = SyncError("Test error")
        assert str(error) == "Test error"

    def test_sync_auth_error(self):
        """Test SyncAuthError exception."""
        from planalign_api.services.sync_service import SyncAuthError

        error = SyncAuthError("Auth failed")
        assert str(error) == "Auth failed"
        assert isinstance(error, Exception)

    def test_sync_conflict_error(self):
        """Test SyncConflictError exception."""
        from planalign_api.services.sync_service import SyncConflictError

        error = SyncConflictError("Conflict detected", ["file1.json", "file2.yaml"])
        assert "Conflict detected" in str(error)
        assert error.conflicting_files == ["file1.json", "file2.yaml"]


@pytest.mark.fast
class TestSyncModelsValidation:
    """Fast unit tests for sync model validation."""

    def test_sync_config_conflict_strategy_validation(self):
        """Test that invalid conflict strategies are rejected."""
        from planalign_api.models.sync import SyncConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SyncConfig(conflict_strategy="invalid-strategy")

    def test_sync_log_entry_operation_validation(self):
        """Test that invalid operations are rejected."""
        from planalign_api.models.sync import SyncLogEntry
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SyncLogEntry(
                timestamp=datetime.utcnow(),
                operation="invalid-op",
                message="Test",
            )
