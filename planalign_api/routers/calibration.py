"""FastAPI router for Fast Compensation Calibration (Feature 105).

Backs the Studio calibration panel: a single endpoint that triggers a comp-only
calibration run and returns the per-year results. The heavy build is offloaded
to a worker thread (sync `def` endpoint) so the event loop stays responsive.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import yaml  # type: ignore[import]
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from planalign_orchestrator.calibration_optimizer import (
    AutoCalibrationResult,
    AutoCalibrationSettings,
    AutoCalibrator,
)
from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
    CalibrationRunner,
    PerYearCompensationResult,
)
from planalign_orchestrator.exceptions import ConfigurationError

from ..config import APISettings, get_settings
from ..storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


class CalibrationRunRequest(BaseModel):
    """Request body for POST /api/calibration/run (contracts/api-calibration.md)."""

    start_year: int = Field(..., ge=2000)
    end_year: int = Field(..., ge=2000)
    config_path: Optional[str] = None
    database_path: Optional[str] = None
    # When set (and no explicit config_path), calibration runs against the
    # workspace's base config -- census, termination rates, everything -- so the
    # calibrated levers transfer to a full simulation of that workspace.
    workspace_id: Optional[str] = None
    params: CalibrationParameterSet = Field(default_factory=CalibrationParameterSet)


class CalibrationRunResponse(BaseModel):
    """Per-year calibration results for the requested range."""

    run_id: str
    results: List[PerYearCompensationResult]


def _workspace_config_path(
    workspace_id: str, storage: WorkspaceStorage
) -> Optional[Path]:
    """Materialize the workspace's base config as a YAML file for the runner.

    Resolves a workspace-relative census path to an absolute one (mirroring the
    simulation service) so the dbt staging rebuild reads the workspace's census.
    """
    workspace = storage.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=404, detail=f"Workspace {workspace_id} not found"
        )
    config = dict(workspace.base_config or {})
    if not config:
        return None

    setup = config.get("setup", {}) or {}
    census = setup.get("census_parquet_path")
    if census and not Path(census).is_absolute():
        candidate = storage._workspace_path(workspace_id) / census
        if candidate.exists():
            config.setdefault("setup", {})["census_parquet_path"] = str(
                candidate.resolve()
            )

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="calibration_config_", delete=False
    )
    with tmp:
        yaml.dump(config, tmp, default_flow_style=False)
    return Path(tmp.name)


@router.post("/calibration/run", response_model=CalibrationRunResponse)
def run_calibration(
    request: CalibrationRunRequest,
    storage: WorkspaceStorage = Depends(get_storage),
) -> CalibrationRunResponse:
    """Trigger a comp-only calibration run and return per-year results.

    Maps the prerequisite-guard failure to 409; pydantic validation errors are
    surfaced by FastAPI as 422 automatically.
    """
    config_path: Optional[Path] = (
        Path(request.config_path) if request.config_path else None
    )
    if config_path is None and request.workspace_id:
        config_path = _workspace_config_path(request.workspace_id, storage)

    try:
        run = CalibrationRun(
            start_year=request.start_year,
            end_year=request.end_year,
            config_path=config_path,
            database_path=(
                Path(request.database_path) if request.database_path else None
            ),
            params=request.params,
        )
    except ValueError as e:  # range ordering / param validation
        raise HTTPException(status_code=422, detail=str(e))

    try:
        results = CalibrationRunner(run, threads=1).run_calibration()
    except ConfigurationError as e:
        # Missing prerequisite DC tables, or a build failure with a clear cause.
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # pragma: no cover - unexpected runtime failure
        logger.exception("Calibration run failed")
        raise HTTPException(status_code=500, detail=str(e))

    run_id = f"cal_{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}"
    return CalibrationRunResponse(run_id=run_id, results=results)


class AutoCalibrationRequest(BaseModel):
    """Request body for POST /api/calibration/optimize.

    Set the two targets; the optimizer sets workforce growth directly (it is
    deterministic via E077) and searches COLA/merit until the mean YoY avg-comp
    growth is within tolerance of the comp target.
    """

    start_year: int = Field(..., ge=2000)
    end_year: int = Field(..., ge=2000)
    config_path: Optional[str] = None
    database_path: Optional[str] = None
    workspace_id: Optional[str] = None
    settings: AutoCalibrationSettings
    # Non-searched levers (age distribution, comp ranges) applied to every run.
    params: CalibrationParameterSet = Field(default_factory=CalibrationParameterSet)


class AutoCalibrationResponse(BaseModel):
    run_id: str
    outcome: AutoCalibrationResult


@router.post("/calibration/optimize", response_model=AutoCalibrationResponse)
def optimize_calibration(
    request: AutoCalibrationRequest,
    storage: WorkspaceStorage = Depends(get_storage),
) -> AutoCalibrationResponse:
    """Search for the COLA/merit that hit the target avg-comp growth.

    Runs several fast comp-only calibration builds (typically 3-6); expect a
    few minutes for a multi-year range.
    """
    if request.end_year <= request.start_year:
        raise HTTPException(
            status_code=422,
            detail="Auto-calibration needs at least a two-year range to "
            "measure year-over-year growth",
        )

    config_path: Optional[Path] = (
        Path(request.config_path) if request.config_path else None
    )
    if config_path is None and request.workspace_id:
        config_path = _workspace_config_path(request.workspace_id, storage)

    try:
        run = CalibrationRun(
            start_year=request.start_year,
            end_year=request.end_year,
            config_path=config_path,
            database_path=(
                Path(request.database_path) if request.database_path else None
            ),
            params=request.params,
        )
        optimizer = AutoCalibrator(run, request.settings, threads=1)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ConfigurationError as e:
        raise HTTPException(status_code=409, detail=str(e))

    try:
        outcome = optimizer.optimize()
    except ConfigurationError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # pragma: no cover - unexpected runtime failure
        logger.exception("Auto-calibration failed")
        raise HTTPException(status_code=500, detail=str(e))

    run_id = f"autocal_{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}"
    return AutoCalibrationResponse(run_id=run_id, outcome=outcome)
