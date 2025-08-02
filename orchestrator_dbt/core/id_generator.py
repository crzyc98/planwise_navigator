#!/usr/bin/env python3
"""Enhanced Unified Employee ID Generation System for orchestrator_dbt.

This module provides centralized, deterministic employee ID generation with
performance optimizations and enhanced validation capabilities. Maintains
full compatibility with the MVP system while adding enterprise-grade features
for large-scale workforce simulations.

Key enhancements:
- Batch processing optimizations for DuckDB integration
- Performance monitoring and throughput metrics
- Enhanced validation with business rule checking
- Thread-safe operations for concurrent processing
- Memory-efficient generation for large workforces
- Integration with orchestrator_dbt configuration system
"""

import hashlib
import re
import time
import logging
import threading
from typing import List, Optional, Union, Dict, Any, Set
from datetime import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from ..core.config import OrchestrationConfig
from ..core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class IDGenerationMetrics:
    """Performance metrics for ID generation operations."""
    total_generated: int = 0
    baseline_count: int = 0
    new_hire_count: int = 0
    generation_time: float = 0.0
    ids_per_second: float = 0.0
    batch_operations: int = 0
    validation_checks: int = 0
    collision_checks: int = 0


class UnifiedIDGenerator:
    """Enhanced centralized service for generating consistent, deterministic employee IDs.

    Implements optimized hybrid approach with enterprise-grade features:
    - Baseline employees: EMP_YYYY_NNNNNN (15 chars) - Year-aware, performance optimized
    - New hire employees: NH_YYYY_XXXXXXXX_NNNNNN (23 chars) - Full deterministic hash

    Performance optimizations:
    - Thread-safe operations for concurrent processing
    - Batch generation with collision detection
    - Memory-efficient tracking for large-scale operations
    - Integration with DuckDB for validation queries
    """

    def __init__(
        self,
        random_seed: int,
        base_year: int,
        database_manager: Optional[DatabaseManager] = None,
        enable_database_validation: bool = True
    ):
        """Initialize the enhanced unified ID generator.

        Args:
            random_seed: Random seed for deterministic hash generation
            base_year: Base year for ID generation (e.g., 2024 for baseline, 2025+ for simulation)
            database_manager: Optional database manager for validation queries
            enable_database_validation: Enable database-based collision checking

        Raises:
            ValueError: If base_year is outside valid range
        """
        if not (2020 <= base_year <= 2050):
            raise ValueError(f"Invalid year: {base_year}. Must be between 2020-2050")

        self.random_seed = random_seed
        self.base_year = base_year
        self.database_manager = database_manager
        self.enable_database_validation = enable_database_validation

        # Thread-safe tracking
        self._lock = threading.Lock()
        self._generated_ids: Set[str] = set()
        self._metrics = IDGenerationMetrics()

        # Performance optimization parameters
        self._batch_size = 10000  # Optimal batch size for large operations
        self._collision_check_batch_size = 1000  # Database collision check batch size

    def generate_employee_id(
        self,
        sequence: int,
        is_baseline: bool = True,
        hire_year: Optional[int] = None,
        validate_collision: bool = True
    ) -> str:
        """Generate a single employee ID using the unified strategy.

        Args:
            sequence: Sequential number for the employee (1-based)
            is_baseline: True for baseline employees, False for new hires
            hire_year: Year for new hire (defaults to base_year)
            validate_collision: Enable collision validation against database

        Returns:
            Formatted employee ID string

        Raises:
            ValueError: If inputs are invalid or ID collision detected
        """
        start_time = time.time()

        # Input validation
        if not (1 <= sequence <= 999999):
            raise ValueError(f"Invalid sequence: {sequence}. Must be between 1-999999")

        year = hire_year if hire_year is not None else self.base_year
        if not (2020 <= year <= 2050):
            raise ValueError(f"Invalid year: {year}. Must be between 2020-2050")

        if is_baseline:
            # Baseline format: EMP_2024_000001 (15 characters)
            employee_id = f'EMP_{year}_{sequence:06d}'
        else:
            # New hire format: NH_2025_25eefbfa_000001 (23 characters)
            combined_string = f"NEW_HIRE_{year}_{sequence}_{self.random_seed}"
            hash_object = hashlib.sha256(combined_string.encode())
            hash_hex = hash_object.hexdigest()[:8]  # 8-char deterministic hash
            employee_id = f'NH_{year}_{hash_hex}_{sequence:06d}'

        # Thread-safe validation and tracking
        with self._lock:
            # Validate format
            if not self._validate_id_format(employee_id, is_baseline):
                raise ValueError(f"Generated ID doesn't match expected pattern: {employee_id}")

            # Check for local duplicates
            if employee_id in self._generated_ids:
                raise ValueError(f"Duplicate employee ID generated: {employee_id}")

            # Database collision check if enabled
            if validate_collision and self.enable_database_validation and self.database_manager:
                if self._check_database_collision(employee_id):
                    raise ValueError(f"Employee ID already exists in database: {employee_id}")
                self._metrics.collision_checks += 1

            self._generated_ids.add(employee_id)

            # Update metrics
            self._metrics.total_generated += 1
            if is_baseline:
                self._metrics.baseline_count += 1
            else:
                self._metrics.new_hire_count += 1

            generation_time = time.time() - start_time
            self._metrics.generation_time += generation_time
            self._metrics.validation_checks += 1

        return employee_id

    def generate_batch_employee_ids(
        self,
        start_sequence: int,
        count: int,
        is_baseline: bool = True,
        hire_year: Optional[int] = None,
        validate_collisions: bool = True,
        parallel_processing: bool = False
    ) -> List[str]:
        """Generate a batch of employee IDs with performance optimizations.

        This method is highly optimized for large-scale ID generation with:
        - Bulk validation and collision checking
        - Optional parallel processing for very large batches
        - Memory-efficient tracking
        - Performance monitoring

        Args:
            start_sequence: Starting sequence number (1-based)
            count: Number of IDs to generate
            is_baseline: True for baseline employees, False for new hires
            hire_year: Year for new hires (defaults to base_year)
            validate_collisions: Enable database collision validation
            parallel_processing: Use parallel processing for large batches

        Returns:
            List of formatted employee ID strings

        Raises:
            ValueError: If batch parameters are invalid
        """
        start_time = time.time()

        # Input validation
        if count <= 0:
            raise ValueError(f"Invalid count: {count}. Must be positive")
        if start_sequence < 1:
            raise ValueError(f"Invalid start_sequence: {start_sequence}. Must be >= 1")
        if start_sequence + count - 1 > 999999:
            raise ValueError(f"Sequence range exceeds maximum (999999): {start_sequence + count - 1}")

        # Determine processing strategy based on batch size
        if parallel_processing and count > 5000:
            batch_ids = self._generate_batch_parallel(start_sequence, count, is_baseline, hire_year)
        else:
            batch_ids = self._generate_batch_sequential(start_sequence, count, is_baseline, hire_year)

        # Bulk collision validation if enabled
        if validate_collisions and self.enable_database_validation and self.database_manager:
            self._validate_batch_collisions(batch_ids)

        # Update metrics
        with self._lock:
            self._metrics.batch_operations += 1
            batch_time = time.time() - start_time
            self._metrics.generation_time += batch_time
            self._metrics.ids_per_second = self._metrics.total_generated / self._metrics.generation_time if self._metrics.generation_time > 0 else 0

        logger.info(
            f"Generated batch of {len(batch_ids)} IDs in {batch_time:.3f}s "
            f"({len(batch_ids)/batch_time:.0f} IDs/sec)"
        )

        return batch_ids

    def _generate_batch_sequential(
        self,
        start_sequence: int,
        count: int,
        is_baseline: bool,
        hire_year: Optional[int]
    ) -> List[str]:
        """Generate batch of IDs sequentially for smaller batches."""
        batch_ids = []
        for i in range(count):
            sequence = start_sequence + i
            employee_id = self.generate_employee_id(
                sequence=sequence,
                is_baseline=is_baseline,
                hire_year=hire_year,
                validate_collision=False  # Skip individual collision checks for batch
            )
            batch_ids.append(employee_id)
        return batch_ids

    def _generate_batch_parallel(
        self,
        start_sequence: int,
        count: int,
        is_baseline: bool,
        hire_year: Optional[int]
    ) -> List[str]:
        """Generate batch of IDs in parallel for large batches."""
        # Split into smaller chunks for parallel processing
        chunk_size = min(self._batch_size, count // 4)  # Use 4 threads
        chunks = [(start_sequence + i, min(chunk_size, count - i))
                  for i in range(0, count, chunk_size)]

        batch_ids = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(self._generate_batch_sequential, start_seq, chunk_count, is_baseline, hire_year)
                for start_seq, chunk_count in chunks
            ]

            for future in futures:
                batch_ids.extend(future.result())

        return batch_ids

    def _validate_batch_collisions(self, employee_ids: List[str]) -> None:
        """Validate batch of IDs against database for collisions."""
        if not employee_ids or not self.database_manager:
            return

        # Process in chunks to avoid large queries
        for i in range(0, len(employee_ids), self._collision_check_batch_size):
            chunk = employee_ids[i:i + self._collision_check_batch_size]

            # Create placeholders for the IN clause
            placeholders = ','.join(['?' for _ in chunk])

            with self.database_manager.get_connection() as conn:
                # Check all possible sources of existing employee IDs
                queries = [
                    f"SELECT employee_id FROM int_baseline_workforce WHERE employee_id IN ({placeholders})",
                    f"SELECT employee_id FROM fct_yearly_events WHERE employee_id IN ({placeholders})",
                    f"SELECT employee_id FROM fct_workforce_snapshot WHERE employee_id IN ({placeholders})"
                ]

                existing_ids = set()
                for query in queries:
                    try:
                        results = conn.execute(query, chunk).fetchall()
                        existing_ids.update(row[0] for row in results)
                    except Exception as e:
                        logger.debug(f"Table not found in collision check: {e}")
                        continue

                # Check for collisions
                collisions = existing_ids.intersection(set(chunk))
                if collisions:
                    raise ValueError(f"Employee ID collisions detected: {list(collisions)}")

        self._metrics.collision_checks += len(employee_ids)

    def validate_employee_id_format(self, employee_id: str) -> bool:
        """Validate that an employee ID matches the expected format.

        Args:
            employee_id: Employee ID string to validate

        Returns:
            True if format is valid, False otherwise
        """
        return self._validate_id_format(employee_id, employee_id.startswith('EMP_'))

    def _validate_id_format(self, employee_id: str, is_baseline: bool) -> bool:
        """Internal format validation."""
        if is_baseline:
            pattern = r'^EMP_\d{4}_\d{6}$'
        else:
            pattern = r'^NH_\d{4}_[a-f0-9]{8}_\d{6}$'

        return bool(re.match(pattern, employee_id))

    def _check_database_collision(self, employee_id: str) -> bool:
        """Check if employee ID already exists in database."""
        if not self.database_manager:
            return False

        with self.database_manager.get_connection() as conn:
            # Check all relevant tables for existing ID
            check_queries = [
                "SELECT 1 FROM int_baseline_workforce WHERE employee_id = ? LIMIT 1",
                "SELECT 1 FROM fct_yearly_events WHERE employee_id = ? LIMIT 1",
                "SELECT 1 FROM fct_workforce_snapshot WHERE employee_id = ? LIMIT 1"
            ]

            for query in check_queries:
                try:
                    result = conn.execute(query, [employee_id]).fetchone()
                    if result:
                        return True  # Collision found
                except Exception:
                    # Table might not exist, continue checking other tables
                    continue

            return False  # No collision found

    def extract_year_from_id(self, employee_id: str) -> Optional[int]:
        """Extract the year from an employee ID.

        Args:
            employee_id: Employee ID string

        Returns:
            Year as integer, or None if format is invalid
        """
        if not self.validate_employee_id_format(employee_id):
            return None

        try:
            if employee_id.startswith('EMP_'):
                return int(employee_id[4:8])  # EMP_YYYY_...
            elif employee_id.startswith('NH_'):
                return int(employee_id[3:7])   # NH_YYYY_...
        except (IndexError, ValueError):
            return None

        return None

    def extract_sequence_from_id(self, employee_id: str) -> Optional[int]:
        """Extract the sequence number from an employee ID.

        Args:
            employee_id: Employee ID string

        Returns:
            Sequence number as integer, or None if format is invalid
        """
        if not self.validate_employee_id_format(employee_id):
            return None

        try:
            # Both formats have sequence at the end
            return int(employee_id[-6:])
        except (IndexError, ValueError):
            return None

    def is_baseline_employee(self, employee_id: str) -> bool:
        """Check if an employee ID represents a baseline employee.

        Args:
            employee_id: Employee ID string

        Returns:
            True if baseline employee, False if new hire or invalid format
        """
        return employee_id.startswith('EMP_') and self.validate_employee_id_format(employee_id)

    def is_new_hire_employee(self, employee_id: str) -> bool:
        """Check if an employee ID represents a new hire employee.

        Args:
            employee_id: Employee ID string

        Returns:
            True if new hire employee, False if baseline or invalid format
        """
        return employee_id.startswith('NH_') and self.validate_employee_id_format(employee_id)

    def get_generation_metrics(self) -> IDGenerationMetrics:
        """Get comprehensive statistics about ID generation for monitoring.

        Returns:
            IDGenerationMetrics with detailed performance data
        """
        with self._lock:
            # Update performance metrics
            if self._metrics.generation_time > 0:
                self._metrics.ids_per_second = self._metrics.total_generated / self._metrics.generation_time

            return self._metrics

    def reset_generation_tracking(self) -> None:
        """Reset the internal tracking of generated IDs and metrics.

        This should be called between simulation runs to prevent false
        duplicate detection across different simulation contexts.
        """
        with self._lock:
            self._generated_ids.clear()
            self._metrics = IDGenerationMetrics()

    def validate_id_uniqueness_batch(self, employee_ids: List[str]) -> Dict[str, Any]:
        """Enhanced batch uniqueness validation with detailed reporting.

        Args:
            employee_ids: List of employee ID strings to validate

        Returns:
            Dictionary with validation results and statistics
        """
        start_time = time.time()

        if not employee_ids:
            return {
                'unique': True,
                'total_ids': 0,
                'duplicates': [],
                'validation_time': 0.0
            }

        # Find duplicates
        seen = set()
        duplicates = []
        for emp_id in employee_ids:
            if emp_id in seen:
                duplicates.append(emp_id)
            else:
                seen.add(emp_id)

        validation_time = time.time() - start_time

        result = {
            'unique': len(duplicates) == 0,
            'total_ids': len(employee_ids),
            'unique_ids': len(seen),
            'duplicates': duplicates,
            'duplicate_count': len(duplicates),
            'validation_time': validation_time,
            'ids_per_second': len(employee_ids) / validation_time if validation_time > 0 else 0
        }

        if duplicates:
            logger.warning(f"Found {len(duplicates)} duplicate employee IDs: {duplicates[:5]}...")
        else:
            logger.info(f"Validated {len(employee_ids)} unique employee IDs in {validation_time:.3f}s")

        return result

    def generate_optimized_batch_for_simulation(
        self,
        simulation_year: int,
        hire_count: int,
        level_distribution: Optional[Dict[int, float]] = None
    ) -> Dict[int, List[str]]:
        """Generate optimized batch of new hire IDs distributed by level.

        This method is specifically optimized for simulation event generation
        with level-aware ID distribution and performance monitoring.

        Args:
            simulation_year: Year for new hire generation
            hire_count: Total number of hires to generate
            level_distribution: Optional level distribution weights

        Returns:
            Dictionary mapping levels to lists of employee IDs
        """
        start_time = time.time()

        # Default level distribution if not provided
        if level_distribution is None:
            level_distribution = {
                1: 0.40,  # 40% Level 1 (entry level)
                2: 0.30,  # 30% Level 2
                3: 0.20,  # 20% Level 3
                4: 0.08,  # 8% Level 4
                5: 0.02   # 2% Level 5 (senior)
            }

        # Calculate hires per level
        level_ids = {}
        sequence_start = 1

        for level, weight in level_distribution.items():
            level_hires = int(hire_count * weight)
            if level_hires > 0:
                level_batch = self.generate_batch_employee_ids(
                    start_sequence=sequence_start,
                    count=level_hires,
                    is_baseline=False,
                    hire_year=simulation_year,
                    validate_collisions=True,
                    parallel_processing=level_hires > 1000
                )
                level_ids[level] = level_batch
                sequence_start += level_hires

        # Handle remaining hires for the last level
        total_generated = sum(len(ids) for ids in level_ids.values())
        remaining = hire_count - total_generated
        if remaining > 0:
            last_level = max(level_distribution.keys())
            additional_ids = self.generate_batch_employee_ids(
                start_sequence=sequence_start,
                count=remaining,
                is_baseline=False,
                hire_year=simulation_year,
                validate_collisions=True
            )
            if last_level in level_ids:
                level_ids[last_level].extend(additional_ids)
            else:
                level_ids[last_level] = additional_ids

        generation_time = time.time() - start_time
        total_ids = sum(len(ids) for ids in level_ids.values())

        logger.info(
            f"Generated {total_ids} simulation IDs by level in {generation_time:.3f}s "
            f"({total_ids/generation_time:.0f} IDs/sec)"
        )

        return level_ids


