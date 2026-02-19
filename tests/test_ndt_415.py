"""Tests for NDT Section 415 Annual Additions Limit Test."""

import duckdb
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from planalign_api.services.ndt_service import (
    NDTService,
    Section415ScenarioResult,
)
from planalign_api.services.database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
)


# ==============================================================================
# Fixtures
# ==============================================================================


def _create_test_db(conn: duckdb.DuckDBPyConnection):
    """Populate an in-memory DuckDB connection with test tables for 415 test."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_irs_limits (
            limit_year INTEGER,
            base_limit INTEGER,
            catch_up_limit INTEGER,
            catch_up_age_threshold INTEGER,
            compensation_limit INTEGER,
            hce_compensation_threshold INTEGER,
            super_catch_up_limit INTEGER,
            super_catch_up_age_min INTEGER,
            super_catch_up_age_max INTEGER,
            is_estimated BOOLEAN,
            annual_additions_limit INTEGER
        )
    """)
    conn.execute("""
        INSERT INTO config_irs_limits VALUES
        (2024, 23000, 30500, 50, 345000, 155000, 30500, 60, 63, false, 69000),
        (2025, 23500, 31000, 50, 350000, 160000, 34750, 60, 63, false, 70000)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS fct_workforce_snapshot (
            employee_id VARCHAR,
            simulation_year INTEGER,
            current_compensation DOUBLE,
            prorated_annual_compensation DOUBLE,
            prorated_annual_contributions DOUBLE,
            employer_match_amount DOUBLE,
            employer_core_amount DOUBLE,
            current_eligibility_status VARCHAR,
            is_enrolled_flag BOOLEAN,
            employment_status VARCHAR,
            current_tenure DOUBLE
        )
    """)


