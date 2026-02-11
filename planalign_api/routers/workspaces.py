"""Workspace management endpoints."""

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from ..config import APISettings, get_settings
from ..models.export import (
    BulkExportRequest,
    BulkExportStatus,
    BulkImportStatus,
    ConflictResolution,
    ExportResult,
    ImportResponse,
    ImportValidationResponse,
)
from ..models.workspace import (
    Workspace,
    WorkspaceCreate,
    WorkspaceSummary,
    WorkspaceUpdate,
)
from ..services.export_service import ExportService
from ..services.seed_config_validator import validate_seed_configs
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()

# In-memory storage for temporary upload files
_temp_upload_files: Dict[str, Path] = {}


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


def get_export_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> ExportService:
    """Dependency to get export service."""
    return ExportService(storage)


async def get_default_config(
    settings: APISettings = Depends(get_settings),
) -> Dict[str, Any]:
    """Get default configuration for new workspaces."""
    import yaml

    if settings.default_config_path.exists():
        with open(settings.default_config_path) as f:
            return yaml.safe_load(f)

    # Built-in defaults
    return {
        "simulation": {
            "start_year": 2025,
            "end_year": 2027,
            "random_seed": 42,
            "target_growth_rate": 0.03,
        },
        "compensation": {
            "cola_rate": 0.02,
            "merit_budget": 0.035,
        },
        "workforce": {
            "total_termination_rate": 0.12,
        },
        "enrollment": {
            "auto_enrollment": {"enabled": True},
        },
        "employer_match": {
            "active_formula": "simple_match",
            "formulas": {
                "simple_match": {
                    "name": "Simple Match",
                    "type": "simple",
                    "match_rate": 0.50,
                    "max_match_percentage": 0.06,
                },
            },
            # E046: New match mode defaults (empty tiers = not configured)
            "tenure_match_tiers": [],
            "points_match_tiers": [],
        },
        "employer_core_contribution": {
            "enabled": True,
            "status": "flat",
            "contribution_rate": 0.03,
        },
    }


@router.get("", response_model=List[WorkspaceSummary])
async def list_workspaces(
    storage: WorkspaceStorage = Depends(get_storage),
) -> List[WorkspaceSummary]:
    """
    List all workspaces.

    Returns summary information for each workspace including scenario count
    and storage usage.
    """
    return storage.list_workspaces()


@router.post("", response_model=Workspace, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    data: WorkspaceCreate,
    storage: WorkspaceStorage = Depends(get_storage),
    default_config: Dict[str, Any] = Depends(get_default_config),
) -> Workspace:
    """
    Create a new workspace.

    If no base_config is provided, uses the system default configuration.
    """
    return storage.create_workspace(data, default_config)


@router.get("/{workspace_id}", response_model=Workspace)
async def get_workspace(
    workspace_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Workspace:
    """
    Get a workspace by ID.

    Returns the full workspace including base configuration.
    """
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return workspace


@router.put("/{workspace_id}", response_model=Workspace)
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdate,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Workspace:
    """
    Update a workspace.

    Allows updating name, description, and base configuration.
    Validates seed config sections (promotion_hazard, age_bands, tenure_bands)
    atomically — if any section is invalid, the entire update is rejected.
    """
    # Validate seed config sections in base_config if present
    if data.base_config:
        errors = validate_seed_configs(data.base_config)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Validation failed",
                    "errors": [
                        {"section": e.section, "field": e.field, "message": e.message}
                        for e in errors
                    ],
                },
            )

    workspace = storage.update_workspace(
        workspace_id,
        name=data.name,
        description=data.description,
        base_config=data.base_config,
    )
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return workspace


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Dict[str, bool]:
    """
    Delete a workspace.

    WARNING: This deletes all scenarios and results in the workspace.
    """
    success = storage.delete_workspace(workspace_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return {"success": True}


# ==================== Export Endpoints ====================


@router.post("/{workspace_id}/export")
async def export_workspace(
    workspace_id: str,
    export_service: ExportService = Depends(get_export_service),
) -> FileResponse:
    """
    Export a workspace as a 7z archive.

    Returns a downloadable archive containing the workspace data and manifest.
    The archive filename includes the workspace name and timestamp.

    Raises:
        404: Workspace not found
        409: Simulation is currently running
    """
    try:
        archive_path, result = export_service.export_workspace(workspace_id)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        elif "simulation is running" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot export workspace while simulation is running",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg,
            )

    return FileResponse(
        path=archive_path,
        filename=result.filename,
        media_type="application/x-7z-compressed",
    )


@router.post("/bulk-export", response_model=BulkExportStatus)
async def start_bulk_export(
    request: BulkExportRequest,
    export_service: ExportService = Depends(get_export_service),
) -> BulkExportStatus:
    """
    Start a bulk export operation.

    Returns an operation ID for tracking progress.
    Use GET /bulk-export/{operation_id} to check status.
    """
    status_obj = export_service.start_bulk_export(request.workspace_ids)

    # Execute export in background (synchronously for now)
    export_service.execute_bulk_export(status_obj.operation_id, request.workspace_ids)

    return export_service.get_bulk_export_status(status_obj.operation_id)


