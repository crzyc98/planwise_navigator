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
import stat
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple

import py7zr

from ..config import APISettings, get_settings
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
from .import_service import sanitize_parquet_index
from .path_guard import PathGuardError, ProtectedPathError
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

# Private temporary directory prefixes and stale bulk-export retention window
SINGLE_EXPORT_DIR_PREFIX = "planalign_export_"
BULK_EXPORT_DIR_PREFIX = "planalign_bulk_export_"
BULK_EXPORT_MAX_AGE_SECONDS = 24 * 3600


def normalize_extracted_permissions(root: Path) -> None:
    """Normalize POSIX permissions on an extracted archive tree.

    Sets directories to ``0o700`` and regular files to ``0o600``, dropping any
    setuid/setgid/sticky and group/other bits carried by archive metadata.
    No-op on Windows.
    """
    if os.name != "posix":
        return
    if root.is_dir() and not root.is_symlink():
        os.chmod(root, 0o700)
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        for dirname in list(dirnames):
            subdir = current / dirname
            if subdir.is_symlink():
                dirnames.remove(dirname)
                continue
            os.chmod(subdir, 0o700)
        for filename in filenames:
            file_path = current / filename
            if file_path.is_symlink():
                continue
            os.chmod(file_path, 0o600)


class ExportWorkspaceNotFoundError(ValueError):
    """Raised when a requested workspace does not exist."""


class ExportWorkspaceRunningError(ValueError):
    """Raised when export is blocked by an active workspace simulation."""


@dataclass(frozen=True)
class _ArchiveLimits:
    """Bounds on unpacked workspace import archive size and entry count."""

    max_unpacked_bytes: int
    max_member_bytes: int
    max_member_count: int


def _archive_limits(settings: APISettings) -> _ArchiveLimits:
    """Build archive extraction limits from API settings."""
    return _ArchiveLimits(
        max_unpacked_bytes=settings.import_max_unpacked_bytes,
        max_member_bytes=settings.import_max_member_bytes,
        max_member_count=settings.import_max_member_count,
    )


def _format_byte_limit(limit_bytes: int) -> str:
    """Format a byte cap cleanly for client-facing validation messages."""
    gib = 1024 * 1024 * 1024
    mib = 1024 * 1024
    if limit_bytes >= gib and limit_bytes % gib == 0:
        return f"{limit_bytes // gib} GB"
    if limit_bytes >= mib:
        return f"{limit_bytes / mib:.1f} MB"
    return f"{limit_bytes} bytes"


def _validate_archive_member_path(name: str, output_root: Optional[Path]) -> None:
    """Reject absolute paths, drive prefixes, and parent-directory traversal."""
    if not name or "\x00" in name:
        raise ValueError("Archive contains an empty or invalid member path")
    if (
        name.startswith(("/", "\\"))
        or PurePosixPath(name).is_absolute()
        or PureWindowsPath(name).is_absolute()
        or bool(PureWindowsPath(name).drive)
    ):
        raise ValueError(f"Archive contains disallowed absolute path: {name!r}")
    normalized = name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if any(part == ".." for part in parts):
        raise ValueError(f"Archive contains disallowed parent traversal: {name!r}")
    if output_root is not None:
        destination = (output_root / PurePosixPath(*parts)).resolve()
        if not destination.is_relative_to(output_root):
            raise ValueError(f"Archive member escapes target directory: {name!r}")


def _validate_archive_member_entry(
    member: Any,
    output_root: Optional[Path],
    limits: _ArchiveLimits,
) -> int:
    """Validate one archive member's path, type, and declared unpacked size."""
    _validate_archive_member_path(member.filename, output_root)
    st_fmt = getattr(member, "st_fmt", None)
    is_special_fmt = st_fmt is not None and st_fmt not in (
        stat.S_IFREG,
        stat.S_IFDIR,
    )
    if (
        member.is_symlink
        or getattr(member, "is_junction", False)
        or getattr(member, "is_socket", False)
        or is_special_fmt
        or not (member.is_file or member.is_directory)
    ):
        raise ValueError(
            f"Archive contains disallowed link or special entry: {member.filename!r}"
        )

    member_size = getattr(member, "uncompressed", 0)
    if (
        not isinstance(member_size, int)
        or isinstance(member_size, bool)
        or member_size < 0
    ):
        raise ValueError("Archive contains an entry with an invalid declared size")
    if member_size > limits.max_member_bytes:
        raise ValueError(
            "Archive entry exceeds maximum unpacked file size "
            f"({_format_byte_limit(limits.max_member_bytes)})"
        )
    return member_size


