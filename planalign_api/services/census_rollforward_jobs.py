"""Roll an old workspace census forward from Studio (#1078).

A census more than a year behind the workspace's start year skips the missing
years' hires, so first-year turnover runs low. A roll-forward job runs
``planalign census roll-forward`` in its own process, under the workspace's
base settings, then saves the bridge census in the workspace, lists it in
Imported Files and makes it the workspace census. The original census stays
listed, so switching back is "Use as Census".

Jobs take a simulation slot first, so they wait behind running simulations
like any other run. Job state lives in memory; a restart forgets it, and the
bridge census is only activated once the job has finished.
"""

import logging
import shutil
import sys
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import duckdb

from ..models.census_rollforward import (
    CensusStatus,
    RollForwardJob,
    RollForwardSummary,
)
from ..storage.workspace_storage import WorkspaceStorage
from .import_service import ImportService
from .simulation.run_execution import (
    build_env,
    prepare_dbt_project,
    resolve_census_with_fallback,
    workspace_census_fallback,
    write_config,
    write_seeds,
)
from .simulation.run_slots import simulation_slot
from .simulation.subprocess_utils import create_subprocess, wait_subprocess

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_jobs: Dict[str, RollForwardJob] = {}
_lock = threading.Lock()


class RollForwardUnavailable(Exception):
    """The workspace census can't be rolled forward right now."""


def census_status(storage: WorkspaceStorage, workspace_id: str) -> CensusStatus:
    """Compare the workspace census year with its simulation start year."""
    from planalign_orchestrator.census_year import census_is_behind, infer_census_year

    config = _workspace_config(storage, workspace_id)
    start_year = int(config.get("simulation", {}).get("start_year", 2025))
    census = _census_path(storage, workspace_id, config)
    census_year = None
    if census is not None:
        try:
            census_year = infer_census_year(census)
        except duckdb.Error as e:
            logger.warning("Could not read the census year from %s: %s", census, e)
    behind = census_year is not None and census_is_behind(census_year, start_year)
    return CensusStatus(
        census_year=census_year,
        start_year=start_year,
        behind=behind,
        bridge_year=start_year - 1 if behind else None,
        active_job=active_job(workspace_id),
    )


def active_job(workspace_id: str) -> Optional[RollForwardJob]:
    with _lock:
        return next(
            (
                job
                for job in _jobs.values()
                if job.workspace_id == workspace_id
                and job.status in ("queued", "running")
            ),
            None,
        )


def get_job(workspace_id: str, job_id: str) -> Optional[RollForwardJob]:
    with _lock:
        job = _jobs.get(job_id)
    return job if job is not None and job.workspace_id == workspace_id else None


def start_job(storage: WorkspaceStorage, workspace_id: str) -> RollForwardJob:
    """Queue a roll-forward; the caller runs ``run_job`` in the background."""
    status = census_status(storage, workspace_id)
    if status.census_year is None:
        raise RollForwardUnavailable("Could not read a census year from the census")
    if not status.behind or status.bridge_year is None:
        raise RollForwardUnavailable(
            "The census is no more than a year behind the start year"
        )
    job = RollForwardJob(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        bridge_year=status.bridge_year,
        status="queued",
        submitted_at=datetime.now(timezone.utc),
    )
    with _lock:
        if any(
            j.workspace_id == workspace_id and j.status in ("queued", "running")
            for j in _jobs.values()
        ):
            raise RollForwardUnavailable("A roll-forward is already running")
        _jobs[job.id] = job
    return job


async def run_job(storage: WorkspaceStorage, job_id: str) -> None:
    """Wait for a simulation slot, roll the census forward and activate it."""
    async with simulation_slot():
        job = _update(job_id, status="running")
        try:
            summary = await _roll_forward(storage, job)
            _activate(storage, job.workspace_id, summary)
        except Exception:
            _update(
                job_id,
                status="failed",
                completed_at=datetime.now(timezone.utc),
                error_message=_failure_message(job_id),
            )
            return
        _update(
            job_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            summary=summary,
        )


def _failure_message(job_id: str) -> str:
    from ..errors import sanitize_job_error

    return sanitize_job_error(
        logger, f"census roll-forward {job_id}", event="Census roll-forward failed"
    )


def _update(job_id: str, **changes: Any) -> RollForwardJob:
    with _lock:
        job = _jobs[job_id].model_copy(update=changes)
        _jobs[job_id] = job
    return job


def _workspace_config(storage: WorkspaceStorage, workspace_id: str) -> Dict[str, Any]:
    """The workspace's base settings, merged the way a scenario's are."""
    config = storage.merge_overrides(workspace_id, {})
    if config is None:
        raise RollForwardUnavailable(f"Workspace {workspace_id} not found")
    return config


