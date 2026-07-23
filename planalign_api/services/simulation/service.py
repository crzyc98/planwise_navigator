"""Simulation service – thin coordinator that delegates to focused modules."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

from .log_writer import SimulationLogWriter
from .output_parser import SimulationOutputParser
from .results_reader import read_results
from .run_archiver import archive_failed_run, archive_run, export_run_excel
from .run_execution import (
    active_process_registry as _active_process_registry,
    build_command,
    build_env,
    execute_run,
    get_memory_mb,
    prepare_dbt_project,
    validate_census,
    write_config,
    write_seeds,
)
from ..provenance.capture import ProvenanceRecorder, initialize_manifest

from planalign_core.constants import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
)

logger = logging.getLogger(__name__)
_get_memory_mb = get_memory_mb


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
        self._process_registry = _active_process_registry
        # Kept as aliases for existing callers and backwards-compatible tests.
        self._cancelled_runs = self._process_registry.cancelled_runs
        self._active_runs: Dict[str, Any] = {}
        self._active_processes = self._process_registry.processes

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
        provenance_recorder: Optional[ProvenanceRecorder] = None
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

            # Allocate the authoritative run directory before the first write.
            run_dir = self.storage.allocate_run_directory(
                workspace_id, scenario_id, run_id
            )

            # Prepare simulation resources
            scenario_path, start_year, end_year, total_years = self._prepare_simulation(
                workspace_id, scenario_id, config, run_dir
            )

            log_writer = SimulationLogWriter(run_dir)
            provenance_recorder = initialize_manifest(
                run_dir=run_dir,
                run_id=run_id,
                workspace_id=workspace_id,
                scenario_id=scenario_id,
                config=config,
                seed_root=run_dir / "seeds",
                project_root=Path(__file__).parent.parent.parent.parent,
            )

            # Run the simulation subprocess loop
            parser, start_time, final_elapsed = await execute_run(
                run_dir=run_dir,
                start_year=start_year,
                end_year=end_year,
                total_years=total_years,
                run_id=run_id,
                update_run_status=update_run_status,
                process_registry=self._process_registry,
                log_writer=log_writer,
                provenance_recorder=provenance_recorder,
            )

            # Handle successful completion
            await self._finalize_successful_simulation(
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
                provenance_recorder=provenance_recorder,
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
                provenance_recorder=provenance_recorder,
            )
        finally:
            if log_writer is not None:
                log_writer.close()

    def _prepare_simulation(
        self,
        workspace_id: str,
        scenario_id: str,
        config: Dict[str, Any],
        run_dir: Path,
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
        config_path = run_dir / "config.yaml"

        validate_census(self.storage, config, scenario_id, workspace_id)
        write_config(config, config_path)
        write_seeds(config, run_dir)

        return scenario_path, start_year, end_year, total_years

    async def _finalize_successful_simulation(
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
        provenance_recorder: Optional[ProvenanceRecorder] = None,
    ) -> None:
        """Finalize artifacts, atomically promote, then expose completed status."""
        scenario = self.storage.get_scenario(workspace_id, scenario_id)
        scenario_name = scenario.name if scenario else scenario_id
        seed = config.get("simulation", {}).get("random_seed")

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
            finalize_provenance=(
                lambda: provenance_recorder.finalize(
                    STATUS_COMPLETED,
                    completed_at=datetime.now().astimezone(),
                    duration_seconds=final_elapsed,
                )
                if provenance_recorder is not None
                else None
            ),
        )
        self.storage.publish_current_result(workspace_id, scenario_id, run_id)
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
        telemetry_service = get_telemetry_service()
        events_per_second = (
            parser.events_generated / final_elapsed if final_elapsed > 0 else 0
        )
        telemetry_service.apply_update(
            run_id,
            progress=100,
            current_stage="COMPLETED",
            current_year=end_year,
            memory_mb=get_memory_mb(),
            events_generated=parser.events_generated,
            elapsed_seconds=final_elapsed,
            events_per_second=events_per_second,
        )
        telemetry_service.set_terminal(run_id, "completed")
        logger.info(
            f"Simulation {run_id} completed successfully in {final_elapsed:.1f}s"
        )

        # Excel export is a non-critical, potentially multi-minute artifact for
        # large populations. Run it in a worker thread via asyncio.to_thread:
        # the `await` yields the event loop so the just-queued "completed"
        # telemetry frame is flushed to the WebSocket immediately (otherwise a
        # synchronous export blocks the loop and the UI sits at the last
        # progress value for the whole export), and so other API requests are
        # served while it runs. Its failure must never flip an already-promoted,
        # already-completed run to "failed", so swallow-and-log here.
        try:
            await asyncio.to_thread(
                export_run_excel,
                scenario_path=scenario_path,
                scenario_name=scenario_name,
                config=config,
                seed=seed,
                run_dir=run_dir or (scenario_path / "runs" / run_id),
            )
        except Exception as exc:  # noqa: BLE001 - artifact is best-effort
            logger.warning(
                "Excel export failed for completed run %s (non-fatal): %s",
                run_id,
                exc,
            )

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
        provenance_recorder: Optional[ProvenanceRecorder] = None,
    ) -> None:
        """Log failure (or cancellation), update status, send terminal telemetry,
        and archive run metadata so the run (and its logs) appear in run history."""
        was_cancelled = self._process_registry.is_cancelled(run_id)
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
            if run_dir is None:
                raise RuntimeError("run directory was not allocated")
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
        if provenance_recorder is not None:
            try:
                provenance_recorder.finalize(
                    terminal_status,
                    completed_at=datetime.now().astimezone(),
                    duration_seconds=max(
                        0.0,
                        (
                            datetime.now() - (start_time or datetime.now())
                        ).total_seconds(),
                    ),
                )
            except Exception as e:
                logger.warning("Failed to finalize provenance for %s: %s", run_id, e)

    # ------------------------------------------------------------------
    # Cancel / Results / Telemetry
    # ------------------------------------------------------------------

    async def cancel_simulation(self, run_id: str) -> bool:
        """Cancel a registered simulation subprocess shared by all service instances."""
        return await self._process_registry.cancel(run_id)

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

    def _validate_census(
        self,
        config: Dict[str, Any],
        scenario_id: str = "",
        workspace_id: str = "",
    ) -> None:
        validate_census(self.storage, config, scenario_id, workspace_id)

    _write_config = staticmethod(write_config)
    _write_seeds = staticmethod(write_seeds)

    _prepare_dbt_project = staticmethod(prepare_dbt_project)
    _build_command = staticmethod(build_command)
    _build_env = staticmethod(build_env)

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
        provenance_recorder: Optional[ProvenanceRecorder] = None,
    ) -> List[str]:
        """Read subprocess output, parse progress, broadcast telemetry.

        Returns the output buffer (last N lines) for error diagnostics.
        """
        output_buffer: List[str] = []
        MAX_OUTPUT_BUFFER = 50

        async for line in line_iterator:
            if self._process_registry.is_cancelled(run_id):
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
                provenance_recorder,
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
        provenance_recorder: Optional[ProvenanceRecorder] = None,
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
            if provenance_recorder is not None:
                provenance_recorder.ingest(changes["structured_record"])
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
