"""
Orchestrator wrapper for Fidelity PlanAlign Engine CLI

Wraps existing planalign_orchestrator components with enhanced error handling,
progress reporting, and user-friendly interfaces.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from planalign_orchestrator.checkpoint_manager import CheckpointManager
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.dbt_runner import DbtRunner
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator
from planalign_orchestrator.recovery_orchestrator import RecoveryOrchestrator
from planalign_orchestrator.registries import RegistryManager
from planalign_orchestrator.scenario_batch_runner import ScenarioBatchRunner
from planalign_orchestrator.utils import DatabaseConnectionManager
from planalign_orchestrator.validation import DataValidator, EventSequenceRule, HireTerminationRatioRule

class OrchestratorWrapper:
    """Wrapper for planalign_orchestrator components with CLI enhancements."""

    def __init__(
        self,
        config_path: Path,
        db_path: Path,
        verbose: bool = False,
    ):
        self.config_path = config_path
        self.db_path = db_path
        self.verbose = verbose

        # Lazy initialization
        self._config = None
        self._db = None
        self._checkpoint_manager = None
        self._recovery_orchestrator = None

    @property
    def config(self):
        """Lazy load configuration."""
        if self._config is None:
            if not self.config_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
            self._config = load_simulation_config(self.config_path)

            # Ensure optimization settings exist
            if not self._config.optimization:
                from planalign_orchestrator.config import OptimizationSettings
                self._config.optimization = OptimizationSettings()

            # All simulations use SQL mode
            self._config.optimization.event_generation.mode = "sql"

        return self._config

    @property
    def db(self):
        """Lazy load database connection."""
        if self._db is None:
            self._db = DatabaseConnectionManager(self.db_path)
        return self._db

    @property
    def checkpoint_manager(self):
        """Lazy load checkpoint manager."""
        if self._checkpoint_manager is None:
            self._checkpoint_manager = CheckpointManager(db_path=str(self.db_path))
        return self._checkpoint_manager

    @property
    def recovery_orchestrator(self):
        """Lazy load recovery orchestrator."""
        if self._recovery_orchestrator is None:
            self._recovery_orchestrator = RecoveryOrchestrator(self.checkpoint_manager)
        return self._recovery_orchestrator

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status information."""
        status = {
            "system_ready": True,
            "system_message": "All systems operational",
            "timestamp": datetime.now().isoformat(),
        }

        # Configuration status
        try:
            config = self.config
            status["config"] = {
                "valid": True,
                "path": str(self.config_path),
                "scenario_id": getattr(config, "scenario_id", None),
                "plan_design_id": getattr(config, "plan_design_id", None),
                "start_year": getattr(config.simulation, "start_year", None) if hasattr(config, "simulation") else None,
                "end_year": getattr(config.simulation, "end_year", None) if hasattr(config, "simulation") else None,
            }
        except Exception as e:
            status["config"] = {"valid": False, "error": str(e)}
            status["system_ready"] = False

        # Database status
        try:
            db_exists = self.db_path.exists()
            if db_exists:
                db_size = self.db_path.stat().st_size / (1024 * 1024)  # MB
                last_modified = datetime.fromtimestamp(self.db_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

                # Try to get table count
                try:
                    with self.db.get_connection() as conn:
                        tables = conn.execute("SHOW TABLES").fetchall()
                        table_count = len(tables)
                    connected = True
                except Exception:
                    table_count = 0
                    connected = False

                status["database"] = {
                    "connected": connected,
                    "path": str(self.db_path),
                    "size_mb": round(db_size, 2),
                    "last_modified": last_modified,
                    "table_count": table_count,
                }
            else:
                status["database"] = {
                    "connected": False,
                    "path": str(self.db_path),
                    "error": "Database file does not exist"
                }
                status["system_ready"] = False

        except Exception as e:
            status["database"] = {"connected": False, "error": str(e)}
            status["system_ready"] = False

        # Checkpoint status
        try:
            checkpoints = self.checkpoint_manager.list_checkpoints()
            config_hash = self.recovery_orchestrator.calculate_config_hash(str(self.config_path))
            recovery_status = self.recovery_orchestrator.get_recovery_status(config_hash)

            status["checkpoints"] = {
                "count": len(checkpoints),
                "latest_year": recovery_status.get("latest_checkpoint_year"),
                "resumable_year": recovery_status.get("resumable_year"),
                "config_compatible": recovery_status.get("config_compatible", False),
                "recommendations": recovery_status.get("recommendations", [])
            }
        except Exception as e:
            status["checkpoints"] = {"error": str(e)}

        # Performance information
        if hasattr(self, "config") and self.config:
            thread_count = self.config.get_thread_count() if hasattr(self.config, "get_thread_count") else 1
            status["performance"] = {
                "thread_count": thread_count,
            }

        # Generate recommendations
        recommendations = []
        if not status["database"]["connected"]:
            recommendations.append("Run a simulation to create the database")
        if status["checkpoints"].get("count", 0) == 0:
            recommendations.append("No checkpoints found - consider running a simulation")
        if not status["config"].get("valid"):
            recommendations.append("Fix configuration errors before running simulations")

        status["recommendations"] = recommendations

        return status

    def check_system_health(self) -> Dict[str, Any]:
        """Quick health check for system readiness."""
        health = {
            "healthy": True,
            "issues": [],
            "warnings": []
        }

        # Check configuration
        try:
            config = self.config
        except Exception as e:
            health["healthy"] = False
            health["issues"].append(f"Configuration error: {e}")

        # Check database accessibility
        if not self.db_path.exists():
            health["warnings"].append("Database file does not exist - will be created on first run")
        else:
            try:
                with self.db.get_connection() as conn:
                    conn.execute("SELECT 1").fetchone()
            except Exception as e:
                health["healthy"] = False
                health["issues"].append(f"Database connection error: {e}")

        # Check required directories
        required_dirs = ["dbt", "config"]
        for dir_name in required_dirs:
            if not Path(dir_name).exists():
                health["healthy"] = False
                health["issues"].append(f"Required directory missing: {dir_name}")

        return health

    def create_orchestrator(self, threads: Optional[int] = None, dry_run: bool = False, verbose: bool = None, progress_callback=None) -> Union[PipelineOrchestrator, "ProgressAwareOrchestrator"]:
        """Create a configured PipelineOrchestrator instance."""
        if verbose is None:
            verbose = self.verbose

        # Get threading configuration
        if self.config.orchestrator:
            self.config.validate_threading_configuration()
        self.config.validate_eligibility_configuration()

        thread_count = threads if threads is not None else self.config.get_thread_count()
        threading_enabled = True
        threading_mode = "selective"

        if self.config.orchestrator and self.config.orchestrator.threading:
            threading_enabled = self.config.orchestrator.threading.enabled
            threading_mode = self.config.orchestrator.threading.mode

        # Create components
        runner = DbtRunner(
            threads=thread_count,
            executable=("echo" if dry_run else "dbt"),
            verbose=verbose,
            threading_enabled=threading_enabled,
            threading_mode=threading_mode,
            db_manager=self.db,  # Pass db_manager for connection cleanup before dbt subprocess
            database_path=str(self.db_path),  # Use scenario-specific database path
        )

        registries = RegistryManager(self.db)

        # Create validator
        validator = DataValidator(self.db)
        validator.register_rule(HireTerminationRatioRule())
        validator.register_rule(EventSequenceRule())

        orchestrator = PipelineOrchestrator(
            self.config,
            self.db,
            runner,
            registries,
            validator,
            verbose=verbose
        )

        # If progress callback provided, wrap with progress monitoring
        if progress_callback:
            return ProgressAwareOrchestrator(orchestrator, progress_callback)

        return orchestrator

    def create_batch_runner(self, scenarios_dir: Path, output_dir: Path) -> ScenarioBatchRunner:
        """Create a configured ScenarioBatchRunner instance."""
        return ScenarioBatchRunner(scenarios_dir, output_dir, self.config_path)

    def validate_configuration(self, enforce_identifiers: bool = False) -> Dict[str, Any]:
        """Validate configuration and return detailed results."""
        try:
            config = self.config

            if enforce_identifiers:
                config.require_identifiers()

            result = {
                "valid": True,
                "config_dict": config.model_dump(),
                "warnings": [],
                "recommendations": []
            }

            # Check for identifier presence
            if not (config.scenario_id and config.plan_design_id):
                result["warnings"].append("Missing scenario_id and/or plan_design_id")
                result["recommendations"].append("Add scenario_id and plan_design_id for full traceability")

            return result

        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "warnings": [],
                "recommendations": ["Fix configuration errors before proceeding"]
            }

    def get_checkpoint_info(self) -> Dict[str, Any]:
        """Get detailed checkpoint information."""
        try:
            checkpoints = self.checkpoint_manager.list_checkpoints()
            config_hash = self.recovery_orchestrator.calculate_config_hash(str(self.config_path))
            recovery_status = self.recovery_orchestrator.get_recovery_status(config_hash)

            return {
                "success": True,
                "checkpoints": checkpoints,
                "recovery_status": recovery_status,
                "total_count": len(checkpoints),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Maximum line length to process — truncate before regex to prevent
# polynomial-time backtracking on adversarial input (ReDoS / SonarQube S5852).
_MAX_LINE_LENGTH = 1000

# Progress indicator patterns (non-overlapping quantifiers to avoid ReDoS)
_YEAR_PATTERN = re.compile(r'🔄 Starting simulation year (\d+)')
_STAGE_PATTERN = re.compile(r'📋 Starting (\w+)')
_EVENT_PATTERN = re.compile(r'📊 Generated (\d+(?:,\d+)*) events')
_COMPLETED_STAGE_PATTERN = re.compile(r'✅ Completed (\w+) in (\d+\.\d+)s')
_FOUNDATION_VALIDATION_PATTERN = re.compile(r'📊 Foundation model validation for year (\d+):')


class _ProgressMonitor:
    """Intercepts stdout to extract progress indicators and route output safely."""

    def __init__(self, callback, original_stdout):
        self.callback = callback
        self.original_stdout = original_stdout
        self.current_year = None
        self.buffer = ""
        self._writing = False

    def write(self, text):
        if self._writing:
            self.original_stdout.write(text)
            return
        self._writing = True
        try:
            self.original_stdout.flush()
            self.buffer += text
            while '\n' in self.buffer:
                line, self.buffer = self.buffer.split('\n', 1)
                self._process_line(line)
                if hasattr(self.callback, 'on_dbt_line'):
                    self.callback.on_dbt_line(line)
        finally:
            self._writing = False

    def _process_line(self, line):
        """Process a complete line for progress indicators."""
        line = line[:_MAX_LINE_LENGTH]
        self._check_year(line)
        self._check_stage(line)
        self._check_events(line)
        self._check_completed_stage(line)
        self._check_foundation_validation(line)

    def _check_year(self, line):
        match = _YEAR_PATTERN.search(line)
        if match:
            self.current_year = int(match.group(1))
            if hasattr(self.callback, 'update_year'):
                self.callback.update_year(self.current_year)

    def _check_stage(self, line):
        match = _STAGE_PATTERN.search(line)
        if match and hasattr(self.callback, 'update_stage'):
            self.callback.update_stage(match.group(1))

    def _check_events(self, line):
        match = _EVENT_PATTERN.search(line)
        if not match:
            return
        try:
            event_count = int(match.group(1).replace(',', ''))
            if hasattr(self.callback, 'update_events'):
                self.callback.update_events(event_count)
        except ValueError:
            pass

    def _check_completed_stage(self, line):
        match = _COMPLETED_STAGE_PATTERN.search(line)
        if match and hasattr(self.callback, 'stage_completed'):
            self.callback.stage_completed(match.group(1), float(match.group(2)))

    def _check_foundation_validation(self, line):
        match = _FOUNDATION_VALIDATION_PATTERN.search(line)
        if match and hasattr(self.callback, 'year_validation'):
            self.callback.year_validation(int(match.group(1)))

    def flush(self):
        self.original_stdout.flush()


class ProgressAwareOrchestrator:
    """
    Wrapper around PipelineOrchestrator that monitors output for progress updates.

    This class intercepts print statements from the orchestrator and parses them
    to extract progress information, then calls the provided callback with updates.
    """

    def __init__(self, orchestrator: PipelineOrchestrator, progress_callback):
        self.orchestrator = orchestrator
        self.progress_callback = progress_callback
        self._current_year = None
        self._current_stage = None

        # Wire progress callback directly to YearExecutor for direct stage signaling
        if hasattr(orchestrator, 'year_executor'):
            orchestrator.year_executor.progress_callback = progress_callback

    def __getattr__(self, name):
        """Delegate all other attributes to the wrapped orchestrator."""
        return getattr(self.orchestrator, name)

    def execute_multi_year_simulation(self, **kwargs):
        """Execute multi-year simulation with enhanced progress monitoring."""
        import sys

        original_stdout = sys.stdout
        progress_monitor = _ProgressMonitor(self.progress_callback, original_stdout)

        try:
            sys.stdout = progress_monitor
            result = self.orchestrator.execute_multi_year_simulation(**kwargs)
            if progress_monitor.buffer.strip():
                progress_monitor._process_line(progress_monitor.buffer)
            return result
        finally:
            sys.stdout = original_stdout
