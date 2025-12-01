"""File upload and validation models."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """Response after successful file upload."""

    success: bool = Field(..., description="Whether upload was successful")
    file_path: str = Field(..., description="Relative path to uploaded file within workspace")
    file_name: str = Field(..., description="Original filename")
    file_size_bytes: int = Field(..., description="File size in bytes")
    row_count: int = Field(..., description="Number of rows in the file")
    columns: List[str] = Field(..., description="List of column names")
    upload_timestamp: datetime = Field(..., description="When the file was uploaded")
    validation_warnings: List[str] = Field(
        default_factory=list, description="Non-fatal validation warnings"
    )


class FileValidationRequest(BaseModel):
    """Request to validate a file path."""

    file_path: str = Field(..., description="File path to validate (relative or absolute)")


class FileValidationResponse(BaseModel):
    """Response from file path validation."""

    valid: bool = Field(..., description="Whether the file is valid and readable")
    file_path: str = Field(..., description="The validated file path")
    exists: bool = Field(..., description="Whether the file exists")
    readable: bool = Field(default=False, description="Whether the file can be read")
    file_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    row_count: Optional[int] = Field(None, description="Number of rows in the file")
    columns: Optional[List[str]] = Field(None, description="List of column names")
    last_modified: Optional[datetime] = Field(None, description="Last modification timestamp")
    error_message: Optional[str] = Field(None, description="Error message if validation failed")
