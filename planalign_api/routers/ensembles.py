"""FastAPI router for Studio ensemble band charts (issue #554).

Backs the Studio Ensembles panel: read-only access to a client-selected
ensemble aggregate database (``ensemble.duckdb``, written by
``planalign_ensemble.aggregate``/``.attribution``). No dbt model, mart, or the
shared dev database (``dbt/simulation.duckdb``) is ever read or written here.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

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

router = APIRouter()


@router.get("/ensembles/discover", response_model=list[EnsembleDatabaseSummary])
def discover_ensembles(
    root: str | None = Query(default=None),
    settings: APISettings = Depends(get_settings),
) -> list[EnsembleDatabaseSummary]:
    """List ensemble databases under a scan root for the Studio picker."""
    scan_root = Path(root) if root else settings.ensembles_root
    try:
        return discover_ensemble_databases(scan_root)
    except InvalidEnsembleDatabaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ensembles/distributions", response_model=list[MetricDistribution])
def get_distributions(
    database: str, ensemble_scenario_id: str, ensemble_id: str
) -> list[MetricDistribution]:
    """Read P10-P90 distributions for one scenario/ensemble.

    The query param is named ``ensemble_scenario_id``, not ``scenario_id`` --
    it identifies a row in the ensemble database, not a workspace-scoped
    scenario resource, so it must not be mistaken for one of the run-tracked
    scenario reads that owe an ``X-PlanAlign-Run-*`` consistency header.
    """
    validated = _validate(database)
    return read_distributions(validated, ensemble_scenario_id, ensemble_id)


@router.get("/ensembles/risk", response_model=list[RiskStatement])
def get_risk(
    database: str,
    ensemble_scenario_id: str,
    ensemble_id: str,
    threshold: list[str] = Query(default=[]),
) -> list[RiskStatement]:
    """Evaluate ad hoc metric:value thresholds against stored seed evidence.

    Thresholds are never persisted in an ensemble database (they're CLI/config
    input only), so Studio supplies them per request, the same way
    ``--threshold metric:value`` does on the CLI.
    """
    validated = _validate(database)
    thresholds = [_parse_threshold(item) for item in threshold]
    return read_risk_statements(
        validated, ensemble_scenario_id, ensemble_id, thresholds
    )


@router.get("/ensembles/attribution", response_model=list[AttributionShare])
def get_attribution(
    database: str, ensemble_scenario_id: str, ensemble_id: str
) -> list[AttributionShare]:
    """Read variance attribution, ranked like the Excel Variance_Attribution sheet."""
    validated = _validate(database)
    return read_attribution(validated, ensemble_scenario_id, ensemble_id)


def _validate(database: str) -> Path:
    try:
        return validate_ensemble_database(Path(database))
    except InvalidEnsembleDatabaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
