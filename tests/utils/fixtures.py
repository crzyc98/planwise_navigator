"""Shared test fixtures."""

import tempfile
import shutil
import time
from pathlib import Path
from typing import Generator

import pytest
import numpy as np
import pandas as pd
import psutil

from planalign_orchestrator.config import get_database_path

# Re-export config fixtures for pytest discovery
from tests.fixtures.config import (
    minimal_config,
    single_threaded_config,
    multi_threaded_config,
    golden_config,
)


@pytest.fixture(scope="session")
def test_database() -> Generator[Path, None, None]:
    """Create isolated test database for production tests."""
    prod_db = get_database_path()
    backup_db = prod_db.parent / "simulation_backup.duckdb"

    if prod_db.exists():
        shutil.copy(prod_db, backup_db)

    yield prod_db

    if backup_db.exists():
        shutil.move(backup_db, prod_db)


@pytest.fixture
def temp_directory() -> Generator[Path, None, None]:
    """Provide temporary directory for test files."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_workforce_data() -> pd.DataFrame:
    """Generate sample workforce data for testing."""
    np.random.seed(42)

    data = []
    for i in range(1000):
        employee = {
            "employee_id": f"EMP_{i:06d}",
            "job_level": np.random.choice([1, 2, 3, 4, 5], p=[0.4, 0.3, 0.2, 0.08, 0.02]),
            "current_compensation": max(35000, np.random.normal(65000, 15000)),
            "years_of_service": max(0, np.random.exponential(5)),
            "department": np.random.choice(["Engineering", "Finance", "HR", "Sales", "Marketing"]),
            "performance_rating": np.random.choice([1, 2, 3, 4, 5], p=[0.05, 0.15, 0.6, 0.15, 0.05]),
        }

        # Adjust compensation by level
        level_multipliers = {1: 0.8, 2: 1.0, 3: 1.4, 4: 2.0, 5: 3.0}
        employee["current_compensation"] *= level_multipliers[employee["job_level"]]

        data.append(employee)

    return pd.DataFrame(data)


@pytest.fixture
def performance_tracker():
    """Track test performance metrics."""

    class PerformanceTracker:
        def __init__(self):
            self.start_time = None
            self.start_memory = None
            self.metrics = {}

        def start(self):
            self.start_time = time.time()
            self.start_memory = psutil.Process().memory_info().rss / 1024 / 1024

        def stop(self):
            if self.start_time is None:
                raise ValueError("Tracker not started")

            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024

            self.metrics = {
                "execution_time": end_time - self.start_time,
                "memory_delta": end_memory - self.start_memory,
                "peak_memory": end_memory,
            }

            return self.metrics

        def assert_performance(self, max_time=None, max_memory=None):
            if max_time and self.metrics["execution_time"] > max_time:
                pytest.fail(
                    f"Execution time {self.metrics['execution_time']:.2f}s "
                    f"exceeds limit {max_time}s"
                )

            if max_memory and self.metrics["memory_delta"] > max_memory:
                pytest.fail(
                    f"Memory usage {self.metrics['memory_delta']:.1f}MB "
                    f"exceeds limit {max_memory}MB"
                )

    return PerformanceTracker()


@pytest.fixture(scope="session")
def benchmark_baseline():
    """Performance benchmarks for comparison."""
    return {
        "parameter_validation": {"max_time": 0.1, "max_memory": 10.0},
        "event_creation": {"max_time": 0.01, "max_memory": 5.0},
        "optimization_execution": {"max_time": 5.0, "max_memory": 100.0},
        "simulation_single_year": {"max_time": 30.0, "max_memory": 200.0},
    }
