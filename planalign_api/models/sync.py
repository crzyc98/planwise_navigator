"""Sync models for workspace cloud synchronization (E083)."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SyncConfig(BaseModel):
    """Sync configuration for the workspace directory."""

    version: int = Field(default=1, description="Config format version")
    enabled: bool = Field(default=False, description="Whether sync is enabled")
    remote: Optional[str] = Field(None, description="Git remote URL")
    branch: str = Field(default="main", description="Git branch to sync with")
    auto_sync: bool = Field(default=False, description="Auto-sync on changes")
    conflict_strategy: Literal["last-write-wins", "ask-user", "keep-local", "keep-remote"] = Field(
        default="last-write-wins",
        description="Strategy for handling sync conflicts"
    )


class SyncStatus(BaseModel):
    """Current sync status."""

    is_initialized: bool = Field(..., description="Whether sync is set up")
    remote_url: Optional[str] = Field(None, description="Configured remote URL")
    branch: str = Field(default="main", description="Current branch")
    local_changes: int = Field(default=0, description="Number of uncommitted changes")
    ahead: int = Field(default=0, description="Commits ahead of remote")
    behind: int = Field(default=0, description="Commits behind remote")
    last_sync: Optional[datetime] = Field(None, description="Last successful sync timestamp")
    conflicts: List[str] = Field(default_factory=list, description="List of conflicting files")
    error: Optional[str] = Field(None, description="Last error message if any")


class SyncLogEntry(BaseModel):
    """A sync operation log entry."""

    timestamp: datetime = Field(..., description="When the operation occurred")
    operation: Literal["push", "pull", "init", "conflict", "disconnect"] = Field(
        ..., description="Type of sync operation"
    )
    workspaces_affected: int = Field(default=0, description="Number of workspaces affected")
    scenarios_affected: int = Field(default=0, description="Number of scenarios affected")
    message: str = Field(..., description="Human-readable description")
    commit_sha: Optional[str] = Field(None, description="Git commit SHA if applicable")
    success: bool = Field(default=True, description="Whether operation succeeded")


class SyncPushResult(BaseModel):
    """Result of a push operation."""

    success: bool = Field(..., description="Whether push succeeded")
    commit_sha: Optional[str] = Field(None, description="New commit SHA")
    files_pushed: int = Field(default=0, description="Number of files pushed")
    message: str = Field(..., description="Status message")


class SyncPullResult(BaseModel):
    """Result of a pull operation."""

    success: bool = Field(..., description="Whether pull succeeded")
    files_updated: int = Field(default=0, description="Number of files updated")
    files_added: int = Field(default=0, description="Number of files added")
    files_removed: int = Field(default=0, description="Number of files removed")
    conflicts: List[str] = Field(default_factory=list, description="Files with conflicts")
    message: str = Field(..., description="Status message")


class SyncInitRequest(BaseModel):
    """Request to initialize sync."""

    remote_url: str = Field(..., description="Git remote URL (e.g., git@github.com:user/repo.git)")
    branch: str = Field(default="main", description="Branch to use")
    auto_sync: bool = Field(default=False, description="Enable auto-sync")


class WorkspaceSyncInfo(BaseModel):
    """Sync information for a specific workspace."""

    workspace_id: str = Field(..., description="Workspace ID")
    workspace_name: str = Field(..., description="Workspace name")
    scenario_count: int = Field(default=0, description="Number of scenarios")
    has_local_changes: bool = Field(default=False, description="Whether there are uncommitted changes")
    last_synced: Optional[datetime] = Field(None, description="When this workspace was last synced")
