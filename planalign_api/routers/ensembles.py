"""FastAPI router for Studio ensemble band charts (issue #554) and jobs.

Backs the Studio Ensembles panel: read-only access to a client-selected
ensemble aggregate database (``ensemble.duckdb``, written by
``planalign_ensemble.aggregate``/``.attribution``). No dbt model, mart, or the
shared dev database (``dbt/simulation.duckdb``) is ever read or written here.

The workspace-scoped job endpoints start a seed ensemble for one scenario
(``planalign simulate --seed-list`` as a subprocess), report its estimate and
per-seed progress, and cancel it. Output stays under the workspace; a finished
job's record names the database, ``ensemble_id`` and ``ensemble_scenario_id``
to pass to the reader endpoints above.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, status

from planalign_ensemble.models import (
    AttributionShare,
    MetricDistribution,
    RiskStatement,
    Threshold,
)
from planalign_ensemble.studio_reader import (
    EnsembleDatabaseSummary,
    InvalidEnsembleDatabaseError,
    discover_ensemble_databases,
    read_attribution,
    read_distributions,
    read_risk_statements,
    validate_ensemble_database,
)

from ..config import APISettings, get_settings
from ..models.ensemble_job import (
    EnsembleCostRanges,
    EnsembleEstimate,
    EnsembleJob,
    EnsembleRequest,
)
from ..services.ensemble_jobs import EnsembleJobError, EnsembleJobService
from ..services.path_guard import PathGuardError, resolve_within_roots
from ..storage.workspace_storage import WorkspaceStorage

router = APIRouter()

# One message for outside, missing and unusable paths, so a response never
# tells a caller whether some path exists on the server.
_ROOT_NOT_FOUND = "ensemble directory not found"
_DATABASE_NOT_FOUND = "ensemble database not found"


def get_ensemble_job_service(
    settings: APISettings = Depends(get_settings),
) -> EnsembleJobService:
    return EnsembleJobService(WorkspaceStorage(settings.workspaces_root))


@router.get("/ensembles/discover", response_model=list[EnsembleDatabaseSummary])
def discover_ensembles(
    root: str | None = Query(default=None),
    settings: APISettings = Depends(get_settings),
) -> list[EnsembleDatabaseSummary]:
    """List ensemble databases under a scan root for the Studio picker."""
    # The root, and each database found under it, must resolve inside the
    # ensemble roots, so a link inside a root never leads outside it.
    roots = settings.ensemble_roots
    try:
        scan_root = resolve_within_roots(
            root or settings.ensembles_root, roots, anchor=settings.ensembles_root
        )
        return discover_ensemble_databases(
            scan_root, include=lambda path: _is_contained(path, roots)
        )
    except (PathGuardError, InvalidEnsembleDatabaseError) as exc:
        raise HTTPException(status_code=404, detail=_ROOT_NOT_FOUND) from exc


@router.get("/ensembles/distributions", response_model=list[MetricDistribution])
def get_distributions(
    database: str,
    ensemble_scenario_id: str,
    ensemble_id: str,
    settings: APISettings = Depends(get_settings),
) -> list[MetricDistribution]:
    """Read P10-P90 distributions for one scenario/ensemble.

    The query param is named ``ensemble_scenario_id``, not ``scenario_id`` --
    it identifies a row in the ensemble database, not a workspace-scoped
    scenario resource, so it must not be mistaken for one of the run-tracked
    scenario reads that owe an ``X-PlanAlign-Run-*`` consistency header.
    """
    validated = _validate(database, settings)
    return read_distributions(validated, ensemble_scenario_id, ensemble_id)


@router.get("/ensembles/risk", response_model=list[RiskStatement])
def get_risk(
    database: str,
    ensemble_scenario_id: str,
    ensemble_id: str,
    threshold: list[str] = Query(default=[]),
    settings: APISettings = Depends(get_settings),
) -> list[RiskStatement]:
    """Evaluate ad hoc metric:value thresholds against stored seed evidence.

    Thresholds are never persisted in an ensemble database (they're CLI/config
    input only), so Studio supplies them per request, the same way
    ``--threshold metric:value`` does on the CLI.
    """
    validated = _validate(database, settings)
    thresholds = [_parse_threshold(item) for item in threshold]
    return read_risk_statements(
        validated, ensemble_scenario_id, ensemble_id, thresholds
    )


@router.get("/ensembles/attribution", response_model=list[AttributionShare])
def get_attribution(
    database: str,
    ensemble_scenario_id: str,
    ensemble_id: str,
    settings: APISettings = Depends(get_settings),
) -> list[AttributionShare]:
    """Read variance attribution, ranked like the Excel Variance_Attribution sheet."""
    validated = _validate(database, settings)
    return read_attribution(validated, ensemble_scenario_id, ensemble_id)


@router.post(
    "/workspaces/{workspace_id}/scenarios/{scenario_id}/ensembles/estimate",
    response_model=EnsembleEstimate,
)
def estimate_ensemble(
    workspace_id: str,
    scenario_id: str,
    request: EnsembleRequest,
    service: EnsembleJobService = Depends(get_ensemble_job_service),
) -> EnsembleEstimate:
    """Seeds, run count, time and disk an ensemble would take; starts nothing."""
    with _job_errors():
        return service.estimate(workspace_id, scenario_id, request)


@router.post(
    "/workspaces/{workspace_id}/scenarios/{scenario_id}/ensembles",
    response_model=EnsembleJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_ensemble(
    workspace_id: str,
    scenario_id: str,
    request: EnsembleRequest,
    service: EnsembleJobService = Depends(get_ensemble_job_service),
) -> EnsembleJob:
    """Queue a seed ensemble; it waits for a simulation slot like any run."""
    with _job_errors():
        return service.start(workspace_id, scenario_id, request)


@router.get("/workspaces/{workspace_id}/ensembles", response_model=list[EnsembleJob])
def list_ensemble_jobs(
    workspace_id: str,
    scenario_id: str | None = Query(default=None),
    service: EnsembleJobService = Depends(get_ensemble_job_service),
) -> list[EnsembleJob]:
    """A workspace's ensemble jobs, newest first, optionally for one scenario."""
    with _job_errors():
        return service.list_jobs(workspace_id, scenario_id)


