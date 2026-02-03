"""Unit tests for ExportService.

Feature: 031-workspace-export
Tests: T011 (manifest generation), T012 (archive creation), T035 (bulk export)
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from planalign_api.models.export import (
    BulkOperationStatus,
    ExportManifest,
    ExportStatus,
    ManifestContents,
)
from planalign_api.models.workspace import Workspace, WorkspaceSummary
from planalign_api.services.export_service import ExportService, MANIFEST_VERSION


@pytest.fixture
def mock_storage():
    """Create a mock WorkspaceStorage."""
    storage = MagicMock()
    storage.list_workspaces.return_value = []
    return storage


@pytest.fixture
def export_service(mock_storage):
    """Create ExportService with mock storage."""
    return ExportService(mock_storage)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_path = Path(temp_dir)

        # Create workspace.json
        workspace_data = {
            "id": "test-workspace-123",
            "name": "Test Workspace",
            "description": "A test workspace",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-15T12:00:00",
        }
        with open(workspace_path / "workspace.json", "w") as f:
            json.dump(workspace_data, f)

        # Create scenarios directory with a scenario
        scenarios_path = workspace_path / "scenarios"
        scenarios_path.mkdir()

        scenario_path = scenarios_path / "scenario-1"
        scenario_path.mkdir()

        scenario_data = {
            "id": "scenario-1",
            "workspace_id": "test-workspace-123",
            "name": "Baseline Scenario",
            "status": "completed",
            "created_at": "2025-01-02T00:00:00",
        }
        with open(scenario_path / "scenario.json", "w") as f:
            json.dump(scenario_data, f)

        # Create a test file in the scenario
        (scenario_path / "simulation.duckdb").write_bytes(b"test database content")

        yield workspace_path


class TestManifestGeneration:
    """T011: Unit test for manifest generation."""

    def test_create_manifest_basic(self, export_service, temp_workspace):
        """Test basic manifest creation."""
        manifest = export_service.create_manifest(
            workspace_id="test-workspace-123",
            workspace_name="Test Workspace",
            workspace_path=temp_workspace,
        )

        assert manifest.workspace_id == "test-workspace-123"
        assert manifest.workspace_name == "Test Workspace"
        assert manifest.version == MANIFEST_VERSION
        assert isinstance(manifest.export_date, datetime)
        assert manifest.contents.scenario_count == 1
        assert "Baseline Scenario" in manifest.contents.scenarios

    def test_create_manifest_file_inventory(self, export_service, temp_workspace):
        """Test manifest includes correct file inventory."""
        manifest = export_service.create_manifest(
            workspace_id="test-workspace-123",
            workspace_name="Test Workspace",
            workspace_path=temp_workspace,
        )

        # Should count workspace.json, scenario.json, and simulation.duckdb
        assert manifest.contents.file_count >= 3
        assert manifest.contents.total_size_bytes > 0

    def test_create_manifest_checksum(self, export_service, temp_workspace):
        """Test manifest includes SHA256 checksum of workspace.json."""
        manifest = export_service.create_manifest(
            workspace_id="test-workspace-123",
            workspace_name="Test Workspace",
            workspace_path=temp_workspace,
        )

        # Checksum should be 64 character hex string
        assert len(manifest.contents.checksum_sha256) == 64
        assert all(c in "0123456789abcdef" for c in manifest.contents.checksum_sha256)

    def test_create_manifest_empty_workspace(self, export_service):
        """Test manifest creation for workspace with no scenarios."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir)

            # Create minimal workspace.json
            workspace_data = {"id": "empty-ws", "name": "Empty"}
            with open(workspace_path / "workspace.json", "w") as f:
                json.dump(workspace_data, f)

            manifest = export_service.create_manifest(
                workspace_id="empty-ws",
                workspace_name="Empty",
                workspace_path=workspace_path,
            )

            assert manifest.contents.scenario_count == 0
            assert manifest.contents.scenarios == []


class TestArchiveCreation:
    """T012: Unit test for archive creation."""

    def test_create_archive_basic(self, export_service, temp_workspace):
        """Test basic archive creation."""
        manifest = export_service.create_manifest(
            workspace_id="test-workspace-123",
            workspace_name="Test Workspace",
            workspace_path=temp_workspace,
        )

        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "test_export.7z"

            size = export_service.create_archive(
                workspace_path=temp_workspace,
                manifest=manifest,
                output_path=output_path,
            )

            assert output_path.exists()
            assert size > 0
            assert output_path.stat().st_size == size

    def test_create_archive_contains_manifest(self, export_service, temp_workspace):
        """Test archive contains manifest.json."""
        import py7zr

        manifest = export_service.create_manifest(
            workspace_id="test-workspace-123",
            workspace_name="Test Workspace",
            workspace_path=temp_workspace,
        )

        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "test_export.7z"

            export_service.create_archive(
                workspace_path=temp_workspace,
                manifest=manifest,
                output_path=output_path,
            )

            # Extract and verify manifest
            extract_dir = Path(output_dir) / "extracted"
            extract_dir.mkdir()

            with py7zr.SevenZipFile(output_path, "r") as archive:
                archive.extractall(path=extract_dir)

            manifest_path = extract_dir / "manifest.json"
            assert manifest_path.exists()

            with open(manifest_path) as f:
                extracted_manifest = json.load(f)

            assert extracted_manifest["workspace_id"] == "test-workspace-123"

    def test_create_archive_contains_workspace_files(self, export_service, temp_workspace):
        """Test archive contains all workspace files."""
        import py7zr

        manifest = export_service.create_manifest(
            workspace_id="test-workspace-123",
            workspace_name="Test Workspace",
            workspace_path=temp_workspace,
        )

        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "test_export.7z"

            export_service.create_archive(
                workspace_path=temp_workspace,
                manifest=manifest,
                output_path=output_path,
            )

            # Extract and verify contents
            extract_dir = Path(output_dir) / "extracted"
            extract_dir.mkdir()

            with py7zr.SevenZipFile(output_path, "r") as archive:
                archive.extractall(path=extract_dir)

            assert (extract_dir / "workspace.json").exists()
            assert (extract_dir / "scenarios" / "scenario-1" / "scenario.json").exists()


