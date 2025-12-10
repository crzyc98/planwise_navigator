"""Simulation service using planalign CLI for execution."""

import asyncio
import logging
import os
import platform
import psutil
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import yaml
import duckdb

# Thread pool for Windows subprocess I/O
_subprocess_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="subprocess_io")

IS_WINDOWS = platform.system() == "Windows"


async def _create_subprocess(
    cmd: List[str],
    cwd: str,
    env: Dict[str, str],
) -> Tuple[Any, AsyncIterator[bytes]]:
    """
    Create a subprocess in a cross-platform way.

    On Windows, uses subprocess.Popen with threaded I/O to avoid
    asyncio event loop issues. On Unix, uses asyncio.create_subprocess_exec.

    Returns:
        Tuple of (process, async_line_iterator)
    """
    if IS_WINDOWS:
        # On Windows, use Popen + thread-based async reading
        # This is more reliable than asyncio subprocess on Windows
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            bufsize=1,  # Line buffered
        )

        async def read_lines() -> AsyncIterator[bytes]:
            """Read lines from process stdout using thread pool."""
            loop = asyncio.get_event_loop()
            while True:
                line = await loop.run_in_executor(
                    _subprocess_executor,
                    process.stdout.readline
                )
                if not line:
                    break
                yield line

        return process, read_lines()
    else:
        # On Unix, asyncio subprocess works fine
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=env,
        )

        async def read_lines() -> AsyncIterator[bytes]:
            """Read lines from asyncio subprocess."""
            async for line in process.stdout:
                yield line

        return process, read_lines()


async def _wait_subprocess(process: Any) -> int:
    """
    Wait for subprocess to complete in a cross-platform way.

    Returns:
        Exit code of the process
    """
    if IS_WINDOWS:
        # For Popen, use thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_subprocess_executor, process.wait)
    else:
        # For asyncio subprocess, use await
        return await process.wait()


from ..models.simulation import (
    PerformanceMetrics,
    RecentEvent,
    SimulationResults,
    SimulationRun,
    SimulationTelemetry,
)
from ..storage.workspace_storage import WorkspaceStorage
from ..constants import MAX_RECENT_EVENTS, DEFAULT_PARTICIPATION_RATE
from .telemetry_service import get_telemetry_service

logger = logging.getLogger(__name__)


