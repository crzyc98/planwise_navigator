"""Public ticket redemption for browser-native streamed artifact downloads."""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..services.artifact_tickets import verify_artifact_ticket
from ..storage.workspace_storage import WorkspaceStorage
from .simulations import download_artifact, get_storage

router = APIRouter()


@router.get("/artifact-download/{ticket}", response_model=None)
def redeem_artifact_ticket(
    ticket: str, storage: WorkspaceStorage = Depends(get_storage)
) -> FileResponse:
    scenario_id, artifact_path = verify_artifact_ticket(ticket)
    response = download_artifact(scenario_id, artifact_path, storage)
    response.headers["Cache-Control"] = "private, no-store"
    return response
