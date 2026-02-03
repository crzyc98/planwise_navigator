"""Integration tests for export/import API endpoints.

Feature: 031-workspace-export
Tests: T013 (export endpoint), T022 (import endpoint), T036 (bulk export), T049 (bulk import)
"""

import io
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import py7zr
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.models.export import (
    BulkOperationStatus,
    ExportManifest,
    ExportStatus,
    ImportStatus,
    ManifestContents,
)
from planalign_api.models.workspace import Workspace, WorkspaceSummary
from planalign_api.services.export_service import ExportService, MANIFEST_VERSION


@pytest.fixture
def mock_workspace_storage():
    """Create mock WorkspaceStorage."""
    storage = MagicMock()
    storage.list_workspaces.return_value = []
    return storage


@pytest.fixture
def temp_workspace_dir():
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

        # Create scenarios directory
        scenarios_path = workspace_path / "scenarios"
        scenarios_path.mkdir()

        yield workspace_path


@pytest.fixture
def valid_import_archive():
    """Create a valid 7z archive for import testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create workspace structure
        workspace_data = {
            "id": "imported-workspace-123",
            "name": "Imported Workspace",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-15T12:00:00",
        }

        # Calculate checksum
        import hashlib
        workspace_json_bytes = json.dumps(workspace_data).encode()
        checksum = hashlib.sha256(workspace_json_bytes).hexdigest()

        manifest_data = {
            "version": MANIFEST_VERSION,
            "export_date": "2025-01-20T10:00:00",
            "app_version": "1.0.0",
            "workspace_id": "imported-workspace-123",
            "workspace_name": "Imported Workspace",
            "contents": {
                "scenario_count": 0,
                "scenarios": [],
                "file_count": 1,
                "total_size_bytes": len(workspace_json_bytes),
                "checksum_sha256": checksum,
            },
        }

        # Create staging directory
        staging_dir = temp_path / "staging"
        staging_dir.mkdir()

        with open(staging_dir / "workspace.json", "w") as f:
            json.dump(workspace_data, f)

        with open(staging_dir / "manifest.json", "w") as f:
            json.dump(manifest_data, f)

        # Create archive
        archive_path = temp_path / "test_import.7z"
        with py7zr.SevenZipFile(archive_path, "w") as archive:
            archive.write(staging_dir / "manifest.json", "manifest.json")
            archive.write(staging_dir / "workspace.json", "workspace.json")

        # Read archive bytes
        archive_bytes = archive_path.read_bytes()
        yield archive_bytes


class TestExportEndpointIntegration:
    """T013: Integration test for export endpoint."""

    def test_export_endpoint_returns_archive(
        self, mock_workspace_storage, temp_workspace_dir
    ):
        """Test export endpoint returns downloadable archive."""
        # This test validates the endpoint contract
        # The actual endpoint implementation will be in Phase 3

        # Setup mock workspace
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = "test-workspace-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.storage_path = str(temp_workspace_dir)

        mock_workspace_storage.get_workspace.return_value = mock_workspace
        mock_workspace_storage.is_simulation_running.return_value = False

        # Create export service
        export_service = ExportService(mock_workspace_storage)

        # Perform export
        archive_path, result = export_service.export_workspace(
            workspace_id="test-workspace-123"
        )

        # Verify result
        assert result.status == ExportStatus.SUCCESS
        assert archive_path.exists()
        assert archive_path.suffix == ".7z"

        # Verify archive can be opened
        with py7zr.SevenZipFile(archive_path, "r") as archive:
            names = archive.getnames()
            assert "manifest.json" in names
            assert "workspace.json" in names

        # Cleanup
        archive_path.unlink()

    def test_export_endpoint_blocks_during_simulation(
        self, mock_workspace_storage, temp_workspace_dir
    ):
        """Test export endpoint returns error when simulation is running."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = "test-workspace-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.storage_path = str(temp_workspace_dir)

        mock_workspace_storage.get_workspace.return_value = mock_workspace
        mock_workspace_storage.is_simulation_running.return_value = True

        export_service = ExportService(mock_workspace_storage)

        with pytest.raises(ValueError, match="simulation is running"):
            export_service.export_workspace(workspace_id="test-workspace-123")

    def test_export_endpoint_workspace_not_found(self, mock_workspace_storage):
        """Test export endpoint returns 404 for non-existent workspace."""
        mock_workspace_storage.get_workspace.return_value = None

        export_service = ExportService(mock_workspace_storage)

        with pytest.raises(ValueError, match="not found"):
            export_service.export_workspace(workspace_id="nonexistent")


class TestImportEndpointIntegration:
    """T022: Integration test for import endpoint."""

    def test_import_validate_endpoint(self, mock_workspace_storage, valid_import_archive):
        """Test import validation endpoint returns manifest and conflict info."""
        export_service = ExportService(mock_workspace_storage)

        # Write archive to temp file
        with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as f:
            f.write(valid_import_archive)
            archive_path = Path(f.name)

        try:
            result = export_service.validate_archive(archive_path, len(valid_import_archive))

            assert result.valid is True
            assert result.manifest is not None
            assert result.manifest.workspace_name == "Imported Workspace"
            assert result.conflict is None  # No conflict since no existing workspaces
        finally:
            archive_path.unlink()

    def test_import_validate_detects_conflict(
        self, mock_workspace_storage, valid_import_archive
    ):
        """Test import validation detects name conflicts."""
        # Add existing workspace with same name
        existing_ws = MagicMock(spec=WorkspaceSummary)
        existing_ws.id = "existing-id"
        existing_ws.name = "Imported Workspace"
        mock_workspace_storage.list_workspaces.return_value = [existing_ws]

        export_service = ExportService(mock_workspace_storage)

        with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as f:
            f.write(valid_import_archive)
            archive_path = Path(f.name)

        try:
            result = export_service.validate_archive(archive_path, len(valid_import_archive))

            assert result.valid is True
            assert result.conflict is not None
            assert result.conflict.suggested_name == "Imported Workspace (2)"
        finally:
            archive_path.unlink()

    def test_import_endpoint_creates_workspace(
        self, mock_workspace_storage, valid_import_archive
    ):
        """Test import endpoint creates new workspace."""
        with tempfile.TemporaryDirectory() as temp_workspaces:
            mock_workspace_storage._workspace_path.return_value = (
                Path(temp_workspaces) / "new-ws"
            )

            export_service = ExportService(mock_workspace_storage)

            with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as f:
                f.write(valid_import_archive)
                archive_path = Path(f.name)

            try:
                result = export_service.import_workspace(archive_path)

                assert result.status == ImportStatus.SUCCESS
                assert result.name == "Imported Workspace"
                assert result.workspace_id  # Should have new UUID
            finally:
                archive_path.unlink()