def _export_results_to_excel(
    scenario_path: Path,
    scenario_name: str,
    config: Dict[str, Any],
    seed: int,
    run_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Export simulation results to Excel after successful completion.

    Args:
        scenario_path: Path to the scenario directory
        scenario_name: Name of the scenario
        config: Simulation configuration dictionary
        seed: Random seed used for the simulation
        run_dir: Optional path to run-specific directory for output

    Returns:
        Path to the Excel file if successful, None otherwise
    """
    try:
        from planalign_orchestrator.utils import DatabaseConnectionManager
        from planalign_orchestrator.excel_exporter import ExcelExporter
        from planalign_orchestrator.config import SimulationConfig

        # Find the database - prefer run-specific database if run_dir provided
        if run_dir and (run_dir / "simulation.duckdb").exists():
            db_path = run_dir / "simulation.duckdb"
        else:
            db_path = scenario_path / "simulation.duckdb"

        if not db_path.exists():
            logger.warning(f"Database not found at {db_path}, skipping Excel export")
            return None

        # Use run directory if provided, otherwise create results directory
        if run_dir:
            results_dir = run_dir
        else:
            results_dir = scenario_path / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database connection manager
        db_manager = DatabaseConnectionManager(db_path)

        # Create exporter
        exporter = ExcelExporter(db_manager)

        # Try to create a SimulationConfig object from the config dict
        # If that fails, create a minimal mock config
        try:
            sim_config = SimulationConfig.from_dict(config)
        except Exception as e:
            logger.warning(f"Could not create SimulationConfig from dict: {e}")
            # Create a minimal mock config object
            class MockConfig:
                class Simulation:
                    start_year = config.get("simulation", {}).get("start_year", 2025)
                    end_year = config.get("simulation", {}).get("end_year", 2027)
                    target_growth_rate = config.get("simulation", {}).get("growth_target", 0.05)

                class Compensation:
                    cola_rate = config.get("compensation", {}).get("cola_rate", 0.03)
                    merit_budget = config.get("compensation", {}).get("merit_budget", 0.03)

                simulation = Simulation()
                compensation = Compensation()

                def model_dump(self):
                    return config

            sim_config = MockConfig()

        # Export to Excel
        excel_path = exporter.export_scenario_results(
            scenario_name=scenario_name,
            output_dir=results_dir,
            config=sim_config,
            seed=seed,
            export_format="excel",
        )

        logger.info(f"Excel export created at: {excel_path}")
        return excel_path

    except ImportError as e:
        logger.error(f"Failed to import excel exporter: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to export results to Excel: {e}")
        return None


class SimulationService:
    """Service for executing and managing simulations."""

    def __init__(self, storage: WorkspaceStorage):
        self.storage = storage
        self._cancelled_runs: set = set()
        self._active_runs: Dict[str, SimulationRun] = {}
        self._active_processes: Dict[str, asyncio.subprocess.Process] = {}

    def _cleanup_years_outside_range(
        self, db_path: Path, start_year: int, end_year: int
    ) -> None:
        """
        Delete simulation data from years outside the configured range.

        This ensures that when a user reconfigures a scenario to a different
        year range, stale data from previous runs is removed.
        """
        tables_with_year = [
            "fct_workforce_snapshot",
            "fct_yearly_events",
            "int_enrollment_state_accumulator",
            "int_deferral_rate_state_accumulator_v2",
            "int_deferral_escalation_state_accumulator",
            "int_baseline_workforce",
            "int_employee_compensation_by_year",
            "int_employee_state_by_year",
            "int_workforce_snapshot_optimized",
        ]

        try:
            conn = duckdb.connect(str(db_path))

            # Get list of existing tables
            existing_tables = {
                row[0] for row in conn.execute("SHOW TABLES").fetchall()
            }

            deleted_counts = {}
            for table in tables_with_year:
                if table not in existing_tables:
                    continue

                # Check if table has simulation_year column
                try:
                    cols = conn.execute(f"DESCRIBE {table}").fetchall()
                    col_names = {col[0] for col in cols}
                    if "simulation_year" not in col_names:
                        continue
                except Exception:
                    continue

                # Delete rows outside the configured year range
                result = conn.execute(f"""
                    DELETE FROM {table}
                    WHERE simulation_year < ? OR simulation_year > ?
                """, [start_year, end_year])

                deleted = result.fetchone()
                if deleted and deleted[0] > 0:
                    deleted_counts[table] = deleted[0]

            conn.close()

            if deleted_counts:
                logger.info(
                    f"Cleaned up data outside year range {start_year}-{end_year}: "
                    f"{deleted_counts}"
                )
            else:
                logger.debug(f"No stale data found outside year range {start_year}-{end_year}")

        except Exception as e:
            logger.warning(f"Failed to cleanup years outside range: {e}")
            # Don't fail the simulation if cleanup fails

    async def execute_simulation(
        self,
        workspace_id: str,
        scenario_id: str,
        run_id: str,
        config: Dict[str, Any],
        resume_from_checkpoint: bool = False,
    ) -> None:
        """
        Execute a simulation using the planalign CLI.

        This method runs `planalign simulate` as a subprocess and parses
        output for progress updates.
        """
        from ..routers.simulations import update_run_status

        logger.info(f"execute_simulation called: workspace={workspace_id}, scenario={scenario_id}, run={run_id}")

        try:
            # Update status to running
            update_run_status(run_id, status="running")
            self.storage.update_scenario_status(workspace_id, scenario_id, "running", run_id)

            # E091: Get simulation years from config with debug logging
            sim_config = config.get("simulation", {})
            start_year = int(sim_config.get("start_year", 2025))
            end_year = int(sim_config.get("end_year", 2027))
            total_years = end_year - start_year + 1
            logger.info(f"E091: SimulationService received config simulation section: {sim_config}")
            logger.info(f"E091: SimulationService year range: {start_year}-{end_year} ({total_years} years)")

            # Write merged config to scenario directory for CLI to use
            scenario_path = self.storage._scenario_path(workspace_id, scenario_id)
            config_path = scenario_path / "config.yaml"

            # E090: Validate and log census file path
            census_path = config.get("setup", {}).get("census_parquet_path")
            if census_path:
                census_file = Path(census_path)
                if not census_file.exists():
                    raise ValueError(f"Census file not found: {census_path}")
                logger.info(f"Using census file: {census_path}")
            else:
                logger.warning("No census_parquet_path in config - using default")

            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False)

            logger.info(f"Wrote merged config to: {config_path}")

            # Build the planalign simulate command as a list (safe for Windows paths)
            year_range = f"{start_year}-{end_year}" if start_year != end_year else str(start_year)

            # Use scenario-specific database for isolation
            scenario_db_path = scenario_path / "simulation.duckdb"

            # Clean up data from years outside the configured range
            if scenario_db_path.exists():
                self._cleanup_years_outside_range(scenario_db_path, start_year, end_year)

            # Build command as list - use os.fspath() for safe path handling on all platforms
            cmd = [
                sys.executable,
                "-m", "planalign_cli.main",
                "simulate", year_range,
                "--config", os.fspath(config_path),
                "--database", os.fspath(scenario_db_path),
                "--verbose",
            ]

            logger.info(f"Starting simulation with config: {config_path}")
            logger.info(f"Scenario database: {scenario_db_path}")
            logger.info(f"Command: {' '.join(cmd)}")

            # Get project root directory
            project_root = Path(__file__).parent.parent.parent

            # Set up environment for subprocess
            # Disable Rich's fancy output for cleaner parsing
            env = {
                **os.environ,
                "PYTHONPATH": str(project_root),
                "PYTHONIOENCODING": "utf-8",  # Force UTF-8 on Windows
                "TERM": "dumb",
                "NO_COLOR": "1",
                "FORCE_COLOR": "0",
                "COLUMNS": "200",
            }

            # Run the simulation as a subprocess (cross-platform)
            process, line_iterator = await _create_subprocess(
                cmd=cmd,
                cwd=str(project_root),
                env=env,
            )

            self._active_processes[run_id] = process

            current_year = start_year
            current_stage = "INITIALIZATION"
            events_generated = 0
            start_time = datetime.now()
            recent_events: List[Dict[str, Any]] = []

            # Get telemetry service for broadcasting updates
            telemetry_service = get_telemetry_service()

            # Wait briefly for WebSocket client to connect before sending telemetry
            # This avoids the race condition where telemetry is sent before the
            # frontend has established its WebSocket connection
            logger.info(f"Waiting for WebSocket listener for run {run_id}")
            max_wait = 5.0  # Maximum wait time in seconds
            wait_interval = 0.1
            waited = 0.0
            while waited < max_wait:
                if run_id in telemetry_service._listeners and telemetry_service._listeners[run_id]:
                    logger.info(f"WebSocket listener connected for run {run_id} after {waited:.1f}s")
                    break
                await asyncio.sleep(wait_interval)
                waited += wait_interval
            else:
                logger.warning(f"No WebSocket listener connected for run {run_id} after {max_wait}s, proceeding anyway")

            # Send initial telemetry immediately so UI knows simulation started
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
                recent_events=[{
                    "event_type": "INFO",
                    "employee_id": "System",
                    "timestamp": datetime.now().isoformat(),
                    "details": f"Simulation started for years {start_year}-{end_year}",
                }],
            )

            def get_memory_mb() -> float:
                """Get current process memory usage in MB."""
                try:
                    proc = psutil.Process()
                    return proc.memory_info().rss / (1024 * 1024)
                except Exception:
                    return 0.0

            # Parse output for progress updates
            # Keep last N lines for error reporting
            output_buffer: List[str] = []
            MAX_OUTPUT_BUFFER = 50

            async for line in line_iterator:
                if run_id in self._cancelled_runs:
                    process.terminate()
                    logger.info(f"Simulation {run_id} cancelled")
                    return

                line_text = line.decode("utf-8", errors="replace").strip()
                if not line_text:
                    continue

                # Store in buffer for error reporting
                output_buffer.append(line_text)
                if len(output_buffer) > MAX_OUTPUT_BUFFER:
                    output_buffer.pop(0)

                # Log simulation output - use INFO for errors/warnings, DEBUG otherwise
                if any(kw in line_text.lower() for kw in ["error", "exception", "failed", "traceback"]):
                    logger.error(f"Simulation: {line_text}")
                elif "warning" in line_text.lower():
                    logger.warning(f"Simulation: {line_text}")
                else:
                    logger.debug(f"Simulation output: {line_text}")

                # Parse year progress from output (e.g., "Processing year 2025")
                prev_year = current_year
                year_match = re.search(r"[Yy]ear[:\s]+(\d{4})", line_text)
                if year_match:
                    current_year = int(year_match.group(1))
                    if current_year != prev_year:
                        year_event = {
                            "event_type": "INFO",
                            "employee_id": f"Year {current_year}",
                            "timestamp": datetime.now().isoformat(),
                            "details": f"Processing simulation year {current_year}",
                        }
                        recent_events.insert(0, year_event)
                        recent_events = recent_events[:MAX_RECENT_EVENTS]

                # Parse stage from output
                stage_patterns = {
                    "INITIALIZATION": r"[Ii]nitializ|[Ss]etup|[Ll]oading",
                    "FOUNDATION": r"[Ff]oundation|[Bb]aseline",
                    "EVENT_GENERATION": r"[Ee]vent|[Gg]enerat",
                    "STATE_ACCUMULATION": r"[Ss]tate|[Aa]ccumul",
                    "VALIDATION": r"[Vv]alidat",
                    "REPORTING": r"[Rr]eport|[Cc]omplet",
                }

                prev_stage = current_stage
                for stage, pattern in stage_patterns.items():
                    if re.search(pattern, line_text):
                        current_stage = stage
                        break

                # Generate stage change event
                if current_stage != prev_stage:
                    stage_event = {
                        "event_type": "STAGE",
                        "employee_id": f"Year {current_year}",
                        "timestamp": datetime.now().isoformat(),
                        "details": f"Entering {current_stage.replace('_', ' ').title()}",
                    }
                    recent_events.insert(0, stage_event)
                    recent_events = recent_events[:MAX_RECENT_EVENTS]

                # Parse events count if available
                events_match = re.search(r"(\d+)\s*events?", line_text, re.IGNORECASE)
                if events_match:
                    events_generated = int(events_match.group(1))

                # Parse individual events from output (e.g., "HIRE: EMP_001", "TERMINATION: EMP_002")
                event_type_match = re.search(r"(HIRE|TERMINATION|PROMOTION|RAISE|ENROLLMENT)[\s:]+(\w+)", line_text, re.IGNORECASE)
                if event_type_match:
                    event_entry = {
                        "event_type": event_type_match.group(1).upper(),
                        "employee_id": event_type_match.group(2),
                        "timestamp": datetime.now().isoformat(),
                        "details": line_text[:100],  # First 100 chars as details
                    }
                    recent_events.insert(0, event_entry)
                    recent_events = recent_events[:MAX_RECENT_EVENTS]  # Keep last 20 events

                # Calculate progress
                year_idx = current_year - start_year
                year_progress = (year_idx / total_years) * 100
                progress = int(min(year_progress + 10, 99))  # Cap at 99 until complete

                # Calculate elapsed time and memory
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                memory_mb = get_memory_mb()

                # Update run status (in-memory)
                update_run_status(
                    run_id,
                    progress=progress,
                    current_year=current_year,
                    current_stage=current_stage,
                )

                # Broadcast telemetry via WebSocket
                telemetry_service.update_telemetry(
                    run_id=run_id,
                    progress=progress,
                    current_stage=current_stage,
                    current_year=current_year,
                    total_years=total_years,
                    memory_mb=memory_mb,
                    events_generated=events_generated,
                    elapsed_seconds=elapsed_seconds,
                    events_per_second=events_generated / elapsed_seconds if elapsed_seconds > 0 else 0,
                    recent_events=recent_events,
                )

            # Wait for process to complete (cross-platform)
            return_code = await _wait_subprocess(process)

            if run_id in self._active_processes:
                del self._active_processes[run_id]

            # Calculate final elapsed time
            final_elapsed = (datetime.now() - start_time).total_seconds()

            if return_code != 0:
                # Log the last few lines for debugging
                logger.error(f"Simulation failed with exit code {return_code}")
                logger.error("Last output lines:")
                for line in output_buffer[-20:]:
                    logger.error(f"  {line}")
                error_context = "\n".join(output_buffer[-10:])
                raise RuntimeError(f"planalign simulate exited with code {return_code}. Last output:\n{error_context}")

            # Mark as completed
            update_run_status(
                run_id,
                status="completed",
                progress=100,
                current_stage="COMPLETED",
                completed_at=datetime.now(),
            )
            self.storage.update_scenario_status(workspace_id, scenario_id, "completed", run_id)

            # Final telemetry broadcast
            telemetry_service.update_telemetry(
                run_id=run_id,
                progress=100,
                current_stage="COMPLETED",
                current_year=end_year,
                total_years=total_years,
                memory_mb=get_memory_mb(),
                events_generated=events_generated,
                elapsed_seconds=final_elapsed,
                events_per_second=events_generated / final_elapsed if final_elapsed > 0 else 0,
                recent_events=recent_events,
            )

            logger.info(f"Simulation {run_id} completed successfully in {final_elapsed:.1f}s")

            # Export results to Excel
            logger.info("Exporting results to Excel...")
            scenario = self.storage.get_scenario(workspace_id, scenario_id)
            scenario_name = scenario.name if scenario else scenario_id
            seed = config.get("simulation", {}).get("seed", 42)

            # Create run-specific directory: runs/{run_id}/
            run_dir = scenario_path / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            # Save config YAML to run directory
            config_yaml_path = run_dir / "config.yaml"
            try:
                with open(config_yaml_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                logger.debug(f"Config YAML saved to: {config_yaml_path}")
            except Exception as e:
                logger.warning(f"Failed to save config YAML: {e}")

            # Save run metadata
            run_metadata = {
                "run_id": run_id,
                "scenario_id": scenario_id,
                "scenario_name": scenario_name,
                "workspace_id": workspace_id,
                "started_at": start_time.isoformat(),
                "completed_at": datetime.now().isoformat(),
                "duration_seconds": final_elapsed,
                "start_year": start_year,
                "end_year": end_year,
                "events_generated": events_generated,
                "seed": seed,
                "status": "completed",
            }
            try:
                import json
                metadata_path = run_dir / "run_metadata.json"
                with open(metadata_path, "w") as f:
                    json.dump(run_metadata, f, indent=2)
                logger.debug(f"Run metadata saved to: {metadata_path}")
            except Exception as e:
                logger.warning(f"Failed to save run metadata: {e}")

            # Copy database to run directory for archival
            db_src = scenario_path / "simulation.duckdb"
            if db_src.exists():
                import shutil
                db_dest = run_dir / "simulation.duckdb"
                try:
                    shutil.copy2(db_src, db_dest)
                    logger.debug(f"Database copied to: {db_dest}")
                except Exception as e:
                    logger.warning(f"Failed to copy database to run directory: {e}")

            # Export to Excel in run directory
            excel_path = _export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name=scenario_name,
                config=config,
                seed=seed,
                run_dir=run_dir,  # Pass run directory for output
            )
            if excel_path:
                logger.info(f"Excel export created: {excel_path}")
            else:
                logger.warning("Excel export skipped or failed")

        except Exception as e:
            logger.exception(f"Simulation {run_id} failed")
            update_run_status(
                run_id,
                status="failed",
                error_message=str(e),
                completed_at=datetime.now(),
            )
            self.storage.update_scenario_status(workspace_id, scenario_id, "failed", run_id)

            # Broadcast failure via telemetry
            try:
                telemetry_service = get_telemetry_service()
                telemetry_service.update_telemetry(
                    run_id=run_id,
                    progress=0,
                    current_stage="FAILED",
                    current_year=current_year if 'current_year' in dir() else start_year,
                    total_years=total_years if 'total_years' in dir() else 3,
                )
            except Exception:
                pass  # Don't fail on telemetry errors

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

                # Calculate progress
                year_progress = year_idx / total_years
                stage_progress = stage_idx / len(stages) / total_years
                total_progress = int((year_progress + stage_progress) * 100)

                update_run_status(
                    run_id,
                    progress=total_progress,
                    current_year=year,
                    current_stage=stage,
                )

                # Simulate work
                await asyncio.sleep(0.3)

    def cancel_simulation(self, run_id: str) -> bool:
        """Signal a running simulation to cancel and terminate subprocess."""
        self._cancelled_runs.add(run_id)

        # Terminate the subprocess if running
        if run_id in self._active_processes:
            process = self._active_processes[run_id]
            try:
                process.terminate()
            except ProcessLookupError:
                pass  # Process already exited
            del self._active_processes[run_id]

        return True

    def get_results(
        self, workspace_id: str, scenario_id: str
    ) -> Optional[SimulationResults]:
        """
        Get simulation results for a completed scenario.

        Returns aggregated results from the DuckDB database.
        """
        scenario_path = self.storage._scenario_path(workspace_id, scenario_id)

        # Get scenario's configured year range
        config = self.storage.get_merged_config(workspace_id, scenario_id)
        if config:
            sim_config = config.get("simulation", {})
            config_start_year = int(sim_config.get("start_year", 2025))
            config_end_year = int(sim_config.get("end_year", 2027))
        else:
            config_start_year = 2025
            config_end_year = 2027

        logger.info(f"Scenario year range: {config_start_year} - {config_end_year}")

        # Try to load results from the database
        try:
            import duckdb

            # Check for scenario-specific database first (preferred)
            db_path = scenario_path / "simulation.duckdb"
            db_source = "scenario"

            if not db_path.exists():
                # Check for parent workspace database
                workspace_path = self.storage._workspace_path(workspace_id)
                db_path = workspace_path / "simulation.duckdb"
                db_source = "workspace"

            if not db_path.exists():
                # Fall back to main project database (dbt/simulation.duckdb)
                # WARNING: This is shared across all scenarios!
                project_root = Path(__file__).parent.parent.parent
                db_path = project_root / "dbt" / "simulation.duckdb"
                db_source = "global (shared - may show data from other scenarios)"
                logger.warning(
                    f"Using global database for scenario {scenario_id}. "
                    "Re-run the simulation to create a scenario-specific database."
                )

            if not db_path.exists():
                logger.warning(f"No database found for scenario {scenario_id}")
                return None

            logger.info(f"Loading results from {db_source} database: {db_path}")

            conn = duckdb.connect(str(db_path), read_only=True)

            # Get workforce progression (filtered by scenario's year range)
            # E091: Use prorated_annual_compensation for accuracy with partial-year employees
            # E093: Include all employees (not just actives) for compensation metrics
            try:
                workforce_df = conn.execute("""
                    SELECT
                        simulation_year,
                        COUNT(DISTINCT CASE WHEN LOWER(employment_status) = 'active' THEN employee_id END) as headcount,
                        AVG(prorated_annual_compensation) as avg_compensation
                    FROM fct_workforce_snapshot
                    WHERE simulation_year >= ?
                      AND simulation_year <= ?
                    GROUP BY simulation_year
                    ORDER BY simulation_year
                """, [config_start_year, config_end_year]).fetchdf()

                workforce_progression = workforce_df.to_dict("records")
            except Exception as e:
                logger.error(f"Error fetching workforce progression: {e}")
                workforce_progression = []

            # E093: Get compensation breakdown by detailed status code
            try:
                comp_by_status_df = conn.execute("""
                    SELECT
                        simulation_year,
                        detailed_status_code as employment_status,
                        COUNT(DISTINCT employee_id) as employee_count,
                        AVG(prorated_annual_compensation) as avg_compensation
                    FROM fct_workforce_snapshot
                    WHERE simulation_year >= ?
                      AND simulation_year <= ?
                    GROUP BY simulation_year, detailed_status_code
                    ORDER BY simulation_year, detailed_status_code
                """, [config_start_year, config_end_year]).fetchdf()

                compensation_by_status = comp_by_status_df.to_dict("records")
            except Exception as e:
                logger.error(f"Error fetching compensation by status: {e}")
                compensation_by_status = []

            # Get event trends (filtered by scenario's year range)
            try:
                events_df = conn.execute("""
                    SELECT
                        event_type,
                        simulation_year,
                        COUNT(*) as count
                    FROM fct_yearly_events
                    WHERE simulation_year >= ?
                      AND simulation_year <= ?
                    GROUP BY event_type, simulation_year
                    ORDER BY event_type, simulation_year
                """, [config_start_year, config_end_year]).fetchdf()

                event_trends = {}
                for _, row in events_df.iterrows():
                    event_type = row["event_type"]
                    if event_type not in event_trends:
                        event_trends[event_type] = []
                    event_trends[event_type].append(int(row["count"]))
            except Exception as e:
                logger.error(f"Error fetching event trends: {e}")
                event_trends = {}

            # E096: Calculate actual participation rate from workforce snapshot
            participation_rate = DEFAULT_PARTICIPATION_RATE
            try:
                participation_df = conn.execute("""
                    SELECT
                        COUNT(DISTINCT CASE WHEN participation_status = 'participating' THEN employee_id END) as participating,
                        COUNT(DISTINCT employee_id) as total_active
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                      AND LOWER(employment_status) = 'active'
                """, [config_end_year]).fetchdf()

                if not participation_df.empty:
                    participating = participation_df["participating"].iloc[0] or 0
                    total_active = participation_df["total_active"].iloc[0] or 0
                    if total_active > 0:
                        participation_rate = participating / total_active
                        logger.info(f"Calculated participation rate: {participation_rate:.2%} ({participating}/{total_active})")
            except Exception as e:
                logger.warning(f"Error calculating participation rate, using default: {e}")

            conn.close()

            # Calculate summary metrics
            if workforce_progression:
                start_headcount = workforce_progression[0].get("headcount", 0)
                final_headcount = workforce_progression[-1].get("headcount", 0)
                start_year = workforce_progression[0].get("simulation_year", 2025)
                end_year = workforce_progression[-1].get("simulation_year", 2027)

                total_growth_pct = (
                    ((final_headcount - start_headcount) / start_headcount * 100)
                    if start_headcount > 0
                    else 0
                )

                years = end_year - start_year
                cagr = (
                    ((final_headcount / start_headcount) ** (1 / years) - 1) * 100
                    if start_headcount > 0 and years > 0
                    else 0
                )
            else:
                start_year = 2025
                end_year = 2027
                final_headcount = 0
                total_growth_pct = 0
                cagr = 0

            return SimulationResults(
                scenario_id=scenario_id,
                run_id="unknown",
                start_year=start_year,
                end_year=end_year,
                final_headcount=final_headcount,
                total_growth_pct=total_growth_pct,
                cagr=cagr,
                participation_rate=participation_rate,  # E096: Now calculated from actual data
                workforce_progression=workforce_progression,
                event_trends=event_trends,
                growth_analysis={
                    "total_growth_pct": total_growth_pct,
                    "cagr": cagr,
                },
                compensation_by_status=compensation_by_status,  # E093
            )

        except Exception as e:
            logger.error(f"Failed to load results: {e}")
            return None

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
