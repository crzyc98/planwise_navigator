"""Export and import service for workspace backup functionality.

This service handles:
- Creating 7z archives of workspaces with manifests
- Extracting and validating workspace archives
- Managing bulk export/import operations with progress tracking
"""

import hashlib
import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import py7zr
import yaml

from ..models.export import (
    BulkExportStatus,
    BulkImportStatus,
    BulkOperationStatus,
    ConflictResolution,
    ExportManifest,
    ExportResult,
    ExportStatus,
    ImportConflict,
    ImportResponse,
    ImportStatus,
    ImportValidationResponse,
    ManifestContents,
)
from ..storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

# Get app version from _version module
try:
    from _version import __version__ as APP_VERSION
except ImportError:
    APP_VERSION = "1.0.0"

# Maximum import file size: 1GB
MAX_IMPORT_SIZE_BYTES = 1 * 1024 * 1024 * 1024

# Current manifest schema version
MANIFEST_VERSION = "1.0"


class ExportService:
    """Service for exporting and importing workspaces."""

    def __init__(self, storage: WorkspaceStorage):
        """Initialize export service.

        Args:
            storage: WorkspaceStorage instance for workspace operations
        """
        self.storage = storage
        self._bulk_export_operations: Dict[str, BulkExportStatus] = {}
        self._bulk_import_operations: Dict[str, BulkImportStatus] = {}
        self._export_temp_files: Dict[str, Dict[str, Path]] = {}

    # ==================== Manifest Operations ====================

    def create_manifest(
        self,
        workspace_id: str,
        workspace_name: str,
        workspace_path: Path,
    ) -> ExportManifest:
        """Create export manifest for a workspace.

        Args:
            workspace_id: UUID of the workspace
            workspace_name: Human-readable workspace name
            workspace_path: Path to workspace directory

        Returns:
            ExportManifest with inventory of workspace contents
        """
        # Calculate contents inventory
        scenarios = []
        file_count = 0
        total_size = 0

        # Count scenarios
        scenarios_path = workspace_path / "scenarios"
        if scenarios_path.exists():
            for scenario_dir in scenarios_path.iterdir():
                if scenario_dir.is_dir():
                    scenario_json = scenario_dir / "scenario.json"
                    if scenario_json.exists():
                        with open(scenario_json) as f:
                            scenario_data = json.load(f)
                        scenarios.append(scenario_data.get("name", scenario_dir.name))

        # Count files and calculate total size
        for file_path in workspace_path.rglob("*"):
            if file_path.is_file():
                file_count += 1
                total_size += file_path.stat().st_size

        # Calculate checksum of workspace.json
        workspace_json_path = workspace_path / "workspace.json"
        if workspace_json_path.exists():
            with open(workspace_json_path, "rb") as f:
                checksum = hashlib.sha256(f.read()).hexdigest()
        else:
            checksum = ""

        contents = ManifestContents(
            scenario_count=len(scenarios),
            scenarios=scenarios,
            file_count=file_count,
            total_size_bytes=total_size,
            checksum_sha256=checksum,
        )

        return ExportManifest(
            version=MANIFEST_VERSION,
            export_date=datetime.utcnow(),
            app_version=APP_VERSION,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            contents=contents,
        )

    # ==================== Archive Operations ====================

    def create_archive(
        self,
        workspace_path: Path,
        manifest: ExportManifest,
        output_path: Path,
    ) -> int:
        """Create 7z archive of workspace with manifest.

        Args:
            workspace_path: Path to workspace directory
            manifest: Export manifest to include
            output_path: Path for output archive file

        Returns:
            Size of created archive in bytes
        """
        # Create temp directory for staging
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Write manifest to temp directory
            manifest_path = temp_path / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest.model_dump(mode="json"), f, indent=2, default=str)

            # Create archive
            with py7zr.SevenZipFile(output_path, "w") as archive:
                # Add manifest
                archive.write(manifest_path, "manifest.json")

                # Add all workspace files
                for file_path in workspace_path.rglob("*"):
                    if file_path.is_file():
                        # Calculate relative path from workspace root
                        rel_path = file_path.relative_to(workspace_path)
                        archive.write(file_path, str(rel_path))

        return output_path.stat().st_size

    def extract_archive(
        self,
        archive_path: Path,
        output_path: Path,
    ) -> ExportManifest:
        """Extract 7z archive and return manifest.

        Args:
            archive_path: Path to 7z archive
            output_path: Directory to extract to

        Returns:
            Parsed ExportManifest from archive

        Raises:
            ValueError: If archive is invalid or missing manifest
        """
        output_path.mkdir(parents=True, exist_ok=True)

        with py7zr.SevenZipFile(archive_path, "r") as archive:
            archive.extractall(path=output_path)

        # Read and parse manifest
        manifest_path = output_path / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("Archive does not contain manifest.json")

        with open(manifest_path) as f:
            manifest_data = json.load(f)

        return ExportManifest(**manifest_data)

    def validate_archive(
        self,
        archive_path: Path,
        file_size: int,
    ) -> ImportValidationResponse:
        """Validate an archive before import.

        Args:
            archive_path: Path to 7z archive file
            file_size: Size of the file in bytes

        Returns:
            ImportValidationResponse with validation results
        """
        errors: List[str] = []
        warnings: List[str] = []
        manifest: Optional[ExportManifest] = None
        conflict: Optional[ImportConflict] = None

        # Check file size
        if file_size > MAX_IMPORT_SIZE_BYTES:
            errors.append(f"File size ({file_size / (1024*1024):.1f} MB) exceeds maximum allowed (1 GB)")
            return ImportValidationResponse(valid=False, errors=errors, warnings=warnings)

        # Try to open and validate archive
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Test archive integrity
                try:
                    with py7zr.SevenZipFile(archive_path, "r") as archive:
                        # Just read the manifest, don't extract everything
                        archive.extract(path=temp_path, targets=["manifest.json"])
                except py7zr.exceptions.Bad7zFile:
                    errors.append("Invalid or corrupted 7z archive")
                    return ImportValidationResponse(valid=False, errors=errors, warnings=warnings)

                # Read manifest
                manifest_path = temp_path / "manifest.json"
                if not manifest_path.exists():
                    errors.append("Archive does not contain manifest.json")
                    return ImportValidationResponse(valid=False, errors=errors, warnings=warnings)

                with open(manifest_path) as f:
                    manifest_data = json.load(f)

                try:
                    manifest = ExportManifest(**manifest_data)
                except Exception as e:
                    errors.append(f"Invalid manifest format: {e}")
                    return ImportValidationResponse(valid=False, errors=errors, warnings=warnings)

                # Check version compatibility
                if manifest.version > MANIFEST_VERSION:
                    warnings.append(
                        f"Archive was created with a newer version ({manifest.version}) "
                        f"than current ({MANIFEST_VERSION}). Some features may not import correctly."
                    )

                # Check for name conflicts
                existing_workspaces = self.storage.list_workspaces()
                for ws in existing_workspaces:
                    if ws.name.lower() == manifest.workspace_name.lower():
                        conflict = ImportConflict(
                            existing_workspace_id=ws.id,
                            existing_workspace_name=ws.name,
                            suggested_name=self._generate_unique_name(manifest.workspace_name, existing_workspaces),
                        )
                        break

        except Exception as e:
            logger.exception("Error validating archive")
            errors.append(f"Validation error: {str(e)}")
            return ImportValidationResponse(valid=False, errors=errors, warnings=warnings)

        return ImportValidationResponse(
            valid=len(errors) == 0,
            manifest=manifest,
            conflict=conflict,
            warnings=warnings,
            errors=errors,
        )

    def _generate_unique_name(self, base_name: str, existing_workspaces: List[Any]) -> str:
        """Generate a unique workspace name by appending (N).

        Args:
            base_name: Original workspace name
            existing_workspaces: List of existing workspace summaries

        Returns:
            Unique name like "name (2)"
        """
        existing_names = {ws.name.lower() for ws in existing_workspaces}
        counter = 2
        while True:
            new_name = f"{base_name} ({counter})"
            if new_name.lower() not in existing_names:
                return new_name
            counter += 1

    # ==================== Single Export/Import ====================

    def export_workspace(
        self,
        workspace_id: str,
        output_dir: Optional[Path] = None,
    ) -> Tuple[Path, ExportResult]:
        """Export a single workspace to a 7z archive.

        Args:
            workspace_id: UUID of workspace to export
            output_dir: Directory to save archive (uses temp if None)

        Returns:
            Tuple of (archive_path, ExportResult)

        Raises:
            ValueError: If workspace not found or has active simulation
        """
        # Get workspace
        workspace = self.storage.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")

        workspace_path = Path(workspace.storage_path)
        workspace_name = workspace.name

        # Check for active simulation
        if self.storage.is_simulation_running(workspace_id):
            raise ValueError("Cannot export workspace while simulation is running")

        # Generate archive filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        # Sanitize workspace name for filename
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in workspace_name)
        safe_name = safe_name.strip().replace(" ", "_")
        filename = f"{safe_name}_{timestamp}.7z"

        # Determine output path
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / "planalign_exports"
        output_dir.mkdir(parents=True, exist_ok=True)
        archive_path = output_dir / filename

        try:
            # Create manifest
            manifest = self.create_manifest(workspace_id, workspace_name, workspace_path)

            # Create archive
            archive_size = self.create_archive(workspace_path, manifest, archive_path)

            logger.info(f"Exported workspace '{workspace_name}' to {archive_path} ({archive_size} bytes)")

            return archive_path, ExportResult(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                filename=filename,
                size_bytes=archive_size,
                status=ExportStatus.SUCCESS,
            )

        except Exception as e:
            logger.exception(f"Failed to export workspace {workspace_id}")
            # Clean up partial archive
            if archive_path.exists():
                archive_path.unlink()
            return archive_path, ExportResult(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                status=ExportStatus.FAILED,
                error=str(e),
            )

    def import_workspace(
        self,
        archive_path: Path,
        conflict_resolution: Optional[ConflictResolution] = None,
        new_name: Optional[str] = None,
    ) -> ImportResponse:
        """Import a workspace from a 7z archive.

        Args:
            archive_path: Path to 7z archive file
            conflict_resolution: How to handle name conflicts
            new_name: Custom name if conflict_resolution=rename

        Returns:
            ImportResponse with import results

        Raises:
            ValueError: If archive is invalid or conflict not resolved
        """
        warnings: List[str] = []

        # Validate archive first
        validation = self.validate_archive(archive_path, archive_path.stat().st_size)
        if not validation.valid:
            raise ValueError(f"Invalid archive: {'; '.join(validation.errors)}")

        manifest = validation.manifest
        assert manifest is not None  # Guaranteed by valid=True

        warnings.extend(validation.warnings)

        # Handle name conflict
        final_name = manifest.workspace_name
        if validation.conflict:
            if conflict_resolution == ConflictResolution.RENAME:
                final_name = new_name or validation.conflict.suggested_name
            elif conflict_resolution == ConflictResolution.REPLACE:
                # Delete existing workspace
                self.storage.delete_workspace(validation.conflict.existing_workspace_id)
            elif conflict_resolution is None:
                raise ValueError(
                    f"Workspace name '{manifest.workspace_name}' already exists. "
                    f"Specify conflict_resolution: 'rename' or 'replace'"
                )

        # Extract to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Extract archive
            extracted_manifest = self.extract_archive(archive_path, temp_path)

            # Validate checksum
            workspace_json_path = temp_path / "workspace.json"
            if workspace_json_path.exists():
                with open(workspace_json_path, "rb") as f:
                    actual_checksum = hashlib.sha256(f.read()).hexdigest()
                if actual_checksum != extracted_manifest.contents.checksum_sha256:
                    warnings.append("Workspace checksum mismatch - file may have been modified")

            # Create new workspace
            new_workspace_id = str(uuid.uuid4())
            new_workspace_path = self.storage._workspace_path(new_workspace_id)
            new_workspace_path.mkdir(parents=True)

            # Copy extracted files (excluding manifest)
            for item in temp_path.iterdir():
                if item.name != "manifest.json":
                    dest = new_workspace_path / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)

            # Update workspace.json with new ID and name
            workspace_json_path = new_workspace_path / "workspace.json"
            if workspace_json_path.exists():
                with open(workspace_json_path) as f:
                    workspace_data = json.load(f)
            else:
                workspace_data = {}

            workspace_data["id"] = new_workspace_id
            workspace_data["name"] = final_name
            workspace_data["updated_at"] = datetime.utcnow().isoformat()

            with open(workspace_json_path, "w") as f:
                json.dump(workspace_data, f, indent=2)

            # Count scenarios
            scenarios_path = new_workspace_path / "scenarios"
            scenario_count = 0
            if scenarios_path.exists():
                for scenario_dir in scenarios_path.iterdir():
                    if scenario_dir.is_dir() and (scenario_dir / "scenario.json").exists():
                        scenario_count += 1

            logger.info(f"Imported workspace '{final_name}' as {new_workspace_id}")

            return ImportResponse(
                workspace_id=new_workspace_id,
                name=final_name,
                scenario_count=scenario_count,
                status=ImportStatus.SUCCESS if not warnings else ImportStatus.PARTIAL,
                warnings=warnings,
            )

    # ==================== Bulk Operations ====================

    def start_bulk_export(self, workspace_ids: List[str]) -> BulkExportStatus:
        """Start a bulk export operation.

        Args:
            workspace_ids: List of workspace UUIDs to export

        Returns:
            BulkExportStatus with operation ID for tracking
        """
        operation_id = str(uuid.uuid4())
        status = BulkExportStatus(
            operation_id=operation_id,
            status=BulkOperationStatus.PENDING,
            total=len(workspace_ids),
            completed=0,
            results=[],
        )
        self._bulk_export_operations[operation_id] = status
        self._export_temp_files[operation_id] = {}
        return status

    def execute_bulk_export(self, operation_id: str, workspace_ids: List[str]) -> BulkExportStatus:
        """Execute bulk export operation.

        This should be called after start_bulk_export to actually perform the exports.

        Args:
            operation_id: Operation ID from start_bulk_export
            workspace_ids: List of workspace UUIDs to export

        Returns:
            Updated BulkExportStatus
        """
        status = self._bulk_export_operations.get(operation_id)
        if status is None:
            raise ValueError(f"Operation not found: {operation_id}")

        status.status = BulkOperationStatus.IN_PROGRESS

        # Create temp directory for exports
        export_dir = Path(tempfile.gettempdir()) / "planalign_exports" / operation_id
        export_dir.mkdir(parents=True, exist_ok=True)

        for workspace_id in workspace_ids:
            try:
                # Get workspace name for status update
                workspace = self.storage.get_workspace(workspace_id)
                if workspace:
                    status.current_workspace = workspace.name

                # Export workspace
                archive_path, result = self.export_workspace(workspace_id, export_dir)

                if result.status == ExportStatus.SUCCESS:
                    self._export_temp_files[operation_id][workspace_id] = archive_path

                status.results.append(result)

            except Exception as e:
                logger.exception(f"Failed to export workspace {workspace_id}")
                status.results.append(ExportResult(
                    workspace_id=workspace_id,
                    workspace_name=workspace.name if workspace else "Unknown",
                    status=ExportStatus.FAILED,
                    error=str(e),
                ))

            status.completed += 1

        status.current_workspace = None
        status.status = BulkOperationStatus.COMPLETED if all(
            r.status == ExportStatus.SUCCESS for r in status.results
        ) else BulkOperationStatus.FAILED

        return status

    def get_bulk_export_status(self, operation_id: str) -> Optional[BulkExportStatus]:
        """Get status of a bulk export operation.

        Args:
            operation_id: Operation ID to check

        Returns:
            BulkExportStatus or None if not found
        """
        return self._bulk_export_operations.get(operation_id)

    def get_export_archive_path(self, operation_id: str, workspace_id: str) -> Optional[Path]:
        """Get path to exported archive for download.

        Args:
            operation_id: Bulk export operation ID
            workspace_id: Workspace ID within the operation

        Returns:
            Path to archive file or None if not found
        """
        operation_files = self._export_temp_files.get(operation_id)
        if operation_files:
            return operation_files.get(workspace_id)
        return None

    def cleanup_bulk_export(self, operation_id: str) -> None:
        """Clean up temporary files from bulk export.

        Args:
            operation_id: Operation ID to clean up
        """
        # Remove temp files
        if operation_id in self._export_temp_files:
            for path in self._export_temp_files[operation_id].values():
                try:
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass
            del self._export_temp_files[operation_id]

        # Remove from operations dict
        self._bulk_export_operations.pop(operation_id, None)

    def start_bulk_import(self, file_count: int) -> BulkImportStatus:
        """Start a bulk import operation.

        Args:
            file_count: Number of files to import

        Returns:
            BulkImportStatus with operation ID for tracking
        """
        operation_id = str(uuid.uuid4())
        status = BulkImportStatus(
            operation_id=operation_id,
            status=BulkOperationStatus.PENDING,
            total=file_count,
            completed=0,
            results=[],
        )
        self._bulk_import_operations[operation_id] = status
        return status

    def get_bulk_import_status(self, operation_id: str) -> Optional[BulkImportStatus]:
        """Get status of a bulk import operation.

        Args:
            operation_id: Operation ID to check

        Returns:
            BulkImportStatus or None if not found
        """
        return self._bulk_import_operations.get(operation_id)
