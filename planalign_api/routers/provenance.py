"""Authenticated read-only archived run provenance endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..models.provenance import ProvenanceReportEnvelope
from ..services.provenance.locator import (
    ArchiveUnstableError,
    IdentityConflictError,
    RunNotFoundError,
)
from ..services.provenance.render import render_markdown, render_zip
from ..services.provenance.report import build_provenance_report

router = APIRouter()


@router.get("/runs/{run_id}/provenance", response_model=ProvenanceReportEnvelope)
def get_run_provenance(
    run_id: str,
    accept: str = Header(default="application/json"),
) -> Response:
    """Generate both representations from one exact archived run."""
    media_type = accept.split(",", 1)[0].split(";", 1)[0].strip().lower()
    if media_type in {"*/*", ""}:
        media_type = "application/json"
    if media_type not in {"application/json", "application/zip"}:
        raise HTTPException(
            status_code=406, detail="unsupported provenance representation"
        )
    try:
        report = build_provenance_report(get_settings().workspaces_root, run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArchiveUnstableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IdentityConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_sheet = render_markdown(report)
    headers = {"ETag": f'"{report.digest.value}"', "Cache-Control": "no-store"}
    if media_type == "application/zip":
        return Response(
            render_zip(run_id, report, audit_sheet),
            media_type="application/zip",
            headers={
                **headers,
                "Content-Disposition": f'attachment; filename="{run_id}-provenance.zip"',
            },
        )
    envelope = ProvenanceReportEnvelope(report=report, audit_sheet=audit_sheet)
    return JSONResponse(envelope.model_dump(mode="json"), headers=headers)
