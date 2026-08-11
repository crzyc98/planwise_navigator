"""FastAPI router for the plan-design optimizer (Roadmap 7/8, issue #461/#557).

Backs the Studio Optimizer panel. A search evaluates up to ``max_runs``
isolated scenario simulations (``planalign_optimizer.search.run_optimizer``),
so like calibration this takes minutes: POST endpoints enqueue a background
job and return a ``run_id`` immediately (202); clients poll
``GET /optimizer/runs/{run_id}`` for status and results.

Unlike calibration, a run cannot serialize on a lock: ``run_optimizer``
requires ``database_dir``/``output_dir`` to be empty *before* it starts, so a
second request targeting the same directory can never usefully wait its turn
-- it is rejected outright (409) via an in-memory directory reservation set
instead of calibration's per-DB ``threading.Lock`` queue.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Literal, Optional
from uuid import uuid4

import yaml  # type: ignore[import]
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from planalign_optimizer.baseline import load_baseline, stale_baseline_warning
from planalign_optimizer.design_space import sample_candidates
from planalign_optimizer.evaluate import validate_levers_against_baseline
from planalign_optimizer.export import write_exports
from planalign_optimizer.models import OptimizerRun, OptimizerSpec
from planalign_optimizer.paths import require_fresh_directory, resolve_output_paths
from planalign_optimizer.report import write_report
from planalign_optimizer.search import run_optimizer, seed_phase_count
from planalign_optimizer.spec_io import (
    OptimizerSpecError,
    dump_resolved_spec,
    validate_spec,
)

from ..config import APISettings, get_settings
from ..storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


# ---------------------------------------------------------------------------
# Background job registry
# ---------------------------------------------------------------------------


class OptimizerJob(BaseModel):
    """Status/result record for a background optimizer job."""

    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[OptimizerRun] = None
    output_dir: Optional[str] = None
    error: Optional[str] = None
    error_status: Optional[int] = None


_jobs: Dict[str, OptimizerJob] = {}
_jobs_lock = threading.Lock()
_MAX_FINISHED_JOBS = 20

# Directories reserved by an in-flight run: a second request targeting the
# same database_dir/output_dir must be rejected, not queued (see module
# docstring) -- there is no lock a caller can usefully wait on here.
_reserved_dirs: set[Path] = set()
_reserved_dirs_guard = threading.Lock()


def _register_job() -> OptimizerJob:
    job = OptimizerJob(
        run_id=f"opt_{uuid4().hex[:12]}",
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
        if job is None:  # pruned while running -- nothing to record
            return
        for key, value in updates.items():
            setattr(job, key, value)


def _reserve_fresh_directories(database_dir: Path, output_dir: Path) -> None:
    """Claim both directories for one run, or 409 if either can't be fresh."""
    targets = {database_dir, output_dir}
    with _reserved_dirs_guard:
        collisions = targets & _reserved_dirs
        if collisions:
            raise HTTPException(
                status_code=409,
                detail=(
                    "optimizer run already in progress for directory: "
                    f"{next(iter(collisions))}"
                ),
            )
        for path in targets:
            try:
                require_fresh_directory(path, "optimizer output")
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        _reserved_dirs.update(targets)


def _release_reserved_directories(database_dir: Path, output_dir: Path) -> None:
    with _reserved_dirs_guard:
        _reserved_dirs.discard(database_dir)
        _reserved_dirs.discard(output_dir)


def _start_job_thread(
    job: OptimizerJob,
    build: Callable[[], None],
    database_dir: Path,
    output_dir: Path,
    workspace_config: Optional[Path],
) -> None:
    def _execute() -> None:
        try:
            _update_job(job.run_id, status="running")
            build()
            _update_job(job.run_id, status="completed", completed_at=datetime.now())
        except (OptimizerSpecError, ValueError) as e:
            _update_job(
                job.run_id,
                status="failed",
                error=str(e),
                error_status=409,
                completed_at=datetime.now(),
            )
        except Exception as e:  # noqa: BLE001 -- surfaced on the job record
            logger.exception("Optimizer job %s failed", job.run_id)
            _update_job(
                job.run_id,
                status="failed",
                error=str(e),
                error_status=500,
                completed_at=datetime.now(),
            )
        finally:
            _release_reserved_directories(database_dir, output_dir)
            _remove_temp_config(workspace_config)

    threading.Thread(
        target=_execute, name=f"optimizer-{job.run_id}", daemon=True
    ).start()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class OptimizerValidateRequest(BaseModel):
    """Exactly one of ``spec``/``spec_yaml`` must be given."""

    spec: Optional[dict] = None
    spec_yaml: Optional[str] = None
    max_runs: Optional[int] = Field(default=None, ge=1)


