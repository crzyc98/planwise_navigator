"""Simulation service – thin coordinator that delegates to focused modules."""

import asyncio
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import yaml  # type: ignore[import]  # types-PyYAML not in CI deps

from ...models.simulation import (
    PerformanceMetrics,
    SimulationResults,
    SimulationTelemetry,
)
from ...storage.workspace_storage import WorkspaceStorage
from ..telemetry_service import get_telemetry_service
from ..database_path_resolver import (
    DatabasePathResolver,
    create_api_database_path_resolver,
)

from .db_cleanup import cleanup_years_outside_range
from .log_writer import SimulationLogWriter
from .output_parser import SimulationOutputParser
from .results_reader import read_results
from .run_archiver import archive_failed_run, archive_run, prune_old_runs
from .subprocess_utils import create_subprocess, wait_subprocess

from planalign_core.constants import (
    DATABASE_FILENAME,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
)

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
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)
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

        log_writer: Optional[SimulationLogWriter] = None
        run_dir: Optional[Path] = None
        run_start_time = datetime.now()

        # Feature 094: create telemetry state before any preparation work so
        # failures during config/census validation still reach the dashboard
        # as a terminal status instead of leaving it stuck on "running".
        sim_config = config.get("simulation", {})
        start_year = int(sim_config.get("start_year", 2025))
        end_year = int(sim_config.get("end_year", 2027))
        total_years = end_year - start_year + 1
        get_telemetry_service().start_run(
            run_id,
            scenario_id=scenario_id,
            start_year=start_year,
            total_years=total_years,
        )

        try:
            # Mark as running
            update_run_status(run_id, status=STATUS_RUNNING)
            self.storage.update_scenario_status(
                workspace_id, scenario_id, STATUS_RUNNING, run_id
            )

            # Prepare simulation resources
            scenario_path, start_year, end_year, total_years = self._prepare_simulation(
                workspace_id, scenario_id, config
            )

            # Create run dir early so partial logs survive failures (T005)
            run_dir = scenario_path / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            log_writer = SimulationLogWriter(run_dir)

            # Run the simulation subprocess loop
            parser, start_time, final_elapsed = await self._run_simulation_loop(
                scenario_path,
                start_year,
                end_year,
                total_years,
                run_id,
                config,
                update_run_status,
                log_writer,
            )

            # Handle successful completion
            self._finalize_successful_simulation(
                workspace_id,
                scenario_id,
                run_id,
                config,
                scenario_path,
                start_year,
                end_year,
                total_years,
                parser,
                start_time,
                final_elapsed,
                update_run_status,
                run_dir=run_dir,
            )

        except Exception as e:
            self._handle_simulation_failure(
                e,
                workspace_id,
                scenario_id,
                run_id,
                update_run_status,
                config=config,
                run_dir=run_dir,
                start_time=run_start_time,
                start_year=start_year,
                end_year=end_year,
            )
        finally:
            if log_writer is not None:
                log_writer.close()

    def _prepare_simulation(
        self,
        workspace_id: str,
        scenario_id: str,
        config: Dict[str, Any],
    ) -> "tuple[Path, int, int, int]":
        """Prepare scenario directory, config, seeds, and year range.

        Returns (scenario_path, start_year, end_year, total_years).
        """
        sim_config = config.get("simulation", {})
        start_year = int(sim_config.get("start_year", 2025))
        end_year = int(sim_config.get("end_year", 2027))
        total_years = end_year - start_year + 1
        logger.info(
            f"SimulationService year range: {start_year}-{end_year} "
            f"({total_years} years)"
        )

        scenario_path = self.storage._scenario_path(workspace_id, scenario_id)
        config_path = scenario_path / "config.yaml"

        self._validate_census(
            config, scenario_id=scenario_id, workspace_id=workspace_id
        )
        self._write_config(config, config_path)
        self._write_seeds(config, scenario_path)

        # Clean stale year data
        scenario_db_path = scenario_path / DATABASE_FILENAME
        if scenario_db_path.exists():
            cleanup_years_outside_range(scenario_db_path, start_year, end_year)

        return scenario_path, start_year, end_year, total_years

    async def _run_simulation_loop(
        self,
        scenario_path: Path,
        start_year: int,
        end_year: int,
        total_years: int,
        run_id: str,
        config: Dict[str, Any],
        update_run_status,
        log_writer: Optional["SimulationLogWriter"] = None,
    ) -> tuple:
        """Launch subprocess, stream output, and await completion.

        Returns (parser, start_time, final_elapsed).
        """
        config_path = scenario_path / "config.yaml"
        scenario_db_path = scenario_path / DATABASE_FILENAME
        dbt_project_dir = self._prepare_dbt_project(scenario_path)

        cmd = self._build_command(
            config_path,
            scenario_db_path,
            start_year,
            end_year,
            dbt_project_dir,
        )
        project_root = Path(__file__).parent.parent.parent.parent
        env = self._build_env(project_root)

        logger.info(f"Command: {' '.join(cmd)}")

        process, line_iterator = await create_subprocess(
            cmd=cmd, cwd=str(project_root), env=env
        )
        self._active_processes[run_id] = process

        # Telemetry state was created at execute_simulation start (feature 094)
        start_time = datetime.now()
        telemetry_service = get_telemetry_service()
        await self._wait_for_ws_listener(telemetry_service, run_id)
        telemetry_service.apply_update(
            run_id,
            progress=1,
            current_stage="INITIALIZATION",
            current_year=start_year,
            memory_mb=_get_memory_mb(),
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
            log_writer,
        )

        # Await exit code
        return_code = await wait_subprocess(process)
        self._active_processes.pop(run_id, None)
        final_elapsed = (datetime.now() - start_time).total_seconds()

        if return_code != 0:
            self._raise_subprocess_error(return_code, output_buffer)

        return parser, start_time, final_elapsed

    def _finalize_successful_simulation(
        self,
        workspace_id: str,
        scenario_id: str,
        run_id: str,
        config: Dict[str, Any],
        scenario_path: Path,
        start_year: int,
        end_year: int,
        total_years: int,
        parser: SimulationOutputParser,
        start_time: datetime,
        final_elapsed: float,
        update_run_status,
        run_dir: Optional[Path] = None,
    ) -> None:
        """Mark simulation completed, send final telemetry, archive artifacts."""
        update_run_status(
            run_id,
            status=STATUS_COMPLETED,
            progress=100,
            current_stage="COMPLETED",
            completed_at=datetime.now(),
        )
        self.storage.update_scenario_status(
            workspace_id, scenario_id, STATUS_COMPLETED, run_id
        )

        # Final telemetry (feature 094: terminal state is retained in memory)
        telemetry_service = get_telemetry_service()
        events_per_second = (
            parser.events_generated / final_elapsed if final_elapsed > 0 else 0
        )
        telemetry_service.apply_update(
            run_id,
            progress=100,
            current_stage="COMPLETED",
            current_year=end_year,
            memory_mb=_get_memory_mb(),
            events_generated=parser.events_generated,
            elapsed_seconds=final_elapsed,
            events_per_second=events_per_second,
        )
        telemetry_service.set_terminal(run_id, "completed")

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
            run_dir=run_dir,
        )

        # Prune old runs
        prune_old_runs(self.storage, workspace_id, scenario_id, config)

    def _handle_simulation_failure(
        self,
        error: Exception,
        workspace_id: str,
        scenario_id: str,
        run_id: str,
        update_run_status,
        *,
        config: Optional[Dict[str, Any]] = None,
        run_dir: Optional[Path] = None,
        start_time: Optional[datetime] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> None:
        """Log failure (or cancellation), update status, send terminal telemetry,
        and archive run metadata so the run (and its logs) appear in run history."""
        was_cancelled = run_id in self._cancelled_runs
        terminal_status = "cancelled" if was_cancelled else STATUS_FAILED
        error_message = None if was_cancelled else str(error)
        if was_cancelled:
            logger.info(f"Simulation {run_id} cancelled by user")
        else:
            logger.exception(f"Simulation {run_id} failed")
        update_run_status(
            run_id,
            status=terminal_status,
            error_message=error_message,
            completed_at=datetime.now(),
        )
        self.storage.update_scenario_status(
            workspace_id, scenario_id, terminal_status, run_id
        )
        # Feature 094: guaranteed terminal telemetry; progress is preserved so
        # the dashboard freezes at last-known values instead of resetting to 0.
        try:
            ts = get_telemetry_service()
            ts.set_terminal(
                run_id,
                terminal_status,
                message=error_message[:500] if error_message else None,
            )
        except Exception as e:
            logger.warning(f"Failed to send terminal telemetry for {run_id}: {e}")

        # Persist run metadata so failed/cancelled runs show up in run history
        # with their error message and simulation.log (feature 094).
        try:
            scenario = self.storage.get_scenario(workspace_id, scenario_id)
            archive_failed_run(
                scenario_path=self.storage._scenario_path(workspace_id, scenario_id),
                run_id=run_id,
                scenario_id=scenario_id,
                scenario_name=scenario.name if scenario else scenario_id,
                workspace_id=workspace_id,
                config=config or {},
                start_time=start_time or datetime.now(),
                start_year=start_year,
                end_year=end_year,
                run_status=terminal_status,
                error_message=error_message,
                run_dir=run_dir,
            )
        except Exception as e:
            logger.warning(f"Failed to archive failed run {run_id}: {e}")

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
        self, workspace_id: str, scenario_id: str, population: str = "active"
    ) -> Optional[SimulationResults]:
        """Get simulation results for a completed scenario."""
        return read_results(
            workspace_id, scenario_id, self.storage, self.db_resolver, population
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
    # Private helpers (config prep / subprocess orchestration)
    # ------------------------------------------------------------------

    def _validate_census(
        self,
        config: Dict[str, Any],
        scenario_id: str = "",
        workspace_id: str = "",
    ) -> None:
        from planalign_orchestrator.exceptions import (
            ConfigurationError,
            ErrorSeverity,
            ExecutionContext,
        )

        census_path = config.get("setup", {}).get("census_parquet_path")

        if not census_path or not str(census_path).strip():
            raise ConfigurationError(
                "census_parquet_path is required but was not found in the "
                "scenario config. Ensure a census file has been uploaded to "
                "the scenario folder before running.",
                context=ExecutionContext(
                    scenario_id=scenario_id,
                    metadata={
                        "missing_field": "setup.census_parquet_path",
                        "workspace_id": workspace_id,
                    },
                ),
                severity=ErrorSeverity.ERROR,
            )

        # Resolve relative census paths (e.g. "data/census.parquet") against the
        # workspace directory. Legacy scenarios stored relative paths that would
        # otherwise be resolved against the process CWD and reported as missing.
        resolved = self._resolve_census_path(str(census_path), workspace_id)

        if resolved is None:
            # Scenario overrides may carry a stale or placeholder path (older
            # studio builds persisted "data/census_preprocessed.parquet" as a
            # form default). Fall back to the workspace-level census if one is
            # configured and exists, rather than failing the run.
            fallback = self._workspace_census_fallback(workspace_id)
            if fallback is not None:
                logger.warning(
                    f"Census file not found at '{census_path}'; falling back "
                    f"to workspace census: {fallback}"
                )
                resolved = fallback

        if resolved is None or not resolved.exists():
            raise ConfigurationError(
                f"Census file not found at '{census_path}'. Upload a valid "
                "census parquet file to the scenario folder and retry.",
                context=ExecutionContext(
                    scenario_id=scenario_id,
                    metadata={
                        "expected_path": str(census_path),
                        "workspace_id": workspace_id,
                    },
                ),
                severity=ErrorSeverity.ERROR,
            )

        # Persist the resolved absolute path so the written config.yaml and the
        # downstream dbt invocation read the file from an unambiguous location.
        absolute = str(resolved.resolve())
        config.setdefault("setup", {})["census_parquet_path"] = absolute
        logger.info(f"Using census file: {absolute}")

    def _resolve_census_path(
        self, census_path: str, workspace_id: str
    ) -> Optional[Path]:
        """Return an existing Path for census_path, trying workspace-relative fallbacks."""
        candidate = Path(census_path)
        if candidate.is_absolute():
            return candidate if candidate.exists() else None

        # Studio runs only ever reference files inside the workspace; resolving
        # against the process CWD could silently pick up the repo's bundled
        # sample data (data/census_preprocessed.parquet) instead.
        resolved = self.storage._workspace_path(workspace_id) / census_path
        return resolved if resolved.exists() else None

    def _workspace_census_fallback(self, workspace_id: str) -> Optional[Path]:
        """Return the workspace base-config census path if it exists on disk."""
        try:
            workspace = self.storage.get_workspace(workspace_id)
        except Exception as e:
            logger.warning(f"Could not load workspace for census fallback: {e}")
            return None
        if workspace is None:
            return None
        base_path = workspace.base_config.get("setup", {}).get("census_parquet_path")
        if not base_path or not str(base_path).strip():
            return None
        return self._resolve_census_path(str(base_path), workspace_id)

    @staticmethod
    def _write_config(config: Dict[str, Any], config_path: Path) -> None:
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.info(f"Wrote merged config to: {config_path}")

    @staticmethod
    def _write_seeds(config: Dict[str, Any], scenario_path: Path) -> None:
        """Create a complete, scenario-local dbt seed directory.

        dbt resolves seed files relative to its project directory. Studio runs
        therefore receive a private copy of the repository defaults before any
        scenario overrides are written. The repository's ``dbt/seeds`` folder
        remains an immutable input to every scenario run.
        """
        try:
            from planalign_orchestrator.pipeline.seed_writer import write_all_seed_csvs

            scenario_seeds_dir = scenario_path / "seeds"
            dbt_seeds_dir = Path(__file__).parent.parent.parent.parent / "dbt" / "seeds"
            if scenario_seeds_dir.exists():
                shutil.rmtree(scenario_seeds_dir)
            shutil.copytree(dbt_seeds_dir, scenario_seeds_dir)
            written = write_all_seed_csvs(config, scenario_seeds_dir)
            written_sections = [k for k, v in written.items() if v]

            if written_sections:
                logger.info(
                    f"313: Wrote scenario-local seeds to {scenario_seeds_dir}: "
                    f"{', '.join(written_sections)}"
                )
            else:
                logger.info(
                    "313: Copied default seeds into scenario-local seed directory"
                )
        except Exception as e:
            logger.warning(f"313: Failed to prepare scenario-local seed CSVs: {e}")

    @staticmethod
    def _prepare_dbt_project(scenario_path: Path) -> Path:
        """Create a dbt overlay that uses the scenario's private seed files."""
        dbt_root = Path(__file__).parent.parent.parent.parent / "dbt"
        overlay_dir = scenario_path / "dbt_project"
        overlay_dir.mkdir(parents=True, exist_ok=True)

        # dbt requires a project file at its project root. The copied file keeps
        # its normal ``seed-paths: [\"seeds\"]`` setting, which is linked below
        # to this scenario's complete private seed snapshot.
        shutil.copy2(dbt_root / "dbt_project.yml", overlay_dir / "dbt_project.yml")

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
            source = dbt_root / entry
            if not source.exists():
                continue
            destination = overlay_dir / entry
            if destination.is_symlink() and destination.resolve() == source.resolve():
                continue
            if destination.is_symlink() or destination.is_file():
                destination.unlink()
            elif destination.exists():
                shutil.rmtree(destination)
            destination.symlink_to(source, target_is_directory=source.is_dir())

        scenario_seeds_dir = scenario_path / "seeds"
        seeds_link = overlay_dir / "seeds"
        if (
            seeds_link.is_symlink()
            and seeds_link.resolve() == scenario_seeds_dir.resolve()
        ):
            return overlay_dir
        if seeds_link.is_symlink() or seeds_link.is_file():
            seeds_link.unlink()
        elif seeds_link.exists():
            shutil.rmtree(seeds_link)
        seeds_link.symlink_to(scenario_seeds_dir, target_is_directory=True)
        return overlay_dir

    @staticmethod
    def _build_command(
        config_path: Path,
        scenario_db_path: Path,
        start_year: int,
        end_year: int,
        dbt_project_dir: Path,
    ) -> List[str]:
        year_range = (
            f"{start_year}-{end_year}" if start_year != end_year else str(start_year)
        )
        return [
            "planalign",
            "simulate",
            year_range,
            "--config",
            os.fspath(config_path),
            "--database",
            os.fspath(scenario_db_path),
            "--dbt-project-dir",
            os.fspath(dbt_project_dir),
            "--verbose",
        ]

    @staticmethod
    def _build_env(project_root: Path) -> Dict[str, str]:
        return {
            **os.environ,
            "PYTHONPATH": str(project_root),
            "PYTHONIOENCODING": "utf-8",
            # Feature 094: deterministic stage/year/count telemetry on stdout
            "PLANALIGN_STRUCTURED_TELEMETRY": "1",
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
            if telemetry_service.has_listeners(run_id):
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
        log_writer: Optional["SimulationLogWriter"] = None,
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

            # Classify severity once for the persisted log
            severity = SimulationOutputParser.classify_line(line_text)

            # Persist line to simulation.log
            if log_writer is not None:
                log_writer.write_line(severity, line_text)

            self._process_output_line(
                line_text,
                run_id,
                parser,
                total_years,
                start_time,
                telemetry_service,
                update_run_status,
            )

        return output_buffer

    @staticmethod
    def _process_output_line(
        line_text: str,
        run_id: str,
        parser: SimulationOutputParser,
        total_years: int,
        start_time: datetime,
        telemetry_service,
        update_run_status,
    ) -> None:
        """Classify, parse, and broadcast a single output line."""
        # Route to appropriate log level
        level = SimulationOutputParser.classify_line(line_text)
        if level == "error":
            logger.error(f"Simulation: {line_text}")
        elif level == "warning":
            logger.warning(f"Simulation: {line_text}")
        else:
            logger.debug(f"Simulation output: {line_text}")

        # Parse progress from line (structured sentinel records take precedence)
        changes = parser.parse_line(line_text)
        if changes.get("structured_record"):
            telemetry_service.apply_structured_record(
                run_id, changes["structured_record"]
            )
        elif level in ("warning", "error"):
            telemetry_service.add_log_milestone(run_id, level, line_text)

        progress = parser.calculate_progress()
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        events_per_second = (
            parser.events_generated / elapsed_seconds if elapsed_seconds > 0 else 0
        )

        update_run_status(
            run_id,
            progress=progress,
            current_year=parser.current_year,
            current_stage=parser.current_stage,
        )

        telemetry_service.apply_update(
            run_id,
            progress=progress,
            current_stage=parser.current_stage,
            current_year=parser.current_year,
            memory_mb=_get_memory_mb(),
            events_generated=parser.events_generated,
            elapsed_seconds=elapsed_seconds,
            events_per_second=events_per_second,
        )

    @staticmethod
    def _raise_subprocess_error(return_code: int, output_buffer: List[str]) -> None:
        logger.error(f"Simulation failed with exit code {return_code}")
        logger.error("Last output lines:")
        for line in output_buffer[-20:]:
            logger.error(f"  {line}")
        error_context = "\n".join(output_buffer[-10:])
        raise RuntimeError(
            f"planalign simulate exited with code {return_code}. "
            f"Last output:\n{error_context}"
        )
