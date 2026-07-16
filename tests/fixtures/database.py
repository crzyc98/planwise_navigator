"""In-memory database fixtures for fast unit tests."""

import duckdb
import pytest
from pathlib import Path
from typing import Generator


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
    conn.execute(
        """
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
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fct_workforce_snapshot (
            employee_id VARCHAR,
            simulation_year INTEGER NOT NULL,
            base_salary DOUBLE NOT NULL,
            enrollment_date DATE,
            scenario_id VARCHAR NOT NULL,
            plan_design_id VARCHAR NOT NULL,
            PRIMARY KEY (employee_id, simulation_year, scenario_id, plan_design_id)
        )
    """
    )

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
        in_memory_db.execute(
            f"""
            INSERT INTO fct_workforce_snapshot VALUES (
                'EMP{i:05d}', 2025, {50000 + (i * 500)}, NULL, 'test_scenario', 'test_plan'
            )
        """
        )

    # Insert sample events
    event_types = ["hire", "termination", "promotion"]
    for i in range(50):
        event_type = event_types[i % 3]
        in_memory_db.execute(
            f"""
            INSERT INTO fct_yearly_events VALUES (
                'EVT{i:05d}', 'EMP{i:05d}', '{event_type}',
                DATE '2025-01-01' + INTERVAL {i * 7} DAY,
                2025, 'test_scenario', 'test_plan', '{{}}'
            )
        """
        )

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


@pytest.fixture
def empty_database(tmp_path) -> Generator[Path, None, None]:
    """
    Empty database file for testing self-healing initialization.

    Creates a DuckDB database file with no tables, simulating
    a new workspace that needs initialization.

    Usage:
        @pytest.mark.fast
        @pytest.mark.unit
        def test_initialization_needed(empty_database):
            from planalign_orchestrator.self_healing import TableExistenceChecker
            # Checker should detect no required tables exist
            checker = TableExistenceChecker(db_manager)
            assert not checker.is_initialized()
    """
    db_path = tmp_path / "empty_simulation.duckdb"

    # Create empty database with just the main schema
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE SCHEMA IF NOT EXISTS main")
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def timeline_db(tmp_path) -> Generator[Path, None, None]:
    """Create a deterministic, isolated database for employee timeline tests."""
    db_path = tmp_path / "timeline.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE fct_yearly_events (
          event_id VARCHAR, employee_id VARCHAR, event_type VARCHAR,
          simulation_year INTEGER, effective_date DATE, event_sequence INTEGER,
          event_details VARCHAR, compensation_amount DOUBLE,
          previous_compensation DOUBLE, employee_deferral_rate DOUBLE,
          prev_employee_deferral_rate DOUBLE, level_id INTEGER
        );
        CREATE TABLE fct_employer_match_events (
          event_id VARCHAR, employee_id VARCHAR, event_type VARCHAR,
          simulation_year INTEGER, effective_date DATE, amount DOUBLE,
          employee_deferral_rate DOUBLE, event_payload JSON
        );
        CREATE TABLE fct_workforce_snapshot (
          employee_id VARCHAR, employee_ssn VARCHAR, employee_birth_date DATE,
          employee_hire_date DATE, simulation_year INTEGER,
          employment_status VARCHAR, detailed_status_code VARCHAR,
          current_compensation DOUBLE, prorated_annual_compensation DOUBLE,
          level_id INTEGER, current_age INTEGER, current_tenure DOUBLE,
          current_eligibility_status VARCHAR, is_enrolled_flag BOOLEAN,
          employee_enrollment_date DATE, current_deferral_rate DOUBLE,
          participation_status VARCHAR, total_deferral_escalations INTEGER,
          has_deferral_escalations BOOLEAN, ytd_contributions DOUBLE,
          pre_tax_contributions DOUBLE, roth_contributions DOUBLE,
          employer_match_amount DOUBLE, employer_core_amount DOUBLE,
          total_employer_contributions DOUBLE, irs_limit_reached BOOLEAN
        )
        """
    )
    conn.executemany(
        "INSERT INTO fct_yearly_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "e-hire",
                "EMP_A",
                "hire",
                2025,
                "2025-01-01",
                10,
                "Hired",
                80000,
                None,
                None,
                None,
                2,
            ),
            (
                "e-elig",
                "EMP_A",
                "eligibility",
                2025,
                "2025-01-01",
                20,
                "Eligible",
                None,
                None,
                None,
                None,
                None,
            ),
            (
                "e-enroll",
                "EMP_A",
                "enrollment",
                2025,
                "2025-02-01",
                30,
                "Enrolled",
                None,
                None,
                0.06,
                0,
                None,
            ),
            (
                "e-escalate",
                "EMP_A",
                "deferral_escalation",
                2026,
                "2026-01-01",
                40,
                "Escalated",
                None,
                None,
                0.07,
                0.06,
                None,
            ),
            (
                "e-raise",
                "EMP_A",
                "raise",
                2026,
                "2026-03-01",
                50,
                "Raised",
                84000,
                80000,
                None,
                None,
                2,
            ),
            (
                "e-term",
                "EMP_A",
                "termination",
                2027,
                "2027-06-01",
                60,
                "Terminated",
                None,
                None,
                None,
                None,
                None,
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO fct_employer_match_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                f"m-{year}",
                "EMP_A",
                "employer_match",
                year,
                f"{year}-12-31",
                2400 + year - 2025,
                0.06,
                "{}",
            )
            for year in (2025, 2026, 2027)
        ],
    )
    snapshot = """INSERT INTO fct_workforce_snapshot VALUES
      (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    conn.executemany(
        snapshot,
        [
            (
                "EMP_A",
                "***-**-0001",
                "1990-05-02",
                "2025-01-01",
                2025,
                "active",
                "active",
                80000,
                80000,
                2,
                35,
                1.0,
                "eligible",
                True,
                "2025-02-01",
                0.06,
                "participating",
                0,
                False,
                4800,
                4800,
                0,
                2400,
                800,
                3200,
                False,
            ),
            (
                "EMP_A",
                "***-**-0001",
                "1990-05-02",
                "2025-01-01",
                2026,
                "active",
                "active",
                84000,
                84000,
                2,
                36,
                2.0,
                "eligible",
                True,
                "2025-02-01",
                0.07,
                "participating",
                1,
                True,
                5880,
                5880,
                0,
                2401,
                840,
                3241,
                False,
            ),
            (
                "EMP_B",
                "***-**-0002",
                "1985-03-04",
                "2020-01-01",
                2025,
                "active",
                "active",
                70000,
                70000,
                1,
                40,
                5.0,
                "eligible",
                False,
                None,
                0,
                "not_participating",
                0,
                False,
                0,
                0,
                0,
                0,
                700,
                700,
                False,
            ),
            (
                "EMP_B",
                "***-**-0002",
                "1985-03-04",
                "2020-01-01",
                2026,
                "terminated",
                "terminated",
                70000,
                35000,
                1,
                41,
                6.0,
                "eligible",
                False,
                None,
                0,
                "not_participating",
                0,
                False,
                0,
                0,
                0,
                0,
                350,
                350,
                False,
            ),
        ],
    )
    conn.close()
    yield db_path
