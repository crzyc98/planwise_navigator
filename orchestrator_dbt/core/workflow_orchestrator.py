"""
Workflow orchestration coordinator for orchestrator_dbt.

Provides the main orchestration logic that coordinates database clearing,
seed loading, staging model execution, and validation in the proper sequence.
"""

from __future__ import annotations

import logging
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from .config import OrchestrationConfig
from .database_manager import DatabaseManager, ClearTablesResult, DatabaseStateValidation
from .dbt_executor import DbtExecutor
from .validation_framework import ValidationFramework, ValidationSummary
from ..loaders.seed_loader import SeedLoader, BatchSeedLoadResult
from ..loaders.staging_loader import StagingLoader, BatchStagingResult


logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """Individual workflow step result."""
    step_name: str
    success: bool
    execution_time: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"WorkflowStep("
            f"step='{self.step_name}', "
            f"success={self.success}, "
            f"time={self.execution_time:.2f}s"
            f")"
        )


@dataclass
class WorkflowResult:
    """Complete workflow execution result."""
    success: bool
    total_execution_time: float
    steps_completed: int
    steps_total: int
    workflow_steps: List[WorkflowStep] = field(default_factory=list)
    final_validation: Optional[ValidationSummary] = None

    @property
    def completion_rate(self) -> float:
        """Calculate completion rate as percentage."""
        if self.steps_total == 0:
            return 100.0
        return (self.steps_completed / self.steps_total) * 100.0

    def get_failed_steps(self) -> List[WorkflowStep]:
        """Get list of failed workflow steps."""
        return [step for step in self.workflow_steps if not step.success]

    def __repr__(self) -> str:
        return (
            f"WorkflowResult("
            f"success={self.success}, "
            f"steps={self.steps_completed}/{self.steps_total}, "
            f"time={self.total_execution_time:.2f}s"
            f")"
        )


