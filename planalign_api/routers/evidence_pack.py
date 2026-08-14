"""Authenticated scenario evidence-pack endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from planalign_evidence.models import EvidencePackEnvelope, MetricId
from planalign_evidence.service import (
    EvidenceConflictError,
    EvidenceNotFoundError,
    UnsupportedEvidenceError,
)

from ..services.evidence_pack_service import get_scenario_evidence_pack as build_pack

router = APIRouter()


@router.get(
    "/{workspace_id}/scenarios/{scenario_id}/evidence-pack",
    response_model=EvidencePackEnvelope,
    name="get_scenario_evidence_pack",
)
def get_scenario_evidence_pack(
    workspace_id: str,
    scenario_id: str,
    metric: MetricId,
    base_year: int = Query(ge=1900, le=2200),
    target_year: int = Query(ge=1900, le=2200),
) -> EvidencePackEnvelope:
    try:
        return build_pack(workspace_id, scenario_id, metric, base_year, target_year)
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EvidenceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsupportedEvidenceError as exc:
        detail = {
            "message": str(exc),
            "available_years": exc.available_years,
            "missing_columns": exc.missing_columns,
        }
        raise HTTPException(status_code=422, detail=detail) from exc