class OptimizerValidateResponse(BaseModel):
    valid: bool
    error: Optional[str] = None
    resolved_spec: Optional[dict] = None
    seed_phase_candidates: Optional[list] = None
    seed_phase_count: Optional[int] = None
    baseline_drift_warning: Optional[str] = None


class OptimizerRunRequest(BaseModel):
    spec: dict
    max_runs: int = Field(..., ge=1)
    search_seed: Optional[int] = None
    parallel: Optional[int] = Field(default=None, ge=1)
    workspace_id: Optional[str] = None
    database_dir: Optional[str] = None
    output_dir: Optional[str] = None
    compare_baseline_to: Optional[str] = None


class OptimizerStartResponse(BaseModel):
    run_id: str
    status: Literal["queued"]
    database_dir: str
    output_dir: str


# ---------------------------------------------------------------------------
# Config materialization helpers (mirrors calibration.py's workspace-config
# materialization -- reimplemented here rather than imported since that
# helper is private to the calibration router).
# ---------------------------------------------------------------------------


def _workspace_baseline_path(
    workspace_id: str, storage: WorkspaceStorage
) -> Optional[Path]:
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
        mode="w", suffix=".yaml", prefix="optimizer_baseline_", delete=False
    )
    with tmp:
        yaml.dump(config, tmp, default_flow_style=False)
    return Path(tmp.name)


