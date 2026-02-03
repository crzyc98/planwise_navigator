"""Simulation execution endpoints."""

import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse

from ..config import APISettings, get_settings
from ..models.simulation import (
    Artifact,
    RunDetails,
    RunRequest,
    RunSummary,
    SimulationResults,
    SimulationRun,
)
from ..storage.workspace_storage import WorkspaceStorage
from ..models.scenario import Scenario
from ..models.workspace import Workspace
from ..services.simulation_service import SimulationService
from ..constants import ARTIFACT_TYPE_MAP, MEDIA_TYPE_MAP

router = APIRouter()

# Import for logging
import logging
logger = logging.getLogger(__name__)


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


def get_simulation_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> SimulationService:
    """Dependency to get simulation service."""
    return SimulationService(storage)


# In-memory store for active runs (would use Redis in production)
_active_runs: Dict[str, SimulationRun] = {}


def _find_scenario_and_workspace(
    storage: WorkspaceStorage, scenario_id: str
) -> tuple[Optional[Workspace], Optional[Scenario]]:
    """Find a scenario and its workspace by scenario_id.

    Args:
        storage: The workspace storage instance
        scenario_id: The scenario identifier to find

    Returns:
        Tuple of (workspace, scenario) or (None, None) if not found
    """
    for ws in storage.list_workspaces():
        scenario = storage.get_scenario(ws.id, scenario_id)
        if scenario:
            return ws, scenario
    return None, None


@router.post("/{scenario_id}/run", response_model=SimulationRun)
async def start_simulation(
    scenario_id: str,
    request: RunRequest = RunRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    storage: WorkspaceStorage = Depends(get_storage),
    simulation_service: SimulationService = Depends(get_simulation_service),
) -> SimulationRun:
    """
    Start a simulation run for a scenario.

    The simulation runs in the background. Use the status endpoint or
    WebSocket to monitor progress.
    """
    workspace, scenario = _find_scenario_and_workspace(storage, scenario_id)
    if not scenario or not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )
    workspace_id = workspace.id

    # Check if already running
    if scenario.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scenario {scenario_id} is already running",
        )

    # Get merged config
    config = storage.get_merged_config(workspace_id, scenario_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load scenario configuration",
        )

    # Create run record
    run_id = str(uuid.uuid4())

    # E091: Extract year range from merged config with debug logging
    sim_config = config.get("simulation", {})
    start_year = int(sim_config.get("start_year", 2025))
    end_year = int(sim_config.get("end_year", 2027))
    logger.info(f"E091: Merged config simulation section: {sim_config}")
    logger.info(f"E091: Year range from config: {start_year}-{end_year}")

    run = SimulationRun(
        id=run_id,
        scenario_id=scenario_id,
        status="pending",
        progress=0,
        current_stage="INITIALIZATION",
        current_year=start_year,
        total_years=end_year - start_year + 1,
        started_at=datetime.now(),
    )

    _active_runs[run_id] = run

    # Update scenario status
    storage.update_scenario_status(workspace_id, scenario_id, "queued", run_id)

    # Start simulation in background
    background_tasks.add_task(
        simulation_service.execute_simulation,
        workspace_id,
        scenario_id,
        run_id,
        config,
        request.resume_from_checkpoint,
    )

    return run


