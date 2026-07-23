"""Run-local simulation process construction, streaming, and cancellation."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import yaml

from planalign_core.constants import DATABASE_FILENAME

from ...storage.workspace_storage import WorkspaceStorage
from ..provenance.capture import ProvenanceRecorder
from ..telemetry_service import get_telemetry_service
from .log_writer import SimulationLogWriter
from .output_parser import SimulationOutputParser
from .subprocess_utils import create_subprocess, wait_subprocess

logger = logging.getLogger(__name__)
CANCEL_GRACE_SECONDS = 5.0


class ActiveProcessRegistry:
    """Process-local subprocess ownership shared by request-scoped services."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.processes: Dict[str, Any] = {}
        self.cancelled_runs: set[str] = set()

    def register(self, run_id: str, process: Any) -> None:
        with self._lock:
            self.processes[run_id] = process

    def remove(self, run_id: str, process: Optional[Any] = None) -> None:
        with self._lock:
            if process is None or self.processes.get(run_id) is process:
                self.processes.pop(run_id, None)

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self.cancelled_runs

    async def cancel(self, run_id: str) -> bool:
        with self._lock:
            process = self.processes.get(run_id)
        if process is None or not await _stop_process(process, run_id):
            return False
        with self._lock:
            self.cancelled_runs.add(run_id)
            if self.processes.get(run_id) is process:
                self.processes.pop(run_id, None)
        return True


async def _stop_process(process: Any, run_id: str) -> bool:
    try:
        process.terminate()
    except ProcessLookupError:
        return True
    except OSError as exc:
        logger.warning("Could not terminate simulation %s: %s", run_id, exc)
        return False
    try:
        await asyncio.wait_for(wait_subprocess(process), timeout=CANCEL_GRACE_SECONDS)
        return True
    except asyncio.TimeoutError:
        return await _kill_process(process, run_id)
    except (OSError, ProcessLookupError) as exc:
        logger.warning("Could not confirm simulation %s exited: %s", run_id, exc)
        return False


async def _kill_process(process: Any, run_id: str) -> bool:
    try:
        process.kill()
        await wait_subprocess(process)
        return True
    except ProcessLookupError:
        return True
    except OSError as exc:
        logger.warning("Could not kill simulation %s: %s", run_id, exc)
        return False


active_process_registry = ActiveProcessRegistry()


def get_memory_mb() -> float:
    try:
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def resolve_census_path(
    storage: WorkspaceStorage, census_path: str, workspace_id: str
) -> Optional[Path]:
    candidate = Path(census_path)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    resolved = storage._workspace_path(workspace_id) / census_path
    return resolved if resolved.exists() else None


def workspace_census_fallback(
    storage: WorkspaceStorage, workspace_id: str
) -> Optional[Path]:
    try:
        workspace = storage.get_workspace(workspace_id)
    except Exception as exc:
        logger.warning("Could not load workspace for census fallback: %s", exc)
        return None
    if workspace is None:
        return None
    configured = workspace.base_config.get("setup", {}).get("census_parquet_path")
    if not configured or not str(configured).strip():
        return None
    return resolve_census_path(storage, str(configured), workspace_id)


def validate_census(
    storage: WorkspaceStorage,
    config: Dict[str, Any],
    scenario_id: str,
    workspace_id: str,
) -> None:
    from planalign_orchestrator.exceptions import (
        ConfigurationError,
        ErrorSeverity,
        ExecutionContext,
    )

    configured = config.get("setup", {}).get("census_parquet_path")
    if not configured or not str(configured).strip():
        raise ConfigurationError(
            "census_parquet_path is required but was not found in the scenario config.",
            context=ExecutionContext(
                scenario_id=scenario_id,
                metadata={
                    "missing_field": "setup.census_parquet_path",
                    "workspace_id": workspace_id,
                },
            ),
            severity=ErrorSeverity.ERROR,
        )
    resolved = resolve_census_path(storage, str(configured), workspace_id)
    if resolved is None:
        resolved = workspace_census_fallback(storage, workspace_id)
    if resolved is None or not resolved.exists():
        raise ConfigurationError(
            f"Census file not found at '{configured}'. Upload a valid census parquet file and retry.",
            context=ExecutionContext(
                scenario_id=scenario_id,
                metadata={
                    "expected_path": str(configured),
                    "workspace_id": workspace_id,
                },
            ),
            severity=ErrorSeverity.ERROR,
        )
    config.setdefault("setup", {})["census_parquet_path"] = str(resolved.resolve())


def write_config(config: Dict[str, Any], config_path: Path) -> None:
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.dump(config, handle, default_flow_style=False)


def write_seeds(config: Dict[str, Any], run_dir: Path) -> None:
    from planalign_orchestrator.pipeline.seed_writer import write_all_seed_csvs

    seeds_dir = run_dir / "seeds"
    default_seeds = Path(__file__).parents[3] / "dbt" / "seeds"
    if seeds_dir.exists():
        shutil.rmtree(seeds_dir)
    shutil.copytree(default_seeds, seeds_dir)
    write_all_seed_csvs(config, seeds_dir)


def prepare_dbt_project(run_dir: Path) -> Path:
    dbt_root = Path(__file__).parents[3] / "dbt"
    overlay = run_dir / "dbt_project"
    overlay.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dbt_root / "dbt_project.yml", overlay / "dbt_project.yml")
    for entry in (
        "analyses",
        "macros",
        "models",
        "snapshots",
        "tests",
        "packages.yml",
        "package-lock.yml",
        "dbt_packages",
    ):
        _replace_with_link(dbt_root / entry, overlay / entry)
    _replace_with_link(run_dir / "seeds", overlay / "seeds")
    return overlay


