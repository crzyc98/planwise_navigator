"""Export and import models for workspace backup functionality."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ManifestContents(BaseModel):
    """Inventory section of the export manifest for validation."""

    scenario_count: int = Field(..., ge=0, description="Number of scenarios included")
    scenarios: List[str] = Field(..., description="List of scenario names")
    file_count: int = Field(..., ge=0, description="Total files in archive")
    total_size_bytes: int = Field(..., ge=0, description="Uncompressed size in bytes")
    checksum_sha256: str = Field(..., description="SHA256 of workspace.json for integrity")


class ExportManifest(BaseModel):
    """Manifest file included in every workspace archive for integrity and version tracking."""

    version: str = Field(default="1.0", description="Manifest schema version")
    export_date: datetime = Field(..., description="ISO 8601 timestamp when export was created")
    app_version: str = Field(..., description="PlanAlign version that created the export")
    workspace_id: str = Field(..., description="Original workspace UUID")
    workspace_name: str = Field(..., description="Human-readable workspace name")
    contents: ManifestContents = Field(..., description="Inventory of archive contents")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class ExportStatus(str, Enum):
    """Status of an export operation."""
    SUCCESS = "success"
    FAILED = "failed"


class ExportResult(BaseModel):
    """Result for a single workspace export."""

    workspace_id: str = Field(..., description="UUID of exported workspace")
    workspace_name: str = Field(..., description="Name of exported workspace")
    filename: str = Field(default="", description="Generated archive filename")
    size_bytes: int = Field(default=0, ge=0, description="Archive size in bytes")
    status: ExportStatus = Field(..., description="Export status")
    error: Optional[str] = Field(None, description="Error message if failed")


class BulkExportRequest(BaseModel):
    """Request model for bulk export operation."""

    workspace_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of workspace UUIDs to export"
    )


class BulkOperationStatus(str, Enum):
    """Status of a bulk operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class BulkExportStatus(BaseModel):
    """Progress tracking for bulk export operations."""

    operation_id: str = Field(..., description="Unique ID for tracking operation")
    status: BulkOperationStatus = Field(..., description="Operation status")
    total: int = Field(..., ge=0, description="Total workspaces to export")
    completed: int = Field(default=0, ge=0, description="Number completed so far")
    current_workspace: Optional[str] = Field(None, description="Name of workspace currently being processed")
    results: List[ExportResult] = Field(default_factory=list, description="Results for completed exports")


class ImportConflict(BaseModel):
    """Details about a workspace name conflict."""

    existing_workspace_id: str = Field(..., description="UUID of conflicting workspace")
    existing_workspace_name: str = Field(..., description="Name of existing workspace")
    suggested_name: str = Field(..., description="Auto-generated alternative name")


class ImportValidationResponse(BaseModel):
    """Result of archive validation."""

    valid: bool = Field(..., description="Whether archive is valid for import")
    manifest: Optional[ExportManifest] = Field(None, description="Parsed manifest if valid")
    conflict: Optional[ImportConflict] = Field(None, description="Conflict details if name collision")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking warnings")
    errors: List[str] = Field(default_factory=list, description="Blocking errors (if invalid)")


class ConflictResolution(str, Enum):
    """How to handle import name conflicts."""
    RENAME = "rename"
    REPLACE = "replace"
    SKIP = "skip"


class ImportStatus(str, Enum):
    """Status of an import operation."""
    SUCCESS = "success"
    PARTIAL = "partial"


class ImportResponse(BaseModel):
    """Result of import operation."""

    workspace_id: str = Field(..., description="UUID of imported workspace")
    name: str = Field(..., description="Final workspace name")
    scenario_count: int = Field(..., ge=0, description="Number of scenarios imported")
    status: ImportStatus = Field(..., description="Import status")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking issues encountered")


class BulkImportStatus(BaseModel):
    """Progress tracking for bulk import operations."""

    operation_id: str = Field(..., description="Unique ID for tracking operation")
    status: BulkOperationStatus = Field(..., description="Operation status")
    total: int = Field(..., ge=0, description="Total archives to import")
    completed: int = Field(default=0, ge=0, description="Number completed so far")
    current_file: Optional[str] = Field(None, description="Name of file currently being processed")
    results: List[ImportResponse] = Field(default_factory=list, description="Results for completed imports")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error context")