def _insert_employee(
    conn,
    employee_id: str,
    year: int,
    compensation: float,
    prorated_comp: float,
    contributions: float = 0.0,
    match_amount: float = 0.0,
    core_amount: float = 0.0,
    eligibility: str = "eligible",
    enrolled: bool = True,
    status: str = "active",
    tenure: float = 5.0,
):
    conn.execute(
        """INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [employee_id, year, compensation, prorated_comp, contributions,
         match_amount, core_amount, eligibility, enrolled, status, tenure],
    )


class MockStorage:
    """Mock WorkspaceStorage for testing."""

    def _workspace_path(self, workspace_id: str) -> Path:
        return Path("/mock/workspaces") / workspace_id

    def _scenario_path(self, workspace_id: str, scenario_id: str) -> Path:
        return Path("/mock/workspaces") / workspace_id / "scenarios" / scenario_id


@pytest.fixture
def service_with_db():
    """Create an NDTService with an in-memory DuckDB database."""
    conn = duckdb.connect(":memory:")
    _create_test_db(conn)

    storage = MockStorage()
    mock_resolver = MagicMock(spec=DatabasePathResolver)

    service = NDTService(storage, db_resolver=mock_resolver)
    service._ensure_seed_current = MagicMock()
    return service, conn, mock_resolver


# ==============================================================================
# Test 1: No breaches - all under limit
# ==============================================================================


class TestNoBreaches:
    """All participants under 415 limit, test passes."""

    def test_no_breaches_passes(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # Employee with total additions well under $70K limit
        # base deferrals = min(20000, 23500) = 20000
        # total = 20000 + 5000 (match) + 3000 (nec) = 28000
        _insert_employee(conn, "EMP1", 2025, 150000.0, 150000.0,
                         contributions=20000.0, match_amount=5000.0,
                         core_amount=3000.0, tenure=5.0)
        _insert_employee(conn, "EMP2", 2025, 100000.0, 100000.0,
                         contributions=15000.0, match_amount=3000.0,
                         core_amount=2000.0, tenure=3.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "pass"
        assert result.breach_count == 0
        assert result.passing_count == 2


# ==============================================================================
# Test 2: Breach via IRS dollar limit
# ==============================================================================


class TestBreachDollarLimit:
    """Participant with total additions exceeding IRS 415 dollar limit."""

    def test_breach_dollar_limit(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # Use 2024 limits: annual_additions_limit = $69,000
        # base deferrals = min(23000, 23000) = 23000
        # match = 30000, nec = 20000 -> total = 73000 > 69000
        _insert_employee(conn, "BREACH1", 2024, 250000.0, 250000.0,
                         contributions=23000.0, match_amount=30000.0,
                         core_amount=20000.0, tenure=10.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2024)

        assert result.test_result == "fail"
        assert result.breach_count == 1


# ==============================================================================
# Test 3: Breach via 100% comp rule
# ==============================================================================


class TestBreachCompRule:
    """Participant earning $60K with $65K total additions, applicable limit is $60K."""

    def test_breach_100_pct_comp(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # Employee earns $60K (< $70K IRS limit), so applicable limit = $60K
        # base deferrals = min(23500, 23500) = 23500
        # match = 20000, nec = 21500 -> total = 65000 > 60000
        _insert_employee(conn, "LOW_COMP1", 2025, 60000.0, 60000.0,
                         contributions=23500.0, match_amount=20000.0,
                         core_amount=21500.0, tenure=8.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2025,
                                          include_employees=True)

        assert result.test_result == "fail"
        assert result.breach_count == 1
        # Verify the applicable limit used was $60K (100% of comp) not $70K
        emp = result.employees[0]
        assert abs(emp.applicable_limit - 60000.0) < 0.01
        assert emp.headroom < 0  # Negative headroom = breach


# ==============================================================================
# Test 4: At-risk flagging
# ==============================================================================


class TestAtRiskFlagging:
    """Participant at 96% utilization with default 95% threshold."""

    def test_at_risk_with_default_threshold(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # 96% of $70K = $67,200
        # base deferrals = min(23500, 23500) = 23500
        # match = 23700, nec = 20000 -> total = 67200
        _insert_employee(conn, "ATRISK1", 2025, 200000.0, 200000.0,
                         contributions=23500.0, match_amount=23700.0,
                         core_amount=20000.0, tenure=10.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2025,
                                          include_employees=True)

        assert result.test_result == "pass"  # Not a breach
        assert result.at_risk_count == 1
        emp = result.employees[0]
        assert emp.status == "at_risk"
        assert emp.utilization_pct >= 0.95


# ==============================================================================
# Test 5: Custom warning threshold
# ==============================================================================


class TestCustomThreshold:
    """warning_threshold=0.90 flags participants at 91% utilization."""

    def test_custom_warning_threshold(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # 91% of $70K = $63,700
        # base deferrals = min(23500, 23500) = 23500
        # match = 20200, nec = 20000 -> total = 63700
        _insert_employee(conn, "ATRISK_90", 2025, 200000.0, 200000.0,
                         contributions=23500.0, match_amount=20200.0,
                         core_amount=20000.0, tenure=10.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2025,
                                          warning_threshold=0.90,
                                          include_employees=True)

        assert result.at_risk_count == 1
        assert result.warning_threshold_pct == 0.90
        emp = result.employees[0]
        assert emp.status == "at_risk"


# ==============================================================================
# Test 6: Threshold at 100%
# ==============================================================================


class TestThresholdAt100:
    """Only actual breaches flagged, no at-risk."""

    def test_threshold_100_no_at_risk(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # 96% utilization - should be "pass" not "at_risk" with 100% threshold
        _insert_employee(conn, "HIGH_UTIL", 2025, 200000.0, 200000.0,
                         contributions=23500.0, match_amount=23700.0,
                         core_amount=20000.0, tenure=10.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2025,
                                          warning_threshold=1.0,
                                          include_employees=True)

        assert result.at_risk_count == 0
        emp = result.employees[0]
        assert emp.status == "pass"


# ==============================================================================
# Test 7: Catch-up exclusion
# ==============================================================================


class TestCatchUpExclusion:
    """Base deferrals capped at base_limit for 415 calculation."""

    def test_catch_up_excluded(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # Employee contributes $31000 (includes catch-up)
        # base_limit for 2025 = $23500
        # base deferrals = min(31000, 23500) = 23500
        # total = 23500 + 5000 + 3000 = 31500
        _insert_employee(conn, "CATCHUP1", 2025, 200000.0, 200000.0,
                         contributions=31000.0, match_amount=5000.0,
                         core_amount=3000.0, tenure=10.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2025,
                                          include_employees=True)

        emp = result.employees[0]
        # Base deferrals should be capped at 23500, not 31000
        assert abs(emp.employee_deferrals - 23500.0) < 0.01
        assert abs(emp.total_annual_additions - 31500.0) < 0.01


# ==============================================================================
# Test 8: Plan-level summary
# ==============================================================================


class TestPlanLevelSummary:
    """Overall fail if any breach, counts correct."""

    def test_plan_summary_with_breach(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # One passing employee
        _insert_employee(conn, "PASS1", 2025, 200000.0, 200000.0,
                         contributions=10000.0, match_amount=5000.0,
                         core_amount=3000.0, tenure=5.0)
        # One breaching employee (total > 70K)
        _insert_employee(conn, "BREACH1", 2025, 250000.0, 250000.0,
                         contributions=23500.0, match_amount=30000.0,
                         core_amount=20000.0, tenure=10.0)
        # One at-risk employee (96% util)
        _insert_employee(conn, "ATRISK1", 2025, 200000.0, 200000.0,
                         contributions=23500.0, match_amount=23700.0,
                         core_amount=20000.0, tenure=8.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "fail"
        assert result.total_participants == 3
        assert result.breach_count == 1
        assert result.at_risk_count == 1
        assert result.passing_count == 1


# ==============================================================================
# Test 9: Edge case - zero compensation excluded
# ==============================================================================


class TestZeroCompExcluded415:
    """Zero compensation employees excluded from 415 test."""

    def test_zero_comp_excluded(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "NORMAL1", 2025, 100000.0, 100000.0,
                         contributions=10000.0, match_amount=5000.0,
                         core_amount=3000.0, tenure=5.0)
        # Zero comp employee
        _insert_employee(conn, "ZERO1", 2025, 0.0, 0.0,
                         contributions=0.0, match_amount=0.0,
                         core_amount=0.0, tenure=1.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2025)

        assert result.total_participants == 1
        assert result.excluded_count >= 1


# ==============================================================================
# Test 10: Edge case - missing IRS limits year
# ==============================================================================


class TestMissingIRSLimits:
    """Missing IRS limits year returns error."""

    def test_missing_limits_year(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "EMP1", 2030, 100000.0, 100000.0,
                         contributions=10000.0, match_amount=5000.0,
                         core_amount=3000.0, tenure=5.0)

        # Remove all limits
        conn.execute("DELETE FROM config_irs_limits")

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_415_test("ws1", "sc1", "Test", 2030)

        assert result.test_result == "error"
        assert result.test_message is not None
