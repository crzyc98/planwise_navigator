"""Sync API endpoints for workspace cloud synchronization (E083)."""

from typing import List

from fastapi import APIRouter, HTTPException

from ..models.sync import (
    SyncConfig,
    SyncStatus,
    SyncLogEntry,
    SyncPushResult,
    SyncPullResult,
    SyncInitRequest,
    WorkspaceSyncInfo,
)
from ..services.sync_service import (
    SyncService,
    SyncError,
    SyncAuthError,
    SyncConflictError,
    GIT_AVAILABLE,
)

router = APIRouter(prefix="/sync", tags=["sync"])


def get_sync_service() -> SyncService:
    """Get sync service instance."""
    if not GIT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="GitPython is required for sync functionality. Install with: pip install GitPython"
        )
    return SyncService()


@router.get("/status", response_model=SyncStatus)
async def get_sync_status():
    """Get current sync status.

    Returns information about:
    - Whether sync is initialized
    - Configured remote and branch
    - Number of local changes
    - Ahead/behind remote status
    """
    try:
        service = get_sync_service()
        return service.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=SyncConfig)
async def get_sync_config():
    """Get sync configuration."""
    try:
        service = get_sync_service()
        return service.get_sync_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/init", response_model=SyncStatus)
async def init_sync(request: SyncInitRequest):
    """Initialize sync with a Git remote.

    Sets up Git-based synchronization for all workspaces.
    Creates necessary .gitignore and configuration files.
    """
    try:
        service = get_sync_service()
        return service.init(
            remote_url=request.remote_url,
            branch=request.branch,
            auto_sync=request.auto_sync,
        )
    except SyncAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/push", response_model=SyncPushResult)
async def push_changes(message: str = None):
    """Push local changes to remote.

    Stages all workspace metadata files and pushes to the configured remote.
    Large files (databases, exports) are automatically excluded.
    """
    try:
        service = get_sync_service()

        if not service.is_initialized():
            raise HTTPException(
                status_code=400,
                detail="Sync not initialized. Call POST /api/sync/init first."
            )

        return service.push(message=message)
    except SyncAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pull", response_model=SyncPullResult)
async def pull_changes():
    """Pull remote changes to local workspaces.

    Fetches and merges changes from the remote repository.
    Conflicts are handled according to the configured strategy.
    """
    try:
        service = get_sync_service()

        if not service.is_initialized():
            raise HTTPException(
                status_code=400,
                detail="Sync not initialized. Call POST /api/sync/init first."
            )

        return service.pull()
    except SyncAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except SyncConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(e),
                "conflicts": e.conflicting_files,
            }
        )
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log", response_model=List[SyncLogEntry])
async def get_sync_log(limit: int = 20):
    """Get sync operation history.

    Returns recent push, pull, and other sync operations.
    """
    try:
        service = get_sync_service()
        return service.get_sync_log(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces", response_model=List[WorkspaceSyncInfo])
async def get_workspace_sync_info():
    """Get sync information for all workspaces.

    Returns status of each workspace including whether
    it has local changes pending sync.
    """
    try:
        service = get_sync_service()
        return service.get_workspace_sync_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect_sync():
    """Disconnect sync from remote.

    Removes Git remote configuration but preserves local files.
    """
    try:
        service = get_sync_service()

        if not service.is_initialized():
            return {"success": True, "message": "Sync was not initialized"}

        success = service.disconnect()
        if success:
            return {"success": True, "message": "Sync disconnected. Local files preserved."}
        else:
            raise HTTPException(status_code=500, detail="Failed to disconnect sync")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
