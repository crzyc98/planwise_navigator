"""Unit tests for import validation and import operations.

Feature: 031-workspace-export
Tests: T020 (archive validation), T021 (import with name conflict), T048 (bulk import)
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import py7zr
import pytest

from planalign_api.models.export import (
    BulkOperationStatus,
    ConflictResolution,
    ImportStatus,
)
from planalign_api.models.workspace import WorkspaceSummary
from planalign_api.services.export_service import (
    ExportService,
    MANIFEST_VERSION,
    MAX_IMPORT_SIZE_BYTES,
)


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
def valid_archive():
    """Create a valid 7z archive for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create workspace structure
        workspace_data = {
            "id": "imported-workspace-123",
            "name": "Imported Workspace",
            "description": "A workspace to import",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-15T12:00:00",
        }

        # Create manifest
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
                "total_size_bytes": 100,
                "checksum_sha256": "abc123",  # Simplified for test
            },
        }

        # Create staging directory
        staging_dir = temp_path / "staging"
        staging_dir.mkdir()

        # Write workspace.json
        with open(staging_dir / "workspace.json", "w") as f:
            json.dump(workspace_data, f)

        # Write manifest.json
        with open(staging_dir / "manifest.json", "w") as f:
            json.dump(manifest_data, f)

        # Create archive
        archive_path = temp_path / "test_import.7z"
        with py7zr.SevenZipFile(archive_path, "w") as archive:
            archive.write(staging_dir / "manifest.json", "manifest.json")
            archive.write(staging_dir / "workspace.json", "workspace.json")

        yield archive_path


@pytest.fixture
def archive_with_scenarios():
    """Create a 7z archive with scenarios for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create workspace structure
        workspace_data = {
            "id": "ws-with-scenarios",
            "name": "Workspace With Scenarios",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-15T12:00:00",
        }

        scenario_data = {
            "id": "scenario-1",
            "workspace_id": "ws-with-scenarios",
            "name": "Test Scenario",
            "status": "completed",
            "created_at": "2025-01-02T00:00:00",
        }

        # Create staging directory
        staging_dir = temp_path / "staging"
        staging_dir.mkdir()
        (staging_dir / "scenarios" / "scenario-1").mkdir(parents=True)

        # Write files
        with open(staging_dir / "workspace.json", "w") as f:
            json.dump(workspace_data, f)

        with open(staging_dir / "scenarios" / "scenario-1" / "scenario.json", "w") as f:
            json.dump(scenario_data, f)

        # Calculate checksum
        import hashlib

        with open(staging_dir / "workspace.json", "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()

        manifest_data = {
            "version": MANIFEST_VERSION,
            "export_date": "2025-01-20T10:00:00",
            "app_version": "1.0.0",
            "workspace_id": "ws-with-scenarios",
            "workspace_name": "Workspace With Scenarios",
            "contents": {
                "scenario_count": 1,
                "scenarios": ["Test Scenario"],
                "file_count": 2,
                "total_size_bytes": 500,
                "checksum_sha256": checksum,
            },
        }

        with open(staging_dir / "manifest.json", "w") as f:
            json.dump(manifest_data, f)

        # Create archive
        archive_path = temp_path / "test_import_with_scenarios.7z"
        with py7zr.SevenZipFile(archive_path, "w") as archive:
            archive.write(staging_dir / "manifest.json", "manifest.json")
            archive.write(staging_dir / "workspace.json", "workspace.json")
            archive.write(
                staging_dir / "scenarios" / "scenario-1" / "scenario.json",
                "scenarios/scenario-1/scenario.json",
            )

        yield archive_path


class TestArchiveValidation:
    """T020: Unit test for archive validation."""

    def test_validate_valid_archive(self, export_service, valid_archive):
        """Test validation passes for valid archive."""
        file_size = valid_archive.stat().st_size

        result = export_service.validate_archive(valid_archive, file_size)

        assert result.valid is True
        assert result.manifest is not None
        assert result.manifest.workspace_name == "Imported Workspace"
        assert len(result.errors) == 0

    def test_validate_archive_file_too_large(self, export_service, valid_archive):
        """Test validation fails for oversized file."""
        # Simulate a file larger than 1GB
        file_size = MAX_IMPORT_SIZE_BYTES + 1

        result = export_service.validate_archive(valid_archive, file_size)

        assert result.valid is False
        assert any("exceeds maximum" in err for err in result.errors)

    def test_validate_corrupted_archive(self, export_service):
        """Test validation fails for corrupted archive."""
        with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as f:
            f.write(b"not a valid 7z archive")
            f.flush()
            archive_path = Path(f.name)

        try:
            result = export_service.validate_archive(
                archive_path, archive_path.stat().st_size
            )

            assert result.valid is False
            assert any("Invalid" in err or "corrupted" in err for err in result.errors)
        finally:
            archive_path.unlink()

    def test_validate_archive_missing_manifest(self, export_service):
        """Test validation fails when manifest.json is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create archive without manifest
            archive_path = temp_path / "no_manifest.7z"
            dummy_file = temp_path / "dummy.txt"
            dummy_file.write_text("dummy content")

            with py7zr.SevenZipFile(archive_path, "w") as archive:
                archive.write(dummy_file, "dummy.txt")

            result = export_service.validate_archive(
                archive_path, archive_path.stat().st_size
            )

            assert result.valid is False
            assert any("manifest.json" in err for err in result.errors)