def _remove_temp_config(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Could not remove temp optimizer baseline %s: %s", path, e)


def _parse_spec(spec: Optional[dict], spec_yaml: Optional[str]) -> OptimizerSpec:
    if (spec is None) == (spec_yaml is None):
        raise HTTPException(
            status_code=422, detail="exactly one of `spec` or `spec_yaml` is required"
        )
    try:
        if spec_yaml is not None:
            raw = yaml.safe_load(spec_yaml) or {}
            if not isinstance(raw, dict):
                raise OptimizerSpecError("optimizer spec root must be a mapping")
            parsed = OptimizerSpec.model_validate(raw)
        else:
            parsed = OptimizerSpec.model_validate(spec)
        return validate_spec(parsed)
    except (yaml.YAMLError, ValidationError, OptimizerSpecError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/optimizer/validate", response_model=OptimizerValidateResponse)
def validate_optimizer_spec(
    request: OptimizerValidateRequest,
) -> OptimizerValidateResponse:
    """Cheap, synchronous spec validation + optional seed-phase dry-run preview.

    Always returns 200; a bad spec is reported via `valid`/`error`, not raised,
    since this endpoint exists precisely to preview invalid input.
    """
    if (request.spec is None) == (request.spec_yaml is None):
        return OptimizerValidateResponse(
            valid=False, error="exactly one of `spec` or `spec_yaml` is required"
        )
    try:
        if request.spec_yaml is not None:
            raw = yaml.safe_load(request.spec_yaml) or {}
            if not isinstance(raw, dict):
                raise OptimizerSpecError("optimizer spec root must be a mapping")
            parsed = OptimizerSpec.model_validate(raw)
        else:
            parsed = OptimizerSpec.model_validate(request.spec)
        parsed = validate_spec(parsed)
        baseline = load_baseline(parsed.baseline.config_path)
        validate_levers_against_baseline(baseline, parsed.design_space.levers)
    except (yaml.YAMLError, ValidationError, OptimizerSpecError, ValueError) as exc:
        return OptimizerValidateResponse(valid=False, error=str(exc))
    except OSError as exc:
        return OptimizerValidateResponse(valid=False, error=str(exc))

    response = OptimizerValidateResponse(
        valid=True, resolved_spec=parsed.model_dump(mode="json")
    )
    if request.max_runs is not None:
        seed_count = seed_phase_count(request.max_runs)
        candidates = sample_candidates(parsed.design_space, seed_count, seed=0)
        response.seed_phase_candidates = candidates
        response.seed_phase_count = seed_count
    return response


@router.post("/optimizer/run", response_model=OptimizerStartResponse, status_code=202)
def start_optimizer_run(
    request: OptimizerRunRequest,
    storage: WorkspaceStorage = Depends(get_storage),
) -> OptimizerStartResponse:
    """Enqueue a plan-design optimizer search; poll /optimizer/runs/{run_id}.

    Request validation fails fast (404 unknown workspace, 422 bad spec, 409
    non-fresh output directory); build-time failures surface on the job
    record instead (409 spec/baseline resolution issue, 500 unexpected).
    """
    spec = _parse_spec(request.spec, None)

    workspace_config: Optional[Path] = None
    if request.workspace_id is not None:
        workspace_config = _workspace_baseline_path(request.workspace_id, storage)
        if workspace_config is not None:
            spec = spec.model_copy(
                update={
                    "baseline": spec.baseline.model_copy(
                        update={"config_path": workspace_config}
                    )
                }
            )

    try:
        database_dir, output_dir = resolve_output_paths(
            Path(request.database_dir) if request.database_dir else None,
            Path(request.output_dir) if request.output_dir else None,
        )
    except ValueError as exc:
        _remove_temp_config(workspace_config)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        _reserve_fresh_directories(database_dir, output_dir)
    except HTTPException:
        _remove_temp_config(workspace_config)
        raise

    try:
        baseline = load_baseline(spec.baseline.config_path)
        validate_levers_against_baseline(baseline, spec.design_space.levers)
    except (OSError, ValueError) as exc:
        _release_reserved_directories(database_dir, output_dir)
        _remove_temp_config(workspace_config)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    drift_warning: Optional[str] = None
    if request.compare_baseline_to is not None:
        drift_warning = stale_baseline_warning(
            baseline, Path(request.compare_baseline_to)
        )
        if drift_warning:
            logger.warning("Optimizer run baseline drift: %s", drift_warning)

    job = _register_job()
    search_seed = request.search_seed if request.search_seed is not None else 0

    def _build() -> None:
        run, _budget = run_optimizer(
            spec,
            baseline,
            max_runs=request.max_runs,
            search_seed=search_seed,
            database_dir=database_dir,
            parallel=request.parallel,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        dump_resolved_spec(spec, output_dir / "spec.yaml")
        write_exports(run, output_dir)
        write_report(run, output_dir)
        _update_job(job.run_id, result=run, output_dir=str(output_dir))

    _start_job_thread(job, _build, database_dir, output_dir, workspace_config)
    return OptimizerStartResponse(
        run_id=job.run_id,
        status="queued",
        database_dir=str(database_dir),
        output_dir=str(output_dir),
    )


@router.get("/optimizer/runs/{run_id}", response_model=OptimizerJob)
def get_optimizer_run(run_id: str) -> OptimizerJob:
    """Poll an optimizer job: status, then result or error."""
    with _jobs_lock:
        job = _jobs.get(run_id)
        if job is None:
            raise HTTPException(
                status_code=404, detail=f"Optimizer run {run_id} not found"
            )
        return job.model_copy(deep=True)


@router.get("/optimizer/runs/{run_id}/candidates/{candidate_id}")
def get_optimizer_candidate(run_id: str, candidate_id: str) -> dict:
    """Drill down to one candidate's already-computed result (no new query)."""
    with _jobs_lock:
        job = _jobs.get(run_id)
    if job is None or job.result is None:
        raise HTTPException(
            status_code=404, detail=f"Optimizer run {run_id} not found or incomplete"
        )
    for candidate in job.result.candidates:
        if candidate.candidate_id == candidate_id:
            return candidate.model_dump(mode="json")
    raise HTTPException(
        status_code=404,
        detail=f"Candidate {candidate_id} not found in run {run_id}",
    )