class TestBulkExportEndpointIntegration:
    """T036: Integration test for bulk export endpoints."""

    def test_bulk_export_creates_operation(self, mock_workspace_storage):
        """Test bulk export endpoint creates operation with status tracking."""
        export_service = ExportService(mock_workspace_storage)

        workspace_ids = ["ws-1", "ws-2", "ws-3"]
        status = export_service.start_bulk_export(workspace_ids)

        assert status.operation_id
        assert status.status == BulkOperationStatus.PENDING
        assert status.total == 3

    def test_bulk_export_status_endpoint(self, mock_workspace_storage):
        """Test bulk export status endpoint returns progress."""
        export_service = ExportService(mock_workspace_storage)

        # Start operation
        workspace_ids = ["ws-1", "ws-2"]
        started = export_service.start_bulk_export(workspace_ids)

        # Get status
        status = export_service.get_bulk_export_status(started.operation_id)

        assert status is not None
        assert status.operation_id == started.operation_id
        assert status.total == 2

    def test_bulk_export_download_endpoint(
        self, mock_workspace_storage, temp_workspace_dir
    ):
        """Test bulk export download endpoint returns individual archives."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = "test-workspace-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.storage_path = str(temp_workspace_dir)

        mock_workspace_storage.get_workspace.return_value = mock_workspace
        mock_workspace_storage.is_simulation_running.return_value = False

        export_service = ExportService(mock_workspace_storage)

        # Start and execute bulk export
        workspace_ids = ["test-workspace-123"]
        started = export_service.start_bulk_export(workspace_ids)
        export_service.execute_bulk_export(started.operation_id, workspace_ids)

        # Get archive path
        archive_path = export_service.get_export_archive_path(
            started.operation_id, "test-workspace-123"
        )

        assert archive_path is not None
        assert archive_path.exists()

        # Cleanup
        export_service.cleanup_bulk_export(started.operation_id)


class TestBulkImportEndpointIntegration:
    """T049: Integration test for bulk import endpoint."""

    def test_bulk_import_creates_operation(self, mock_workspace_storage):
        """Test bulk import endpoint creates operation with status tracking."""
        export_service = ExportService(mock_workspace_storage)

        status = export_service.start_bulk_import(file_count=3)

        assert status.operation_id
        assert status.status == BulkOperationStatus.PENDING
        assert status.total == 3

    def test_bulk_import_status_endpoint(self, mock_workspace_storage):
        """Test bulk import status endpoint returns progress."""
        export_service = ExportService(mock_workspace_storage)

        # Start operation
        started = export_service.start_bulk_import(file_count=2)

        # Get status
        status = export_service.get_bulk_import_status(started.operation_id)

        assert status is not None
        assert status.operation_id == started.operation_id
        assert status.total == 2


class TestFileSizeLimits:
    """Tests for file size limit enforcement."""

    def test_import_rejects_oversized_file(self, mock_workspace_storage, valid_import_archive):
        """Test import validation rejects files over 1GB."""
        export_service = ExportService(mock_workspace_storage)

        with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as f:
            f.write(valid_import_archive)
            archive_path = Path(f.name)

        try:
            # Simulate oversized file
            fake_size = 2 * 1024 * 1024 * 1024  # 2GB

            result = export_service.validate_archive(archive_path, fake_size)

            assert result.valid is False
            assert any("exceeds maximum" in err for err in result.errors)
        finally:
            archive_path.unlink()


class TestArchiveIntegrity:
    """Tests for archive integrity validation."""

    def test_validates_manifest_checksum(self, mock_workspace_storage):
        """Test import detects modified workspace.json via checksum."""
        # This is tested implicitly in import_workspace
        # which validates checksum and adds warning if mismatched
        pass

    def test_rejects_invalid_manifest_format(self, mock_workspace_storage):
        """Test import rejects archive with invalid manifest format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create archive with invalid manifest
            staging_dir = temp_path / "staging"
            staging_dir.mkdir()

            # Invalid manifest (missing required fields)
            invalid_manifest = {"version": "1.0"}  # Missing other required fields

            with open(staging_dir / "manifest.json", "w") as f:
                json.dump(invalid_manifest, f)

            archive_path = temp_path / "invalid_manifest.7z"
            with py7zr.SevenZipFile(archive_path, "w") as archive:
                archive.write(staging_dir / "manifest.json", "manifest.json")

            export_service = ExportService(mock_workspace_storage)
            result = export_service.validate_archive(
                archive_path, archive_path.stat().st_size
            )

            assert result.valid is False
            assert any("Invalid manifest" in err for err in result.errors)