def _validate_archive_members(
    archive: py7zr.SevenZipFile,
    output_root: Optional[Path] = None,
    *,
    limits: Optional[_ArchiveLimits] = None,
) -> None:
    """Reject archive members with unsafe paths, special types, or excessive size."""
    active_limits = limits or _archive_limits(get_settings())
    member_count = len(archive.files)
    if member_count > active_limits.max_member_count:
        raise ValueError(
            f"Archive contains too many entries ({member_count} exceeds limit of "
            f"{active_limits.max_member_count})"
        )

    total_unpacked = 0
    for member in archive.files:
        total_unpacked += _validate_archive_member_entry(
            member, output_root, active_limits
        )
        if total_unpacked > active_limits.max_unpacked_bytes:
            raise ValueError(
                "Archive unpacked size exceeds maximum allowed "
                f"({_format_byte_limit(active_limits.max_unpacked_bytes)})"
            )


class ExportService:
    """Service for exporting and importing workspaces."""

    def __init__(
        self, storage: WorkspaceStorage, settings: Optional[APISettings] = None
    ):
        """Initialize export service.

        Args:
            storage: WorkspaceStorage instance for workspace operations
        """
        self.storage = storage
        self.settings = settings or get_settings()
        self._bulk_export_operations: Dict[str, BulkExportStatus] = {}
        self._bulk_export_dirs: Dict[str, Path] = {}
        self._bulk_export_created_at: Dict[str, datetime] = {}
        self._bulk_import_operations: Dict[str, BulkImportStatus] = {}
        self._bulk_import_created_at: Dict[str, datetime] = {}
        self._bulk_import_terminal_at: Dict[str, datetime] = {}
        self._export_temp_files: Dict[str, Dict[str, Path]] = {}

    def _prune_bulk_import_operations(self, now: Optional[datetime] = None) -> None:
        """Remove expired/old terminal imports while retaining active imports."""
        current_time = now or datetime.now(timezone.utc)
        terminal = [
            (operation_id, operation)
            for operation_id, operation in self._bulk_import_operations.items()
            if operation.status
            in {BulkOperationStatus.COMPLETED, BulkOperationStatus.FAILED}
        ]
        expired = [
            operation_id
            for operation_id, _ in terminal
            if (
                current_time
                - self._bulk_import_terminal_at.get(
                    operation_id, self._bulk_import_created_at[operation_id]
                )
            ).total_seconds()
            >= self.settings.bulk_import_operation_ttl_seconds
        ]
        for operation_id in expired:
            self._bulk_import_operations.pop(operation_id, None)
            self._bulk_import_created_at.pop(operation_id, None)
            self._bulk_import_terminal_at.pop(operation_id, None)

        remaining_terminal = [
            operation_id
            for operation_id, operation in self._bulk_import_operations.items()
            if operation.status
            in {BulkOperationStatus.COMPLETED, BulkOperationStatus.FAILED}
        ]
        excess = (
            len(remaining_terminal) - self.settings.bulk_import_operation_max_entries
        )
        if excess > 0:
            remaining_terminal.sort(
                key=lambda operation_id: self._bulk_import_terminal_at.get(
                    operation_id, self._bulk_import_created_at[operation_id]
                )
            )
            for operation_id in remaining_terminal[:excess]:
                self._bulk_import_operations.pop(operation_id, None)
                self._bulk_import_created_at.pop(operation_id, None)
                self._bulk_import_terminal_at.pop(operation_id, None)

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
            export_date=datetime.now(timezone.utc),
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
        resolved_output = output_path.resolve()
        limits = _archive_limits(self.settings)

        with py7zr.SevenZipFile(archive_path, "r") as archive:
            _validate_archive_members(archive, resolved_output, limits=limits)
            # py7zr writes at most each member's declared size, so the check
            # above bounds what extraction can put on disk.
            output_path.mkdir(parents=True, exist_ok=True)
            archive.extractall(path=output_path)

        normalize_extracted_permissions(output_path)

        for extracted in output_path.rglob("*"):
            if extracted.is_symlink():
                raise ValueError(
                    f"Archive contains disallowed symbolic link: {extracted.name!r}"
                )

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

        # Check file size
        if file_size > MAX_IMPORT_SIZE_BYTES:
            errors.append(
                f"File size ({file_size / (1024*1024):.1f} MB) exceeds maximum allowed (1 GB)"
            )
            return ImportValidationResponse(
                valid=False, errors=errors, warnings=warnings
            )

        try:
            manifest = self._extract_and_validate_manifest(archive_path, errors)
            if manifest is None:
                return ImportValidationResponse(
                    valid=False, errors=errors, warnings=warnings
                )

            # Check version compatibility
            if manifest.version > MANIFEST_VERSION:
                warnings.append(
                    f"Archive was created with a newer version ({manifest.version}) "
                    f"than current ({MANIFEST_VERSION}). Some features may not import correctly."
                )

            conflict = self._check_name_conflicts(manifest.workspace_name)

        except Exception as e:
            logger.exception("Error validating archive")
            errors.append(f"Validation error: {str(e)}")
            return ImportValidationResponse(
                valid=False, errors=errors, warnings=warnings
            )

        return ImportValidationResponse(
            valid=len(errors) == 0,
            manifest=manifest,
            conflict=conflict,
            warnings=warnings,
            errors=errors,
        )

    def _extract_and_validate_manifest(
        self,
        archive_path: Path,
        errors: List[str],
    ) -> Optional[ExportManifest]:
        """Extract manifest from archive and validate its format.

        Args:
            archive_path: Path to 7z archive file
            errors: List to append error messages to

        Returns:
            Parsed ExportManifest, or None if extraction/validation failed
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            resolved_temp = temp_path.resolve()
            limits = _archive_limits(self.settings)

            try:
                with py7zr.SevenZipFile(archive_path, "r") as archive:
                    _validate_archive_members(archive, resolved_temp, limits=limits)
                    archive.extract(path=temp_path, targets=["manifest.json"])
            except py7zr.exceptions.Bad7zFile:
                errors.append("Invalid or corrupted 7z archive")
                return None
            except ValueError as exc:
                errors.append(str(exc))
                return None

            normalize_extracted_permissions(temp_path)

            manifest_path = temp_path / "manifest.json"
            if not manifest_path.exists():
                errors.append("Archive does not contain manifest.json")
                return None

            with open(manifest_path) as f:
                manifest_data = json.load(f)

            try:
                return ExportManifest(**manifest_data)
            except Exception as e:
                errors.append(f"Invalid manifest format: {e}")
                return None

    def _check_name_conflicts(
        self,
        workspace_name: str,
    ) -> Optional[ImportConflict]:
        """Check if a workspace name conflicts with existing workspaces.

        Args:
            workspace_name: Name to check for conflicts

        Returns:
            ImportConflict if a conflict exists, None otherwise
        """
        existing_workspaces = self.storage.list_workspaces()
        for ws in existing_workspaces:
            if ws.name.lower() == workspace_name.lower():
                return ImportConflict(
                    existing_workspace_id=ws.id,
                    existing_workspace_name=ws.name,
                    suggested_name=self._generate_unique_name(
                        workspace_name, existing_workspaces
                    ),
                )
        return None

    def _generate_unique_name(
        self, base_name: str, existing_workspaces: List[Any]
    ) -> str:
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
            ExportWorkspaceNotFoundError: If workspace does not exist.
            ExportWorkspaceRunningError: If a simulation is active.
        """
        # Get workspace
        workspace = self.storage.get_workspace(workspace_id)
        if workspace is None:
            raise ExportWorkspaceNotFoundError("Workspace not found")

        workspace_path = Path(workspace.storage_path)
        workspace_name = workspace.name

        # Check for active simulation
        if self.storage.is_simulation_running(workspace_id):
            raise ExportWorkspaceRunningError(
                "Cannot export workspace while simulation is running"
            )

        # Generate archive filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # Sanitize workspace name for filename
        safe_name = "".join(
            c if c.isalnum() or c in " -_" else "_" for c in workspace_name
        )
        safe_name = safe_name.strip().replace(" ", "_")
        filename = f"{safe_name}_{timestamp}.7z"

        # Determine output path
        created_temp_dir: Optional[Path] = None
        if output_dir is None:
            created_temp_dir = Path(tempfile.mkdtemp(prefix=SINGLE_EXPORT_DIR_PREFIX))
            output_dir = created_temp_dir
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
        archive_path = output_dir / filename

        try:
            # Create manifest
            manifest = self.create_manifest(
                workspace_id, workspace_name, workspace_path
            )

            # Create archive
            archive_size = self.create_archive(workspace_path, manifest, archive_path)

            logger.info(
                f"Exported workspace '{workspace_name}' to {archive_path} ({archive_size} bytes)"
            )

            return archive_path, ExportResult(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                filename=filename,
                size_bytes=archive_size,
                status=ExportStatus.SUCCESS,
            )

        except Exception as e:
            logger.exception(f"Failed to export workspace {workspace_id}")
            # Clean up partial archive (and private temp dir if we created it)
            if created_temp_dir is not None:
                shutil.rmtree(created_temp_dir, ignore_errors=True)
            elif archive_path.exists():
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

        # Resolve name conflict
        final_name = self._resolve_conflict(
            manifest.workspace_name, validation.conflict, conflict_resolution, new_name
        )

        return self._create_workspace_from_archive(archive_path, final_name, warnings)

    def _resolve_conflict(
        self,
        workspace_name: str,
        conflict: Optional[ImportConflict],
        conflict_resolution: Optional[ConflictResolution],
        new_name: Optional[str],
    ) -> str:
        """Resolve a workspace name conflict.

        Args:
            workspace_name: Original workspace name from manifest
            conflict: Detected conflict, if any
            conflict_resolution: How to handle the conflict
            new_name: Custom name if renaming

        Returns:
            Final workspace name to use

        Raises:
            ValueError: If conflict exists but no resolution specified
        """
        if not conflict:
            return workspace_name

        if conflict_resolution == ConflictResolution.RENAME:
            return new_name or conflict.suggested_name

        if conflict_resolution == ConflictResolution.REPLACE:
            try:
                self.storage.delete_workspace(conflict.existing_workspace_id)
            except (PathGuardError, ProtectedPathError) as exc:
                raise ValueError(
                    f"Existing workspace '{conflict.existing_workspace_id}' "
                    f"cannot be replaced safely: {exc}"
                ) from exc
            return workspace_name

        raise ValueError(
            f"Workspace name '{workspace_name}' already exists. "
            f"Specify conflict_resolution: 'rename' or 'replace'"
        )

    def _create_workspace_from_archive(
        self,
        archive_path: Path,
        final_name: str,
        warnings: List[str],
    ) -> ImportResponse:
        """Extract archive and create a new workspace from its contents.

        Args:
            archive_path: Path to 7z archive file
            final_name: Name to assign to the new workspace
            warnings: List to append warning messages to

        Returns:
            ImportResponse with import results
        """
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
                    warnings.append(
                        "Workspace checksum mismatch - file may have been modified"
                    )

            # Create new workspace
            new_workspace_id = str(uuid.uuid4())
            new_workspace_path = self.storage._workspace_path(new_workspace_id)
            new_workspace_path.mkdir(parents=True)

            # Copy extracted files (excluding manifest)
            for item in temp_path.iterdir():
                if item.name == "manifest.json":
                    continue
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
            workspace_data["updated_at"] = datetime.now(timezone.utc).isoformat()

            with open(workspace_json_path, "w") as f:
                json.dump(workspace_data, f, indent=2)

            normalize_extracted_permissions(new_workspace_path)

            # Keep imported file records inside the new workspace
            dropped_records = sanitize_parquet_index(
                new_workspace_path, new_workspace_id
            )
            if dropped_records > 0:
                warnings.append(
                    f"Skipped {dropped_records} imported file record(s) outside the workspace"
                )

            # Count scenarios
            scenario_count = self._count_scenarios(new_workspace_path)

            logger.info(f"Imported workspace '{final_name}' as {new_workspace_id}")

            return ImportResponse(
                workspace_id=new_workspace_id,
                name=final_name,
                scenario_count=scenario_count,
                status=ImportStatus.SUCCESS if not warnings else ImportStatus.PARTIAL,
                warnings=warnings,
            )

    def _count_scenarios(self, workspace_path: Path) -> int:
        """Count valid scenarios in a workspace directory.

        Args:
            workspace_path: Path to workspace directory

        Returns:
            Number of valid scenario directories found
        """
        scenarios_path = workspace_path / "scenarios"
        if not scenarios_path.exists():
            return 0
        return sum(
            1
            for d in scenarios_path.iterdir()
            if d.is_dir() and (d / "scenario.json").exists()
        )

    # ==================== Bulk Operations ====================

    def _prune_expired_bulk_export_ops(self, cutoff: datetime) -> None:
        """Clean up finished bulk-export operations created before ``cutoff``."""
        for op_id, created_at in list(self._bulk_export_created_at.items()):
            op = self._bulk_export_operations.get(op_id)
            in_progress = (
                op is not None and op.status == BulkOperationStatus.IN_PROGRESS
            )
            if created_at < cutoff and not in_progress:
                self.cleanup_bulk_export(op_id)

    def prune_stale_bulk_exports(
        self, max_age_seconds: float = BULK_EXPORT_MAX_AGE_SECONDS
    ) -> None:
        """Remove never-downloaded bulk exports older than ``max_age_seconds``.

        Also removes leftover ``planalign_bulk_export_*`` directories in the
        system temp directory, e.g. from before a server restart.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        self._prune_expired_bulk_export_ops(cutoff)
        active = set(self._bulk_export_dirs.values())
        root = Path(tempfile.gettempdir())
        for candidate in root.glob(f"{BULK_EXPORT_DIR_PREFIX}*"):
            if candidate in active or candidate.is_symlink() or not candidate.is_dir():
                continue
            try:
                stale = candidate.stat().st_mtime < cutoff.timestamp()
            except FileNotFoundError:
                continue
            if stale:
                shutil.rmtree(candidate, ignore_errors=True)

    def start_bulk_export(self, workspace_ids: List[str]) -> BulkExportStatus:
        """Start a bulk export operation.

        Args:
            workspace_ids: List of workspace UUIDs to export

        Returns:
            BulkExportStatus with operation ID for tracking
        """
        self.prune_stale_bulk_exports()
        operation_id = str(uuid.uuid4())
        status = BulkExportStatus(
            operation_id=operation_id,
            status=BulkOperationStatus.PENDING,
            total=len(workspace_ids),
            completed=0,
            results=[],
        )
        self._bulk_export_operations[operation_id] = status
        self._bulk_export_created_at[operation_id] = datetime.now(timezone.utc)
        self._export_temp_files[operation_id] = {}
        return status

    def execute_bulk_export(
        self, operation_id: str, workspace_ids: List[str]
    ) -> BulkExportStatus:
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

        # Create one private temp directory for this operation
        export_dir = Path(tempfile.mkdtemp(prefix=BULK_EXPORT_DIR_PREFIX))
        self._bulk_export_dirs[operation_id] = export_dir

        for workspace_id in workspace_ids:
            workspace = None
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
                status.results.append(
                    ExportResult(
                        workspace_id=workspace_id,
                        workspace_name=workspace.name if workspace else "Unknown",
                        status=ExportStatus.FAILED,
                        error=str(e),
                    )
                )

            status.completed += 1

        status.current_workspace = None
        status.status = (
            BulkOperationStatus.COMPLETED
            if all(r.status == ExportStatus.SUCCESS for r in status.results)
            else BulkOperationStatus.FAILED
        )

        if not self._export_temp_files.get(operation_id):
            shutil.rmtree(export_dir, ignore_errors=True)
            self._bulk_export_dirs.pop(operation_id, None)

        return status

    def get_bulk_export_status(self, operation_id: str) -> Optional[BulkExportStatus]:
        """Get status of a bulk export operation.

        Args:
            operation_id: Operation ID to check

        Returns:
            BulkExportStatus or None if not found
        """
        return self._bulk_export_operations.get(operation_id)

    def get_export_archive_path(
        self, operation_id: str, workspace_id: str
    ) -> Optional[Path]:
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

    def complete_bulk_export_download(
        self, operation_id: str, workspace_id: str
    ) -> None:
        """Remove a downloaded bulk-export archive and clean up once all are served."""
        operation_files = self._export_temp_files.get(operation_id)
        if operation_files is not None:
            archive_path = operation_files.pop(workspace_id, None)
            if archive_path is not None:
                try:
                    archive_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Could not remove bulk export archive %s",
                        archive_path,
                        exc_info=True,
                    )
        if not operation_files:
            self.cleanup_bulk_export(operation_id)

    def cleanup_bulk_export(self, operation_id: str) -> None:
        """Clean up temporary files and directory from bulk export.

        Args:
            operation_id: Operation ID to clean up
        """
        export_dir = self._bulk_export_dirs.pop(operation_id, None)
        if export_dir is not None:
            shutil.rmtree(export_dir, ignore_errors=True)

        # Remove any remaining temp files tracked outside export_dir
        remaining = self._export_temp_files.pop(operation_id, None)
        if remaining:
            for path in remaining.values():
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Could not remove bulk export file %s", path, exc_info=True
                    )

        # Remove from operations dicts
        self._bulk_export_operations.pop(operation_id, None)
        self._bulk_export_created_at.pop(operation_id, None)

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
        self._bulk_import_created_at[operation_id] = datetime.now(timezone.utc)
        self._prune_bulk_import_operations()
        return status

    def complete_bulk_import(self, operation_id: str) -> None:
        """Record terminal time so retention is measured after completion."""
        if operation_id in self._bulk_import_operations:
            self._bulk_import_terminal_at[operation_id] = datetime.now(timezone.utc)
            self._prune_bulk_import_operations()

    def get_bulk_import_status(self, operation_id: str) -> Optional[BulkImportStatus]:
        """Get status of a bulk import operation.

        Args:
            operation_id: Operation ID to check

        Returns:
            BulkImportStatus or None if not found
        """
        self._prune_bulk_import_operations()
        return self._bulk_import_operations.get(operation_id)
