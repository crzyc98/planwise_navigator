"""FastAPI router for Fast Compensation Calibration (Feature 105).

Backs the Studio calibration panel: a single endpoint that triggers a comp-only
calibration run and returns the per-year results. The heavy build is offloaded
to a worker thread (sync `def` endpoint) so the event loop stays responsive.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
    CalibrationRunner,
    PerYearCompensationResult,
)
from planalign_orchestrator.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

router = APIRouter()


class CalibrationRunRequest(BaseModel):
    """Request body for POST /api/calibration/run (contracts/api-calibration.md)."""

    start_year: int = Field(..., ge=2000)
    end_year: int = Field(..., ge=2000)
    config_path: Optional[str] = None
    database_path: Optional[str] = None
    params: CalibrationParameterSet = Field(default_factory=CalibrationParameterSet)


class CalibrationRunResponse(BaseModel):
    """Per-year calibration results for the requested range."""

    run_id: str
    results: List[PerYearCompensationResult]


@router.post("/calibration/run", response_model=CalibrationRunResponse)
def run_calibration(request: CalibrationRunRequest) -> CalibrationRunResponse:
    """Trigger a comp-only calibration run and return per-year results.

    Maps the prerequisite-guard failure to 409; pydantic validation errors are
    surfaced by FastAPI as 422 automatically.
    """
    try:
        run = CalibrationRun(
            start_year=request.start_year,
            end_year=request.end_year,
            config_path=Path(request.config_path) if request.config_path else None,
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