class TestExportWorkspace:
    """Tests for export_workspace method."""

    def test_export_workspace_success(self, export_service, mock_storage, temp_workspace):
        """Test successful workspace export."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = "test-workspace-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.storage_path = str(temp_workspace)

        mock_storage.get_workspace.return_value = mock_workspace
        mock_storage.is_simulation_running.return_value = False

        with tempfile.TemporaryDirectory() as output_dir:
            archive_path, result = export_service.export_workspace(
                workspace_id="test-workspace-123",
                output_dir=Path(output_dir),
            )

            assert result.status == ExportStatus.SUCCESS
            assert result.workspace_id == "test-workspace-123"
            assert result.workspace_name == "Test Workspace"
            assert result.size_bytes > 0
            assert archive_path.exists()
            assert archive_path.suffix == ".7z"

    def test_export_workspace_not_found(self, export_service, mock_storage):
        """Test export fails for non-existent workspace."""
        mock_storage.get_workspace.return_value = None

        with pytest.raises(ValueError, match="Workspace not found"):
            export_service.export_workspace(workspace_id="nonexistent")

    def test_export_workspace_simulation_running(self, export_service, mock_storage, temp_workspace):
        """Test export fails when simulation is running."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = "test-workspace-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.storage_path = str(temp_workspace)

        mock_storage.get_workspace.return_value = mock_workspace
        mock_storage.is_simulation_running.return_value = True

        with pytest.raises(ValueError, match="simulation is running"):
            export_service.export_workspace(workspace_id="test-workspace-123")

    def test_export_workspace_filename_format(self, export_service, mock_storage, temp_workspace):
        """Test exported file has correct naming format."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = "test-workspace-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.storage_path = str(temp_workspace)

        mock_storage.get_workspace.return_value = mock_workspace
        mock_storage.is_simulation_running.return_value = False

        with tempfile.TemporaryDirectory() as output_dir:
            archive_path, result = export_service.export_workspace(
                workspace_id="test-workspace-123",
                output_dir=Path(output_dir),
            )

            # Filename should be: SafeName_YYYYMMDD_HHMMSS.7z
            filename = archive_path.name
            assert filename.startswith("Test_Workspace_")
            assert filename.endswith(".7z")
            # Check timestamp portion (YYYYMMDD_HHMMSS)
            timestamp_part = filename.replace("Test_Workspace_", "").replace(".7z", "")
            assert len(timestamp_part) == 15  # YYYYMMDD_HHMMSS


class TestBulkExport:
    """T035: Unit test for bulk export operation."""

    def test_start_bulk_export(self, export_service):
        """Test starting bulk export creates operation status."""
        workspace_ids = ["ws-1", "ws-2", "ws-3"]

        status = export_service.start_bulk_export(workspace_ids)

        assert status.operation_id
        assert status.status == BulkOperationStatus.PENDING
        assert status.total == 3
        assert status.completed == 0
        assert status.results == []

    def test_get_bulk_export_status(self, export_service):
        """Test retrieving bulk export status."""
        workspace_ids = ["ws-1", "ws-2"]
        started = export_service.start_bulk_export(workspace_ids)

        retrieved = export_service.get_bulk_export_status(started.operation_id)

        assert retrieved is not None
        assert retrieved.operation_id == started.operation_id
        assert retrieved.total == 2

    def test_get_bulk_export_status_not_found(self, export_service):
        """Test retrieving non-existent operation returns None."""
        status = export_service.get_bulk_export_status("nonexistent-id")
        assert status is None

    def test_execute_bulk_export(self, export_service, mock_storage, temp_workspace):
        """Test executing bulk export processes all workspaces."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = "test-workspace-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.storage_path = str(temp_workspace)

        mock_storage.get_workspace.return_value = mock_workspace
        mock_storage.is_simulation_running.return_value = False

        workspace_ids = ["test-workspace-123"]
        started = export_service.start_bulk_export(workspace_ids)

        result = export_service.execute_bulk_export(started.operation_id, workspace_ids)

        assert result.status == BulkOperationStatus.COMPLETED
        assert result.completed == 1
        assert len(result.results) == 1
        assert result.results[0].status == ExportStatus.SUCCESS

    def test_cleanup_bulk_export(self, export_service, mock_storage, temp_workspace):
        """Test cleaning up bulk export removes temporary files."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = "test-workspace-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.storage_path = str(temp_workspace)

        mock_storage.get_workspace.return_value = mock_workspace
        mock_storage.is_simulation_running.return_value = False

        workspace_ids = ["test-workspace-123"]
        started = export_service.start_bulk_export(workspace_ids)
        export_service.execute_bulk_export(started.operation_id, workspace_ids)

        # Get archive path before cleanup
        archive_path = export_service.get_export_archive_path(
            started.operation_id, "test-workspace-123"
        )
        assert archive_path is not None
        assert archive_path.exists()

        # Cleanup
        export_service.cleanup_bulk_export(started.operation_id)

        # Status should be gone
        assert export_service.get_bulk_export_status(started.operation_id) is None
        # File should be deleted
        assert not archive_path.exists()
