"""FastAPI router for Fast Compensation Calibration (Feature 105).

Backs the Studio calibration panel. Calibration builds take minutes (optimize =
3-6 builds), so POST endpoints enqueue a background job and return a ``run_id``
immediately (202); clients poll ``GET /calibration/runs/{run_id}`` for status
and results (issue #380). Workspace requests copy a completed provenance-matched
run to a disposable isolated database. The shared development database is
neither read nor written.
"""

from __future__ import annotations

import logging
import json
import shutil
import tempfile
import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional
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
from planalign_api.services.provenance.capture import config_fingerprint, sha256_file

from ..config import APISettings, get_settings
from ..errors import sanitize_job_error
from ..services.current_result import CurrentResultIntegrityError
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
    context: Optional["CalibrationContext"] = None
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
    """Per-DB serialization lock; None when no legacy database was supplied."""
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
    calibration_database: Optional[Path] = None,
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
    except Exception:
        _update_job(
            job.run_id,
            status="failed",
            error=sanitize_job_error(
                logger, job.run_id, event="Calibration job failed"
            ),
            error_status=500,
            completed_at=datetime.now(),
        )
    finally:
        if db_lock is not None:
            db_lock.release()
        _remove_temp_config(workspace_config)
        _remove_temp_database(calibration_database)


def _start_job_thread(
    job: CalibrationJob,
    build: Callable[[], None],
    database_path: Optional[str],
    workspace_config: Optional[Path],
    calibration_database: Optional[Path] = None,
) -> None:
    threading.Thread(
        target=_execute_job,
        args=(job, build, database_path, workspace_config, calibration_database),
        name=f"calibration-{job.run_id}",
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class CalibrationRunRequest(BaseModel):
    """Request body for POST /api/calibration/run (contracts/api-calibration.md)."""

    start_year: Optional[int] = Field(default=None, ge=2000)
    end_year: Optional[int] = Field(default=None, ge=2000)
    config_path: Optional[str] = None
    database_path: Optional[str] = None
    # When set (and no explicit config_path), calibration runs against the
    # workspace's base config -- census, termination rates, everything -- so the
    # calibrated levers transfer to a full simulation of that workspace.
    workspace_id: Optional[str] = None
    scenario_id: Optional[str] = None
    params: CalibrationParameterSet = Field(default_factory=CalibrationParameterSet)


class CalibrationStartResponse(BaseModel):
    """Acknowledgement that a calibration job was enqueued."""

    run_id: str
    status: Literal["queued"]


class AutoCalibrationRequest(BaseModel):
    """Request body for POST /api/calibration/optimize.

    Set the two targets; the optimizer sets workforce growth directly (it is
    deterministic via E077) and searches until every annual avg-comp growth
    result is within tolerance of the compensation target.
    """

    start_year: Optional[int] = Field(default=None, ge=2000)
    end_year: Optional[int] = Field(default=None, ge=2000)
    config_path: Optional[str] = None
    database_path: Optional[str] = None
    workspace_id: Optional[str] = None
    scenario_id: Optional[str] = None
    settings: AutoCalibrationSettings
    # Non-searched levers (age distribution, comp ranges) applied to every run.
    params: CalibrationParameterSet = Field(default_factory=CalibrationParameterSet)


class CalibrationApplyRequest(BaseModel):
    """Exact optimizer candidate and the target context it was evaluated in."""

    context: "CalibrationContext"
    best_params: CalibrationParameterSet
    target_comp_growth_pct: float = Field(ge=-100.0, le=100.0)


class CalibrationApplyOutcome(BaseModel):
    scenario_id: str
    success: bool
    error: Optional[str] = None


class CalibrationApplyResult(BaseModel):
    workspace_updated: bool
    scenarios: List[CalibrationApplyOutcome]
    total_applied: int
    total_failed: int


# ---------------------------------------------------------------------------
# Config materialization helpers
# ---------------------------------------------------------------------------


class CalibrationContext(BaseModel):
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


@dataclass(frozen=True)
class _ResolvedTarget:
    config_path: Path
    database_path: Path
    context: CalibrationContext


def _effective_workspace_config(
    workspace_id: str,
    scenario_id: Optional[str],
    storage: WorkspaceStorage,
) -> Dict[str, Any]:
    workspace = storage.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=404, detail=f"Workspace {workspace_id} not found"
        )
    if scenario_id:
        config = storage.get_merged_config(workspace_id, scenario_id)
        if config is None:
            raise HTTPException(
                status_code=404,
                detail=f"Scenario {scenario_id} not found in workspace {workspace_id}",
            )
        return dict(config)
    return dict(workspace.base_config or {})


