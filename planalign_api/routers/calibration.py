"""FastAPI router for Fast Compensation Calibration (Feature 105).

Backs the Studio calibration panel. Calibration builds take minutes (optimize =
3-6 builds), so POST endpoints enqueue a background job and return a ``run_id``
immediately (202); clients poll ``GET /calibration/runs/{run_id}`` for status
and results (issue #380). Jobs targeting the same explicit database serialize
on a per-DB lock so concurrent runs queue instead of colliding on the DuckDB
file lock; default runs each get an isolated timestamped DB and never contend.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional
from uuid import uuid4

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


# ---------------------------------------------------------------------------
# Background job registry (issue #380)
# ---------------------------------------------------------------------------


class CalibrationJob(BaseModel):
    """Status/result record for a background calibration job."""

    run_id: str
    kind: Literal["run", "optimize"]
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    completed_at: Optional[datetime] = None
    # Populated on completion: `results` for kind="run", `outcome` for "optimize".
    results: Optional[List[PerYearCompensationResult]] = None
    outcome: Optional[AutoCalibrationResult] = None
    # Populated on failure; error_status carries the HTTP-equivalent code the
    # old sync endpoints returned (409 prerequisite guard, 500 unexpected).
    error: Optional[str] = None
    error_status: Optional[int] = None


_jobs: Dict[str, CalibrationJob] = {}
_jobs_lock = threading.Lock()
_MAX_FINISHED_JOBS = 20

# One lock per explicit target DB path: a second calibration against the same
# DuckDB file queues behind the first instead of failing on the file lock.
_db_locks: Dict[str, threading.Lock] = {}
_db_locks_guard = threading.Lock()


def _register_job(kind: Literal["run", "optimize"]) -> CalibrationJob:
    prefix = "cal" if kind == "run" else "autocal"
    job = CalibrationJob(
        run_id=f"{prefix}_{uuid4().hex[:12]}",
        kind=kind,
        status="queued",
        created_at=datetime.now(),
    )
    with _jobs_lock:
        _jobs[job.run_id] = job
        _prune_finished_jobs_locked()
    return job


def _prune_finished_jobs_locked() -> None:
    """Drop the oldest finished jobs beyond the retention cap (holds _jobs_lock)."""
    finished = [j for j in _jobs.values() if j.status in ("completed", "failed")]
    excess = len(finished) - _MAX_FINISHED_JOBS
    if excess <= 0:
        return
    finished.sort(key=lambda j: j.created_at)
    for job in finished[:excess]:
        del _jobs[job.run_id]


def _update_job(run_id: str, **updates: object) -> None:
    with _jobs_lock:
        job = _jobs.get(run_id)
        if job is None:  # pruned while running — nothing to record
            return
        for key, value in updates.items():
            setattr(job, key, value)


def _db_lock_for(database_path: Optional[str]) -> Optional[threading.Lock]:
    """Per-DB serialization lock; None when the run uses an isolated default DB."""
    if not database_path:
        return None
    key = str(Path(database_path).resolve())
    with _db_locks_guard:
        return _db_locks.setdefault(key, threading.Lock())


def _execute_job(
    job: CalibrationJob,
    build: Callable[[], None],
    database_path: Optional[str],
    workspace_config: Optional[Path],
) -> None:
    """Worker-thread body: serialize per target DB, run the build, record the outcome."""
    db_lock = _db_lock_for(database_path)
    try:
        if db_lock is not None:
            db_lock.acquire()
        _update_job(job.run_id, status="running")
        build()
        _update_job(job.run_id, status="completed", completed_at=datetime.now())
    except ConfigurationError as e:
        # Missing prerequisite DC tables, or a build failure with a clear cause.
        _update_job(
            job.run_id,
            status="failed",
            error=str(e),
            error_status=409,
            completed_at=datetime.now(),
        )
    except Exception as e:
        logger.exception("Calibration job %s failed", job.run_id)
        _update_job(
            job.run_id,
            status="failed",
            error=str(e),
            error_status=500,
            completed_at=datetime.now(),
        )
    finally:
        if db_lock is not None:
            db_lock.release()
        _remove_temp_config(workspace_config)


def _start_job_thread(
    job: CalibrationJob,
    build: Callable[[], None],
    database_path: Optional[str],
    workspace_config: Optional[Path],
) -> None:
    threading.Thread(
        target=_execute_job,
        args=(job, build, database_path, workspace_config),
        name=f"calibration-{job.run_id}",
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


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


class CalibrationStartResponse(BaseModel):
    """Acknowledgement that a calibration job was enqueued."""

    run_id: str
    status: Literal["queued"]


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


# ---------------------------------------------------------------------------
# Config materialization helpers
# ---------------------------------------------------------------------------


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


def _remove_temp_config(path: Optional[Path]) -> None:
    """Delete a materialized workspace-config YAML once the run is done."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Could not remove temp calibration config %s: %s", path, e)