class TestImportNameConflict:
    """T021: Unit test for import with name conflict."""

    def test_validate_detects_name_conflict(
        self, export_service, mock_storage, valid_archive
    ):
        """Test validation detects name conflict with existing workspace."""
        # Set up existing workspace with same name
        existing_ws = MagicMock(spec=WorkspaceSummary)
        existing_ws.id = "existing-ws-id"
        existing_ws.name = "Imported Workspace"  # Same name as in archive

        mock_storage.list_workspaces.return_value = [existing_ws]

        result = export_service.validate_archive(
            valid_archive, valid_archive.stat().st_size
        )

        assert result.valid is True  # Still valid, just has conflict
        assert result.conflict is not None
        assert result.conflict.existing_workspace_id == "existing-ws-id"
        assert result.conflict.existing_workspace_name == "Imported Workspace"
        assert "Imported Workspace (2)" in result.conflict.suggested_name

    def test_suggested_name_increments(
        self, export_service, mock_storage, valid_archive
    ):
        """Test suggested name increments when conflicts exist."""
        # Set up multiple existing workspaces
        ws1 = MagicMock(spec=WorkspaceSummary)
        ws1.id = "ws-1"
        ws1.name = "Imported Workspace"

        ws2 = MagicMock(spec=WorkspaceSummary)
        ws2.id = "ws-2"
        ws2.name = "Imported Workspace (2)"

        mock_storage.list_workspaces.return_value = [ws1, ws2]

        result = export_service.validate_archive(
            valid_archive, valid_archive.stat().st_size
        )

        assert result.conflict is not None
        assert result.conflict.suggested_name == "Imported Workspace (3)"

    def test_no_conflict_different_name(
        self, export_service, mock_storage, valid_archive
    ):
        """Test no conflict when names are different."""
        existing_ws = MagicMock(spec=WorkspaceSummary)
        existing_ws.id = "existing-ws-id"
        existing_ws.name = "Different Name"

        mock_storage.list_workspaces.return_value = [existing_ws]

        result = export_service.validate_archive(
            valid_archive, valid_archive.stat().st_size
        )

        assert result.valid is True
        assert result.conflict is None

    def test_conflict_case_insensitive(
        self, export_service, mock_storage, valid_archive
    ):
        """Test name conflict detection is case-insensitive."""
        existing_ws = MagicMock(spec=WorkspaceSummary)
        existing_ws.id = "existing-ws-id"
        existing_ws.name = "IMPORTED WORKSPACE"  # Different case

        mock_storage.list_workspaces.return_value = [existing_ws]

        result = export_service.validate_archive(
            valid_archive, valid_archive.stat().st_size
        )

        assert result.conflict is not None


