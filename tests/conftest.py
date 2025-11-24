"""
Pytest Configuration for Fidelity PlanAlign Engine Testing
====================================================

Root conftest.py - delegates to tests/utils/ for reusable components.
"""

import warnings
import gc

import pytest

# Import shared utilities
from tests.utils import *


def pytest_configure(config):
    """Configure pytest with custom markers."""
    # Markers are defined in pyproject.toml
    pass


def pytest_collection_modifyitems(config, items):
    """Automatically add markers based on test location."""
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
    print("Fidelity PlanAlign Engine Testing Framework")
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
