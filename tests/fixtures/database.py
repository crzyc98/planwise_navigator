"""In-memory database fixtures for fast unit tests."""

import duckdb
import pytest
from pathlib import Path
from typing import Generator
import tempfile


@pytest.fixture
def in_memory_db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """
    Create in-memory DuckDB database with minimal schema.

    Provides ultra-fast database for unit tests without disk I/O.
    Setup time: <0.01s

    Usage:
        @pytest.mark.fast
        @pytest.mark.unit
        def test_query(in_memory_db):
            result = in_memory_db.execute("SELECT 1").fetchone()
            assert result[0] == 1
    """
    conn = duckdb.connect(":memory:")

    # Create minimal schema for testing
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fct_yearly_events (
            event_id VARCHAR PRIMARY KEY,
            employee_id VARCHAR NOT NULL,
            event_type VARCHAR NOT NULL,
            event_date DATE NOT NULL,
            simulation_year INTEGER NOT NULL,
            scenario_id VARCHAR NOT NULL,
            plan_design_id VARCHAR NOT NULL,
            payload JSON
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS fct_workforce_snapshot (
            employee_id VARCHAR,
            simulation_year INTEGER NOT NULL,
            base_salary DOUBLE NOT NULL,
            enrollment_date DATE,
            scenario_id VARCHAR NOT NULL,
            plan_design_id VARCHAR NOT NULL,
            PRIMARY KEY (employee_id, simulation_year, scenario_id, plan_design_id)
        )
    """)

    yield conn
    conn.close()


@pytest.fixture
def populated_test_db(in_memory_db) -> duckdb.DuckDBPyConnection:
    """
    In-memory database with sample test data.

    Contains:
    - 100 sample employees in workforce snapshot
    - 50 sample events (hire/termination/promotion)

    Usage:
        @pytest.mark.fast
        @pytest.mark.unit
        def test_event_count(populated_test_db):
            result = populated_test_db.execute(
                "SELECT COUNT(*) FROM fct_yearly_events"
            ).fetchone()
            assert result[0] == 50
    """
    # Insert sample workforce data
    for i in range(100):
        in_memory_db.execute(f"""
            INSERT INTO fct_workforce_snapshot VALUES (
                'EMP{i:05d}', 2025, {50000 + (i * 500)}, NULL, 'test_scenario', 'test_plan'
            )
        """)

    # Insert sample events
    event_types = ['hire', 'termination', 'promotion']
    for i in range(50):
        event_type = event_types[i % 3]
        in_memory_db.execute(f"""
            INSERT INTO fct_yearly_events VALUES (
                'EVT{i:05d}', 'EMP{i:05d}', '{event_type}',
                DATE '2025-01-01' + INTERVAL {i * 7} DAY,
                2025, 'test_scenario', 'test_plan', '{{}}'
            )
        """)

    return in_memory_db


@pytest.fixture
def isolated_test_db(tmp_path) -> Generator[Path, None, None]:
    """
    Isolated file-based test database with automatic cleanup.

    Creates temporary DuckDB file for integration tests that need
    persistence across operations.

    Usage:
        @pytest.mark.integration
        def test_with_file_db(isolated_test_db):
            conn = duckdb.connect(str(isolated_test_db))
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.close()
    """
    db_path = tmp_path / "test_simulation.duckdb"

    # Initialize database
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE SCHEMA IF NOT EXISTS main")
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()
