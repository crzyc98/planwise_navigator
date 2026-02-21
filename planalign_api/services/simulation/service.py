"""Simulation service – thin coordinator that delegates to focused modules."""

import asyncio
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import yaml

from ...models.simulation import (
    PerformanceMetrics,
    SimulationResults,
    SimulationTelemetry,
)
from ...storage.workspace_storage import WorkspaceStorage
from ..telemetry_service import get_telemetry_service
from ..database_path_resolver import DatabasePathResolver

from .db_cleanup import cleanup_years_outside_range
from .output_parser import SimulationOutputParser
from .results_reader import read_results
from .run_archiver import archive_run, prune_old_runs
from .subprocess_utils import create_subprocess, wait_subprocess

logger = logging.getLogger(__name__)


def _get_memory_mb() -> float:
    """Get current process memory usage in MB."""
    try:
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


class SimulationService:
    """Service for executing and managing simulations.

    Orchestrates subprocess execution, progress tracking, result retrieval,
    and run archival by composing focused helper modules.
    """

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(storage)
        self._cancelled_runs: set = set()
        self._active_runs: Dict[str, Any] = {}
        self._active_processes: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute_simulation(
        self,
        workspace_id: str,
        scenario_id: str,
        run_id: str,
        config: Dict[str, Any],
        resume_from_checkpoint: bool = False,
    ) -> None:
        """Execute a simulation using the planalign CLI.

        Runs ``planalign simulate`` as a subprocess, parses output for
        progress updates, and archives run artifacts on completion.
        """
        from ...routers.simulations import update_run_status

        logger.info(
            f"execute_simulation called: workspace={workspace_id}, "
            f"scenario={scenario_id}, run={run_id}"
        )

        try:
            # Mark as running
            update_run_status(run_id, status="running")
            self.storage.update_scenario_status(
                workspace_id, scenario_id, "running", run_id
            )

            # Extract year range
            sim_config = config.get("simulation", {})
            start_year = int(sim_config.get("start_year", 2025))
            end_year = int(sim_config.get("end_year", 2027))
            total_years = end_year - start_year + 1
            logger.info(
                f"SimulationService year range: {start_year}-{end_year} "
                f"({total_years} years)"
            )

            # Prepare scenario directory and config
            scenario_path = self.storage._scenario_path(workspace_id, scenario_id)
            config_path = scenario_path / "config.yaml"

            self._validate_census(config)
            self._write_config(config, config_path)
            self._write_seeds(config, scenario_path)

            # Clean stale year data
            scenario_db_path = scenario_path / "simulation.duckdb"
            if scenario_db_path.exists():
                cleanup_years_outside_range(scenario_db_path, start_year, end_year)

            # Launch subprocess
            cmd = self._build_command(
                config_path, scenario_db_path, start_year, end_year
            )
            project_root = Path(__file__).parent.parent.parent.parent
            env = self._build_env(project_root)

            logger.info(f"Command: {' '.join(cmd)}")

            process, line_iterator = await create_subprocess(
                cmd=cmd, cwd=str(project_root), env=env
            )
            self._active_processes[run_id] = process

            # Set up telemetry and output parsing
            start_time = datetime.now()
            telemetry_service = get_telemetry_service()
            await self._wait_for_ws_listener(telemetry_service, run_id)
            self._send_initial_telemetry(
                telemetry_service, run_id, start_year, end_year, total_years
            )

            parser = SimulationOutputParser(start_year, total_years)

            # Stream and parse subprocess output
            output_buffer = await self._stream_output(
                process,
                line_iterator,
                run_id,
                parser,
                total_years,
                start_time,
                telemetry_service,
                update_run_status,
            )

            # Await exit code
            return_code = await wait_subprocess(process)
            self._active_processes.pop(run_id, None)
            final_elapsed = (datetime.now() - start_time).total_seconds()

            if return_code != 0:
                self._raise_subprocess_error(return_code, output_buffer)

            # Mark completed
            update_run_status(
                run_id,
                status="completed",
                progress=100,
                current_stage="COMPLETED",
                completed_at=datetime.now(),
            )
            self.storage.update_scenario_status(
                workspace_id, scenario_id, "completed", run_id
            )

            # Final telemetry
            telemetry_service.update_telemetry(
                run_id=run_id,
                progress=100,
                current_stage="COMPLETED",
                current_year=end_year,
                total_years=total_years,
                memory_mb=_get_memory_mb(),
                events_generated=parser.events_generated,
                elapsed_seconds=final_elapsed,
                events_per_second=(
                    parser.events_generated / final_elapsed
                    if final_elapsed > 0
                    else 0
                ),
                recent_events=parser.recent_events,
            )

            logger.info(
                f"Simulation {run_id} completed successfully in {final_elapsed:.1f}s"
            )

            # Archive run artifacts
            scenario = self.storage.get_scenario(workspace_id, scenario_id)
            scenario_name = scenario.name if scenario else scenario_id
            seed = config.get("simulation", {}).get("seed", 42)

            archive_run(
                scenario_path=scenario_path,
                run_id=run_id,
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                workspace_id=workspace_id,
                config=config,
                start_time=start_time,
                elapsed_seconds=final_elapsed,
                start_year=start_year,
                end_year=end_year,
                events_generated=parser.events_generated,
                seed=seed,
            )

            # Prune old runs
            prune_old_runs(self.storage, workspace_id, scenario_id, config)

        except Exception as e:
            logger.exception(f"Simulation {run_id} failed")
            update_run_status(
                run_id,
                status="failed",
                error_message=str(e),
                completed_at=datetime.now(),
            )
            self.storage.update_scenario_status(
                workspace_id, scenario_id, "failed", run_id
            )
            try:
                ts = get_telemetry_service()
                ts.update_telemetry(
                    run_id=run_id,
                    progress=0,
                    current_stage="FAILED",
                    current_year=(
                        current_year if "current_year" in dir() else start_year  # noqa: F821
                    ),
                    total_years=total_years if "total_years" in dir() else 3,  # noqa: F821
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Cancel / Results / Telemetry
    # ------------------------------------------------------------------

    def cancel_simulation(self, run_id: str) -> bool:
        """Signal a running simulation to cancel and terminate subprocess."""
        self._cancelled_runs.add(run_id)
        if run_id in self._active_processes:
            process = self._active_processes[run_id]
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            del self._active_processes[run_id]
        return True

    def get_results(
        self, workspace_id: str, scenario_id: str
    ) -> Optional[SimulationResults]:
        """Get simulation results for a completed scenario."""
        return read_results(
            workspace_id, scenario_id, self.storage, self.db_resolver
        )

    def get_telemetry(self, run_id: str) -> Optional[SimulationTelemetry]:
        """Get current telemetry for a running simulation."""
        if run_id not in self._active_runs:
            return None
        run = self._active_runs[run_id]
        return SimulationTelemetry(
            run_id=run_id,
            progress=run.progress,
            current_stage=run.current_stage or "UNKNOWN",
            current_year=run.current_year or 2025,
            total_years=run.total_years or 3,
            performance_metrics=PerformanceMetrics(
                memory_mb=512.0,
                memory_pressure="low",
                elapsed_seconds=0.0,
                events_generated=0,
                events_per_second=0.0,
            ),
            recent_events=[],
        )

    # ------------------------------------------------------------------
    # Dev helper
    # ------------------------------------------------------------------

    async def _simulate_progress(
        self,
        run_id: str,
        start_year: int,
        end_year: int,
        total_years: int,
        update_run_status,
    ) -> None:
        """Simulate progress for development when orchestrator is unavailable."""
        stages = [
            "INITIALIZATION",
            "FOUNDATION",
            "EVENT_GENERATION",
            "STATE_ACCUMULATION",
            "VALIDATION",
            "REPORTING",
        ]
        for year_idx, year in enumerate(range(start_year, end_year + 1)):
            if run_id in self._cancelled_runs:
                return
            for stage_idx, stage in enumerate(stages):
                if run_id in self._cancelled_runs:
                    return
                year_progress = year_idx / total_years
                stage_progress = stage_idx / len(stages) / total_years
                total_progress = int((year_progress + stage_progress) * 100)
                update_run_status(
                    run_id,
                    progress=total_progress,
                    current_year=year,
                    current_stage=stage,
                )
                await asyncio.sleep(0.3)

    # ------------------------------------------------------------------
    # Private helpers (config prep / subprocess orchestration)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_census(config: Dict[str, Any]) -> None:
        census_path = config.get("setup", {}).get("census_parquet_path")
        if census_path:
            if not Path(census_path).exists():
                raise ValueError(f"Census file not found: {census_path}")
            logger.info(f"Using census file: {census_path}")
        else:
            logger.warning("No census_parquet_path in config - using default")

    @staticmethod
    def _write_config(config: Dict[str, Any], config_path: Path) -> None:
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.info(f"Wrote merged config to: {config_path}")

    @staticmethod
    def _write_seeds(config: Dict[str, Any], scenario_path: Path) -> None:
        try:
            from planalign_orchestrator.pipeline.seed_writer import write_all_seed_csvs

            scenario_seeds_dir = scenario_path / "seeds"
            written = write_all_seed_csvs(config, scenario_seeds_dir)
            written_sections = [k for k, v in written.items() if v]

            if written_sections:
                dbt_seeds_dir = (
                    Path(__file__).parent.parent.parent.parent / "dbt" / "seeds"
                )
                for csv_file in scenario_seeds_dir.glob("config_*.csv"):
                    shutil.copy2(csv_file, dbt_seeds_dir / csv_file.name)
                logger.info(
                    f"313: Wrote scenario seeds to {scenario_seeds_dir} "
                    f"and copied to dbt/seeds/: {', '.join(written_sections)}"
                )
            else:
                logger.info("313: No seed config overrides — using global CSV defaults")
        except Exception as e:
            logger.warning(
                f"313: Failed to write seed CSVs (using global defaults): {e}"
            )

    @staticmethod
    def _build_command(
        config_path: Path,
        scenario_db_path: Path,
        start_year: int,
        end_year: int,
    ) -> List[str]:
        year_range = (
            f"{start_year}-{end_year}" if start_year != end_year else str(start_year)
        )
        return [
            sys.executable,
            "-m",
            "planalign_cli.main",
            "simulate",
            year_range,
            "--config",
            os.fspath(config_path),
            "--database",
            os.fspath(scenario_db_path),
            "--verbose",
        ]

    @staticmethod
    def _build_env(project_root: Path) -> Dict[str, str]:
        return {
            **os.environ,
            "PYTHONPATH": str(project_root),
            "PYTHONIOENCODING": "utf-8",
            "TERM": "dumb",
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
            "COLUMNS": "200",
        }

    @staticmethod
    async def _wait_for_ws_listener(telemetry_service, run_id: str) -> None:
        logger.info(f"Waiting for WebSocket listener for run {run_id}")
        max_wait, interval, waited = 5.0, 0.1, 0.0
        while waited < max_wait:
            if (
                run_id in telemetry_service._listeners
                and telemetry_service._listeners[run_id]
            ):
                logger.info(
                    f"WebSocket listener connected for run {run_id} after {waited:.1f}s"
                )
                return
            await asyncio.sleep(interval)
            waited += interval
        logger.warning(
            f"No WebSocket listener connected for run {run_id} after {max_wait}s, "
            "proceeding anyway"
        )

    @staticmethod
    def _send_initial_telemetry(
        telemetry_service,
        run_id: str,
        start_year: int,
        end_year: int,
        total_years: int,
    ) -> None:
        logger.info(f"Sending initial telemetry for run {run_id}")
        telemetry_service.update_telemetry(
            run_id=run_id,
            progress=1,
            current_stage="INITIALIZATION",
            current_year=start_year,
            total_years=total_years,
            memory_mb=0.0,
            events_generated=0,
            elapsed_seconds=0.0,
            events_per_second=0.0,
            recent_events=[
                {
                    "event_type": "INFO",
                    "employee_id": "System",
                    "timestamp": datetime.now().isoformat(),
                    "details": f"Simulation started for years {start_year}-{end_year}",
                }
            ],
        )

    async def _stream_output(
        self,
        process,
        line_iterator,
        run_id: str,
        parser: SimulationOutputParser,
        total_years: int,
        start_time: datetime,
        telemetry_service,
        update_run_status,
    ) -> List[str]:
        """Read subprocess output, parse progress, broadcast telemetry.

        Returns the output buffer (last N lines) for error diagnostics.
        """
        output_buffer: List[str] = []
        MAX_OUTPUT_BUFFER = 50

        async for line in line_iterator:
            if run_id in self._cancelled_runs:
                process.terminate()
                logger.info(f"Simulation {run_id} cancelled")
                return output_buffer

            line_text = line.decode("utf-8", errors="replace").strip()
            if not line_text:
                continue

            # Rolling buffer for error context
            output_buffer.append(line_text)
            if len(output_buffer) > MAX_OUTPUT_BUFFER:
                output_buffer.pop(0)

            # Route to appropriate log level
            level = SimulationOutputParser.classify_line(line_text)
            if level == "error":
                logger.error(f"Simulation: {line_text}")
            elif level == "warning":
                logger.warning(f"Simulation: {line_text}")
            else:
                logger.debug(f"Simulation output: {line_text}")

            # Parse progress from line
            parser.parse_line(line_text)
            progress = parser.calculate_progress()

            elapsed_seconds = (datetime.now() - start_time).total_seconds()

            update_run_status(
                run_id,
                progress=progress,
                current_year=parser.current_year,
                current_stage=parser.current_stage,
            )

            telemetry_service.update_telemetry(
                run_id=run_id,
                progress=progress,
                current_stage=parser.current_stage,
                current_year=parser.current_year,
                total_years=total_years,
                memory_mb=_get_memory_mb(),
                events_generated=parser.events_generated,
                elapsed_seconds=elapsed_seconds,
                events_per_second=(
                    parser.events_generated / elapsed_seconds
                    if elapsed_seconds > 0
                    else 0
                ),
                recent_events=parser.recent_events,
            )

        return output_buffer

    @staticmethod
    def _raise_subprocess_error(
        return_code: int, output_buffer: List[str]
    ) -> None:
        logger.error(f"Simulation failed with exit code {return_code}")
        logger.error("Last output lines:")
        for line in output_buffer[-20:]:
            logger.error(f"  {line}")
        error_context = "\n".join(output_buffer[-10:])
        raise RuntimeError(
            f"planalign simulate exited with code {return_code}. "
            f"Last output:\n{error_context}"
        )