def _replace_with_link(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if destination.is_symlink() and destination.resolve() == source.resolve():
        return
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.exists():
        shutil.rmtree(destination)
    destination.symlink_to(source, target_is_directory=source.is_dir())


def build_command(
    config_path: Path,
    database_path: Path,
    start_year: int,
    end_year: int,
    dbt_project_dir: Path,
) -> List[str]:
    years = f"{start_year}-{end_year}" if start_year != end_year else str(start_year)
    return [
        "planalign",
        "simulate",
        years,
        "--config",
        os.fspath(config_path),
        "--database",
        os.fspath(database_path),
        "--dbt-project-dir",
        os.fspath(dbt_project_dir),
        "--verbose",
    ]


def build_env(
    project_root: Path,
    run_id: Optional[str] = None,
    database_path: Optional[Path] = None,
) -> Dict[str, str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(project_root),
        "PYTHONIOENCODING": "utf-8",
        "PLANALIGN_STRUCTURED_TELEMETRY": "1",
        "PLANALIGN_ENTRY_POINT": "studio",
        "TERM": "dumb",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "COLUMNS": "200",
    }
    if run_id is not None:
        env["PLANALIGN_RUN_ID"] = run_id
    if database_path is not None:
        env["DATABASE_PATH"] = str(database_path)
    return env


async def wait_for_ws_listener(telemetry_service: Any, run_id: str) -> None:
    waited = 0.0
    while waited < 5.0:
        if telemetry_service.has_listeners(run_id):
            return
        await asyncio.sleep(0.1)
        waited += 0.1


async def execute_run(
    *,
    run_dir: Path,
    start_year: int,
    end_year: int,
    total_years: int,
    run_id: str,
    update_run_status: Any,
    process_registry: ActiveProcessRegistry,
    log_writer: Optional[SimulationLogWriter] = None,
    provenance_recorder: Optional[ProvenanceRecorder] = None,
) -> tuple[SimulationOutputParser, datetime, float]:
    database = run_dir / DATABASE_FILENAME
    project = prepare_dbt_project(run_dir)
    root = Path(__file__).parents[3]
    command = build_command(
        run_dir / "config.yaml", database, start_year, end_year, project
    )
    process, lines = await create_subprocess(
        cmd=command, cwd=str(root), env=build_env(root, run_id, database)
    )
    process_registry.register(run_id, process)
    started = datetime.now()
    telemetry = get_telemetry_service()
    await wait_for_ws_listener(telemetry, run_id)
    telemetry.apply_update(
        run_id,
        progress=1,
        current_stage="INITIALIZATION",
        current_year=start_year,
        memory_mb=get_memory_mb(),
    )
    parser = SimulationOutputParser(start_year, total_years)
    output = await stream_output(
        process=process,
        lines=lines,
        run_id=run_id,
        parser=parser,
        total_years=total_years,
        started=started,
        telemetry=telemetry,
        update_run_status=update_run_status,
        process_registry=process_registry,
        log_writer=log_writer,
        provenance_recorder=provenance_recorder,
    )
    return_code = await wait_subprocess(process)
    process_registry.remove(run_id, process)
    elapsed = (datetime.now() - started).total_seconds()
    if process_registry.is_cancelled(run_id):
        raise RuntimeError("Simulation cancelled by user")
    if return_code != 0:
        raise_subprocess_error(return_code, output)
    return parser, started, elapsed


async def stream_output(
    *,
    process: Any,
    lines: Any,
    run_id: str,
    parser: SimulationOutputParser,
    total_years: int,
    started: datetime,
    telemetry: Any,
    update_run_status: Any,
    process_registry: ActiveProcessRegistry,
    log_writer: Optional[SimulationLogWriter],
    provenance_recorder: Optional[ProvenanceRecorder],
) -> List[str]:
    output: List[str] = []
    async for line in lines:
        if process_registry.is_cancelled(run_id):
            return output
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        output.append(text)
        output = output[-50:]
        severity = SimulationOutputParser.classify_line(text)
        if log_writer is not None:
            log_writer.write_line(severity, text)
        process_output_line(
            text,
            run_id,
            parser,
            total_years,
            started,
            telemetry,
            update_run_status,
            provenance_recorder,
        )
    return output


def process_output_line(
    line: str,
    run_id: str,
    parser: SimulationOutputParser,
    total_years: int,
    started: datetime,
    telemetry: Any,
    update_run_status: Any,
    provenance_recorder: Optional[ProvenanceRecorder],
) -> None:
    changes = parser.parse_line(line)
    level = SimulationOutputParser.classify_line(line)
    if changes.get("structured_record"):
        if provenance_recorder is not None:
            provenance_recorder.ingest(changes["structured_record"])
        telemetry.apply_structured_record(run_id, changes["structured_record"])
    elif level in {"warning", "error"}:
        telemetry.add_log_milestone(run_id, level, line)
    elapsed = (datetime.now() - started).total_seconds()
    progress = parser.calculate_progress()
    update_run_status(
        run_id,
        progress=progress,
        current_year=parser.current_year,
        current_stage=parser.current_stage,
    )
    telemetry.apply_update(
        run_id,
        progress=progress,
        current_stage=parser.current_stage,
        current_year=parser.current_year,
        memory_mb=get_memory_mb(),
        events_generated=parser.events_generated,
        elapsed_seconds=elapsed,
        events_per_second=parser.events_generated / elapsed if elapsed > 0 else 0,
    )


def raise_subprocess_error(return_code: int, output: List[str]) -> None:
    context = "\n".join(output[-10:])
    raise RuntimeError(
        f"planalign simulate exited with code {return_code}. Last output:\n{context}"
    )
