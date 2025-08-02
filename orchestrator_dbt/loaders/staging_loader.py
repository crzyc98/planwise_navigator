"""
Staging model execution for orchestrator_dbt.

Handles execution of dbt staging models with proper dependency management,
variable handling, and comprehensive validation.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import OrchestrationConfig
from ..core.dbt_executor import DbtExecutor, DbtExecutionResult


logger = logging.getLogger(__name__)


@dataclass
class StagingModelResult:
    """Result of staging model execution."""
    model_name: str
    success: bool
    execution_time: float = 0.0
    row_count: Optional[int] = None
    error_message: Optional[str] = None
    variables_used: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"StagingModelResult("
            f"model='{self.model_name}', "
            f"success={self.success}, "
            f"rows={self.row_count}"
            f")"
        )


@dataclass
class BatchStagingResult:
    """Result of batch staging model execution."""
    total_models: int = 0
    successful_models: int = 0
    failed_models: int = 0
    skipped_models: int = 0
    total_execution_time: float = 0.0
    model_results: List[StagingModelResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_models == 0:
            return 100.0
        return (self.successful_models / self.total_models) * 100.0

    @property
    def overall_success(self) -> bool:
        """Check if all models executed successfully."""
        return self.failed_models == 0

    def get_failed_models(self) -> List[StagingModelResult]:
        """Get list of failed model results."""
        return [r for r in self.model_results if not r.success]

    def __repr__(self) -> str:
        return (
            f"BatchStagingResult("
            f"total={self.total_models}, "
            f"successful={self.successful_models}, "
            f"failed={self.failed_models}, "
            f"success_rate={self.success_rate:.1f}%"
            f")"
        )


class StagingLoader:
    """
    Staging model execution for dbt setup.

    Provides methods for running individual staging models, batch operations,
    and dependency-aware execution ordering.
    """

    def __init__(self, config: OrchestrationConfig, dbt_executor: DbtExecutor):
        """
        Initialize staging loader.

        Args:
            config: Orchestration configuration
            dbt_executor: dbt command executor
        """
        self.config = config
        self.dbt_executor = dbt_executor
        self.models_dir = config.dbt.project_dir / "models" / "staging"

        # Get default variables for staging models
        self.default_vars = config.get_dbt_vars()

    def discover_staging_models(self) -> List[str]:
        """
        Discover all staging models in the staging directory.

        Returns:
            List of staging model names (without .sql extension)
        """
        staging_models = []

        if self.models_dir.exists():
            for sql_file in self.models_dir.glob("stg_*.sql"):
                model_name = sql_file.stem  # Remove .sql extension
                staging_models.append(model_name)

        logger.info(f"Discovered {len(staging_models)} staging models: {staging_models}")
        return sorted(staging_models)

    def validate_staging_model(self, model_name: str) -> bool:
        """
        Validate that a staging model file exists and is readable.

        Args:
            model_name: Name of the staging model

        Returns:
            True if model file is valid
        """
        model_file = self.models_dir / f"{model_name}.sql"

        if not model_file.exists():
            logger.error(f"Staging model file not found: {model_file}")
            return False

        if not model_file.is_file():
            logger.error(f"Model path is not a file: {model_file}")
            return False

        try:
            # Try to read file to validate it's accessible
            with open(model_file, 'r', encoding='utf-8') as f:
                content = f.read(100)  # Read first 100 characters
                if not content.strip():
                    logger.error(f"Staging model file appears to be empty: {model_file}")
                    return False

            logger.debug(f"Staging model validated successfully: {model_name}")
            return True

        except Exception as e:
            logger.error(f"Error validating staging model {model_name}: {e}")
            return False

    def run_staging_model(
        self,
        model_name: str,
        variables: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False
    ) -> StagingModelResult:
        """
        Run a single staging model.

        Args:
            model_name: Name of the staging model to run
            variables: Variables to pass to the model
            full_refresh: Whether to use full refresh

        Returns:
            StagingModelResult with execution details
        """
        logger.info(f"Running staging model: {model_name}")

        # Validate model exists
        if not self.validate_staging_model(model_name):
            return StagingModelResult(
                model_name=model_name,
                success=False,
                error_message=f"Model validation failed: {model_name}"
            )

        # Prepare variables (merge defaults with provided)
        model_vars = self.default_vars.copy()
        if variables:
            model_vars.update(variables)

        try:
            # Execute dbt run command
            result = self.dbt_executor.run_model(
                model_name=model_name,
                vars_dict=model_vars,
                full_refresh=full_refresh,
                description=f"running staging model {model_name}"
            )

            # Create result object
            staging_result = StagingModelResult(
                model_name=model_name,
                success=result.success,
                execution_time=0.0,  # TODO: Track execution time
                variables_used=model_vars.copy(),
                error_message=result.stderr if not result.success else None,
                details={
                    "command": result.command,
                    "returncode": result.returncode,
                    "stdout": result.stdout[:1000] if result.stdout else None  # Truncate for logging
                }
            )

            # Try to get row count if successful
            if result.success:
                try:
                    from ..core.database_manager import DatabaseManager
                    db_manager = DatabaseManager(self.config)
                    if db_manager.table_exists(model_name):
                        staging_result.row_count = db_manager.get_table_row_count(model_name)
                        logger.info(f"Staging model {model_name} executed successfully: {staging_result.row_count:,} rows")
                    else:
                        logger.warning(f"Staging model {model_name} completed but table not found")
                except Exception as e:
                    logger.warning(f"Could not get row count for {model_name}: {e}")
            else:
                logger.error(f"Staging model {model_name} failed: {result.stderr}")

            return staging_result

        except Exception as e:
            logger.error(f"Error running staging model {model_name}: {e}")
            return StagingModelResult(
                model_name=model_name,
                success=False,
                error_message=f"Execution error: {e}",
                variables_used=model_vars.copy(),
                details={"error": str(e)}
            )

    def run_staging_models(
        self,
        model_names: Optional[List[str]] = None,
        variables: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        fail_fast: bool = False
    ) -> BatchStagingResult:
        """
        Run multiple staging models.

        Args:
            model_names: List of model names to run (None for all discovered models)
            variables: Variables to pass to models
            full_refresh: Whether to use full refresh
            fail_fast: Whether to stop on first failure

        Returns:
            BatchStagingResult with operation details
        """
        # Discover models if not provided
        if model_names is None:
            model_names = self.discover_staging_models()

        logger.info(f"Running {len(model_names)} staging models: {model_names}")

        batch_result = BatchStagingResult(total_models=len(model_names))

        for i, model_name in enumerate(model_names, 1):
            logger.info(f"Running staging model {i}/{len(model_names)}: {model_name}")

            model_result = self.run_staging_model(model_name, variables, full_refresh)
            batch_result.model_results.append(model_result)
            batch_result.total_execution_time += model_result.execution_time

            if model_result.success:
                batch_result.successful_models += 1
            else:
                batch_result.failed_models += 1

                if fail_fast:
                    logger.error(f"Staging model execution failed fast on {model_name}")
                    # Mark remaining models as skipped
                    remaining_models = model_names[i:]
                    for remaining_model in remaining_models:
                        skipped_result = StagingModelResult(
                            model_name=remaining_model,
                            success=False,
                            error_message="Skipped due to fail_fast mode"
                        )
                        batch_result.model_results.append(skipped_result)
                        batch_result.skipped_models += 1

                    batch_result.total_models = len(batch_result.model_results)
                    break

        logger.info(f"Staging model execution completed: {batch_result}")

        # Log detailed results
        successful_models = [r.model_name for r in batch_result.model_results if r.success]
        failed_models = [r.model_name for r in batch_result.model_results if not r.success and not r.error_message == "Skipped due to fail_fast mode"]

        if successful_models:
            logger.info(f"Successfully executed staging models: {successful_models}")

        if failed_models:
            logger.error(f"Failed to execute staging models: {failed_models}")

        return batch_result

    def get_staging_model_dependencies(self) -> Dict[str, List[str]]:
        """
        Get staging model dependencies based on project structure.

        Returns:
            Dictionary mapping model names to their dependencies
        """
        dependencies = {
            # Foundation models (no dependencies)
            "stg_census_data": [],  # Primary workforce data
            "stg_census_duplicates_audit": ["stg_census_data"],

            # Configuration staging models (depend on seeds)
            "stg_config_job_levels": [],
            "stg_config_cola_by_year": [],
            "stg_comp_levers": [],
            "stg_comp_targets": [],
            "stg_scenario_meta": [],

            # Hazard configuration models
            "stg_config_termination_hazard_base": [],
            "stg_config_termination_hazard_age_multipliers": [],
            "stg_config_termination_hazard_tenure_multipliers": [],
            "stg_config_promotion_hazard_base": [],
            "stg_config_promotion_hazard_age_multipliers": [],
            "stg_config_promotion_hazard_tenure_multipliers": [],
            "stg_config_raises_hazard": [],

            # Timing configuration
            "stg_config_raise_timing_distribution": [],
            "stg_config_timing_validation_rules": [],
        }

        return dependencies

    def get_optimal_execution_order(self, model_names: Optional[List[str]] = None) -> List[str]:
        """
        Get optimal execution order for staging models based on dependencies.

        Args:
            model_names: List of models to order (None for all discovered models)

        Returns:
            List of model names in optimal execution order
        """
        if model_names is None:
            model_names = self.discover_staging_models()

        dependencies = self.get_staging_model_dependencies()
        ordered_models = []
        remaining_models = set(model_names)

        # Simple topological sort
        while remaining_models:
            # Find models with no unmet dependencies
            ready_models = []
            for model in remaining_models:
                deps = dependencies.get(model, [])
                if all(dep in ordered_models or dep not in model_names for dep in deps):
                    ready_models.append(model)

            if not ready_models:
                # No models are ready, add remaining in alphabetical order
                # This handles circular dependencies or unknown dependencies
                ready_models = sorted(remaining_models)
                logger.warning(f"Circular or unresolved dependencies detected, adding remaining models: {ready_models}")

            # Add ready models to ordered list
            for model in ready_models:
                ordered_models.append(model)
                remaining_models.remove(model)

        logger.info(f"Optimal staging model execution order: {ordered_models}")
        return ordered_models

    def run_staging_models_in_optimal_order(
        self,
        model_names: Optional[List[str]] = None,
        variables: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        fail_fast: bool = True
    ) -> BatchStagingResult:
        """
        Run staging models in optimal order based on dependencies.

        Args:
            model_names: List of model names to run (None for all discovered models)
            variables: Variables to pass to models
            full_refresh: Whether to use full refresh
            fail_fast: Whether to stop on first failure

        Returns:
            BatchStagingResult with operation details
        """
        optimal_order = self.get_optimal_execution_order(model_names)

        return self.run_staging_models(
            model_names=optimal_order,
            variables=variables,
            full_refresh=full_refresh,
            fail_fast=fail_fast
        )

    def run_foundation_models(
        self,
        variables: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False
    ) -> BatchStagingResult:
        """
        Run foundation staging models (census and basic configuration).

        Args:
            variables: Variables to pass to models
            full_refresh: Whether to use full refresh

        Returns:
            BatchStagingResult with operation details
        """
        foundation_models = [
            "stg_census_data",
            "stg_config_job_levels",
            "stg_comp_levers"
        ]

        # Filter to only models that exist
        discovered_models = self.discover_staging_models()
        existing_foundation_models = [m for m in foundation_models if m in discovered_models]

        logger.info(f"Running foundation staging models: {existing_foundation_models}")

        return self.run_staging_models_in_optimal_order(
            model_names=existing_foundation_models,
            variables=variables,
            full_refresh=full_refresh,
            fail_fast=True
        )

    def run_configuration_models(
        self,
        variables: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False
    ) -> BatchStagingResult:
        """
        Run configuration staging models (all config models).

        Args:
            variables: Variables to pass to models
            full_refresh: Whether to use full refresh

        Returns:
            BatchStagingResult with operation details
        """
        discovered_models = self.discover_staging_models()
        config_models = [m for m in discovered_models if m.startswith("stg_config_") or m.startswith("stg_comp_")]

        logger.info(f"Running configuration staging models: {config_models}")

        return self.run_staging_models_in_optimal_order(
            model_names=config_models,
            variables=variables,
            full_refresh=full_refresh,
            fail_fast=False  # Allow some config models to fail
        )

    def run_models_batch_optimized(
        self,
        model_names: List[str],
        variables: Optional[Dict[str, Any]] = None,
        full_refresh: bool = False,
        description: str = ""
    ) -> BatchStagingResult:
        """
        Run multiple staging models using optimized batch execution.

        This method reduces dbt startup overhead by running multiple models
        in a single dbt command instead of individual commands.

        Args:
            model_names: List of model names to run
            variables: Variables to pass to models
            full_refresh: Whether to use full refresh
            description: Description for logging

        Returns:
            BatchStagingResult with batch execution details
        """
        import time
        start_time = time.time()

        if not model_names:
            return BatchStagingResult(
                total_models=0,
                successful_models=0,
                failed_models=0,
                model_results=[],
                total_execution_time=0.0
            )

        logger.info(f"🚀 Running {len(model_names)} models in batch: {', '.join(model_names)}")

        try:
            # Use the new batch method from dbt_executor
            batch_result = self.dbt_executor.run_models_batch(
                model_names=model_names,
                vars_dict=variables,
                full_refresh=full_refresh,
                description=f"batch {description}" if description else f"batch staging models"
            )

            execution_time = time.time() - start_time

            if batch_result.success:
                # Create individual results for each model (successful)
                individual_results = []
                for model_name in model_names:
                    result = StagingModelResult(
                        model_name=model_name,
                        success=True,
                        execution_time=execution_time / len(model_names),  # Approximate individual time
                        variables_used=variables.copy() if variables else {},
                        details={"batch_execution": True, "command": batch_result.command}
                    )
                    individual_results.append(result)

                    # Try to get row count
                    try:
                        from ..core.database_manager import DatabaseManager
                        db_manager = DatabaseManager(self.config)
                        if db_manager.table_exists(model_name):
                            result.row_count = db_manager.get_table_row_count(model_name)
                            logger.info(f"Model {model_name} executed successfully: {result.row_count:,} rows")
                    except Exception as e:
                        logger.warning(f"Could not get row count for {model_name}: {e}")

                return BatchStagingResult(
                    total_models=len(model_names),
                    successful_models=len(model_names),
                    failed_models=0,
                    model_results=individual_results,
                    total_execution_time=execution_time
                )
            else:
                # Batch failed, create failed results
                logger.error(f"Batch execution failed: {batch_result.stderr}")
                individual_results = []
                for model_name in model_names:
                    result = StagingModelResult(
                        model_name=model_name,
                        success=False,
                        execution_time=0.0,
                        variables_used=variables.copy() if variables else {},
                        error_message=f"Batch execution failed: {batch_result.stderr}",
                        details={"batch_execution": True, "command": batch_result.command}
                    )
                    individual_results.append(result)

                return BatchStagingResult(
                    total_models=len(model_names),
                    successful_models=0,
                    failed_models=len(model_names),
                    model_results=individual_results,
                    total_execution_time=execution_time
                )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error in batch model execution: {e}")

            # Create failed results for all models
            individual_results = []
            for model_name in model_names:
                result = StagingModelResult(
                    model_name=model_name,
                    success=False,
                    execution_time=0.0,
                    variables_used=variables.copy() if variables else {},
                    error_message=f"Batch execution error: {e}",
                    details={"batch_execution": True, "error": str(e)}
                )
                individual_results.append(result)

            return BatchStagingResult(
                total_models=len(model_names),
                successful_models=0,
                failed_models=len(model_names),
                model_results=individual_results,
                total_execution_time=execution_time
            )


class StagingLoaderError(Exception):
    """Exception raised for staging loader errors."""
    pass
