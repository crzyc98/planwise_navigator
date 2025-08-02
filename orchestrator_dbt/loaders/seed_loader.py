"""
CSV seed loading operations for orchestrator_dbt.

Handles loading dbt seed files with validation, error handling, and
comprehensive logging. Provides both individual and batch loading operations.
"""

from __future__ import annotations

import logging
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import OrchestrationConfig
from ..core.dbt_executor import DbtExecutor, DbtExecutionResult


logger = logging.getLogger(__name__)


@dataclass
class SeedLoadResult:
    """Result of seed loading operation."""
    seed_name: str
    success: bool
    execution_time: float = 0.0
    row_count: Optional[int] = None
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"SeedLoadResult("
            f"seed='{self.seed_name}', "
            f"success={self.success}, "
            f"rows={self.row_count}"
            f")"
        )


@dataclass
class BatchSeedLoadResult:
    """Result of batch seed loading operation."""
    total_seeds: int = 0
    successful_seeds: int = 0
    failed_seeds: int = 0
    skipped_seeds: int = 0
    total_execution_time: float = 0.0
    seed_results: List[SeedLoadResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_seeds == 0:
            return 100.0
        return (self.successful_seeds / self.total_seeds) * 100.0

    @property
    def overall_success(self) -> bool:
        """Check if all seeds loaded successfully."""
        return self.failed_seeds == 0

    def get_failed_seeds(self) -> List[SeedLoadResult]:
        """Get list of failed seed results."""
        return [r for r in self.seed_results if not r.success]

    def __repr__(self) -> str:
        return (
            f"BatchSeedLoadResult("
            f"total={self.total_seeds}, "
            f"successful={self.successful_seeds}, "
            f"failed={self.failed_seeds}, "
            f"success_rate={self.success_rate:.1f}%"
            f")"
        )


class SeedLoader:
    """
    CSV seed loading operations for dbt setup.

    Provides methods for loading individual seeds, batch operations,
    and validation of seed files and data.
    """

    def __init__(self, config: OrchestrationConfig, dbt_executor: DbtExecutor):
        """
        Initialize seed loader.

        Args:
            config: Orchestration configuration
            dbt_executor: dbt command executor
        """
        self.config = config
        self.dbt_executor = dbt_executor
        self.seeds_dir = config.dbt.project_dir / "seeds"

        # Validate seeds directory exists
        if not self.seeds_dir.exists():
            raise SeedLoaderError(f"Seeds directory not found: {self.seeds_dir}")

    def discover_seed_files(self) -> List[str]:
        """
        Discover all CSV seed files in the seeds directory.

        Returns:
            List of seed file names (without .csv extension)
        """
        seed_files = []

        if self.seeds_dir.exists():
            for csv_file in self.seeds_dir.glob("*.csv"):
                seed_name = csv_file.stem  # Remove .csv extension
                seed_files.append(seed_name)

        logger.info(f"Discovered {len(seed_files)} seed files: {seed_files}")
        return sorted(seed_files)

    def validate_seed_file(self, seed_name: str) -> bool:
        """
        Validate that a seed file exists and is readable.

        Args:
            seed_name: Name of the seed (without .csv extension)

        Returns:
            True if seed file is valid
        """
        seed_file = self.seeds_dir / f"{seed_name}.csv"

        if not seed_file.exists():
            logger.error(f"Seed file not found: {seed_file}")
            return False

        if not seed_file.is_file():
            logger.error(f"Seed path is not a file: {seed_file}")
            return False

        try:
            # Try to read first few lines to validate format
            with open(seed_file, 'r', encoding='utf-8') as f:
                header = f.readline().strip()
                if not header:
                    logger.error(f"Seed file appears to be empty: {seed_file}")
                    return False

                # Check for basic CSV structure
                if ',' not in header and ';' not in header and '\t' not in header:
                    logger.warning(f"Seed file may not be properly formatted CSV: {seed_file}")

            logger.debug(f"Seed file validated successfully: {seed_name}")
            return True

        except Exception as e:
            logger.error(f"Error validating seed file {seed_name}: {e}")
            return False

    def load_seed(self, seed_name: str, full_refresh: bool = False) -> SeedLoadResult:
        """
        Load a single dbt seed.

        Args:
            seed_name: Name of the seed to load
            full_refresh: Whether to use full refresh

        Returns:
            SeedLoadResult with operation details
        """
        logger.info(f"Loading seed: {seed_name}")

        # Validate seed file exists
        if not self.validate_seed_file(seed_name):
            return SeedLoadResult(
                seed_name=seed_name,
                success=False,
                error_message=f"Seed file validation failed: {seed_name}"
            )

        try:
            # Execute dbt seed command
            result = self.dbt_executor.load_seed(
                seed_name=seed_name,
                full_refresh=full_refresh,
                description=f"loading seed {seed_name}"
            )

            # Create result object
            seed_result = SeedLoadResult(
                seed_name=seed_name,
                success=result.success,
                execution_time=0.0,  # TODO: Track execution time
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
                    if db_manager.table_exists(seed_name):
                        seed_result.row_count = db_manager.get_table_row_count(seed_name)
                        logger.info(f"Seed {seed_name} loaded successfully: {seed_result.row_count:,} rows")
                    else:
                        logger.warning(f"Seed {seed_name} completed but table not found")
                except Exception as e:
                    logger.warning(f"Could not get row count for {seed_name}: {e}")
            else:
                logger.error(f"Seed {seed_name} failed to load: {result.stderr}")

            return seed_result

        except Exception as e:
            logger.error(f"Error loading seed {seed_name}: {e}")
            return SeedLoadResult(
                seed_name=seed_name,
                success=False,
                error_message=f"Execution error: {e}",
                details={"error": str(e)}
            )

    def load_seeds(
        self,
        seed_names: Optional[List[str]] = None,
        full_refresh: bool = False,
        fail_fast: bool = False
    ) -> BatchSeedLoadResult:
        """
        Load multiple dbt seeds.

        Args:
            seed_names: List of seed names to load (None for all discovered seeds)
            full_refresh: Whether to use full refresh
            fail_fast: Whether to stop on first failure

        Returns:
            BatchSeedLoadResult with operation details
        """
        # Discover seeds if not provided
        if seed_names is None:
            seed_names = self.discover_seed_files()

        logger.info(f"Loading {len(seed_names)} seeds: {seed_names}")

        batch_result = BatchSeedLoadResult(total_seeds=len(seed_names))

        for i, seed_name in enumerate(seed_names, 1):
            logger.info(f"Loading seed {i}/{len(seed_names)}: {seed_name}")

            seed_result = self.load_seed(seed_name, full_refresh)
            batch_result.seed_results.append(seed_result)
            batch_result.total_execution_time += seed_result.execution_time

            if seed_result.success:
                batch_result.successful_seeds += 1
            else:
                batch_result.failed_seeds += 1

                if fail_fast:
                    logger.error(f"Seed loading failed fast on {seed_name}")
                    # Mark remaining seeds as skipped
                    remaining_seeds = seed_names[i:]
                    for remaining_seed in remaining_seeds:
                        skipped_result = SeedLoadResult(
                            seed_name=remaining_seed,
                            success=False,
                            error_message="Skipped due to fail_fast mode"
                        )
                        batch_result.seed_results.append(skipped_result)
                        batch_result.skipped_seeds += 1

                    batch_result.total_seeds = len(batch_result.seed_results)
                    break

        logger.info(f"Seed loading completed: {batch_result}")

        # Log detailed results
        successful_seeds = [r.seed_name for r in batch_result.seed_results if r.success]
        failed_seeds = [r.seed_name for r in batch_result.seed_results if not r.success and not r.error_message == "Skipped due to fail_fast mode"]

        if successful_seeds:
            logger.info(f"Successfully loaded seeds: {successful_seeds}")

        if failed_seeds:
            logger.error(f"Failed to load seeds: {failed_seeds}")

        return batch_result

    def load_all_seeds_batch(self, full_refresh: bool = False) -> DbtExecutionResult:
        """
        Load all seeds using single dbt seed command (more efficient).

        Args:
            full_refresh: Whether to use full refresh

        Returns:
            DbtExecutionResult from batch operation
        """
        logger.info("Loading all seeds in batch mode")

        return self.dbt_executor.load_all_seeds(
            full_refresh=full_refresh,
            description="loading all seeds in batch"
        )

    def get_seed_dependencies(self) -> Dict[str, List[str]]:
        """
        Get seed dependencies (seeds that must be loaded before others).

        Returns:
            Dictionary mapping seed names to their dependencies
        """
        # Define known dependencies based on project structure
        dependencies = {
            # Configuration seeds should be loaded first
            "config_job_levels": [],
            "config_cola_by_year": [],
            "scenario_meta": [],

            # Compensation configuration
            "comp_levers": ["scenario_meta"],
            "comp_targets": ["scenario_meta"],

            # Hazard configuration depends on job levels
            "config_termination_hazard_base": ["config_job_levels"],
            "config_promotion_hazard_base": ["config_job_levels"],
            "config_raises_hazard": ["config_job_levels"],

            # Multiplier tables depend on base hazard tables
            "config_termination_hazard_age_multipliers": ["config_termination_hazard_base"],
            "config_termination_hazard_tenure_multipliers": ["config_termination_hazard_base"],
            "config_promotion_hazard_age_multipliers": ["config_promotion_hazard_base"],
            "config_promotion_hazard_tenure_multipliers": ["config_promotion_hazard_base"],

            # Timing configuration
            "config_raise_timing_distribution": [],
            "config_timing_validation_rules": [],
        }

        return dependencies

    def get_optimal_load_order(self, seed_names: Optional[List[str]] = None) -> List[str]:
        """
        Get optimal order for loading seeds based on dependencies.

        Args:
            seed_names: List of seeds to order (None for all discovered seeds)

        Returns:
            List of seed names in optimal load order
        """
        if seed_names is None:
            seed_names = self.discover_seed_files()

        dependencies = self.get_seed_dependencies()
        ordered_seeds = []
        remaining_seeds = set(seed_names)

        # Simple topological sort
        while remaining_seeds:
            # Find seeds with no unmet dependencies
            ready_seeds = []
            for seed in remaining_seeds:
                deps = dependencies.get(seed, [])
                if all(dep in ordered_seeds or dep not in seed_names for dep in deps):
                    ready_seeds.append(seed)

            if not ready_seeds:
                # No seeds are ready, add remaining in alphabetical order
                # This handles circular dependencies or unknown dependencies
                ready_seeds = sorted(remaining_seeds)
                logger.warning(f"Circular or unresolved dependencies detected, adding remaining seeds: {ready_seeds}")

            # Add ready seeds to ordered list
            for seed in ready_seeds:
                ordered_seeds.append(seed)
                remaining_seeds.remove(seed)

        logger.info(f"Optimal seed load order: {ordered_seeds}")
        return ordered_seeds

    def load_seeds_in_optimal_order(
        self,
        seed_names: Optional[List[str]] = None,
        full_refresh: bool = False,
        fail_fast: bool = True
    ) -> BatchSeedLoadResult:
        """
        Load seeds in optimal order based on dependencies.

        Args:
            seed_names: List of seed names to load (None for all discovered seeds)
            full_refresh: Whether to use full refresh
            fail_fast: Whether to stop on first failure

        Returns:
            BatchSeedLoadResult with operation details
        """
        optimal_order = self.get_optimal_load_order(seed_names)

        return self.load_seeds(
            seed_names=optimal_order,
            full_refresh=full_refresh,
            fail_fast=fail_fast
        )

    def load_seeds_batch_optimized(
        self,
        seed_names: Optional[List[str]] = None,
        full_refresh: bool = False,
        fail_fast: bool = True,
        max_workers: int = 4
    ) -> BatchSeedLoadResult:
        """
        Load seeds with optimized batch and concurrent execution.

        This method provides multiple optimization strategies:
        1. Try single batch command first (fastest)
        2. Fall back to concurrent execution if batch fails
        3. Fall back to sequential execution if needed

        Args:
            seed_names: List of seed names to load (None for all discovered seeds)
            full_refresh: Whether to use full refresh
            fail_fast: Whether to stop on first failure
            max_workers: Maximum concurrent workers for parallel execution

        Returns:
            BatchSeedLoadResult with operation details
        """
        start_time = time.time()

        # Discover seeds if not provided
        if seed_names is None:
            seed_names = self.discover_seed_files()

        logger.info(f"Loading {len(seed_names)} seeds with optimized batch execution")

        # Strategy 1: Try single batch command (most efficient)
        if len(seed_names) > 5:  # Only use batch for multiple seeds
            logger.info("Attempting optimized batch seed loading...")
            try:
                batch_result = self._try_batch_load_all_seeds(full_refresh)
                if batch_result.success:
                    execution_time = time.time() - start_time
                    logger.info(f"✅ Batch seed loading completed successfully in {execution_time:.2f}s")

                    # Create detailed result object
                    return self._create_batch_result_from_batch_execution(
                        seed_names, batch_result, execution_time
                    )
                else:
                    logger.warning("Batch seed loading failed, falling back to concurrent execution")
            except Exception as e:
                logger.warning(f"Batch seed loading failed with error: {e}, falling back to concurrent execution")

        # Strategy 2: Concurrent execution with dependency management
        logger.info("Using concurrent seed loading with dependency resolution...")
        try:
            result = self._load_seeds_concurrent_with_dependencies(
                seed_names, full_refresh, fail_fast, max_workers
            )
            execution_time = time.time() - start_time
            result.total_execution_time = execution_time
            logger.info(f"✅ Concurrent seed loading completed in {execution_time:.2f}s")
            return result
        except Exception as e:
            logger.warning(f"Concurrent seed loading failed: {e}, falling back to sequential execution")

        # Strategy 3: Fall back to sequential execution (most reliable)
        logger.info("Falling back to sequential seed loading...")
        result = self.load_seeds_in_optimal_order(seed_names, full_refresh, fail_fast)
        execution_time = time.time() - start_time
        result.total_execution_time = execution_time
        logger.info(f"✅ Sequential seed loading completed in {execution_time:.2f}s")
        return result

    def _try_batch_load_all_seeds(self, full_refresh: bool = False) -> DbtExecutionResult:
        """
        Try to load all seeds in a single batch command.

        Args:
            full_refresh: Whether to use full refresh

        Returns:
            DbtExecutionResult from batch operation
        """
        return self.dbt_executor.load_all_seeds(
            full_refresh=full_refresh,
            description="optimized batch seed loading"
        )

    def _create_batch_result_from_batch_execution(
        self,
        seed_names: List[str],
        batch_result: DbtExecutionResult,
        execution_time: float
    ) -> BatchSeedLoadResult:
        """
        Create BatchSeedLoadResult from successful batch execution.

        Args:
            seed_names: List of seed names that were loaded
            batch_result: DbtExecutionResult from batch command
            execution_time: Total execution time

        Returns:
            BatchSeedLoadResult representing the batch operation
        """
        # Create individual seed results (estimated from batch)
        seed_results = []
        for seed_name in seed_names:
            seed_result = SeedLoadResult(
                seed_name=seed_name,
                success=batch_result.success,
                execution_time=execution_time / len(seed_names),  # Estimate
                error_message=batch_result.stderr if not batch_result.success else None,
                details={
                    "command": batch_result.command,
                    "batch_operation": True,
                    "returncode": batch_result.returncode
                }
            )

            # Try to get row count if successful
            if batch_result.success:
                try:
                    from ..core.database_manager import DatabaseManager
                    db_manager = DatabaseManager(self.config)
                    if db_manager.table_exists(seed_name):
                        seed_result.row_count = db_manager.get_table_row_count(seed_name)
                except Exception as e:
                    logger.debug(f"Could not get row count for {seed_name}: {e}")

            seed_results.append(seed_result)

        return BatchSeedLoadResult(
            total_seeds=len(seed_names),
            successful_seeds=len(seed_names) if batch_result.success else 0,
            failed_seeds=0 if batch_result.success else len(seed_names),
            total_execution_time=execution_time,
            seed_results=seed_results
        )

    def _load_seeds_concurrent_with_dependencies(
        self,
        seed_names: List[str],
        full_refresh: bool,
        fail_fast: bool,
        max_workers: int
    ) -> BatchSeedLoadResult:
        """
        Load seeds concurrently while respecting dependencies.

        Args:
            seed_names: List of seed names to load
            full_refresh: Whether to use full refresh
            fail_fast: Whether to stop on first failure
            max_workers: Maximum concurrent workers

        Returns:
            BatchSeedLoadResult with operation details
        """
        dependencies = self.get_seed_dependencies()
        batch_result = BatchSeedLoadResult(total_seeds=len(seed_names))

        # Group seeds by dependency level
        dependency_levels = self._group_seeds_by_dependency_level(seed_names, dependencies)

        # Process each dependency level concurrently
        completed_seeds = set()

        for level, level_seeds in dependency_levels.items():
            if not level_seeds:
                continue

            logger.info(f"Processing dependency level {level} with {len(level_seeds)} seeds: {level_seeds}")

            # Load seeds in this level concurrently
            level_results = self._load_seeds_concurrent_batch(
                level_seeds, full_refresh, max_workers
            )

            # Process results
            for result in level_results:
                batch_result.seed_results.append(result)
                batch_result.total_execution_time += result.execution_time

                if result.success:
                    batch_result.successful_seeds += 1
                    completed_seeds.add(result.seed_name)
                else:
                    batch_result.failed_seeds += 1

                    if fail_fast:
                        logger.error(f"Seed loading failed fast on {result.seed_name}")
                        # Mark remaining seeds as skipped
                        remaining_seeds = [
                            s for s in seed_names
                            if s not in completed_seeds and s != result.seed_name
                        ]
                        for remaining_seed in remaining_seeds:
                            skipped_result = SeedLoadResult(
                                seed_name=remaining_seed,
                                success=False,
                                error_message="Skipped due to fail_fast mode"
                            )
                            batch_result.seed_results.append(skipped_result)
                            batch_result.skipped_seeds += 1

                        batch_result.total_seeds = len(batch_result.seed_results)
                        return batch_result

        return batch_result

    def _group_seeds_by_dependency_level(
        self,
        seed_names: List[str],
        dependencies: Dict[str, List[str]]
    ) -> Dict[int, List[str]]:
        """
        Group seeds by dependency level for concurrent execution.

        Args:
            seed_names: List of seed names to group
            dependencies: Dependency mapping

        Returns:
            Dictionary mapping dependency level to seed names
        """
        levels = {}
        assigned_seeds = set()
        level = 0

        while len(assigned_seeds) < len(seed_names):
            current_level_seeds = []

            for seed in seed_names:
                if seed in assigned_seeds:
                    continue

                seed_deps = dependencies.get(seed, [])
                # Check if all dependencies are satisfied
                if all(dep in assigned_seeds or dep not in seed_names for dep in seed_deps):
                    current_level_seeds.append(seed)

            if not current_level_seeds:
                # Handle circular dependencies - add remaining seeds
                remaining_seeds = [s for s in seed_names if s not in assigned_seeds]
                logger.warning(f"Circular dependencies detected, adding remaining seeds to level {level}: {remaining_seeds}")
                current_level_seeds = remaining_seeds

            levels[level] = current_level_seeds
            assigned_seeds.update(current_level_seeds)
            level += 1

        return levels

    def _load_seeds_concurrent_batch(
        self,
        seed_names: List[str],
        full_refresh: bool,
        max_workers: int
    ) -> List[SeedLoadResult]:
        """
        Load a batch of seeds concurrently.

        Args:
            seed_names: List of seed names to load
            full_refresh: Whether to use full refresh
            max_workers: Maximum concurrent workers

        Returns:
            List of SeedLoadResult objects
        """
        results = []

        # Use ThreadPoolExecutor for concurrent execution
        with ThreadPoolExecutor(max_workers=min(max_workers, len(seed_names))) as executor:
            # Submit all seed loading tasks
            future_to_seed = {
                executor.submit(self.load_seed, seed_name, full_refresh): seed_name
                for seed_name in seed_names
            }

            # Collect results as they complete
            for future in as_completed(future_to_seed):
                seed_name = future_to_seed[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.debug(f"Completed loading seed: {seed_name} ({'✅' if result.success else '❌'})")
                except Exception as e:
                    logger.error(f"Exception loading seed {seed_name}: {e}")
                    error_result = SeedLoadResult(
                        seed_name=seed_name,
                        success=False,
                        error_message=f"Concurrent execution error: {e}"
                    )
                    results.append(error_result)

        # Sort results to match original order
        results.sort(key=lambda x: seed_names.index(x.seed_name) if x.seed_name in seed_names else 999)
        return results


    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for seed loading operations.

        Returns:
            Dictionary with performance metrics
        """
        discovered_seeds = self.discover_seed_files()

        return {
            "total_seeds_available": len(discovered_seeds),
            "seeds_with_dependencies": len([s for s in discovered_seeds if self.get_seed_dependencies().get(s, [])]),
            "max_dependency_depth": self._calculate_max_dependency_depth(),
            "optimal_load_order": self.get_optimal_load_order(),
            "parallelization_potential": self._estimate_parallelization_potential()
        }

    def _calculate_max_dependency_depth(self) -> int:
        """
        Calculate the maximum dependency depth for dependency planning.

        Returns:
            Maximum dependency depth
        """
        seeds = self.discover_seed_files()
        dependencies = self.get_seed_dependencies()
        levels = self._group_seeds_by_dependency_level(seeds, dependencies)
        return len(levels)

    def _estimate_parallelization_potential(self) -> Dict[str, Any]:
        """
        Estimate the parallelization potential for seed loading.

        Returns:
            Dictionary with parallelization metrics
        """
        seeds = self.discover_seed_files()
        dependencies = self.get_seed_dependencies()
        levels = self._group_seeds_by_dependency_level(seeds, dependencies)

        total_seeds = len(seeds)
        parallelizable_seeds = sum(len(level_seeds) for level_seeds in levels.values() if len(level_seeds) > 1)

        return {
            "total_seeds": total_seeds,
            "dependency_levels": len(levels),
            "parallelizable_seeds": parallelizable_seeds,
            "max_concurrent_seeds": max(len(level_seeds) for level_seeds in levels.values()) if levels else 0,
            "parallelization_ratio": parallelizable_seeds / total_seeds if total_seeds > 0 else 0.0
        }


class SeedLoaderError(Exception):
    """Exception raised for seed loading errors."""
    pass