@router.get("/bulk-export/{operation_id}", response_model=BulkExportStatus)
async def get_bulk_export_status(
    operation_id: str,
    export_service: ExportService = Depends(get_export_service),
) -> BulkExportStatus:
    """
    Get status of a bulk export operation.

    Returns progress information including completed exports.
    """
    status_obj = export_service.get_bulk_export_status(operation_id)
    if status_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Operation {operation_id} not found",
        )
    return status_obj


@router.get("/bulk-export/{operation_id}/download/{workspace_id}")
async def download_bulk_export(
    operation_id: str,
    workspace_id: str,
    export_service: ExportService = Depends(get_export_service),
) -> FileResponse:
    """
    Download an individual archive from a bulk export operation.

    Each workspace in a bulk export generates its own archive.
    """
    archive_path = export_service.get_export_archive_path(operation_id, workspace_id)
    if archive_path is None or not archive_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Archive not found for workspace {workspace_id} in operation {operation_id}",
        )

    return FileResponse(
        path=archive_path,
        filename=archive_path.name,
        media_type="application/x-7z-compressed",
    )


# ==================== Import Endpoints ====================


@router.post("/import/validate", response_model=ImportValidationResponse)
async def validate_import(
    file: UploadFile = File(...),
    export_service: ExportService = Depends(get_export_service),
) -> ImportValidationResponse:
    """
    Validate an archive before import.

    Checks archive integrity, manifest validity, and name conflicts.
    Returns validation result with any conflicts or warnings.
    """
    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_path = Path(temp_file.name)

    try:
        # Get file size
        file_size = len(content)

        # Validate archive
        result = export_service.validate_archive(temp_path, file_size)

        # Store temp file path for later import if valid
        if result.valid:
            # Generate a temp ID for this upload
            import uuid
            upload_id = str(uuid.uuid4())
            _temp_upload_files[upload_id] = temp_path
            # Add upload_id to response for import reference
            # Note: This is a workaround; ideally we'd use a session or multipart upload
        else:
            # Clean up invalid archive
            temp_path.unlink()

        return result

    except Exception as e:
        # Clean up on error
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation error: {str(e)}",
        )


@router.post("/import", response_model=ImportResponse)
async def import_workspace(
    file: UploadFile = File(...),
    conflict_resolution: Optional[str] = Form(None),
    new_name: Optional[str] = Form(None),
    export_service: ExportService = Depends(get_export_service),
) -> ImportResponse:
    """
    Import a workspace from a 7z archive.

    If a name conflict exists, provide conflict_resolution:
    - 'rename': Use new_name or auto-generated unique name
    - 'replace': Delete existing workspace and import
    - 'skip': Skip this import (not applicable for single import)
    """
    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_path = Path(temp_file.name)

    try:
        # Parse conflict resolution
        resolution = None
        if conflict_resolution:
            try:
                resolution = ConflictResolution(conflict_resolution)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid conflict_resolution: {conflict_resolution}. "
                           f"Valid values: rename, replace, skip",
                )

        # Import workspace
        result = export_service.import_workspace(
            archive_path=temp_path,
            conflict_resolution=resolution,
            new_name=new_name,
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


@router.post("/bulk-import", response_model=BulkImportStatus)
async def start_bulk_import(
    files: List[UploadFile] = File(...),
    default_resolution: Optional[str] = Form("rename"),
    export_service: ExportService = Depends(get_export_service),
) -> BulkImportStatus:
    """
    Start a bulk import operation.

    Uploads multiple archives and imports them sequentially.
    Default conflict resolution is 'rename' (auto-generate unique names).
    """
    # Start bulk import operation
    status_obj = export_service.start_bulk_import(file_count=len(files))

    # Parse default resolution
    resolution = ConflictResolution.RENAME
    if default_resolution:
        try:
            resolution = ConflictResolution(default_resolution)
        except ValueError:
            pass

    # Process each file
    for file in files:
        # Update current file in status
        status_obj.current_file = file.filename

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        try:
            # Import workspace
            result = export_service.import_workspace(
                archive_path=temp_path,
                conflict_resolution=resolution,
            )
            status_obj.results.append(result)
        except Exception as e:
            # Record failed import
            from ..models.export import ImportStatus
            status_obj.results.append(
                ImportResponse(
                    workspace_id="",
                    name=file.filename or "Unknown",
                    scenario_count=0,
                    status=ImportStatus.PARTIAL,
                    warnings=[str(e)],
                )
            )
        finally:
            # Clean up temp file
            if temp_path.exists():
                temp_path.unlink()

        status_obj.completed += 1

    # Update final status
    from ..models.export import BulkOperationStatus
    status_obj.current_file = None
    status_obj.status = BulkOperationStatus.COMPLETED

    return status_obj


@router.get("/bulk-import/{operation_id}", response_model=BulkImportStatus)
async def get_bulk_import_status(
    operation_id: str,
    export_service: ExportService = Depends(get_export_service),
) -> BulkImportStatus:
    """
    Get status of a bulk import operation.

    Returns progress information including imported workspaces.
    """
    status_obj = export_service.get_bulk_import_status(operation_id)
    if status_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Operation {operation_id} not found",
        )
    return status_obj
