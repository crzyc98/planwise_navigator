"""Workspace models."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    """Request model for creating a workspace."""

    name: str = Field(..., min_length=1, max_length=100, description="Workspace name")
    description: Optional[str] = Field(None, max_length=500, description="Workspace description")
    base_config: Optional[Dict[str, Any]] = Field(
        None, description="Base configuration (uses defaults if not provided)"
    )


class WorkspaceUpdate(BaseModel):
    """Request model for updating a workspace."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    base_config: Optional[Dict[str, Any]] = None


class Workspace(BaseModel):
    """Full workspace model."""

    id: str = Field(..., description="Unique workspace ID (UUID)")
    name: str = Field(..., description="Workspace name")
    description: Optional[str] = Field(None, description="Workspace description")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    base_config: Dict[str, Any] = Field(..., description="Base simulation configuration")
    storage_path: str = Field(..., description="Absolute path to workspace directory")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Path: str,
        }


class WorkspaceSummary(BaseModel):
    """Lightweight workspace model for list views."""

    id: str = Field(..., description="Unique workspace ID")
    name: str = Field(..., description="Workspace name")
    description: Optional[str] = Field(None, description="Workspace description")
    created_at: datetime = Field(..., description="Creation timestamp")
    scenario_count: int = Field(default=0, description="Number of scenarios")
    last_run_at: Optional[datetime] = Field(None, description="Last simulation run timestamp")
    storage_used_mb: float = Field(default=0.0, description="Storage used in MB")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
