"""
Simulation state management for multi-year orchestration.

Provides efficient state management with compression, caching, and persistence
for multi-year workforce simulations. Implements memory-efficient patterns
for handling large workforce datasets across multiple simulation years.
"""

from __future__ import annotations

import pickle
import lz4
import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Union, Protocol
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

from ..core.database_manager import DatabaseManager
from ..core.config import OrchestrationConfig


logger = logging.getLogger(__name__)


@dataclass
class WorkforceRecord:
    """Individual workforce record with comprehensive employee data."""
    employee_id: str
    hire_date: date
    termination_date: Optional[date] = None
    job_level: str = ""
    salary: float = 0.0
    department: str = ""
    location: str = ""
    age: int = 0
    tenure_years: float = 0.0
    is_active: bool = True

    # Plan participation data
    plan_eligible: bool = False
    plan_enrolled: bool = False
    enrollment_date: Optional[date] = None
    contribution_rate: float = 0.0

    # Metadata
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for serialization."""
        return {
            "employee_id": self.employee_id,
            "hire_date": self.hire_date.isoformat() if self.hire_date else None,
            "termination_date": self.termination_date.isoformat() if self.termination_date else None,
            "job_level": self.job_level,
            "salary": self.salary,
            "department": self.department,
            "location": self.location,
            "age": self.age,
            "tenure_years": self.tenure_years,
            "is_active": self.is_active,
            "plan_eligible": self.plan_eligible,
            "plan_enrolled": self.plan_enrolled,
            "enrollment_date": self.enrollment_date.isoformat() if self.enrollment_date else None,
            "contribution_rate": self.contribution_rate,
            "last_updated": self.last_updated.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkforceRecord:
        """Create record from dictionary."""
        return cls(
            employee_id=data["employee_id"],
            hire_date=date.fromisoformat(data["hire_date"]) if data.get("hire_date") else None,
            termination_date=date.fromisoformat(data["termination_date"]) if data.get("termination_date") else None,
            job_level=data.get("job_level", ""),
            salary=data.get("salary", 0.0),
            department=data.get("department", ""),
            location=data.get("location", ""),
            age=data.get("age", 0),
            tenure_years=data.get("tenure_years", 0.0),
            is_active=data.get("is_active", True),
            plan_eligible=data.get("plan_eligible", False),
            plan_enrolled=data.get("plan_enrolled", False),
            enrollment_date=date.fromisoformat(data["enrollment_date"]) if data.get("enrollment_date") else None,
            contribution_rate=data.get("contribution_rate", 0.0),
            last_updated=datetime.fromisoformat(data.get("last_updated", datetime.utcnow().isoformat()))
        )


@dataclass
class WorkforceState:
    """Complete workforce state for a simulation year."""
    year: int
    workforce_records: List[WorkforceRecord] = field(default_factory=list)
    total_active_employees: int = 0
    total_enrolled_employees: int = 0
    total_payroll: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Calculate derived metrics after initialization."""
        self.update_metrics()

    def update_metrics(self) -> None:
        """Update derived metrics from workforce records."""
        active_records = [r for r in self.workforce_records if r.is_active]

        self.total_active_employees = len(active_records)
        self.total_enrolled_employees = sum(1 for r in active_records if r.plan_enrolled)
        self.total_payroll = sum(r.salary for r in active_records)

    def get_active_workforce(self) -> List[WorkforceRecord]:
        """Get list of active workforce records."""
        return [r for r in self.workforce_records if r.is_active]

    def get_enrolled_workforce(self) -> List[WorkforceRecord]:
        """Get list of plan-enrolled workforce records."""
        return [r for r in self.workforce_records if r.is_active and r.plan_enrolled]

    def to_dataframe(self) -> pd.DataFrame:
        """Convert workforce state to pandas DataFrame."""
        if not self.workforce_records:
            return pd.DataFrame()

        return pd.DataFrame([record.to_dict() for record in self.workforce_records])

    @classmethod
    def from_dataframe(cls, year: int, df: pd.DataFrame) -> WorkforceState:
        """Create workforce state from pandas DataFrame."""
        records = [WorkforceRecord.from_dict(row.to_dict()) for _, row in df.iterrows()]
        return cls(year=year, workforce_records=records)


@dataclass
class CompressedState:
    """Compressed simulation state for memory efficiency."""
    data: bytes
    original_size: int
    compressed_size: int
    compression_ratio: float
    created_at: datetime = field(default_factory=datetime.utcnow)


