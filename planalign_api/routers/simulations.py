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
    SimulationResults,
    SimulationRun,
)
from ..storage.workspace_storage import WorkspaceStorage
from ..services.simulation_service import SimulationService

router = APIRouter()


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
    # Find the scenario (need to search all workspaces for now)
    # In production, scenario_id should be globally unique or include workspace_id
    scenario = None
    workspace_id = None

    for ws in storage.list_workspaces():
        scenario = storage.get_scenario(ws.id, scenario_id)
        if scenario:
            workspace_id = ws.id
            break

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

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
    start_year = int(config.get("simulation", {}).get("start_year", 2025))
    end_year = int(config.get("simulation", {}).get("end_year", 2027))

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
    # Find scenario and its last run
    for ws in storage.list_workspaces():
        scenario = storage.get_scenario(ws.id, scenario_id)
        if scenario:
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

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Scenario {scenario_id} not found",
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
            for ws in storage.list_workspaces():
                scenario = storage.get_scenario(ws.id, scenario_id)
                if scenario:
                    storage.update_scenario_status(ws.id, scenario_id, "cancelled")
                    break

            return {"success": True}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No running simulation found for scenario {scenario_id}",
    )


@router.get("/{scenario_id}/results", response_model=SimulationResults)
async def get_results(
    scenario_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
    simulation_service: SimulationService = Depends(get_simulation_service),
) -> SimulationResults:
    """
    Get simulation results for a completed scenario.
    """
    # Find scenario
    for ws in storage.list_workspaces():
        scenario = storage.get_scenario(ws.id, scenario_id)
        if scenario:
            if scenario.status != "completed":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Scenario {scenario_id} has not completed successfully",
                )

            results = simulation_service.get_results(ws.id, scenario_id)
            if results:
                return results

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Results not found for scenario {scenario_id}",
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Scenario {scenario_id} not found",
    )


@router.get("/{scenario_id}/results/export")
async def export_results(
    scenario_id: str,
    format: str = "excel",
    storage: WorkspaceStorage = Depends(get_storage),
) -> FileResponse:
    """
    Export simulation results as Excel or CSV.
    """
    # Find scenario
    for ws in storage.list_workspaces():
        scenario = storage.get_scenario(ws.id, scenario_id)
        if scenario:
            if scenario.status != "completed":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Scenario {scenario_id} has not completed successfully",
                )

            # Check for results file - look for {scenario_name}_results.xlsx pattern
            scenario_path = storage._scenario_path(ws.id, scenario_id)
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

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Scenario {scenario_id} not found",
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
    type_map = {
        ".xlsx": "excel",
        ".xls": "excel",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".duckdb": "duckdb",
        ".json": "json",
        ".txt": "text",
        ".csv": "text",
        ".log": "text",
    }
    return type_map.get(ext, "other")


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

    # Find scenario and workspace
    workspace = None
    scenario = None

    for ws in storage.list_workspaces():
        scenario = storage.get_scenario(ws.id, scenario_id)
        if scenario:
            workspace = ws
            break

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

    if run_metadata:
        duration_seconds = run_metadata.get("duration_seconds")
        total_events = run_metadata.get("events_generated")
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
    total_years = (end_year - start_year + 1) if start_year and end_year else None

    # Get artifacts
    artifacts = _list_artifacts(scenario_path) if scenario_path.exists() else []

    # Get results summary if completed
    final_headcount = None
    participation_rate = None

    if scenario.status == "completed" and scenario.results_summary:
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
        completed_at=completed_at if scenario.status == "completed" else None,
        duration_seconds=duration_seconds,
        start_year=start_year,
        end_year=end_year,
        total_years=total_years,
        final_headcount=final_headcount,
        total_events=total_events,
        participation_rate=participation_rate,
        config=config,
        artifacts=artifacts,
        error_message=None,  # TODO: Store error messages
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
    # Find scenario
    for ws in storage.list_workspaces():
        scenario = storage.get_scenario(ws.id, scenario_id)
        if scenario:
            scenario_path = storage._scenario_path(ws.id, scenario_id)
            file_path = scenario_path / artifact_path

            if file_path.exists() and file_path.is_file():
                # Determine media type
                ext = file_path.suffix.lower()
                media_types = {
                    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ".yaml": "application/x-yaml",
                    ".yml": "application/x-yaml",
                    ".json": "application/json",
                    ".csv": "text/csv",
                    ".txt": "text/plain",
                    ".log": "text/plain",
                    ".duckdb": "application/octet-stream",
                }
                media_type = media_types.get(ext, "application/octet-stream")

                return FileResponse(
                    path=file_path,
                    media_type=media_type,
                    filename=file_path.name,
                )

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Artifact {artifact_path} not found",
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Scenario {scenario_id} not found",
    )