class TestImportWorkspace:
    """Tests for import_workspace method."""

    def test_import_workspace_success(
        self, export_service, mock_storage, archive_with_scenarios
    ):
        """Test successful workspace import."""
        mock_storage.list_workspaces.return_value = []

        # Mock workspace path creation
        with tempfile.TemporaryDirectory() as temp_workspaces:
            mock_storage._workspace_path.return_value = Path(temp_workspaces) / "new-ws"
            mock_storage.delete_workspace.return_value = True

            result = export_service.import_workspace(archive_with_scenarios)

            assert result.status == ImportStatus.SUCCESS
            assert result.name == "Workspace With Scenarios"
            assert result.scenario_count == 1

    def test_import_workspace_with_rename(
        self, export_service, mock_storage, valid_archive
    ):
        """Test import with rename conflict resolution."""
        # Set up existing workspace with same name
        existing_ws = MagicMock(spec=WorkspaceSummary)
        existing_ws.id = "existing-ws-id"
        existing_ws.name = "Imported Workspace"
        mock_storage.list_workspaces.return_value = [existing_ws]

        with tempfile.TemporaryDirectory() as temp_workspaces:
            mock_storage._workspace_path.return_value = Path(temp_workspaces) / "new-ws"

            result = export_service.import_workspace(
                valid_archive,
                conflict_resolution=ConflictResolution.RENAME,
                new_name="My Custom Name",
            )

            assert result.name == "My Custom Name"

    def test_import_workspace_with_replace(
        self, export_service, mock_storage, valid_archive
    ):
        """Test import with replace conflict resolution."""
        # Set up existing workspace with same name
        existing_ws = MagicMock(spec=WorkspaceSummary)
        existing_ws.id = "existing-ws-id"
        existing_ws.name = "Imported Workspace"
        mock_storage.list_workspaces.return_value = [existing_ws]
        mock_storage.delete_workspace.return_value = True

        with tempfile.TemporaryDirectory() as temp_workspaces:
            mock_storage._workspace_path.return_value = Path(temp_workspaces) / "new-ws"

            result = export_service.import_workspace(
                valid_archive,
                conflict_resolution=ConflictResolution.REPLACE,
            )

            # Should have deleted existing workspace
            mock_storage.delete_workspace.assert_called_once_with("existing-ws-id")
            assert result.name == "Imported Workspace"

    def test_import_workspace_conflict_not_resolved(
        self, export_service, mock_storage, valid_archive
    ):
        """Test import fails when conflict not resolved."""
        existing_ws = MagicMock(spec=WorkspaceSummary)
        existing_ws.id = "existing-ws-id"
        existing_ws.name = "Imported Workspace"
        mock_storage.list_workspaces.return_value = [existing_ws]

        with pytest.raises(ValueError, match="already exists"):
            export_service.import_workspace(valid_archive)

    def test_import_invalid_archive_fails(self, export_service, mock_storage):
        """Test import fails for invalid archive."""
        with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as f:
            f.write(b"invalid archive")
            f.flush()
            archive_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid archive"):
                export_service.import_workspace(archive_path)
        finally:
            archive_path.unlink()


class TestBulkImport:
    """T048: Unit test for bulk import operation."""

    def test_start_bulk_import(self, export_service):
        """Test starting bulk import creates operation status."""
        status = export_service.start_bulk_import(file_count=3)

        assert status.operation_id
        assert status.status == BulkOperationStatus.PENDING
        assert status.total == 3
        assert status.completed == 0
        assert status.results == []

    def test_get_bulk_import_status(self, export_service):
        """Test retrieving bulk import status."""
        started = export_service.start_bulk_import(file_count=2)

        retrieved = export_service.get_bulk_import_status(started.operation_id)

        assert retrieved is not None
        assert retrieved.operation_id == started.operation_id
        assert retrieved.total == 2

    def test_get_bulk_import_status_not_found(self, export_service):
        """Test retrieving non-existent operation returns None."""
        status = export_service.get_bulk_import_status("nonexistent-id")
        assert status is None