def _census_path(
    storage: WorkspaceStorage, workspace_id: str, config: Dict[str, Any]
) -> Optional[Path]:
    configured = (config.get("setup") or {}).get("census_parquet_path")
    if configured:
        return resolve_census_with_fallback(storage, str(configured), workspace_id)
    return workspace_census_fallback(storage, workspace_id)


async def _roll_forward(
    storage: WorkspaceStorage, job: RollForwardJob
) -> RollForwardSummary:
    """Run the roll-forward CLI in an isolated run directory."""
    config = _workspace_config(storage, job.workspace_id)
    census = _census_path(storage, job.workspace_id, config)
    if census is None:
        raise RollForwardUnavailable("The workspace has no census")
    config.setdefault("setup", {})["census_parquet_path"] = str(census)
    workspace_dir = storage._workspace_path(job.workspace_id)
    work = workspace_dir / "census_rollforward" / job.id
    work.mkdir(parents=True, exist_ok=True)
    try:
        write_config(config, work / "config.yaml")
        write_seeds(config, work)
        command = _command(work, census, job.bridge_year, work / "bridge.parquet")
        await run_cli(
            command, build_env(PROJECT_ROOT, database_path=work / "db.duckdb")
        )
        summary = RollForwardSummary.model_validate_json(
            (work / "summary.json").read_text()
        )
        # Only a finished bridge reaches the workspace data folder.
        final = workspace_dir / "data" / f"census_bridge_{job.bridge_year}.parquet"
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(work / "bridge.parquet"), final)
        return summary.model_copy(update={"census_path": str(final)})
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _command(work: Path, census: Path, year: int, output: Path) -> List[str]:
    return [
        sys.executable,
        "-m",
        "planalign_cli",
        "census",
        "roll-forward",
        "--config",
        str(work / "config.yaml"),
        "--census",
        str(census),
        "--to-year",
        str(year),
        "--output",
        str(output),
        "--database",
        str(work / "db.duckdb"),
        "--dbt-project-dir",
        str(prepare_dbt_project(work)),
        "--summary-json",
        str(work / "summary.json"),
    ]


async def run_cli(command: List[str], env: Dict[str, str]) -> None:
    """Run the roll-forward CLI; raise with its last output lines on failure."""
    process, lines = await create_subprocess(command, str(PROJECT_ROOT), env)
    tail: Deque[str] = deque(maxlen=20)
    async for line in lines:
        tail.append(line.decode("utf-8", errors="replace").rstrip())
    code = await wait_subprocess(process)
    if code != 0:
        raise RuntimeError(f"roll-forward exited {code}:\n" + "\n".join(tail))


def _activate(
    storage: WorkspaceStorage, workspace_id: str, summary: RollForwardSummary
) -> None:
    """Make the bridge census the workspace census and list it in Imported Files."""
    path = Path(summary.census_path)
    if not storage.update_base_config_key(
        workspace_id, "setup.census_parquet_path", str(path)
    ):
        raise RuntimeError(f"Could not set the census for workspace {workspace_id}")
    _move_explicit_plan_year(storage, workspace_id, summary.bridge_year)
    try:
        _register(storage, workspace_id, path, summary)
    except Exception as e:
        # The census is already in use; listing it is a convenience.
        logger.warning("Could not list the bridge census in Imported Files: %s", e)


def _move_explicit_plan_year(
    storage: WorkspaceStorage, workspace_id: str, year: int
) -> None:
    """Plan-year dates set by hand must follow the census to its new year."""
    workspace = storage.get_workspace(workspace_id)
    setup = (workspace.base_config.get("setup") or {}) if workspace else {}
    for key, month_day in (
        ("plan_year_start_date", "01-01"),
        ("plan_year_end_date", "12-31"),
    ):
        if setup.get(key):
            storage.update_base_config_key(
                workspace_id, f"setup.{key}", f"{year}-{month_day}"
            )


def _register(
    storage: WorkspaceStorage,
    workspace_id: str,
    path: Path,
    summary: RollForwardSummary,
) -> None:
    with duckdb.connect() as conn:
        columns = [
            row[0]
            for row in conn.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
            ).fetchall()
        ]
    ImportService(workspaces_root=storage.workspaces_root).register_external_parquet(
        workspace_id=workspace_id,
        storage_path=str(path),
        original_filename=(
            f"Census rolled forward from {summary.census_year} to {summary.bridge_year}"
        ),
        row_count=summary.ending_headcount,
        columns=columns,
        file_size_bytes=path.stat().st_size,
    )
