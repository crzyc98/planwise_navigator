"""File upload and validation router."""

import logging
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from ..config import get_settings
from ..models.files import (
    FileUploadResponse,
    FileValidationRequest,
    FileValidationResponse,
)
from ..services.file_service import FileService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_file_service() -> FileService:
    """Get file service instance."""
    settings = get_settings()
    return FileService(settings.workspaces_root)


@router.post(
    "/{workspace_id}/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload census file",
    description="Upload a census file (Parquet or CSV) to a workspace's data directory",
)
async def upload_census_file(
    workspace_id: str,
    file: UploadFile = File(..., description="Census file (.parquet or .csv)"),
) -> FileUploadResponse:
    """Upload a census file to a workspace."""
    service = get_file_service()

    # Validate file extension early
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided",
        )

    suffix = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if f".{suffix}" not in service.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File must be .parquet or .csv, got: .{suffix}",
        )

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {e}",
        )

    # Check file size
    if len(content) > service.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {service.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB limit",
        )

    # Save and validate file
    try:
        relative_path, metadata = service.save_uploaded_file(
            workspace_id=workspace_id,
            file_content=content,
            filename=file.filename,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error saving file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {e}",
        )

    return FileUploadResponse(
        success=True,
        file_path=relative_path,
        file_name=file.filename,
        file_size_bytes=metadata["file_size_bytes"],
        row_count=metadata["row_count"],
        columns=metadata["columns"],
        upload_timestamp=datetime.utcnow(),
        validation_warnings=metadata.get("validation_warnings", []),
    )


@router.post(
    "/{workspace_id}/validate-path",
    response_model=FileValidationResponse,
    summary="Validate file path",
    description="Validate a file path and return metadata if valid",
)
async def validate_file_path(
    workspace_id: str,
    request: FileValidationRequest,
) -> FileValidationResponse:
    """Validate a file path and return metadata."""
    service = get_file_service()

    result = service.validate_path(
        workspace_id=workspace_id,
        file_path=request.file_path,
    )

    return FileValidationResponse(
        file_path=request.file_path,
        **result,
    )
