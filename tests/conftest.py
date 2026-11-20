"""
Pytest Configuration for PlanAlign Engine Testing
====================================================

Root conftest.py - delegates to tests/utils/ for reusable components.
"""

import gc
import hashlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
import warnings

import duckdb
import pytest

from scripts import ci_policy as _ci_policy

# Register fixtures here for pytest auto-discovery so individual test modules
# don't need to import them (which would trigger F811 redefinition on the test
# parameters). Not referenced directly here, hence the noqa.
from tests.fixtures.config import (  # noqa: F401
    minimal_config,
    single_threaded_config,
    multi_threaded_config,
    golden_config,
    config_with_decimal_fields,
)
from tests.fixtures import (  # noqa: F401
    in_memory_db,
    populated_test_db,
    mock_dbt_runner,
    sample_employees,
    baseline_workforce_df,
    census_enrollment_rows,
    enrollment_history_rows,
)

pytest_plugins = ["tests.file_shards", "pytester"]

SHARED_DEV_DB = Path(__file__).resolve().parents[1] / "dbt" / "simulation.duckdb"
FileSignature = tuple[int, str] | None


def _file_signature(path: Path) -> FileSignature:
    """Return the file signature without opening DuckDB."""
    if not path.exists():
        return None
    return path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="session", autouse=True)
def shared_dev_database_guard() -> Iterator[FileSignature]:
    """Ensure no test writes to the shared development database."""
    before = _file_signature(SHARED_DEV_DB)
    yield before
    after = _file_signature(SHARED_DEV_DB)
    assert after == before, (
        "Tests modified the shared development database "
        f"{SHARED_DEV_DB}: before={before!r}, after={after!r}. "
        "Use an isolated database under tmp_path instead."
    )


def pytest_configure(config):
    """Configure pytest with custom markers."""
    # Markers are defined in pyproject.toml
    # Starlette's TestClient sends Host "testserver"; allow it for tests only.
    os.environ["PLANALIGN_API_ALLOWED_HOSTS"] = "localhost,127.0.0.1,::1,testserver"
    if os.environ.get("PYTEST_XDIST_WORKER"):
        _default_duckdb_to_one_thread()


def _default_duckdb_to_one_thread() -> None:
    """Stop xdist workers oversubscribing the CPU.

    DuckDB uses every core per connection by default, so four workers ran
    sixteen query threads on a four-vCPU runner. An explicit setting wins.
    """
    connect = duckdb.connect

    def single_threaded(
        database: object = ":memory:",
        read_only: bool = False,
        config: dict[str, Any] | None = None,
    ) -> duckdb.DuckDBPyConnection:
        return connect(database, read_only, {"threads": 1, **(config or {})})

    duckdb.connect = single_threaded


def _reject_simulation_suite_drift(items: list[pytest.Item]) -> None:
    """Fail collection when CI's simulation suite list disagrees with pytest.

    CI finds simulation suites by searching test files for the marker
    (scripts/ci_policy.py) and gives each its own runner. A marked test in a
    file the search misses would never run there, and a listed file with no
    marked test would fail its runner with "no tests collected". Simulations
    only run after merge, so catch both here, in every PR's fast suite.
    """
    seen = {item.nodeid.split("::")[0] for item in items}
    marked = {
        item.nodeid.split("::")[0]
        for item in items
        if any(item.get_closest_marker(m) for m in _ci_policy.SIMULATION_MARKERS)
    }
    listed = set(_ci_policy.simulation_suites())
    if unlisted := sorted(marked - listed):
        raise pytest.UsageError(
            "Simulation-marked tests that CI would not run. Put "
            f"pytest.mark.<marker> in a test_*.py file: {unlisted}"
        )
    if empty := sorted((listed & seen) - marked):
        raise pytest.UsageError(
            "Files that mention a simulation marker but have no marked test; "
            f"CI would give each an empty runner: {empty}"
        )


def pytest_collection_modifyitems(config, items):
    """Automatically add markers based on test location."""
    _reject_simulation_suite_drift(items)
    for item in items:
        # Add markers based on test file paths
        if "/unit/" in item.nodeid:
            item.add_marker(pytest.mark.unit)
            item.add_marker(pytest.mark.fast)  # Unit tests are fast by default
        elif "/integration/" in item.nodeid:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)
        elif "/e2e/" in item.nodeid:
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.very_slow)
        elif "/performance/" in item.nodeid:
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.slow)
        elif "/stress/" in item.nodeid:
            item.add_marker(pytest.mark.stress)
            item.add_marker(pytest.mark.very_slow)

        # Add feature area markers
        if "/events/" in item.nodeid:
            item.add_marker(pytest.mark.events)
        if "/orchestrator/" in item.nodeid:
            item.add_marker(pytest.mark.orchestrator)
        if "/cli/" in item.nodeid:
            item.add_marker(pytest.mark.cli)
        if "threading" in item.nodeid.lower():
            item.add_marker(pytest.mark.threading)
        if "config" in item.nodeid.lower():
            item.add_marker(pytest.mark.config)

        # Add database marker for tests requiring DB
        if "database" in item.nodeid or "dbt" in item.nodeid:
            item.add_marker(pytest.mark.database)


def pytest_runtest_setup(item):
    """Setup for each test run."""
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)


def pytest_runtest_teardown(item):
    """Teardown after each test run."""
    gc.collect()


def pytest_sessionstart(session):
    """Called at start of test session."""
    print("\n" + "=" * 80)
    print("PlanAlign Engine Testing Framework")
    print("=" * 80)
    print()


def pytest_sessionfinish(session, exitstatus):
    """Called at end of test session."""
    print("\n" + "=" * 80)
    print("Test Execution Summary")
    print("=" * 80)

    if hasattr(session, "testscollected"):
        print(f"Tests collected: {session.testscollected}")

    if exitstatus == 0:
        print("✓ All tests passed successfully")
    else:
        print(f"✗ Tests failed with exit status: {exitstatus}")

    print("=" * 80)