def _canonical_census(
    config: Dict[str, Any], workspace_id: str, storage: WorkspaceStorage
) -> Path:
    configured = (config.get("setup") or {}).get("census_parquet_path")
    if not configured:
        raise HTTPException(
            status_code=409,
            detail="The target workspace has no uploaded census. Upload one before calibration.",
        )
    census = Path(str(configured))
    workspace_root = storage._workspace_path(workspace_id).resolve()
    if not census.is_absolute():
        census = workspace_root / census
    if not census.is_file():
        raise HTTPException(
            status_code=409,
            detail="The target workspace census is missing. Upload it again before calibration.",
        )
    resolved = census.resolve()
    if resolved != workspace_root and workspace_root not in resolved.parents:
        raise HTTPException(
            status_code=409,
            detail="The configured census is not an uploaded artifact in the active workspace.",
        )
    config.setdefault("setup", {})["census_parquet_path"] = str(resolved)
    return resolved


def _effective_horizon(
    config: Dict[str, Any], start_year: Optional[int], end_year: Optional[int]
) -> tuple[int, int]:
    simulation = config.setdefault("simulation", {})
    start = start_year if start_year is not None else simulation.get("start_year")
    end = end_year if end_year is not None else simulation.get("end_year")
    if start is None or end is None:
        raise HTTPException(
            status_code=422,
            detail="The target config must define simulation.start_year and simulation.end_year",
        )
    if int(end) < int(start):
        raise HTTPException(status_code=422, detail="end_year must be >= start_year")
    simulation["start_year"] = int(start)
    simulation["end_year"] = int(end)
    return int(start), int(end)


def _manifest_matches(
    manifest_path: Path,
    *,
    workspace_id: str,
    expected_config: str,
    expected_census: str,
    expected_seed: int,
    start_year: int,
    end_year: int,
) -> tuple[bool, Optional[str]]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        identity = manifest["run_identity"]
        matches = (
            manifest.get("capture_state") == "completed"
            and identity.get("workspace_id") == workspace_id
            and identity.get("intended_start_year") == start_year
            and identity.get("intended_end_year") == end_year
            and (manifest.get("configuration") or {}).get("fingerprint")
            == expected_config
            and manifest.get("random_seed") == expected_seed
            and (manifest.get("census_input") or {}).get("sha256") == expected_census
        )
        return matches, str(manifest.get("run_id")) if matches else None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False, None


def _matching_source(
    workspace_id: str,
    scenario_id: Optional[str],
    storage: WorkspaceStorage,
    *,
    config_hash: str,
    census_hash: str,
    seed: int,
    start_year: int,
    end_year: int,
) -> tuple[str, str, Path]:
    scenarios = (
        [storage.get_scenario(workspace_id, scenario_id)]
        if scenario_id
        else storage.list_scenarios(workspace_id)
    )
    for scenario in scenarios:
        if scenario is None:
            continue
        try:
            read_context = storage.get_scenario_read_context(workspace_id, scenario.id)
        except (CurrentResultIntegrityError, OSError, ValueError):
            continue
        database = read_context.database_path
        run_id = read_context.result_run_id
        if database is None or run_id is None:
            continue
        manifest = database.parent / "provenance.json"
        matches, manifest_run_id = _manifest_matches(
            manifest,
            workspace_id=workspace_id,
            expected_config=config_hash,
            expected_census=census_hash,
            expected_seed=seed,
            start_year=start_year,
            end_year=end_year,
        )
        if matches and manifest_run_id == str(run_id):
            return scenario.id, str(run_id), database
    raise HTTPException(
        status_code=409,
        detail=(
            "No completed simulation matches this workspace census, target config, "
            "seed, and horizon. Run the target scenario successfully, then calibrate."
        ),
    )