@router.get(
    "/workspaces/{workspace_id}/ensembles/cost-ranges",
    response_model=EnsembleCostRanges,
)
def get_ensemble_cost_ranges(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated compared scenario IDs"),
    anchor: str = Query(..., description="Anchor scenario ID, one of `scenarios`"),
    service: EnsembleJobService = Depends(get_ensemble_job_service),
) -> EnsembleCostRanges:
    """Seed ranges beside Cost Comparison's gross employer cost.

    Each scenario's latest finished ensemble gives P10-P90 of annual and total
    employer cost; a scenario whose ensemble ran on the anchor's seeds and
    years also gets its difference from the anchor, taken seed by seed.
    Registered before ``/ensembles/{job_id}`` so the path isn't read as a job id.
    """
    scenario_ids = list(
        dict.fromkeys(item.strip() for item in scenarios.split(",") if item.strip())
    )
    with _job_errors():
        return service.cost_ranges(workspace_id, scenario_ids, anchor.strip())


@router.get("/workspaces/{workspace_id}/ensembles/{job_id}", response_model=EnsembleJob)
def get_ensemble_job(
    workspace_id: str,
    job_id: str,
    service: EnsembleJobService = Depends(get_ensemble_job_service),
) -> EnsembleJob:
    with _job_errors():
        return service.get(workspace_id, job_id)


@router.post(
    "/workspaces/{workspace_id}/ensembles/{job_id}/cancel", response_model=EnsembleJob
)
def cancel_ensemble_job(
    workspace_id: str,
    job_id: str,
    service: EnsembleJobService = Depends(get_ensemble_job_service),
) -> EnsembleJob:
    """Stop a queued or running ensemble and its whole process tree."""
    with _job_errors():
        return service.cancel(workspace_id, job_id)


@contextmanager
def _job_errors() -> Iterator[None]:
    try:
        yield
    except EnsembleJobError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


def _validate(database: str, settings: APISettings) -> Path:
    """Contain ``database`` in the ensemble roots before anything opens it."""
    try:
        contained = resolve_within_roots(
            database, settings.ensemble_roots, anchor=settings.ensembles_root
        )
        return validate_ensemble_database(contained)
    except (PathGuardError, InvalidEnsembleDatabaseError, duckdb.Error) as exc:
        raise HTTPException(status_code=404, detail=_DATABASE_NOT_FOUND) from exc


def _is_contained(path: Path, roots: list[Path]) -> bool:
    try:
        resolve_within_roots(path, roots)
    except PathGuardError:
        return False
    return True


def _parse_threshold(raw: str) -> Threshold:
    metric, _, raw_value = raw.partition(":")
    if not metric.strip() or not raw_value.strip():
        raise HTTPException(
            status_code=422, detail=f"threshold must use metric:value form, got '{raw}'"
        )
    try:
        return Threshold(metric=metric, value=float(raw_value))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"threshold value must be numeric, got '{raw}'"
        ) from exc
