"""FastAPI router for Studio parameter fit & backtest (issue #588).

Backs the Studio "Fit & Backtest" page. History uploads are validated by the
fitter itself; fit/backtest jobs run as cancellable ``planalign`` CLI
subprocesses, so POST returns 202 immediately and clients poll the job. Job
records persist on disk per workspace and survive an API restart. Applying a
pack always creates a new scenario after a fingerprint-verified review. The
shared development database is never read or written.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from ..config import APISettings, get_settings
from ..models.param_fit import (
    ApplyPreview,
    ApplyRequest,
    HistorySet,
    ParamFitJob,
    ParamFitJobSummary,
    ParamFitRequest,
)
from ..models.scenario import Scenario
from ..services.param_fit import ParamFitError, ParamFitService, UploadedFile
from ..storage.workspace_storage import WorkspaceStorage
from .files import MAX_UPLOAD_SIZE

router = APIRouter()


def get_param_fit_service(
    settings: APISettings = Depends(get_settings),
) -> ParamFitService:
    return ParamFitService(
        WorkspaceStorage(settings.workspaces_root),
        max_jobs_per_workspace=settings.param_fit_max_jobs_per_workspace,
    )


def _error(exc: ParamFitError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content={"detail": exc.detail, **exc.extra}
    )


# ---------------------------------------------------------------------------
# History sets
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/fit-history",
    response_model=HistorySet,
    status_code=status.HTTP_201_CREATED,
)
async def upload_fit_history(
    workspace_id: str,
    files: list[UploadFile] = File(..., description="2-5 annual census snapshots"),
    service: ParamFitService = Depends(get_param_fit_service),
) -> HistorySet | JSONResponse:
    """Upload and validate a census history set (validated by the fitter)."""
    uploads = [await _read_upload(upload) for upload in files]
    try:
        return service.create_history(workspace_id, uploads)
    except ParamFitError as exc:
        return _error(exc)


@router.get("/{workspace_id}/fit-history", response_model=list[HistorySet])
def list_fit_history(
    workspace_id: str, service: ParamFitService = Depends(get_param_fit_service)
) -> list[HistorySet] | JSONResponse:
    try:
        return service.list_history(workspace_id)
    except ParamFitError as exc:
        return _error(exc)


@router.get("/{workspace_id}/fit-history/{history_id}", response_model=HistorySet)
def get_fit_history(
    workspace_id: str,
    history_id: str,
    service: ParamFitService = Depends(get_param_fit_service),
) -> HistorySet | JSONResponse:
    """Re-hash and re-validate a stored history set."""
    try:
        return service.get_history(workspace_id, history_id)
    except ParamFitError as exc:
        return _error(exc)


@router.delete(
    "/{workspace_id}/fit-history/{history_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_fit_history(
    workspace_id: str,
    history_id: str,
    service: ParamFitService = Depends(get_param_fit_service),
) -> Response:
    try:
        service.delete_history(workspace_id, history_id)
    except ParamFitError as exc:
        return _error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/param-fits",
    response_model=ParamFitJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_param_fit(
    workspace_id: str,
    request: ParamFitRequest,
    service: ParamFitService = Depends(get_param_fit_service),
) -> ParamFitJob | JSONResponse:
    """Enqueue a fit or fit+backtest job; poll GET …/param-fits/{job_id}."""
    try:
        return service.start(workspace_id, request)
    except ParamFitError as exc:
        return _error(exc)


@router.get("/{workspace_id}/param-fits", response_model=list[ParamFitJobSummary])
def list_param_fits(
    workspace_id: str, service: ParamFitService = Depends(get_param_fit_service)
) -> list[ParamFitJobSummary] | JSONResponse:
    try:
        return service.list_jobs(workspace_id)
    except ParamFitError as exc:
        return _error(exc)


@router.get("/{workspace_id}/param-fits/{job_id}", response_model=ParamFitJob)
def get_param_fit(
    workspace_id: str,
    job_id: str,
    service: ParamFitService = Depends(get_param_fit_service),
) -> ParamFitJob | JSONResponse:
    """Job status, progress, and — once completed — its result."""
    try:
        return service.get(workspace_id, job_id)
    except ParamFitError as exc:
        return _error(exc)


@router.post("/{workspace_id}/param-fits/{job_id}/cancel", response_model=ParamFitJob)
def cancel_param_fit(
    workspace_id: str,
    job_id: str,
    service: ParamFitService = Depends(get_param_fit_service),
) -> ParamFitJob | JSONResponse:
    """Stop a queued/running job and remove its partial artifacts."""
    try:
        return service.cancel(workspace_id, job_id)
    except ParamFitError as exc:
        return _error(exc)


@router.get(
    "/{workspace_id}/param-fits/{job_id}/reports/{kind}",
    response_class=PlainTextResponse,
    response_model=None,
)
def get_param_fit_report(
    workspace_id: str,
    job_id: str,
    kind: Literal["fit", "scorecard"],
    service: ParamFitService = Depends(get_param_fit_service),
) -> Response:
    """The written fit report or backtest scorecard (Markdown)."""
    try:
        text = service.report(workspace_id, job_id, kind)
    except ParamFitError as exc:
        return _error(exc)
    return PlainTextResponse(text, media_type="text/markdown")


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/param-fits/{job_id}/apply-preview", response_model=ApplyPreview
)
def preview_param_pack_apply(
    workspace_id: str,
    job_id: str,
    source_scenario_id: str = Query(..., min_length=1),
    service: ParamFitService = Depends(get_param_fit_service),
) -> ApplyPreview | JSONResponse:
    """What applying this pack to a source scenario would change and require."""
    try:
        return service.apply_preview(workspace_id, job_id, source_scenario_id)
    except ParamFitError as exc:
        return _error(exc)


@router.post(
    "/{workspace_id}/param-fits/{job_id}/apply",
    response_model=Scenario,
    status_code=status.HTTP_201_CREATED,
)
def apply_param_pack(
    workspace_id: str,
    job_id: str,
    request: ApplyRequest,
    service: ParamFitService = Depends(get_param_fit_service),
) -> Scenario | JSONResponse:
    """Create a NEW scenario from a reviewed pack; the source is never modified."""
    try:
        return service.apply(workspace_id, job_id, request)
    except ParamFitError as exc:
        return _error(exc)


async def _read_upload(upload: UploadFile) -> UploadedFile:
    """Read one upload in chunks, refusing anything over the size limit."""
    if upload.size and upload.size > MAX_UPLOAD_SIZE:
        raise _too_large()
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(1024 * 1024):
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            raise _too_large()
        chunks.append(chunk)
    return UploadedFile(filename=upload.filename or "", content=b"".join(chunks))


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail=f"Each file must be at most {MAX_UPLOAD_SIZE // (1024 * 1024)}MB",
    )
