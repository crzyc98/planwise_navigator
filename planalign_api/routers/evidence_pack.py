"""Authenticated scenario evidence-pack endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from planalign_evidence.cross_models import CrossScenarioEvidencePackEnvelope
from planalign_evidence.models import EvidencePackEnvelope, MetricId
from planalign_evidence.service import (
    EvidenceConflictError,
    EvidenceNotFoundError,
    UnsupportedEvidenceError,
)

from ..services.evidence_pack_service import (
    get_cross_scenario_evidence_pack as build_cross_pack,
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
    except (
        EvidenceNotFoundError,
        EvidenceConflictError,
        UnsupportedEvidenceError,
    ) as exc:
        raise _http_error(exc) from exc


@router.get(
    "/{workspace_id}/evidence-pack/compare",
    response_model=CrossScenarioEvidencePackEnvelope,
    name="get_cross_scenario_evidence_pack",
)
def get_cross_scenario_evidence_pack(
    workspace_id: str,
    scenario_a: str,
    scenario_b: str,
    metric: MetricId,
    year: int = Query(ge=1900, le=2200),
) -> CrossScenarioEvidencePackEnvelope:
    try:
        return build_cross_pack(workspace_id, scenario_a, scenario_b, metric, year)
    except (
        EvidenceNotFoundError,
        EvidenceConflictError,
        UnsupportedEvidenceError,
    ) as exc:
        raise _http_error(exc) from exc


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EvidenceNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, EvidenceConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    assert isinstance(exc, UnsupportedEvidenceError)
    detail = {
        "message": str(exc),
        "available_years": exc.available_years,
        "missing_columns": exc.missing_columns,
    }
    return HTTPException(status_code=422, detail=detail)
