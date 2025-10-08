"""
Shared Test Fixtures for PlanWise Navigator

This package contains reusable test fixtures organized by category:
- database.py: In-memory database fixtures for fast unit tests
- config.py: Configuration fixtures for simulation testing
- mock_dbt.py: Mock dbt runner and result fixtures
- workforce_data.py: Test data generators for workforce simulations
"""

from .database import (
    in_memory_db,
    populated_test_db,
    isolated_test_db,
)
from .config import (
    minimal_config,
    single_threaded_config,
    multi_threaded_config,
)
from .mock_dbt import (
    mock_dbt_runner,
    failing_dbt_runner,
    mock_dbt_result,
)
from .workforce_data import (
    sample_employees,
    baseline_workforce_df,
    sample_yearly_events,
)

__all__ = [
    # Database fixtures
    "in_memory_db",
    "populated_test_db",
    "isolated_test_db",

    # Configuration fixtures
    "minimal_config",
    "single_threaded_config",
    "multi_threaded_config",

    # Mock dbt fixtures
    "mock_dbt_runner",
    "failing_dbt_runner",
    "mock_dbt_result",

    # Workforce data fixtures
    "sample_employees",
    "baseline_workforce_df",
    "sample_yearly_events",
]
