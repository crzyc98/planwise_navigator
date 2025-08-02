"""
dbt command execution wrapper for orchestrator_dbt.

Provides standardized dbt command execution with error handling, logging,
and variable management. Supports both standalone and Dagster-integrated execution.
"""

from __future__ import annotations

import os
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Generator
from contextlib import contextmanager

from .config import OrchestrationConfig


logger = logging.getLogger(__name__)


class DbtExecutionResult:
    """Result of dbt command execution."""

    def __init__(
        self,
        command: List[str],
        returncode: int,
        stdout: str = "",
        stderr: str = "",
        description: str = "",
        execution_time: float = 0.0
    ):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.description = description
        self.execution_time = execution_time
        self.success = returncode == 0

    def __repr__(self) -> str:
        return (
            f"DbtExecutionResult("
            f"command={' '.join(self.command)}, "
            f"success={self.success}, "
            f"returncode={self.returncode}, "
            f"time={self.execution_time:.2f}s"
            f")"
        )


class DbtExecutor:
    """
    dbt command execution wrapper with standardized error handling and logging.

    Provides methods for executing dbt commands in both standalone and integrated
    modes, with proper variable handling, error reporting, and logging.
    """

    def __init__(self, config: OrchestrationConfig):
        """
        Initialize dbt executor with configuration.

        Args:
            config: Orchestration configuration containing dbt settings
        """
        self.config = config
        self.dbt_project_dir = config.dbt.project_dir
        self.profiles_dir = config.dbt.profiles_dir
        self.target = config.dbt.target
        self.threads = config.dbt.threads

        # Find dbt executable
        self.dbt_executable = self._find_dbt_executable()

        # Validate dbt project
        self._validate_dbt_project()

    def _find_dbt_executable(self) -> str:
        """Find the dbt executable, checking virtual environment first."""
        # Check if we're in a virtual environment
        project_root = self.config.project_root_path
        venv_dbt = project_root / "venv" / "bin" / "dbt"

        if venv_dbt.exists():
            logger.debug(f"Using virtual environment dbt: {venv_dbt}")
            return str(venv_dbt)

        # Check for dbt in PATH
        try:
            result = subprocess.run(
                ["which", "dbt"],
                capture_output=True,
                text=True,
                check=True
            )
            dbt_path = result.stdout.strip()
            logger.debug(f"Using system dbt: {dbt_path}")
            return "dbt"
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("dbt executable not found in PATH")
            return "dbt"  # Fallback, will likely fail but provides clear error

    def _validate_dbt_project(self) -> None:
        """Validate dbt project configuration."""
        if not self.dbt_project_dir.exists():
            raise DbtExecutorError(f"dbt project directory not found: {self.dbt_project_dir}")

        dbt_project_yml = self.dbt_project_dir / "dbt_project.yml"
        if not dbt_project_yml.exists():
            raise DbtExecutorError(f"dbt_project.yml not found: {dbt_project_yml}")

    @contextmanager
    def _working_directory(self):
        """Context manager to temporarily change working directory."""
        original_dir = os.getcwd()
        try:
            os.chdir(self.dbt_project_dir)
            yield
        finally:
            os.chdir(original_dir)

    def _build_command(
        self,
        base_command: List[str],
        vars_dict: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        additional_args: Optional[List[str]] = None
    ) -> List[str]:
        """
        Build complete dbt command with all arguments.

        Args:
            base_command: Base dbt command (e.g., ["run", "--select", "model"])
            vars_dict: Variables to pass to dbt
            full_refresh: Whether to add --full-refresh flag
            additional_args: Additional command line arguments

        Returns:
            Complete command list ready for execution
        """
        command = [self.dbt_executable] + base_command

        # Add target if specified
        if self.target and self.target != "dev":
            command.extend(["--target", self.target])

        # Add profiles directory if specified
        if self.profiles_dir:
            command.extend(["--profiles-dir", str(self.profiles_dir)])

        # Add threads if specified
        if self.threads > 1:
            command.extend(["--threads", str(self.threads)])

        # Add variables
        if vars_dict:
            # Use JSON format for complex variables
            vars_json = json.dumps(vars_dict)
            command.extend(["--vars", vars_json])

        # Add full refresh flag
        if full_refresh:
            command.append("--full-refresh")

        # Add additional arguments
        if additional_args:
            command.extend(additional_args)

        return command

    def execute_command(
        self,
        command: List[str],
        vars_dict: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        description: str = "",
        fail_on_error: bool = True,
        additional_args: Optional[List[str]] = None
    ) -> DbtExecutionResult:
        """
        Execute a dbt command with standardized error handling.

        Args:
            command: Base dbt command (e.g., ["run", "--select", "model"])
            vars_dict: Variables to pass to dbt
            full_refresh: Whether to add --full-refresh flag
            description: Human-readable description for logging
            fail_on_error: Whether to raise exception on command failure
            additional_args: Additional command line arguments

        Returns:
            DbtExecutionResult with execution details

        Raises:
            DbtExecutorError: If command fails and fail_on_error is True
        """
        # Build complete command
        full_command = self._build_command(command, vars_dict, full_refresh, additional_args)

        # Log execution start
        logger.info(f"Executing dbt command: {' '.join(full_command)}")
        if description:
            logger.info(f"Description: {description}")

        if vars_dict:
            logger.debug(f"Variables: {vars_dict}")

        # Execute command with timing
        start_time = time.time()
        with self._working_directory():
            try:
                result = subprocess.run(
                    full_command,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour timeout
                )

                execution_time = time.time() - start_time

                # Create result object with timing
                execution_result = DbtExecutionResult(
                    command=full_command,
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    description=description,
                    execution_time=execution_time
                )

                # Log output
                if result.stdout:
                    logger.debug(f"STDOUT:\n{result.stdout}")

                if result.stderr:
                    if result.returncode != 0:
                        logger.error(f"STDERR:\n{result.stderr}")
                    else:
                        logger.debug(f"STDERR:\n{result.stderr}")

                # Handle success/failure
                if result.returncode == 0:
                    logger.info(f"Successfully executed: dbt {' '.join(command)}")
                else:
                    error_msg = f"dbt command failed with exit code {result.returncode}"
                    if description:
                        error_msg += f" ({description})"

                    logger.error(error_msg)

                    if fail_on_error:
                        raise DbtExecutorError(
                            f"{error_msg}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
                        )

                return execution_result

            except subprocess.TimeoutExpired as e:
                error_msg = f"dbt command timed out after 1 hour: {' '.join(full_command)}"
                logger.error(error_msg)

                if fail_on_error:
                    raise DbtExecutorError(error_msg) from e

                return DbtExecutionResult(
                    command=full_command,
                    returncode=-1,
                    stderr=error_msg,
                    description=description
                )

            except Exception as e:
                error_msg = f"Failed to execute dbt command: {e}"
                logger.error(error_msg)

                if fail_on_error:
                    raise DbtExecutorError(error_msg) from e

                return DbtExecutionResult(
                    command=full_command,
                    returncode=-1,
                    stderr=str(e),
                    description=description
                )

    def run_model(
        self,
        model_name: str,
        vars_dict: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        description: str = ""
    ) -> DbtExecutionResult:
        """
        Run a specific dbt model.

        Args:
            model_name: Name of the model to run
            vars_dict: Variables to pass to dbt
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            DbtExecutionResult with execution details
        """
        command = ["run", "--select", model_name]
        desc = description or f"running model {model_name}"

        return self.execute_command(
            command=command,
            vars_dict=vars_dict,
            full_refresh=full_refresh,
            description=desc
        )

    def run_models(
        self,
        model_names: List[str],
        vars_dict: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        description: str = ""
    ) -> List[DbtExecutionResult]:
        """
        Run multiple dbt models in sequence.

        Args:
            model_names: List of model names to run
            vars_dict: Variables to pass to dbt
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            List of DbtExecutionResult objects
        """
        results = []

        for model_name in model_names:
            logger.info(f"Running model {model_name} ({len(results) + 1}/{len(model_names)})")

            result = self.run_model(
                model_name=model_name,
                vars_dict=vars_dict,
                full_refresh=full_refresh,
                description=f"{description} - {model_name}" if description else ""
            )

            results.append(result)

            if not result.success:
                logger.error(f"Model {model_name} failed, stopping execution")
                break

        successful_count = sum(1 for r in results if r.success)
        logger.info(f"Completed {successful_count}/{len(model_names)} models successfully")

        return results

    def load_seed(
        self,
        seed_name: str,
        full_refresh: bool = False,
        description: str = ""
    ) -> DbtExecutionResult:
        """
        Load a specific dbt seed.

        Args:
            seed_name: Name of the seed to load
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            DbtExecutionResult with execution details
        """
        command = ["seed", "--select", seed_name]
        desc = description or f"loading seed {seed_name}"

        return self.execute_command(
            command=command,
            full_refresh=full_refresh,
            description=desc
        )

    def load_all_seeds(
        self,
        full_refresh: bool = False,
        description: str = ""
    ) -> DbtExecutionResult:
        """
        Load all dbt seeds.

        Args:
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            DbtExecutionResult with execution details
        """
        command = ["seed"]
        desc = description or "loading all seeds"

        return self.execute_command(
            command=command,
            full_refresh=full_refresh,
            description=desc
        )

    def run_tests(
        self,
        select: Optional[str] = None,
        description: str = ""
    ) -> DbtExecutionResult:
        """
        Run dbt tests.

        Args:
            select: Optional selector for specific tests
            description: Description for logging

        Returns:
            DbtExecutionResult with execution details
        """
        command = ["test"]
        if select:
            command.extend(["--select", select])

        desc = description or f"running tests{f' for {select}' if select else ''}"

        return self.execute_command(
            command=command,
            description=desc,
            fail_on_error=False  # Tests may fail, but we want to capture results
        )

    def build(
        self,
        select: Optional[str] = None,
        vars_dict: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        description: str = ""
    ) -> DbtExecutionResult:
        """
        Run dbt build (run + test).

        Args:
            select: Optional selector for specific models
            vars_dict: Variables to pass to dbt
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            DbtExecutionResult with execution details
        """
        command = ["build"]
        if select:
            command.extend(["--select", select])

        desc = description or f"building{f' {select}' if select else ' all models'}"

        return self.execute_command(
            command=command,
            vars_dict=vars_dict,
            full_refresh=full_refresh,
            description=desc
        )

    def get_dbt_version(self) -> str:
        """
        Get dbt version information.

        Returns:
            dbt version string
        """
        try:
            result = subprocess.run(
                [self.dbt_executable, "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except Exception as e:
            logger.warning(f"Could not get dbt version: {e}")
            return "unknown"

    def list_models(self) -> List[str]:
        """
        List all available dbt models.

        Returns:
            List of model names
        """
        with self._working_directory():
            try:
                result = subprocess.run(
                    [self.dbt_executable, "list", "--resource-type", "model"],
                    capture_output=True,
                    text=True,
                    check=True
                )

                models = []
                for line in result.stdout.strip().split('\n'):
                    if line and not line.startswith('INFO'):
                        models.append(line.strip())

                return models

            except Exception as e:
                logger.warning(f"Could not list dbt models: {e}")
                return []

    def list_seeds(self) -> List[str]:
        """
        List all available dbt seeds.

        Returns:
            List of seed names
        """
        with self._working_directory():
            try:
                result = subprocess.run(
                    [self.dbt_executable, "list", "--resource-type", "seed"],
                    capture_output=True,
                    text=True,
                    check=True
                )

                seeds = []
                for line in result.stdout.strip().split('\n'):
                    if line and not line.startswith('INFO'):
                        seeds.append(line.strip())

                return seeds

            except Exception as e:
                logger.warning(f"Could not list dbt seeds: {e}")
                return []

    def run_models_batch(
        self,
        model_names: List[str],
        vars_dict: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        description: str = ""
    ) -> DbtExecutionResult:
        """
        Run multiple dbt models in a single batch command (more efficient).

        Args:
            model_names: List of model names to run
            vars_dict: Variables to pass to dbt
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            DbtExecutionResult from batch operation
        """
        if not model_names:
            logger.warning("No models specified for batch execution")
            return DbtExecutionResult(
                command=[],
                returncode=0,
                description="No models to run in batch"
            )

        # Create model selector for batch execution
        model_selector = "+".join(model_names)
        command = ["run", "--select", model_selector]
        desc = description or f"batch run for {len(model_names)} models"

        logger.info(f"Running {len(model_names)} models in batch: {model_names[:3]}{'...' if len(model_names) > 3 else ''}")

        return self.execute_command(
            command=command,
            vars_dict=vars_dict,
            full_refresh=full_refresh,
            description=desc
        )

    def load_seeds_batch(
        self,
        seed_names: List[str],
        full_refresh: bool = False,
        description: str = ""
    ) -> DbtExecutionResult:
        """
        Load multiple dbt seeds in a single batch command (more efficient).

        Args:
            seed_names: List of seed names to load
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            DbtExecutionResult from batch operation
        """
        if not seed_names:
            logger.warning("No seeds specified for batch execution")
            return DbtExecutionResult(
                command=[],
                returncode=0,
                description="No seeds to load in batch"
            )

        # Create seed selector for batch execution
        seed_selector = "+".join(seed_names)
        command = ["seed", "--select", seed_selector]
        desc = description or f"batch load for {len(seed_names)} seeds"

        logger.info(f"Loading {len(seed_names)} seeds in batch: {seed_names[:3]}{'...' if len(seed_names) > 3 else ''}")

        return self.execute_command(
            command=command,
            full_refresh=full_refresh,
            description=desc
        )

    def get_performance_summary(self, results: List[DbtExecutionResult]) -> Dict[str, Any]:
        """
        Get performance summary from multiple dbt execution results.

        Args:
            results: List of DbtExecutionResult objects

        Returns:
            Dictionary with performance metrics
        """
        if not results:
            return {
                "total_commands": 0,
                "total_execution_time": 0.0,
                "successful_commands": 0,
                "failed_commands": 0,
                "average_execution_time": 0.0,
                "fastest_command": None,
                "slowest_command": None
            }

        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]

        total_time = sum(r.execution_time for r in results)
        execution_times = [r.execution_time for r in results if r.execution_time > 0]

        fastest = min(results, key=lambda x: x.execution_time) if execution_times else None
        slowest = max(results, key=lambda x: x.execution_time) if execution_times else None

        return {
            "total_commands": len(results),
            "total_execution_time": total_time,
            "successful_commands": len(successful_results),
            "failed_commands": len(failed_results),
            "success_rate": len(successful_results) / len(results) * 100 if results else 0.0,
            "average_execution_time": total_time / len(results) if results else 0.0,
            "fastest_command": {
                "command": ' '.join(fastest.command) if fastest else None,
                "time": fastest.execution_time if fastest else None
            },
            "slowest_command": {
                "command": ' '.join(slowest.command) if slowest else None,
                "time": slowest.execution_time if slowest else None
            }
        }

    def run_models_batch(
        self,
        model_names: List[str],
        vars_dict: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        description: str = ""
    ) -> DbtExecutionResult:
        """
        Run multiple dbt models in a single batch command.

        This reduces dbt startup overhead by executing all models in one command
        instead of multiple individual commands.

        Args:
            model_names: List of model names to run
            vars_dict: Variables to pass to dbt
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            DbtExecutionResult with batch execution details
        """
        if not model_names:
            return DbtExecutionResult(
                success=False,
                command=[],
                stdout="",
                stderr="No models provided",
                execution_time=0.0,
                description="batch run models - empty list"
            )

        # Create batch select argument
        select_arg = " ".join(model_names)
        command = ["run", "--select"] + model_names
        desc = description or f"running {len(model_names)} models in batch"

        logger.info(f"🚀 Running {len(model_names)} models in batch: {', '.join(model_names)}")

        return self.execute_command(
            command=command,
            vars_dict=vars_dict,
            full_refresh=full_refresh,
            description=desc
        )

    def load_seeds_batch(
        self,
        seed_names: List[str],
        full_refresh: bool = False,
        description: str = ""
    ) -> DbtExecutionResult:
        """
        Load multiple dbt seeds in a single batch command.

        This reduces dbt startup overhead by executing all seeds in one command
        instead of multiple individual commands.

        Args:
            seed_names: List of seed names to load
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            DbtExecutionResult with batch execution details
        """
        if not seed_names:
            return DbtExecutionResult(
                success=False,
                command=[],
                stdout="",
                stderr="No seeds provided",
                execution_time=0.0,
                description="batch load seeds - empty list"
            )

        command = ["seed", "--select"] + seed_names
        desc = description or f"loading {len(seed_names)} seeds in batch"

        logger.info(f"🚀 Loading {len(seed_names)} seeds in batch: {', '.join(seed_names)}")

        return self.execute_command(
            command=command,
            full_refresh=full_refresh,
            description=desc
        )


class DbtExecutorError(Exception):
    """Exception raised for dbt execution errors."""
    pass