def _materialize_target(
    request: CalibrationRunRequest | AutoCalibrationRequest,
    storage: WorkspaceStorage,
) -> _ResolvedTarget:
    assert request.workspace_id is not None
    if request.config_path or request.database_path:
        raise HTTPException(
            status_code=422,
            detail=(
                "workspace calibration resolves its config and isolated database "
                "from the workspace target; config_path/database_path are not allowed"
            ),
        )
    config = _effective_workspace_config(
        request.workspace_id, request.scenario_id, storage
    )
    census = _canonical_census(config, request.workspace_id, storage)
    start_year, end_year = _effective_horizon(
        config, request.start_year, request.end_year
    )
    seed = int((config.get("simulation") or {}).get("random_seed", 42))
    config_hash = config_fingerprint(config)
    census_hash, _ = sha256_file(census)
    source_scenario, source_run, source_database = _matching_source(
        request.workspace_id,
        request.scenario_id,
        storage,
        config_hash=config_hash,
        census_hash=census_hash,
        seed=seed,
        start_year=start_year,
        end_year=end_year,
    )
    config_file = _write_temp_config(config)
    try:
        database_file = _copy_calibration_database(source_database)
    except OSError:
        _remove_temp_config(config_file)
        raise HTTPException(
            status_code=409,
            detail="The matched simulation database could not be copied for calibration.",
        )
    return _ResolvedTarget(
        config_path=config_file,
        database_path=database_file,
        context=CalibrationContext(
            workspace_id=request.workspace_id,
            scenario_id=request.scenario_id,
            source_scenario_id=source_scenario,
            source_run_id=source_run,
            config_fingerprint=config_hash,
            census_fingerprint=census_hash,
            random_seed=seed,
            start_year=start_year,
            end_year=end_year,
        ),
    )


def _write_temp_config(config: Dict[str, Any]) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="calibration_config_", delete=False
    )
    with tmp:
        yaml.safe_dump(config, tmp, default_flow_style=False)
    return Path(tmp.name)


def _copy_calibration_database(source: Path) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        suffix=".duckdb", prefix="planalign_calibration_", delete=False
    )
    target = Path(tmp.name)
    tmp.close()
    shutil.copyfile(source, target)
    return target


def _remove_temp_config(path: Optional[Path]) -> None:
    """Delete a materialized workspace-config YAML once the run is done."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Could not remove temp calibration config %s: %s", path, e)


def _remove_temp_database(path: Optional[Path]) -> None:
    """Remove only the disposable database created by this router."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
        Path(f"{path}.wal").unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Could not remove temporary calibration database: %s", e)


def _resolve_config_path(
    config_path: Optional[str],
) -> "tuple[Optional[Path], Optional[Path]]":
    """Return an explicit legacy config and no router-owned temp file."""
    if config_path:
        return Path(config_path), None
    return None, None


def _merge_calibration_candidate(
    config: Dict[str, Any], request: CalibrationApplyRequest
) -> Dict[str, Any]:
    """Persist exactly the evaluated candidate without display-derived rounding."""
    merged = deepcopy(config)
    params = request.best_params
    simulation = merged.setdefault("simulation", {})
    simulation["start_year"] = request.context.start_year
    simulation["end_year"] = request.context.end_year
    if params.workforce_growth_rate is not None:
        simulation["target_growth_rate"] = params.workforce_growth_rate

    compensation = merged.setdefault("compensation", {})
    compensation["target_compensation_growth_percent"] = request.target_comp_growth_pct
    for field in ("cola_rate", "merit_budget", "promotion_increase"):
        value = getattr(params, field)
        if value is not None:
            compensation[field] = value
            compensation[f"{field}_percent"] = value * 100

    workforce = merged.setdefault("workforce", {})
    for field in ("total_termination_rate", "new_hire_termination_rate"):
        value = getattr(params, field)
        if value is not None:
            workforce[field] = value

    new_hire = merged.setdefault("new_hire", {})
    if params.new_hire_age_distribution is not None:
        new_hire["age_distribution"] = params.new_hire_age_distribution
    if params.job_level_compensation is not None:
        new_hire["job_level_compensation"] = params.job_level_compensation
    return merged