@router.get("/{scenario_id}/run/status", response_model=SimulationRun)
async def get_run_status(
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> SimulationRun:
    """
    Get the status of the current or last simulation run.
    """
    _, scenario = _find_scenario_and_workspace(storage, scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    if scenario.last_run_id and scenario.last_run_id in _active_runs:
        return _active_runs[scenario.last_run_id]

    # Return a completed/failed status based on scenario status
    return SimulationRun(
        id=scenario.last_run_id or "unknown",
        scenario_id=scenario_id,
        status="completed" if scenario.status == "completed" else "not_run",
        progress=100 if scenario.status == "completed" else 0,
        started_at=scenario.last_run_at or datetime.utcnow(),
        completed_at=scenario.last_run_at,
    )


@router.post("/{scenario_id}/run/cancel")
async def cancel_simulation(
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
    simulation_service: SimulationService = Depends(get_simulation_service),
) -> Dict[str, bool]:
    """
    Cancel a running simulation.
    """
    # Find the active run
    for run_id, run in _active_runs.items():
        if run.scenario_id == scenario_id and run.status == "running":
            # Signal cancellation
            simulation_service.cancel_simulation(run_id)

            run.status = "cancelled"
            run.completed_at = datetime.utcnow()

            # Update scenario status
            workspace, scenario = _find_scenario_and_workspace(storage, scenario_id)
            if workspace and scenario:
                storage.update_scenario_status(workspace.id, scenario_id, "cancelled")

            return {"success": True}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No running simulation found for scenario {scenario_id}",
    )


@router.post("/{scenario_id}/run/reset")
async def reset_simulation_status(
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> Dict[str, Any]:
    """Force reset a stuck simulation status."""
    workspace, scenario = _find_scenario_and_workspace(storage, scenario_id)
    if not scenario or not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    # Only allow reset if status is "running" or "queued"
    if scenario.status not in ("running", "queued"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Scenario status is '{scenario.status}', not stuck",
        )

    # Check if actually running (has active process)
    if scenario.last_run_id and scenario.last_run_id in _active_runs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Simulation is actively running. Use cancel instead.",
        )

    # Reset the status
    previous_status = scenario.status
    storage.update_scenario_status(workspace.id, scenario_id, "failed", None)

    return {
        "success": True,
        "scenario_id": scenario_id,
        "previous_status": previous_status,
        "new_status": "failed",
        "message": "Simulation status reset from stuck state",
    }


@router.get("/{scenario_id}/runs", response_model=List[RunSummary])
async def list_runs(
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> List[RunSummary]:
    """
    List all runs for a scenario.
    """
    import json

    workspace, scenario = _find_scenario_and_workspace(storage, scenario_id)
    if not scenario or not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    # Get scenario path and look for runs
    scenario_path = storage._scenario_path(workspace.id, scenario_id)
    runs_path = scenario_path / "runs"

    runs: List[RunSummary] = []

    if runs_path.exists():
        for run_dir in sorted(runs_path.iterdir(), reverse=True):
            if run_dir.is_dir():
                metadata_file = run_dir / "run_metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file) as f:
                            metadata = json.load(f)

                        # Count artifacts
                        artifact_count = sum(1 for f in run_dir.iterdir() if f.is_file())

                        runs.append(RunSummary(
                            id=run_dir.name,
                            scenario_id=scenario_id,
                            status=metadata.get("status", "completed"),
                            started_at=datetime.fromisoformat(metadata["started_at"]),
                            completed_at=datetime.fromisoformat(metadata["completed_at"]) if metadata.get("completed_at") else None,
                            duration_seconds=metadata.get("duration_seconds"),
                            start_year=metadata.get("start_year"),
                            end_year=metadata.get("end_year"),
                            total_events=metadata.get("events_generated"),
                            final_headcount=metadata.get("final_headcount"),
                            artifact_count=artifact_count,
                        ))
                    except Exception as e:
                        logger.warning(f"Error loading run metadata from {run_dir}: {e}")
                        continue

    # Also check for legacy runs in results/ folder (migration path)
    # Include these alongside new runs for complete history
    results_path = scenario_path / "results"
    if results_path.exists():
        legacy_metadata = results_path / "run_metadata.json"
        if legacy_metadata.exists():
            try:
                with open(legacy_metadata) as f:
                    metadata = json.load(f)

                # Get run_id from metadata (preferred) or use scenario's last_run_id
                run_id = metadata.get("run_id") or scenario.last_run_id or "legacy"

                # Check if this run_id is already in the runs list (avoid duplicates)
                existing_ids = {r.id for r in runs}
                if run_id not in existing_ids:
                    # Count artifacts in results folder
                    artifact_count = sum(1 for f in results_path.iterdir() if f.is_file())

                    runs.append(RunSummary(
                        id=run_id,
                        scenario_id=scenario_id,
                        status=metadata.get("status", "completed"),
                        started_at=datetime.fromisoformat(metadata["started_at"]),
                        completed_at=datetime.fromisoformat(metadata["completed_at"]) if metadata.get("completed_at") else None,
                        duration_seconds=metadata.get("duration_seconds"),
                        start_year=metadata.get("start_year"),
                        end_year=metadata.get("end_year"),
                        total_events=metadata.get("events_generated"),
                        final_headcount=metadata.get("final_headcount"),
                        artifact_count=artifact_count,
                    ))
            except Exception as e:
                logger.warning(f"Error loading legacy run metadata: {e}")

    # Sort all runs by started_at descending (most recent first)
    runs.sort(key=lambda r: r.started_at, reverse=True)

    return runs


@router.get("/{scenario_id}/runs/{run_id}", response_model=RunDetails)
async def get_run(
    scenario_id: str,
    run_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> RunDetails:
    """
    Get details for a specific run.
    """
    import json

    workspace, scenario = _find_scenario_and_workspace(storage, scenario_id)
    if not scenario or not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    scenario_path = storage._scenario_path(workspace.id, scenario_id)

    # Try new runs folder structure first
    run_path = scenario_path / "runs" / run_id
    if not run_path.exists():
        # Fall back to legacy results folder
        run_path = scenario_path / "results"
        if not run_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

    # Load run metadata
    metadata_file = run_path / "run_metadata.json"
    metadata = {}
    if metadata_file.exists():
        try:
            with open(metadata_file) as f:
                metadata = json.load(f)
        except Exception:
            pass

    # Load config used for this run
    config = None
    config_file = run_path / "config.yaml"
    if not config_file.exists():
        # Try scenario name pattern
        for f in run_path.glob("*_config.yaml"):
            config_file = f
            break

    if config_file.exists():
        try:
            import yaml
            with open(config_file) as f:
                config = yaml.safe_load(f)
        except Exception:
            pass

    # List artifacts
    artifacts = []
    for file_path in run_path.iterdir():
        if file_path.is_file():
            stat = file_path.stat()
            artifacts.append(Artifact(
                name=file_path.name,
                type=_get_artifact_type(file_path.name),
                size_bytes=stat.st_size,
                path=f"runs/{run_id}/{file_path.name}" if "runs" in str(run_path) else f"results/{file_path.name}",
                created_at=datetime.fromtimestamp(stat.st_ctime),
            ))

    return RunDetails(
        id=run_id,
        scenario_id=scenario_id,
        scenario_name=scenario.name,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        status=metadata.get("status", "completed"),
        started_at=datetime.fromisoformat(metadata["started_at"]) if metadata.get("started_at") else None,
        completed_at=datetime.fromisoformat(metadata["completed_at"]) if metadata.get("completed_at") else None,
        duration_seconds=metadata.get("duration_seconds"),
        start_year=metadata.get("start_year"),
        end_year=metadata.get("end_year"),
        total_years=metadata.get("total_years"),
        total_events=metadata.get("events_generated"),
        final_headcount=metadata.get("final_headcount"),
        participation_rate=metadata.get("participation_rate"),
        config=config,
        artifacts=sorted(artifacts, key=lambda a: a.name),
        error_message=metadata.get("error_message"),
    )


@router.get("/{scenario_id}/results", response_model=SimulationResults)
async def get_results(
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
    simulation_service: SimulationService = Depends(get_simulation_service),
) -> SimulationResults:
    """
    Get simulation results for a completed scenario.

    Will return results if either:
    - The scenario status is "completed", OR
    - There is a completed run in the run history
    """
    workspace, scenario = _find_scenario_and_workspace(storage, scenario_id)
    if not scenario or not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    # First check if results exist (this also validates scenario has completed runs)
    results = simulation_service.get_results(workspace.id, scenario_id)
    if results:
        # Update scenario status if it's stale (has results but status isn't completed)
        if scenario.status != "completed":
            storage.update_scenario_status(workspace.id, scenario_id, "completed")
        return results

    # If no results and scenario status is not completed, return appropriate error
    if scenario.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Scenario {scenario_id} has not completed successfully (status: {scenario.status})",
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Results not found for scenario {scenario_id}",
    )


@router.get("/{scenario_id}/results/export")
async def export_results(
    scenario_id: str,
    format: str = "excel",
    storage: WorkspaceStorage = Depends(get_storage),
) -> FileResponse:
    """
    Export simulation results as Excel or CSV.

    Will attempt export if results files exist, regardless of scenario status.
    """
    workspace, scenario = _find_scenario_and_workspace(storage, scenario_id)
    if not scenario or not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    # Check for results file - look for {scenario_name}_results.xlsx pattern
    scenario_path = storage._scenario_path(workspace.id, scenario_id)
    results_dir = scenario_path / "results"

    if format == "excel":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        media_type = "text/csv"
        ext = "csv"

    # Try to find the results file (check multiple naming patterns)
    results_file = None
    if results_dir.exists():
        # First try: {scenario_name}_results.xlsx
        candidate = results_dir / f"{scenario.name}_results.{ext}"
        if candidate.exists():
            results_file = candidate
        else:
            # Second try: results.xlsx
            candidate = results_dir / f"results.{ext}"
            if candidate.exists():
                results_file = candidate
            else:
                # Third try: any *_results.xlsx file
                for f in results_dir.glob(f"*_results.{ext}"):
                    results_file = f
                    break

    if results_file and results_file.exists():
        return FileResponse(
            path=results_file,
            media_type=media_type,
            filename=f"{scenario.name}_results.{ext}",
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Export file not found for scenario {scenario_id}. Run the simulation first to generate results.",
    )


def update_run_status(run_id: str, **updates):
    """Update an active run's status (called by simulation service)."""
    if run_id in _active_runs:
        run = _active_runs[run_id]
        for key, value in updates.items():
            if hasattr(run, key):
                setattr(run, key, value)


def _get_artifact_type(filename: str) -> str:
    """Determine artifact type from filename."""
    ext = Path(filename).suffix.lower()
    return ARTIFACT_TYPE_MAP.get(ext, "other")


def _list_artifacts(scenario_path: Path) -> List[Artifact]:
    """List all artifacts in a scenario's results directory."""
    artifacts = []

    # Check results directory
    results_path = scenario_path / "results"
    if results_path.exists():
        for file_path in results_path.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                artifacts.append(
                    Artifact(
                        name=file_path.name,
                        type=_get_artifact_type(file_path.name),
                        size_bytes=stat.st_size,
                        path=f"results/{file_path.name}",
                        created_at=datetime.fromtimestamp(stat.st_ctime),
                    )
                )

    # Also check for files directly in scenario dir
    for file_path in scenario_path.iterdir():
        if file_path.is_file() and file_path.name != "metadata.json":
            stat = file_path.stat()
            artifacts.append(
                Artifact(
                    name=file_path.name,
                    type=_get_artifact_type(file_path.name),
                    size_bytes=stat.st_size,
                    path=file_path.name,
                    created_at=datetime.fromtimestamp(stat.st_ctime),
                )
            )

    return sorted(artifacts, key=lambda a: a.name)


@router.get("/{scenario_id}/details", response_model=RunDetails)
async def get_run_details(
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> RunDetails:
    """
    Get detailed information about a scenario's last simulation run.

    Includes timing, configuration, artifacts, and results summary.
    """
    import json

    try:
        workspace, scenario = _find_scenario_and_workspace(storage, scenario_id)
        if not scenario or not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )

        # Get merged config
        config = storage.get_merged_config(workspace.id, scenario_id)

        # Get scenario path
        scenario_path = storage._scenario_path(workspace.id, scenario_id)

        # Try to load run metadata from file
        run_metadata = None

        # First try: Look in runs/{run_id}/ directory (new structure)
        if scenario.last_run_id:
            metadata_path = scenario_path / "runs" / scenario.last_run_id / "run_metadata.json"
            if metadata_path.exists():
                try:
                    with open(metadata_path) as f:
                        run_metadata = json.load(f)
                except Exception:
                    pass

        # Second try: Look in most recent run directory
        if not run_metadata:
            runs_dir = scenario_path / "runs"
            if runs_dir.exists():
                run_dirs = sorted(
                    [d for d in runs_dir.iterdir() if d.is_dir()],
                    key=lambda d: d.stat().st_mtime,
                    reverse=True,
                )
                for run_dir in run_dirs:
                    metadata_path = run_dir / "run_metadata.json"
                    if metadata_path.exists():
                        try:
                            with open(metadata_path) as f:
                                run_metadata = json.load(f)
                            break
                        except Exception:
                            continue

        # Third try: Legacy results/ directory
        if not run_metadata:
            metadata_path = scenario_path / "results" / "run_metadata.json"
            if metadata_path.exists():
                try:
                    with open(metadata_path) as f:
                        run_metadata = json.load(f)
                except Exception:
                    pass

        # Calculate duration - prefer metadata file, then active run
        duration_seconds = None
        started_at = scenario.last_run_at
        completed_at = None
        total_events = None

        error_message = None
        final_headcount_from_metadata = None
        if run_metadata:
            duration_seconds = run_metadata.get("duration_seconds")
            total_events = run_metadata.get("events_generated")
            final_headcount_from_metadata = run_metadata.get("final_headcount")
            error_message = run_metadata.get("error_message")
            if run_metadata.get("started_at"):
                started_at = datetime.fromisoformat(run_metadata["started_at"])
            if run_metadata.get("completed_at"):
                completed_at = datetime.fromisoformat(run_metadata["completed_at"])
        elif scenario.last_run_at:
            # Check if still running
            if scenario.last_run_id and scenario.last_run_id in _active_runs:
                active_run = _active_runs[scenario.last_run_id]
                if active_run.started_at:
                    duration_seconds = (datetime.now() - active_run.started_at).total_seconds()

        # Get simulation years from config
        sim_config = config.get("simulation", {}) if config else {}
        start_year = sim_config.get("start_year")
        end_year = sim_config.get("end_year")
        # Convert to int if they're strings
        if start_year is not None:
            start_year = int(start_year)
        if end_year is not None:
            end_year = int(end_year)
        total_years = (end_year - start_year + 1) if start_year and end_year else None

        # Get artifacts
        artifacts = _list_artifacts(scenario_path) if scenario_path.exists() else []

        # Get results summary if completed
        final_headcount = final_headcount_from_metadata  # Start with run_metadata value
        participation_rate = None

        if scenario.status == "completed" and scenario.results_summary:
            # Prefer results_summary values if available
            if scenario.results_summary.get("final_headcount"):
                final_headcount = scenario.results_summary.get("final_headcount")
            if not total_events:
                total_events = scenario.results_summary.get("total_events")
            participation_rate = scenario.results_summary.get("participation_rate")

        return RunDetails(
            id=scenario.last_run_id or "none",
            scenario_id=scenario_id,
            scenario_name=scenario.name,
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            status=scenario.status if scenario.status != "not_run" else "not_run",
            started_at=started_at,
            completed_at=completed_at,  # Already set from run_metadata if available
            duration_seconds=duration_seconds,
            start_year=start_year,
            end_year=end_year,
            total_years=total_years,
            final_headcount=final_headcount,
            total_events=total_events,
            participation_rate=participation_rate,
            config=config,
            artifacts=artifacts,
            error_message=error_message,
            storage_path=str(scenario_path) if scenario_path.exists() else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get_run_details for scenario {scenario_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )


@router.get("/{scenario_id}/artifacts/{artifact_path:path}")
async def download_artifact(
    scenario_id: str,
    artifact_path: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> FileResponse:
    """
    Download a specific artifact file.
    """
    workspace, scenario = _find_scenario_and_workspace(storage, scenario_id)
    if not scenario or not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    scenario_path = storage._scenario_path(workspace.id, scenario_id)
    file_path = scenario_path / artifact_path

    if file_path.exists() and file_path.is_file():
        # Determine media type
        ext = file_path.suffix.lower()
        media_type = MEDIA_TYPE_MAP.get(ext, "application/octet-stream")

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=file_path.name,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Artifact {artifact_path} not found",
    )
