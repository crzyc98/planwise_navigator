"""Scenario report download endpoints."""

from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import APISettings, get_settings
from ..services.report_service import (
    ReportNotFoundError,
    build_scenario_report,
    render_report,
)
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()


@router.get("/{workspace_id}/scenarios/{scenario_id}/report")
def download_scenario_report(
    workspace_id: str,
    scenario_id: str,
    format: str = Query("pdf", pattern="^(pdf|pptx|html)$"),
    compare: str
    | None = Query(None, description="Comma-separated comparison scenario IDs"),
    settings: APISettings = Depends(get_settings),
) -> FileResponse:
    storage = WorkspaceStorage(settings.workspaces_root)
    try:
        report = build_scenario_report(
            storage,
            workspace_id,
            scenario_id,
            [item.strip() for item in compare.split(",") if item.strip()]
            if compare
            else None,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    directory = TemporaryDirectory(prefix="planalign-report-")
    output = Path(directory.name) / f"{scenario_id}-report.{format}"
    try:
        render_report(report, output, format)
    except RuntimeError as exc:
        directory.cleanup()
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    response = FileResponse(
        output,
        filename=output.name,
        media_type={
            "pdf": "application/pdf",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "html": "text/html",
        }[format],
    )
    response.background = _cleanup(directory)
    return response


def _cleanup(directory: TemporaryDirectory):
    from starlette.background import BackgroundTask

    return BackgroundTask(directory.cleanup)