class WorkflowOrchestrator:
    """
    Main workflow orchestration coordinator.

    Orchestrates the complete setup workflow including database clearing,
    seed loading, staging model execution, and comprehensive validation.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize workflow orchestrator.

        Args:
            config_path: Optional path to configuration file
        """
        # Load configuration
        self.config = OrchestrationConfig(config_path)

        # Initialize core components
        self.db_manager = DatabaseManager(self.config)
        self.dbt_executor = DbtExecutor(self.config)
        self.validation_framework = ValidationFramework(self.config, self.db_manager)

        # Initialize loaders
        self.seed_loader = SeedLoader(self.config, self.dbt_executor)
        self.staging_loader = StagingLoader(self.config, self.dbt_executor)

        logger.info(f"WorkflowOrchestrator initialized with config: {self.config}")

    def _execute_step(self, step_name: str, step_func, *args, **kwargs) -> WorkflowStep:
        """
        Execute a workflow step with timing and error handling.

        Args:
            step_name: Name of the step for logging
            step_func: Function to execute
            *args: Arguments to pass to step_func
            **kwargs: Keyword arguments to pass to step_func

        Returns:
            WorkflowStep with execution results
        """
        logger.info(f"🚀 Starting step: {step_name}")
        start_time = time.time()

        try:
            result = step_func(*args, **kwargs)
            execution_time = time.time() - start_time

            # Determine success based on result type
            if hasattr(result, 'success'):
                success = result.success
            elif hasattr(result, 'overall_success'):
                success = result.overall_success
            elif hasattr(result, 'is_valid'):
                success = result.is_valid
            else:
                success = True  # Assume success if no clear indicator

            message = f"Step completed {'successfully' if success else 'with errors'}"

            step_result = WorkflowStep(
                step_name=step_name,
                success=success,
                execution_time=execution_time,
                message=message,
                details={"result": result}
            )

            if success:
                logger.info(f"✅ Step completed successfully: {step_name} ({execution_time:.2f}s)")
            else:
                logger.error(f"❌ Step failed: {step_name} ({execution_time:.2f}s)")

            return step_result

        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"Step execution error: {e}"

            logger.error(f"💥 Step failed with exception: {step_name} - {error_message}")

            return WorkflowStep(
                step_name=step_name,
                success=False,
                execution_time=execution_time,
                message=error_message,
                details={"error": str(e)}
            )

    def clear_database_tables(self) -> WorkflowStep:
        """
        Clear database tables based on configuration.

        Returns:
            WorkflowStep with clearing results
        """
        if not self.config.setup.clear_tables:
            logger.info("Database table clearing disabled in configuration")
            return WorkflowStep(
                step_name="clear_database_tables",
                success=True,
                execution_time=0.0,
                message="Skipped - disabled in configuration"
            )

        return self._execute_step(
            "clear_database_tables",
            self.db_manager.clear_tables,
            self.config.setup.clear_table_patterns
        )

    def load_seed_data(self) -> WorkflowStep:
        """
        Load all CSV seed data.

        Returns:
            WorkflowStep with seed loading results
        """
        if not self.config.setup.load_seeds:
            logger.info("Seed loading disabled in configuration")
            return WorkflowStep(
                step_name="load_seed_data",
                success=True,
                execution_time=0.0,
                message="Skipped - disabled in configuration"
            )

        return self._execute_step(
            "load_seed_data",
            self.seed_loader.load_seeds_in_optimal_order,
            None,  # seed_names (all)
            False,  # full_refresh
            True   # fail_fast
        )

    def load_seed_data_optimized(self) -> WorkflowStep:
        """
        Load all CSV seed data using optimized batch operations.

        Returns:
            WorkflowStep with seed loading results
        """
        if not self.config.setup.load_seeds:
            logger.info("Seed loading disabled in configuration")
            return WorkflowStep(
                step_name="load_seed_data_optimized",
                success=True,
                execution_time=0.0,
                message="Skipped - disabled in configuration"
            )

        return self._execute_step(
            "load_seed_data_optimized",
            self.seed_loader.load_seeds_batch_optimized,
            None,  # seed_names (all)
            False,  # full_refresh
            True,   # fail_fast
            4      # max_workers
        )

    def run_foundation_staging_models(self) -> WorkflowStep:
        """
        Run foundation staging models (census data and basic configuration).

        Returns:
            WorkflowStep with foundation models results
        """
        if not self.config.setup.run_staging_models:
            logger.info("Staging model execution disabled in configuration")
            return WorkflowStep(
                step_name="run_foundation_staging_models",
                success=True,
                execution_time=0.0,
                message="Skipped - disabled in configuration"
            )

        return self._execute_step(
            "run_foundation_staging_models",
            self.staging_loader.run_foundation_models,
            self.config.get_dbt_vars(),  # variables
            False   # full_refresh
        )

    def run_foundation_staging_models_optimized(self) -> WorkflowStep:
        """
        Run foundation staging models using optimized batch execution.

        Returns:
            WorkflowStep with foundation models results
        """
        if not self.config.setup.run_staging_models:
            logger.info("Staging model execution disabled in configuration")
            return WorkflowStep(
                step_name="run_foundation_staging_models_optimized",
                success=True,
                execution_time=0.0,
                message="Skipped - disabled in configuration"
            )

        # Get foundation model names
        foundation_models = ["stg_census_data", "stg_config_job_levels", "stg_comp_levers"]

        return self._execute_step(
            "run_foundation_staging_models_optimized",
            self.staging_loader.run_models_batch_optimized,
            foundation_models,
            self.config.get_dbt_vars(),  # variables
            False,   # full_refresh
            "foundation models"  # description
        )

    def run_configuration_staging_models(self) -> WorkflowStep:
        """
        Run configuration staging models.

        Returns:
            WorkflowStep with configuration models results
        """
        if not self.config.setup.run_staging_models:
            logger.info("Staging model execution disabled in configuration")
            return WorkflowStep(
                step_name="run_configuration_staging_models",
                success=True,
                execution_time=0.0,
                message="Skipped - disabled in configuration"
            )

        return self._execute_step(
            "run_configuration_staging_models",
            self.staging_loader.run_configuration_models,
            self.config.get_dbt_vars(),  # variables
            False   # full_refresh
        )

    def run_configuration_staging_models_optimized(self) -> WorkflowStep:
        """
        Run configuration staging models using optimized batch execution.

        Returns:
            WorkflowStep with configuration models results
        """
        if not self.config.setup.run_staging_models:
            logger.info("Staging model execution disabled in configuration")
            return WorkflowStep(
                step_name="run_configuration_staging_models_optimized",
                success=True,
                execution_time=0.0,
                message="Skipped - disabled in configuration"
            )

        # Get configuration model names
        discovered_models = self.staging_loader.discover_staging_models()
        config_models = [m for m in discovered_models if m.startswith("stg_config_") or m.startswith("stg_comp_")]
        # Remove foundation models from config list
        foundation_models = {"stg_config_job_levels", "stg_comp_levers"}
        config_models = [m for m in config_models if m not in foundation_models]

        return self._execute_step(
            "run_configuration_staging_models_optimized",
            self.staging_loader.run_models_batch_optimized,
            config_models,
            self.config.get_dbt_vars(),  # variables
            False,   # full_refresh
            "configuration models"  # description
        )

    def validate_setup_results(self) -> WorkflowStep:
        """
        Validate setup results and data quality.

        Returns:
            WorkflowStep with validation results
        """
        if not self.config.setup.validate_results:
            logger.info("Result validation disabled in configuration")
            return WorkflowStep(
                step_name="validate_setup_results",
                success=True,
                execution_time=0.0,
                message="Skipped - disabled in configuration"
            )

        return self._execute_step(
            "validate_setup_results",
            self.validation_framework.run_comprehensive_validation
        )

    def run_complete_setup_workflow(self) -> WorkflowResult:
        """
        Run the complete setup workflow.

        Returns:
            WorkflowResult with complete workflow results
        """
        logger.info("🎯 Starting complete setup workflow")
        logger.info("=" * 80)

        start_time = time.time()
        workflow_steps = []

        # Define workflow steps
        steps = [
            ("clear_database_tables", self.clear_database_tables),
            ("load_seed_data", self.load_seed_data),
            ("run_foundation_staging_models", self.run_foundation_staging_models),
            ("run_configuration_staging_models", self.run_configuration_staging_models),
            ("validate_setup_results", self.validate_setup_results)
        ]

        steps_completed = 0
        overall_success = True
        final_validation = None

        for step_name, step_func in steps:
            step_result = step_func()
            workflow_steps.append(step_result)

            if step_result.success:
                steps_completed += 1
            else:
                overall_success = False

                # Check if we should fail fast
                if self.config.setup.fail_on_validation_error and step_result.step_name == "validate_setup_results":
                    logger.error("❌ Validation failed and fail_on_validation_error is enabled")
                    break
                elif step_result.step_name in ["clear_database_tables", "load_seed_data", "run_foundation_staging_models"]:
                    logger.error(f"❌ Critical step failed: {step_name}")
                    break

            # Extract validation results if available
            if step_result.step_name == "validate_setup_results" and "result" in step_result.details:
                final_validation = step_result.details["result"]

        total_execution_time = time.time() - start_time

        # Create final result
        result = WorkflowResult(
            success=overall_success,
            total_execution_time=total_execution_time,
            steps_completed=steps_completed,
            steps_total=len(steps),
            workflow_steps=workflow_steps,
            final_validation=final_validation
        )

        # Log final summary
        logger.info("=" * 80)
        if result.success:
            logger.info(f"🎉 Setup workflow completed successfully!")
            logger.info(f"   ✅ All {result.steps_total} steps completed in {result.total_execution_time:.2f}s")
        else:
            logger.error(f"💥 Setup workflow failed!")
            logger.error(f"   ❌ {result.steps_completed}/{result.steps_total} steps completed in {result.total_execution_time:.2f}s")

            failed_steps = result.get_failed_steps()
            if failed_steps:
                logger.error(f"   Failed steps: {[s.step_name for s in failed_steps]}")

        # Log validation summary if available
        if final_validation:
            if final_validation.is_valid:
                logger.info(f"   📊 Validation: {final_validation.passed_checks}/{final_validation.total_checks} checks passed")
            else:
                logger.warning(f"   ⚠️  Validation: {final_validation.failed_checks} failures, {final_validation.warnings} warnings")

        logger.info("=" * 80)

        return result

    def run_quick_setup(self) -> WorkflowResult:
        """
        Run a quick setup workflow (foundation models only).

        Returns:
            WorkflowResult with quick setup results
        """
        logger.info("🚀 Starting quick setup workflow (foundation only)")

        start_time = time.time()
        workflow_steps = []

        # Quick setup steps
        steps = [
            ("clear_database_tables", self.clear_database_tables),
            ("load_seed_data", self.load_seed_data),
            ("run_foundation_staging_models", self.run_foundation_staging_models)
        ]

        steps_completed = 0
        overall_success = True

        for step_name, step_func in steps:
            step_result = step_func()
            workflow_steps.append(step_result)

            if step_result.success:
                steps_completed += 1
            else:
                overall_success = False
                logger.error(f"❌ Quick setup step failed: {step_name}")
                break

        total_execution_time = time.time() - start_time

        result = WorkflowResult(
            success=overall_success,
            total_execution_time=total_execution_time,
            steps_completed=steps_completed,
            steps_total=len(steps),
            workflow_steps=workflow_steps
        )

        if result.success:
            logger.info(f"✅ Quick setup completed successfully in {result.total_execution_time:.2f}s")
        else:
            logger.error(f"❌ Quick setup failed after {result.total_execution_time:.2f}s")

        return result

    def run_complete_setup_workflow_optimized(self) -> WorkflowResult:
        """
        Run the complete setup workflow using optimized batch operations.

        This method uses batch operations to reduce dbt startup overhead
        and should be significantly faster than the standard workflow.

        Returns:
            WorkflowResult with complete workflow results
        """
        logger.info("🎯 Starting OPTIMIZED complete setup workflow")
        logger.info("=" * 80)

        start_time = time.time()
        workflow_steps = []

        # Define optimized workflow steps
        steps = [
            ("clear_database_tables", self.clear_database_tables),
            ("load_seed_data_optimized", self.load_seed_data_optimized),
            ("run_foundation_staging_models_optimized", self.run_foundation_staging_models_optimized),
            ("run_configuration_staging_models_optimized", self.run_configuration_staging_models_optimized),
            ("validate_setup_results", self.validate_setup_results)
        ]

        steps_completed = 0
        overall_success = True
        final_validation = None

        for step_name, step_func in steps:
            step_result = step_func()
            workflow_steps.append(step_result)

            if step_result.success:
                steps_completed += 1
            else:
                overall_success = False

                # Check if we should fail fast
                if self.config.setup.fail_on_validation_error and step_result.step_name == "validate_setup_results":
                    logger.error("❌ Validation failed and fail_on_validation_error is enabled")
                    break
                elif step_result.step_name in ["clear_database_tables", "load_seed_data_optimized", "run_foundation_staging_models_optimized"]:
                    logger.error(f"❌ Critical step failed: {step_name}")
                    break

            # Extract validation results if available
            if step_result.step_name == "validate_setup_results" and "result" in step_result.details:
                final_validation = step_result.details["result"]

        total_execution_time = time.time() - start_time

        # Create final result
        result = WorkflowResult(
            success=overall_success,
            total_execution_time=total_execution_time,
            steps_completed=steps_completed,
            steps_total=len(steps),
            workflow_steps=workflow_steps,
            final_validation=final_validation
        )

        # Log final summary
        logger.info("=" * 80)
        if result.success:
            logger.info(f"🎉 OPTIMIZED setup workflow completed successfully!")
            logger.info(f"   ✅ All {result.steps_total} steps completed in {result.total_execution_time:.2f}s")
        else:
            logger.error(f"💥 OPTIMIZED setup workflow failed!")
            logger.error(f"   ❌ {result.steps_completed}/{result.steps_total} steps completed in {result.total_execution_time:.2f}s")

            failed_steps = result.get_failed_steps()
            if failed_steps:
                logger.error(f"   Failed steps: {[s.step_name for s in failed_steps]}")

        # Log validation summary if available
        if final_validation:
            if final_validation.is_valid:
                logger.info(f"   📊 Validation: {final_validation.passed_checks}/{final_validation.total_checks} checks passed")
            else:
                logger.warning(f"   ⚠️  Validation: {final_validation.failed_checks} failures, {final_validation.warnings} warnings")

        logger.info("=" * 80)

        return result

    def run_quick_setup_optimized(self) -> WorkflowResult:
        """
        Run a quick setup workflow using optimized batch operations (foundation models only).

        Returns:
            WorkflowResult with quick setup results
        """
        logger.info("🚀 Starting OPTIMIZED quick setup workflow (foundation only)")

        start_time = time.time()
        workflow_steps = []

        # Optimized quick setup steps
        steps = [
            ("clear_database_tables", self.clear_database_tables),
            ("load_seed_data_optimized", self.load_seed_data_optimized),
            ("run_foundation_staging_models_optimized", self.run_foundation_staging_models_optimized)
        ]

        steps_completed = 0
        overall_success = True

        for step_name, step_func in steps:
            step_result = step_func()
            workflow_steps.append(step_result)

            if step_result.success:
                steps_completed += 1
            else:
                overall_success = False
                logger.error(f"❌ OPTIMIZED quick setup step failed: {step_name}")
                break

        total_execution_time = time.time() - start_time

        result = WorkflowResult(
            success=overall_success,
            total_execution_time=total_execution_time,
            steps_completed=steps_completed,
            steps_total=len(steps),
            workflow_steps=workflow_steps
        )

        if result.success:
            logger.info(f"✅ OPTIMIZED quick setup completed successfully in {result.total_execution_time:.2f}s")
        else:
            logger.error(f"❌ OPTIMIZED quick setup failed after {result.total_execution_time:.2f}s")

        return result

    def get_system_status(self) -> Dict[str, Any]:
        """
        Get current system status and readiness.

        Returns:
            Dictionary with system status information
        """
        logger.info("Checking system status...")

        status = {
            "timestamp": time.time(),
            "config_valid": True,
            "database_accessible": False,
            "dbt_available": False,
            "seeds_available": False,
            "staging_models_available": False,
            "ready_for_setup": False
        }

        try:
            # Check database accessibility
            db_validation = self.db_manager.validate_database_state()
            status["database_accessible"] = db_validation.database_accessible
            status["database_details"] = {
                "total_tables": db_validation.total_tables,
                "staging_tables": db_validation.staging_tables,
                "fact_tables": db_validation.fact_tables
            }

            # Check dbt availability
            try:
                dbt_version = self.dbt_executor.get_dbt_version()
                status["dbt_available"] = True
                status["dbt_version"] = dbt_version
            except Exception as e:
                status["dbt_error"] = str(e)

            # Check seeds availability
            try:
                available_seeds = self.seed_loader.discover_seed_files()
                status["seeds_available"] = len(available_seeds) > 0
                status["seeds_count"] = len(available_seeds)
                status["seeds_list"] = available_seeds
            except Exception as e:
                status["seeds_error"] = str(e)

            # Check staging models availability
            try:
                available_models = self.staging_loader.discover_staging_models()
                status["staging_models_available"] = len(available_models) > 0
                status["staging_models_count"] = len(available_models)
                status["staging_models_list"] = available_models
            except Exception as e:
                status["staging_models_error"] = str(e)

            # Determine overall readiness
            status["ready_for_setup"] = (
                status["config_valid"] and
                status["database_accessible"] and
                status["dbt_available"] and
                status["seeds_available"] and
                status["staging_models_available"]
            )

        except Exception as e:
            logger.error(f"Error checking system status: {e}")
            status["system_error"] = str(e)

        logger.info(f"System status: ready_for_setup={status['ready_for_setup']}")
        return status

    def run_optimized_setup_workflow(self, max_workers: int = 4) -> WorkflowResult:
        """
        Run setup workflow with optimized concurrent execution and graceful fallbacks.

        This method implements a multi-strategy approach:
        1. Try optimized concurrent/batch execution first
        2. Fall back to standard sequential execution if needed
        3. Provide comprehensive error recovery

        Args:
            max_workers: Maximum concurrent workers for parallel operations

        Returns:
            WorkflowResult with complete workflow results
        """
        logger.info("🎯 Starting optimized setup workflow with concurrent execution")
        logger.info("=" * 80)

        start_time = time.time()
        workflow_steps = []

        # Strategy 1: Try optimized execution
        logger.info("🚀 Attempting optimized concurrent execution...")
        try:
            result = self._run_optimized_workflow_execution(max_workers)
            if result.success:
                logger.info(f"✅ Optimized workflow completed successfully in {result.total_execution_time:.2f}s")
                return result
            else:
                logger.warning("⚠️ Optimized workflow failed, falling back to standard execution")
                workflow_steps.extend(result.workflow_steps)
        except Exception as e:
            logger.warning(f"⚠️ Optimized workflow failed with exception: {e}, falling back to standard execution")

        # Strategy 2: Fall back to standard sequential execution
        logger.info("🔄 Falling back to standard sequential workflow...")
        try:
            result = self.run_complete_setup_workflow()
            # Merge any previous steps
            if workflow_steps:
                result.workflow_steps = workflow_steps + result.workflow_steps
                result.steps_total = len(result.workflow_steps)

            total_execution_time = time.time() - start_time
            result.total_execution_time = total_execution_time

            if result.success:
                logger.info(f"✅ Standard workflow completed successfully in {total_execution_time:.2f}s")
            else:
                logger.error(f"❌ Both optimized and standard workflows failed")

            return result

        except Exception as e:
            logger.error(f"💥 Both optimized and standard workflows failed: {e}")

            # Return failure result
            total_execution_time = time.time() - start_time
            return WorkflowResult(
                success=False,
                total_execution_time=total_execution_time,
                steps_completed=0,
                steps_total=5,
                workflow_steps=workflow_steps + [WorkflowStep(
                    step_name="workflow_execution",
                    success=False,
                    execution_time=total_execution_time,
                    message=f"Complete workflow failure: {e}"
                )]
            )

    def _run_optimized_workflow_execution(self, max_workers: int) -> WorkflowResult:
        """
        Execute optimized workflow with concurrent operations.

        Args:
            max_workers: Maximum concurrent workers

        Returns:
            WorkflowResult with execution details
        """
        start_time = time.time()
        workflow_steps = []

        # Step 1: Clear database tables (quick, run first)
        step_result = self.clear_database_tables()
        workflow_steps.append(step_result)

        if not step_result.success:
            return WorkflowResult(
                success=False,
                total_execution_time=time.time() - start_time,
                steps_completed=0,
                steps_total=5,
                workflow_steps=workflow_steps
            )

        # Step 2: Load seeds with optimized batch/concurrent execution
        step_result = self._execute_step(
            "load_seed_data_optimized",
            self.seed_loader.load_seeds_batch_optimized,
            None,  # seed_names (all)
            False,  # full_refresh
            True,   # fail_fast
            max_workers
        )
        workflow_steps.append(step_result)

        if not step_result.success:
            return WorkflowResult(
                success=False,
                total_execution_time=time.time() - start_time,
                steps_completed=1,
                steps_total=5,
                workflow_steps=workflow_steps
            )

        # Step 3: Run staging models with concurrent execution
        # Run foundation and configuration models in parallel if possible
        concurrent_steps = self._run_staging_models_concurrent(max_workers)
        workflow_steps.extend(concurrent_steps)

        # Check if staging steps succeeded
        staging_success = all(step.success for step in concurrent_steps)
        steps_completed = sum(1 for step in workflow_steps if step.success)

        if not staging_success:
            return WorkflowResult(
                success=False,
                total_execution_time=time.time() - start_time,
                steps_completed=steps_completed,
                steps_total=5,
                workflow_steps=workflow_steps
            )

        # Step 4: Validate results
        step_result = self.validate_setup_results()
        workflow_steps.append(step_result)

        if step_result.success:
            steps_completed += 1

        total_execution_time = time.time() - start_time
        overall_success = all(step.success for step in workflow_steps)

        return WorkflowResult(
            success=overall_success,
            total_execution_time=total_execution_time,
            steps_completed=steps_completed,
            steps_total=5,
            workflow_steps=workflow_steps,
            final_validation=step_result.details.get("result") if "result" in step_result.details else None
        )

    def _run_staging_models_concurrent(self, max_workers: int) -> List[WorkflowStep]:
        """
        Run staging models with concurrent execution where possible.

        Args:
            max_workers: Maximum concurrent workers

        Returns:
            List of WorkflowStep results
        """
        steps = []

        # Try to run foundation and configuration models concurrently
        # if they have no dependencies between them
        try:
            with ThreadPoolExecutor(max_workers=min(2, max_workers)) as executor:
                # Submit concurrent tasks
                foundation_future = executor.submit(
                    self._execute_step,
                    "run_foundation_staging_models_concurrent",
                    self.staging_loader.run_foundation_models_concurrent,
                    self.config.get_dbt_vars(),
                    False,  # full_refresh
                    2  # max_workers for foundation
                )

                config_future = executor.submit(
                    self._execute_step,
                    "run_configuration_staging_models_concurrent",
                    self.staging_loader.run_configuration_models_concurrent,
                    self.config.get_dbt_vars(),
                    False,  # full_refresh
                    max_workers - 2  # remaining workers for config
                )

                # Collect results
                foundation_result = foundation_future.result()
                config_result = config_future.result()

                steps.extend([foundation_result, config_result])

        except Exception as e:
            logger.warning(f"Concurrent staging execution failed: {e}, falling back to sequential")

            # Fall back to sequential execution
            foundation_result = self.run_foundation_staging_models()
            config_result = self.run_configuration_staging_models()
            steps.extend([foundation_result, config_result])

        return steps

    def get_workflow_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for workflow optimization analysis.

        Returns:
            Dictionary with performance metrics
        """
        try:
            seed_metrics = self.seed_loader.get_performance_metrics()
            staging_metrics = self.staging_loader.get_performance_metrics()

            return {
                "seed_loading": seed_metrics,
                "staging_models": staging_metrics,
                "optimization_recommendations": self._generate_optimization_recommendations(
                    seed_metrics, staging_metrics
                ),
                "estimated_time_savings": self._estimate_time_savings(
                    seed_metrics, staging_metrics
                )
            }
        except Exception as e:
            logger.warning(f"Could not generate performance metrics: {e}")
            return {
                "error": str(e),
                "seed_loading": {},
                "staging_models": {},
                "optimization_recommendations": [],
                "estimated_time_savings": 0.0
            }

    def _generate_optimization_recommendations(
        self,
        seed_metrics: Dict[str, Any],
        staging_metrics: Dict[str, Any]
    ) -> List[str]:
        """
        Generate optimization recommendations based on metrics.

        Args:
            seed_metrics: Seed loading performance metrics
            staging_metrics: Staging model performance metrics

        Returns:
            List of optimization recommendations
        """
        recommendations = []

        # Seed loading recommendations
        if seed_metrics.get("total_seeds_available", 0) > 5:
            recommendations.append("Use batch seed loading for improved performance")

        if seed_metrics.get("parallelization_ratio", 0) > 0.3:
            recommendations.append("Enable concurrent seed loading for independent seeds")

        # Staging model recommendations
        if staging_metrics.get("total_models_available", 0) > 3:
            recommendations.append("Use batch staging model execution")

        if staging_metrics.get("parallelization_potential", 0) > 0.4:
            recommendations.append("Enable concurrent staging model execution")

        if staging_metrics.get("dependency_levels", 0) <= 2:
            recommendations.append("Consider running foundation and configuration models in parallel")

        return recommendations

    def _estimate_time_savings(
        self,
        seed_metrics: Dict[str, Any],
        staging_metrics: Dict[str, Any]
    ) -> float:
        """
        Estimate potential time savings from optimizations.

        Args:
            seed_metrics: Seed loading performance metrics
            staging_metrics: Staging model performance metrics

        Returns:
            Estimated time savings in seconds
        """
        # Conservative estimates based on typical improvements
        seed_savings = 0.0
        staging_savings = 0.0

        # Seed optimization savings (batch + concurrent)
        total_seeds = seed_metrics.get("total_seeds_available", 0)
        if total_seeds > 5:
            # Estimate 60-80% time savings from batch + concurrent execution
            estimated_sequential_time = total_seeds * 1.5  # ~1.5s per seed
            seed_savings = estimated_sequential_time * 0.7  # 70% savings

        # Staging model optimization savings
        total_models = staging_metrics.get("total_models_available", 0)
        if total_models > 3:
            # Estimate 40-60% time savings from batch + concurrent execution
            estimated_sequential_time = total_models * 2.0  # ~2s per model
            staging_savings = estimated_sequential_time * 0.5  # 50% savings

        return seed_savings + staging_savings


class WorkflowOrchestratorError(Exception):
    """Exception raised for workflow orchestration errors."""
    pass