def validate_employee_id_batch_uniqueness(employee_ids: List[str]) -> None:
    """Standalone batch uniqueness validation for backward compatibility.

    This function provides orchestration-level validation to ensure
    ID uniqueness across different generation contexts.

    Args:
        employee_ids: List of employee ID strings to validate

    Raises:
        ValueError: If duplicate IDs are found
    """
    if not employee_ids:
        return

    unique_ids = set(employee_ids)
    if len(employee_ids) != len(unique_ids):
        # Find duplicates for better error reporting
        seen = set()
        duplicates = set()
        for emp_id in employee_ids:
            if emp_id in seen:
                duplicates.add(emp_id)
            else:
                seen.add(emp_id)

        raise ValueError(f"Duplicate employee IDs found in batch: {list(duplicates)}")

    logger.info(f"Employee ID batch uniqueness validated: {len(employee_ids)} unique IDs")


def create_id_generator_from_config(
    config: OrchestrationConfig,
    base_year: Optional[int] = None,
    database_manager: Optional[DatabaseManager] = None
) -> UnifiedIDGenerator:
    """Create a UnifiedIDGenerator instance from orchestrator_dbt configuration.

    This factory function integrates with the orchestrator_dbt configuration
    system to provide consistent ID generation across the pipeline.

    Args:
        config: OrchestrationConfig instance
        base_year: Override base year (defaults to config or current year)
        database_manager: Optional database manager for validation

    Returns:
        Configured UnifiedIDGenerator instance
    """
    # Extract configuration values
    random_seed = getattr(config, 'random_seed', 42)
    if base_year is None:
        base_year = getattr(config, 'base_year', datetime.now().year)

    return UnifiedIDGenerator(
        random_seed=random_seed,
        base_year=base_year,
        database_manager=database_manager,
        enable_database_validation=True
    )


def create_id_generator_from_dict(
    config: Dict[str, Any],
    base_year: Optional[int] = None,
    database_manager: Optional[DatabaseManager] = None
) -> UnifiedIDGenerator:
    """Create UnifiedIDGenerator from dictionary config for backward compatibility.

    Args:
        config: Configuration dictionary (from simulation_config.yaml)
        base_year: Override base year (defaults to config or current year)
        database_manager: Optional database manager for validation

    Returns:
        Configured UnifiedIDGenerator instance
    """
    random_seed = config.get('random_seed', 42)
    if base_year is None:
        base_year = config.get('base_year', datetime.now().year)

    return UnifiedIDGenerator(
        random_seed=random_seed,
        base_year=base_year,
        database_manager=database_manager,
        enable_database_validation=True
    )