class TestVersionCompatibility:
    """Tests for version compatibility warnings."""

    def test_newer_version_warning(self, export_service, mock_storage):
        """Test warning when archive is from newer version."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create manifest with newer version
            manifest_data = {
                "version": "2.0",  # Newer than current
                "export_date": "2025-01-20T10:00:00",
                "app_version": "2.0.0",
                "workspace_id": "ws-123",
                "workspace_name": "Test",
                "contents": {
                    "scenario_count": 0,
                    "scenarios": [],
                    "file_count": 1,
                    "total_size_bytes": 100,
                    "checksum_sha256": "abc123",
                },
            }

            # Create staging directory
            staging_dir = temp_path / "staging"
            staging_dir.mkdir()

            with open(staging_dir / "manifest.json", "w") as f:
                json.dump(manifest_data, f)

            workspace_data = {"id": "ws-123", "name": "Test"}
            with open(staging_dir / "workspace.json", "w") as f:
                json.dump(workspace_data, f)

            # Create archive
            archive_path = temp_path / "newer_version.7z"
            with py7zr.SevenZipFile(archive_path, "w") as archive:
                archive.write(staging_dir / "manifest.json", "manifest.json")
                archive.write(staging_dir / "workspace.json", "workspace.json")

            result = export_service.validate_archive(
                archive_path, archive_path.stat().st_size
            )

            assert result.valid is True
            assert any("newer version" in w for w in result.warnings)


def _write_archive_with_index(
    tmp_path: Path,
    *,
    workspace_name: str,
    index_entries: list[dict],
    extra_files: dict[str, bytes] | None = None,
) -> Path:
    """Build a valid workspace 7z archive with custom ``data/imports/index.json``."""
    import hashlib

    staging = tmp_path / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    workspace_data = {
        "id": "old-ws-id",
        "name": workspace_name,
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-15T12:00:00",
    }
    ws_json = staging / "workspace.json"
    ws_json.write_text(json.dumps(workspace_data), encoding="utf-8")
    checksum = hashlib.sha256(ws_json.read_bytes()).hexdigest()

    imports_dir = staging / "data" / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    (imports_dir / "index.json").write_text(
        json.dumps(index_entries, indent=2), encoding="utf-8"
    )
    for rel, content in (extra_files or {}).items():
        target = staging / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    manifest_data = {
        "version": MANIFEST_VERSION,
        "export_date": "2025-01-20T10:00:00",
        "app_version": "1.0.0",
        "workspace_id": "old-ws-id",
        "workspace_name": workspace_name,
        "contents": {
            "scenario_count": 0,
            "scenarios": [],
            "file_count": 2 + len(extra_files or {}),
            "total_size_bytes": 500,
            "checksum_sha256": checksum,
        },
    }
    (staging / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    archive_path = tmp_path / f"{workspace_name.replace(' ', '_')}.7z"
    with py7zr.SevenZipFile(archive_path, "w") as archive:
        for file_path in sorted(staging.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, str(file_path.relative_to(staging)))
    return archive_path


@pytest.mark.fast
class TestImportedParquetContainment:
    """Imported workspace records stay inside the workspace and reject unsafe archives."""

    def test_legitimate_archive_from_different_root_yields_working_records(
        self, tmp_path: Path
    ) -> None:
        from planalign_api.services.import_service import ImportService
        from planalign_api.storage.workspace_storage import WorkspaceStorage

        archive_path = _write_archive_with_index(
            tmp_path / "src",
            workspace_name="Moved Workspace",
            index_entries=[
                {
                    "file_id": "file-1",
                    "workspace_id": "old-ws-id",
                    "import_id": "imp-1",
                    "filename": "census.parquet",
                    "storage_path": "/other/machine/workspaces/old-ws-id/data/imports/census.parquet",
                    "original_filename": "census.csv",
                    "row_count": 10,
                    "file_size_bytes": 4,
                    "schema": [],
                    "created_by": "system",
                }
            ],
            extra_files={"data/imports/census.parquet": b"PAR1"},
        )

        storage = WorkspaceStorage(tmp_path / "workspaces")
        svc = ExportService(storage)
        imported = svc.import_workspace(archive_path)

        assert imported.status == ImportStatus.SUCCESS
        import_service = ImportService(workspaces_root=storage.workspaces_root)
        records = import_service.list_parquet_files(imported.workspace_id)
        assert len(records) == 1
        expected_path = (
            storage._workspace_path(imported.workspace_id)
            / "data"
            / "imports"
            / "census.parquet"
        ).resolve()
        assert records[0].workspace_id == imported.workspace_id
        assert records[0].storage_path == str(expected_path)
        assert (
            import_service.resolve_parquet_path(imported.workspace_id, records[0])
            == expected_path
        )
        assert (
            import_service.delete_parquet_file(imported.workspace_id, "file-1") is True
        )
        assert not expected_path.exists()

    def test_archive_with_uncontained_index_yields_no_usable_outside_record(
        self, tmp_path: Path
    ) -> None:
        from planalign_api.services.import_service import ImportService
        from planalign_api.storage.workspace_storage import WorkspaceStorage

        outside = tmp_path / "outside.parquet"
        outside.write_bytes(b"keep me")
        archive_path = _write_archive_with_index(
            tmp_path / "src",
            workspace_name="Mixed Workspace",
            index_entries=[
                {
                    "file_id": "outside-abs",
                    "workspace_id": "old-ws-id",
                    "import_id": "imp-bad-1",
                    "filename": "outside.parquet",
                    "storage_path": str(outside),
                    "original_filename": "outside.csv",
                    "row_count": 1,
                    "file_size_bytes": 7,
                    "schema": [],
                    "created_by": "system",
                },
                {
                    "file_id": "outside-rel",
                    "workspace_id": "old-ws-id",
                    "import_id": "imp-bad-2",
                    "filename": "outside.parquet",
                    "storage_path": "../../../outside.parquet",
                    "original_filename": "outside.csv",
                    "row_count": 1,
                    "file_size_bytes": 7,
                    "schema": [],
                    "created_by": "system",
                },
                {
                    "file_id": "legit",
                    "workspace_id": "old-ws-id",
                    "import_id": "imp-ok",
                    "filename": "inside.parquet",
                    "storage_path": "/old/root/ws/data/imports/inside.parquet",
                    "original_filename": "inside.csv",
                    "row_count": 5,
                    "file_size_bytes": 4,
                    "schema": [],
                    "created_by": "system",
                },
            ],
            extra_files={"data/imports/inside.parquet": b"PAR1"},
        )

        storage = WorkspaceStorage(tmp_path / "workspaces")
        imported = ExportService(storage).import_workspace(archive_path)

        import_service = ImportService(workspaces_root=storage.workspaces_root)
        records = import_service.list_parquet_files(imported.workspace_id)
        assert [r.file_id for r in records] == ["legit"]
        assert outside.read_bytes() == b"keep me"
        assert any("outside the workspace" in w for w in imported.warnings)

    def test_archive_rejects_symlink_member(self, tmp_path: Path) -> None:
        from planalign_api.storage.workspace_storage import WorkspaceStorage

        staging = tmp_path / "staging"
        (staging / "data" / "imports").mkdir(parents=True)
        (staging / "workspace.json").write_text('{"id": "w", "name": "Sym"}')
        manifest = {
            "version": MANIFEST_VERSION,
            "export_date": "2025-01-20T10:00:00",
            "app_version": "1.0.0",
            "workspace_id": "w",
            "workspace_name": "Sym",
            "contents": {
                "scenario_count": 0,
                "scenarios": [],
                "file_count": 1,
                "total_size_bytes": 10,
                "checksum_sha256": "abc",
            },
        }
        (staging / "manifest.json").write_text(json.dumps(manifest))
        link = staging / "data" / "imports" / "link.parquet"
        link.symlink_to("../../workspace.json")

        archive_path = tmp_path / "symlink.7z"
        with py7zr.SevenZipFile(archive_path, "w") as archive:
            archive.write(staging / "manifest.json", "manifest.json")
            archive.write(staging / "workspace.json", "workspace.json")
            archive.write(link, "data/imports/link.parquet")

        svc = ExportService(WorkspaceStorage(tmp_path / "workspaces"))
        validation = svc.validate_archive(archive_path, archive_path.stat().st_size)
        assert validation.valid is False
        assert any("link" in err.lower() for err in validation.errors)
        with pytest.raises(ValueError, match="link"):
            svc.extract_archive(archive_path, tmp_path / "out")

    @pytest.mark.parametrize(
        "bad_name",
        [
            "/etc/passwd",
            "../escape.txt",
            "data/../../escape.txt",
            r"C:\evil.txt",
        ],
    )
    def test_archive_rejects_absolute_and_traversal_members(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_name: str
    ) -> None:
        import py7zr.py7zr as py7zr_mod

        from planalign_api.storage.workspace_storage import WorkspaceStorage

        archive_path = tmp_path / "bad.7z"
        manifest = json.dumps(
            {
                "version": MANIFEST_VERSION,
                "export_date": "2025-01-20T10:00:00",
                "app_version": "1.0.0",
                "workspace_id": "w",
                "workspace_name": "Bad",
                "contents": {
                    "scenario_count": 0,
                    "scenarios": [],
                    "file_count": 1,
                    "total_size_bytes": 10,
                    "checksum_sha256": "abc",
                },
            }
        ).encode("utf-8")

        # Bypass py7zr's write-side helper only to construct the fixture archive.
        with monkeypatch.context() as mp:
            mp.setattr(py7zr_mod, "check_archive_path", lambda _name: True)
            with py7zr.SevenZipFile(archive_path, "w") as archive:
                archive.writestr(manifest, "manifest.json")
                archive.writestr(b"payload", bad_name)

        svc = ExportService(WorkspaceStorage(tmp_path / "workspaces"))
        validation = svc.validate_archive(archive_path, archive_path.stat().st_size)
        assert validation.valid is False
        with pytest.raises(ValueError):
            svc.extract_archive(archive_path, tmp_path / "out")
