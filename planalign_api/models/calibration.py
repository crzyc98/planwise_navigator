"""Persistent calibration job response models."""

from datetime import datetime
from typing import List, Literal, Optional

from planalign_orchestrator.calibration_optimizer import AutoCalibrationResult
from planalign_orchestrator.calibration_runner import PerYearCompensationResult

from .base import APIModel


class CalibrationContext(APIModel):
    """PII-safe identity of the exact target and matched source run."""

    workspace_id: str
    scenario_id: Optional[str] = None
    source_scenario_id: str
    source_run_id: str
    config_fingerprint: str
    census_fingerprint: str
    random_seed: int
    start_year: int
    end_year: int


class CalibrationJob(APIModel):
    """Status/result record for a background calibration job."""

    run_id: str
    kind: Literal["run", "optimize"]
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    created_at: datetime
    completed_at: Optional[datetime] = None
    # Populated on completion: `results` for kind="run", `outcome` for "optimize".
    results: Optional[List[PerYearCompensationResult]] = None
    outcome: Optional[AutoCalibrationResult] = None
    context: Optional["CalibrationContext"] = None
    # Populated on failure; error_status carries the HTTP-equivalent code the
    # old sync endpoints returned (409 prerequisite guard, 500 unexpected).
    error: Optional[str] = None
    error_status: Optional[int] = None