class StateCompression:
    """Handles state compression and decompression operations."""

    def __init__(self, compression_level: int = 6):
        """
        Initialize state compression.

        Args:
            compression_level: LZ4 compression level (1-12, higher = better compression)
        """
        self.compression_level = compression_level

    def compress_state(self, state: WorkforceState) -> CompressedState:
        """
        Compress workforce state for memory efficiency.

        Args:
            state: Workforce state to compress

        Returns:
            Compressed state with metadata
        """
        try:
            # Serialize state to bytes
            serialized = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
            original_size = len(serialized)

            # Compress using LZ4
            compressed = lz4.compress(serialized, compression_level=self.compression_level)
            compressed_size = len(compressed)

            compression_ratio = compressed_size / original_size if original_size > 0 else 1.0

            logger.debug(f"Compressed state: {original_size} -> {compressed_size} bytes "
                        f"({compression_ratio:.2%} ratio)")

            return CompressedState(
                data=compressed,
                original_size=original_size,
                compressed_size=compressed_size,
                compression_ratio=compression_ratio
            )

        except Exception as e:
            logger.error(f"State compression failed: {e}")
            raise StateCompressionError(f"Failed to compress state: {e}") from e

    def decompress_state(self, compressed_state: CompressedState) -> WorkforceState:
        """
        Decompress workforce state.

        Args:
            compressed_state: Compressed state to decompress

        Returns:
            Decompressed workforce state
        """
        try:
            # Decompress data
            decompressed = lz4.decompress(compressed_state.data)

            # Deserialize state
            state = pickle.loads(decompressed)

            logger.debug(f"Decompressed state: {compressed_state.compressed_size} -> "
                        f"{compressed_state.original_size} bytes")

            return state

        except Exception as e:
            logger.error(f"State decompression failed: {e}")
            raise StateCompressionError(f"Failed to decompress state: {e}") from e


class StateManager:
    """
    Manages simulation state with caching, compression, and persistence.

    Provides memory-efficient state management for multi-year simulations
    with automatic compression and LRU caching.
    """

    def __init__(
        self,
        config: OrchestrationConfig,
        database_manager: DatabaseManager,
        cache_size: int = 100,
        enable_compression: bool = True,
        compression_level: int = 6
    ):
        """
        Initialize state manager.

        Args:
            config: Orchestration configuration
            database_manager: Database manager for persistence
            cache_size: Maximum number of states to cache in memory
            enable_compression: Whether to enable state compression
            compression_level: LZ4 compression level (1-12)
        """
        self.config = config
        self.database_manager = database_manager
        self.cache_size = cache_size
        self.enable_compression = enable_compression

        # Initialize compression
        self.compressor = StateCompression(compression_level)

        # Initialize LRU cache for states
        self._state_cache: Dict[int, Union[WorkforceState, CompressedState]] = {}
        self._access_order: List[int] = []

        # Performance metrics
        self._cache_hits = 0
        self._cache_misses = 0
        self._compression_savings = 0

        logger.info(f"StateManager initialized: cache_size={cache_size}, "
                   f"compression={'enabled' if enable_compression else 'disabled'}")

    def store_year_state(self, year: int, state: WorkforceState) -> None:
        """
        Store workforce state for a specific year.

        Args:
            year: Simulation year
            state: Workforce state to store
        """
        try:
            # Update state metrics before storing
            state.update_metrics()

            # Compress state if enabled
            if self.enable_compression:
                compressed_state = self.compressor.compress_state(state)
                self._store_in_cache(year, compressed_state)
                self._compression_savings += (compressed_state.original_size -
                                            compressed_state.compressed_size)
            else:
                self._store_in_cache(year, state)

            logger.debug(f"Stored state for year {year}: {state.total_active_employees} employees")

        except Exception as e:
            logger.error(f"Failed to store state for year {year}: {e}")
            raise StateManagerError(f"Failed to store state for year {year}: {e}") from e

    def get_year_state(self, year: int) -> Optional[WorkforceState]:
        """
        Retrieve workforce state for a specific year.

        Args:
            year: Simulation year

        Returns:
            Workforce state or None if not found
        """
        try:
            # Check cache first
            cached_state = self._get_from_cache(year)

            if cached_state is not None:
                self._cache_hits += 1

                # Decompress if needed
                if isinstance(cached_state, CompressedState):
                    return self.compressor.decompress_state(cached_state)
                else:
                    return cached_state

            # Cache miss - try to load from database
            self._cache_misses += 1
            state = self._load_from_database(year)

            if state is not None:
                # Store in cache for future access
                self.store_year_state(year, state)

            return state

        except Exception as e:
            logger.error(f"Failed to retrieve state for year {year}: {e}")
            raise StateManagerError(f"Failed to retrieve state for year {year}: {e}") from e

    def clear_year_state(self, year: int) -> bool:
        """
        Clear state for a specific year from cache and database.

        Args:
            year: Simulation year to clear

        Returns:
            True if state was cleared successfully
        """
        try:
            # Remove from cache
            if year in self._state_cache:
                del self._state_cache[year]
                if year in self._access_order:
                    self._access_order.remove(year)

            # Remove from database
            self._delete_from_database(year)

            logger.debug(f"Cleared state for year {year}")
            return True

        except Exception as e:
            logger.error(f"Failed to clear state for year {year}: {e}")
            return False

    def get_cached_years(self) -> List[int]:
        """Get list of years currently cached in memory."""
        return list(self._state_cache.keys())

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get state manager performance metrics."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
            "cached_years": len(self._state_cache),
            "cache_size_limit": self.cache_size,
            "compression_enabled": self.enable_compression,
            "compression_savings_bytes": self._compression_savings,
            "memory_efficiency": f"{self._compression_savings / 1024 / 1024:.1f} MB saved"
        }

    def _store_in_cache(self, year: int, state: Union[WorkforceState, CompressedState]) -> None:
        """Store state in LRU cache with size management."""
        # Remove from access order if already exists
        if year in self._access_order:
            self._access_order.remove(year)

        # Add to end of access order (most recent)
        self._access_order.append(year)

        # Store in cache
        self._state_cache[year] = state

        # Enforce cache size limit
        while len(self._state_cache) > self.cache_size:
            # Remove least recently used item
            oldest_year = self._access_order.pop(0)
            if oldest_year in self._state_cache:
                del self._state_cache[oldest_year]

    def _get_from_cache(self, year: int) -> Optional[Union[WorkforceState, CompressedState]]:
        """Retrieve state from cache and update access order."""
        if year not in self._state_cache:
            return None

        # Update access order (move to end)
        if year in self._access_order:
            self._access_order.remove(year)
        self._access_order.append(year)

        return self._state_cache[year]

    def _load_from_database(self, year: int) -> Optional[WorkforceState]:
        """Load state from database (placeholder for actual implementation)."""
        # This would be implemented to load from DuckDB tables
        # For now, return None to indicate no persistent storage
        logger.debug(f"Database loading not implemented for year {year}")
        return None

    def _delete_from_database(self, year: int) -> None:
        """Delete state from database (placeholder for actual implementation)."""
        # This would be implemented to delete from DuckDB tables
        logger.debug(f"Database deletion not implemented for year {year}")
        pass