def _verify_apply_context(
    context: CalibrationContext, storage: WorkspaceStorage
) -> Dict[str, Any]:
    config = _effective_workspace_config(
        context.workspace_id, context.scenario_id, storage
    )
    census = _canonical_census(config, context.workspace_id, storage)
    start, end = _effective_horizon(config, None, None)
    seed = int((config.get("simulation") or {}).get("random_seed", 42))
    census_hash, _ = sha256_file(census)
    if (
        config_fingerprint(config) != context.config_fingerprint
        or census_hash != context.census_fingerprint
        or seed != context.random_seed
        or start != context.start_year
        or end != context.end_year
    ):
        raise HTTPException(
            status_code=409,
            detail="The target config or census changed after calibration; run calibration again before applying.",
        )
    return config


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
    target = _materialize_target(request, storage) if request.workspace_id else None
    config_path, workspace_config = (
        (target.config_path, target.config_path)
        if target
        else _resolve_config_path(request.config_path)
    )
    start_year = target.context.start_year if target else request.start_year
    end_year = target.context.end_year if target else request.end_year
    if start_year is None or end_year is None:
        _remove_temp_config(workspace_config)
        raise HTTPException(
            status_code=422,
            detail="start_year and end_year are required without a workspace target",
        )

    try:
        run = CalibrationRun(
            start_year=start_year,
            end_year=end_year,
            config_path=config_path,
            database_path=(
                target.database_path
                if target
                else (Path(request.database_path) if request.database_path else None)
            ),
            params=request.params,
        )
    except ValueError as e:  # range ordering / param validation
        _remove_temp_config(workspace_config)
        if target:
            _remove_temp_database(target.database_path)
        raise HTTPException(status_code=422, detail=str(e))

    job = _register_job("run")
    if target:
        _update_job(job.run_id, context=target.context)

    def _build() -> None:
        results = CalibrationRunner(run, threads=1).run_calibration()
        _update_job(job.run_id, results=results)

    database_path = str(target.database_path) if target else request.database_path
    _start_job_thread(
        job,
        _build,
        database_path,
        workspace_config,
        target.database_path if target else None,
    )
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
    target = _materialize_target(request, storage) if request.workspace_id else None
    start_year = target.context.start_year if target else request.start_year
    end_year = target.context.end_year if target else request.end_year
    if start_year is None or end_year is None:
        if target:
            _remove_temp_config(target.config_path)
            _remove_temp_database(target.database_path)
        raise HTTPException(
            status_code=422,
            detail="start_year and end_year are required without a workspace target",
        )
    if end_year <= start_year:
        if target:
            _remove_temp_config(target.config_path)
            _remove_temp_database(target.database_path)
        raise HTTPException(
            status_code=422,
            detail="Auto-calibration needs at least a two-year range to "
            "measure year-over-year growth",
        )

    config_path, workspace_config = (
        (target.config_path, target.config_path)
        if target
        else _resolve_config_path(request.config_path)
    )

    try:
        run = CalibrationRun(
            start_year=start_year,
            end_year=end_year,
            config_path=config_path,
            database_path=(
                target.database_path
                if target
                else (Path(request.database_path) if request.database_path else None)
            ),
            params=request.params,
        )
    except ValueError as e:
        _remove_temp_config(workspace_config)
        if target:
            _remove_temp_database(target.database_path)
        raise HTTPException(status_code=422, detail=str(e))

    job = _register_job("optimize")
    if target:
        _update_job(job.run_id, context=target.context)

    def _build() -> None:
        outcome = AutoCalibrator(run, request.settings, threads=1).optimize()
        _update_job(job.run_id, outcome=outcome)

    database_path = str(target.database_path) if target else request.database_path
    _start_job_thread(
        job,
        _build,
        database_path,
        workspace_config,
        target.database_path if target else None,
    )
    return CalibrationStartResponse(run_id=job.run_id, status="queued")


@router.post("/calibration/apply", response_model=CalibrationApplyResult)
def apply_calibration(
    request: CalibrationApplyRequest,
    storage: WorkspaceStorage = Depends(get_storage),
) -> CalibrationApplyResult:
    """Apply the exact evaluated candidate to the workspace and its scenarios."""
    _verify_apply_context(request.context, storage)
    workspace = storage.get_workspace(request.context.workspace_id)
    assert workspace is not None
    base_config = _merge_calibration_candidate(workspace.base_config, request)
    workspace_updated = storage.update_workspace(
        request.context.workspace_id, base_config=base_config
    )
    if workspace_updated is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    outcomes: List[CalibrationApplyOutcome] = []
    for scenario in storage.list_scenarios(request.context.workspace_id):
        try:
            overrides = _merge_calibration_candidate(
                scenario.config_overrides or {}, request
            )
            updated = storage.update_scenario(
                request.context.workspace_id,
                scenario.id,
                config_overrides=overrides,
            )
            if updated is None:
                raise LookupError("scenario no longer exists")
            outcomes.append(
                CalibrationApplyOutcome(scenario_id=scenario.id, success=True)
            )
        except Exception:
            logger.exception("Calibration apply failed for scenario %s", scenario.id)
            outcomes.append(
                CalibrationApplyOutcome(
                    scenario_id=scenario.id,
                    success=False,
                    error="Scenario update failed",
                )
            )
    applied = sum(outcome.success for outcome in outcomes)
    return CalibrationApplyResult(
        workspace_updated=True,
        scenarios=outcomes,
        total_applied=applied,
        total_failed=len(outcomes) - applied,
    )


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