def _resolve_config_path(
    config_path: Optional[str],
    workspace_id: Optional[str],
    storage: WorkspaceStorage,
) -> "tuple[Optional[Path], Optional[Path]]":
    """Return (config_path, workspace_temp_config) for a calibration request."""
    if config_path:
        return Path(config_path), None
    if workspace_id:
        workspace_config = _workspace_config_path(workspace_id, storage)
        return workspace_config, workspace_config
    return None, None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/calibration/run", response_model=CalibrationStartResponse, status_code=202
)
def run_calibration(
    request: CalibrationRunRequest,
    storage: WorkspaceStorage = Depends(get_storage),
) -> CalibrationStartResponse:
    """Enqueue a comp-only calibration run; poll /calibration/runs/{run_id}.

    Request validation still fails fast (404 unknown workspace, 422 bad
    range/params); build-time failures surface on the job record instead
    (409 prerequisite guard, 500 unexpected).
    """
    config_path, workspace_config = _resolve_config_path(
        request.config_path, request.workspace_id, storage
    )

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
        _remove_temp_config(workspace_config)
        raise HTTPException(status_code=422, detail=str(e))

    job = _register_job("run")

    def _build() -> None:
        results = CalibrationRunner(run, threads=1).run_calibration()
        _update_job(job.run_id, results=results)

    _start_job_thread(job, _build, request.database_path, workspace_config)
    return CalibrationStartResponse(run_id=job.run_id, status="queued")


@router.post(
    "/calibration/optimize", response_model=CalibrationStartResponse, status_code=202
)
def optimize_calibration(
    request: AutoCalibrationRequest,
    storage: WorkspaceStorage = Depends(get_storage),
) -> CalibrationStartResponse:
    """Enqueue an auto-calibration search; poll /calibration/runs/{run_id}.

    The search runs several fast comp-only builds (typically 3-6); expect a
    few minutes for a multi-year range.
    """
    if request.end_year <= request.start_year:
        raise HTTPException(
            status_code=422,
            detail="Auto-calibration needs at least a two-year range to "
            "measure year-over-year growth",
        )

    config_path, workspace_config = _resolve_config_path(
        request.config_path, request.workspace_id, storage
    )

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
    except ValueError as e:
        _remove_temp_config(workspace_config)
        raise HTTPException(status_code=422, detail=str(e))

    job = _register_job("optimize")

    def _build() -> None:
        outcome = AutoCalibrator(run, request.settings, threads=1).optimize()
        _update_job(job.run_id, outcome=outcome)

    _start_job_thread(job, _build, request.database_path, workspace_config)
    return CalibrationStartResponse(run_id=job.run_id, status="queued")


@router.get("/calibration/runs/{run_id}", response_model=CalibrationJob)
def get_calibration_run(run_id: str) -> CalibrationJob:
    """Poll a calibration job: status, then results/outcome or error."""
    with _jobs_lock:
        job = _jobs.get(run_id)
        if job is None:
            raise HTTPException(
                status_code=404, detail=f"Calibration run {run_id} not found"
            )
        return job.model_copy(deep=True)