@dataclass
class SimulationState:
    """
    Complete simulation state across all years.

    Manages the overall simulation state including configuration,
    year-specific workforce states, and simulation metadata.
    """
    simulation_id: str
    start_year: int
    end_year: int
    current_year: int
    year_states: Dict[int, WorkforceState] = field(default_factory=dict)
    configuration: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def get_year_range(self) -> range:
        """Get range of simulation years."""
        return range(self.start_year, self.end_year + 1)

    def get_completed_years(self) -> List[int]:
        """Get list of completed simulation years."""
        return sorted(self.year_states.keys())

    def get_remaining_years(self) -> List[int]:
        """Get list of remaining simulation years."""
        completed = set(self.year_states.keys())
        all_years = set(self.get_year_range())
        return sorted(all_years - completed)

    def is_complete(self) -> bool:
        """Check if simulation is complete for all years."""
        return len(self.year_states) == (self.end_year - self.start_year + 1)

    def get_progress_percentage(self) -> float:
        """Get simulation progress as percentage."""
        total_years = self.end_year - self.start_year + 1
        completed_years = len(self.year_states)
        return (completed_years / total_years) * 100.0 if total_years > 0 else 0.0

    def update_timestamp(self) -> None:
        """Update the last_updated timestamp."""
        self.last_updated = datetime.utcnow()


# Custom exceptions
class StateManagerError(Exception):
    """Base exception for state manager errors."""
    pass


class StateCompressionError(StateManagerError):
    """Exception for state compression/decompression errors."""
    pass


class StatePersistenceError(StateManagerError):
    """Exception for state persistence errors."""
    pass


# Protocols for type hints
class StateManagerProtocol(Protocol):
    """Protocol defining state manager interface."""

    def store_year_state(self, year: int, state: WorkforceState) -> None:
        """Store workforce state for a year."""
        ...

    def get_year_state(self, year: int) -> Optional[WorkforceState]:
        """Retrieve workforce state for a year."""
        ...

    def clear_year_state(self, year: int) -> bool:
        """Clear state for a year."""
        ...
