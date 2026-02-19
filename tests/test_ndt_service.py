"""Tests for NDT (Non-Discrimination Testing) service."""

import duckdb
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from planalign_api.services.ndt_service import NDTService, ACPScenarioResult
from planalign_api.services.database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
)


# ==============================================================================
# Fixtures
# ==============================================================================


def _create_test_db(conn: duckdb.DuckDBPyConnection, year: int = 2025):
    """Populate an in-memory DuckDB connection with test tables."""
    # IRS limits seed
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_irs_limits (
            limit_year INTEGER,
            base_limit INTEGER,
            catch_up_limit INTEGER,
            catch_up_age_threshold INTEGER,
            compensation_limit INTEGER,
            hce_compensation_threshold INTEGER
        )
    """)
    conn.execute("""
        INSERT INTO config_irs_limits VALUES
        (2024, 23000, 30500, 50, 345000, 155000),
        (2025, 23500, 31000, 50, 350000, 160000),
        (2026, 24000, 32000, 50, 360000, 165000)
    """)

    # Workforce snapshot
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fct_workforce_snapshot (
            employee_id VARCHAR,
            simulation_year INTEGER,
            current_compensation DOUBLE,
            prorated_annual_compensation DOUBLE,
            employer_match_amount DOUBLE,
            current_eligibility_status VARCHAR,
            is_enrolled_flag BOOLEAN,
            employment_status VARCHAR
        )
    """)


def _insert_employee(
    conn,
    employee_id: str,
    year: int,
    compensation: float,
    prorated_comp: float,
    match_amount: float,
    eligibility: str = "eligible",
    enrolled: bool = True,
    status: str = "active",
):
    conn.execute(
        """INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [employee_id, year, compensation, prorated_comp, match_amount, eligibility, enrolled, status],
    )


class MockStorage:
    """Mock WorkspaceStorage for testing."""

    def _workspace_path(self, workspace_id: str) -> Path:
        return Path("/mock/workspaces") / workspace_id

    def _scenario_path(self, workspace_id: str, scenario_id: str) -> Path:
        return Path("/mock/workspaces") / workspace_id / "scenarios" / scenario_id


@pytest.fixture
def mock_storage():
    return MockStorage()


@pytest.fixture
def service_with_db():
    """Create an NDTService with an in-memory DuckDB database."""
    conn = duckdb.connect(":memory:")
    _create_test_db(conn)

    storage = MockStorage()
    mock_resolver = MagicMock(spec=DatabasePathResolver)

    # We'll patch the duckdb.connect call in the service to return our in-memory conn
    service = NDTService(storage, db_resolver=mock_resolver)
    # Patch _ensure_seed_current since test DBs already have correct schema
    # and in-memory connections can't be shared across duckdb.connect calls
    service._ensure_seed_current = MagicMock()
    return service, conn, mock_resolver


# ==============================================================================
# Test: HCE Classification
# ==============================================================================


class TestHCEClassification:
    """Test correct HCE classification based on prior-year comp vs threshold."""

    def test_hce_above_threshold(self, service_with_db):
        """Employee with prior-year comp above threshold is classified as HCE."""
        service, conn, mock_resolver = service_with_db

        # Prior year (2024): high comp employee
        _insert_employee(conn, "EMP001", 2024, 200000.0, 200000.0, 0.0)
        # Current year (2025): same employee
        _insert_employee(conn, "EMP001", 2025, 210000.0, 210000.0, 10500.0)
        # NHCE employee for valid test
        _insert_employee(conn, "EMP002", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "EMP002", 2025, 85000.0, 85000.0, 2550.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test Scenario", 2025)

        assert result.hce_count == 1
        assert result.nhce_count == 1

    def test_nhce_below_threshold(self, service_with_db):
        """Employee with prior-year comp below threshold is classified as NHCE."""
        service, conn, mock_resolver = service_with_db

        # Two NHCE employees (both below $155K threshold for 2024)
        _insert_employee(conn, "EMP001", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "EMP001", 2025, 85000.0, 85000.0, 4250.0)
        _insert_employee(conn, "EMP002", 2024, 100000.0, 100000.0, 0.0)
        _insert_employee(conn, "EMP002", 2025, 105000.0, 105000.0, 5250.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        assert result.hce_count == 0
        assert result.test_result == "pass"
        assert result.test_message == "No HCE employees in population"

    def test_first_year_fallback_to_current_comp(self, service_with_db):
        """First simulation year uses current-year comp for HCE determination."""
        service, conn, mock_resolver = service_with_db

        # Only current year data (no prior year)
        _insert_employee(conn, "EMP001", 2025, 200000.0, 200000.0, 10000.0)
        _insert_employee(conn, "EMP002", 2025, 80000.0, 80000.0, 4000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        # EMP001 current comp $200K > $160K threshold -> HCE
        assert result.hce_count == 1
        assert result.nhce_count == 1


# ==============================================================================
# Test: Per-Employee ACP Calculation
# ==============================================================================


class TestACPCalculation:
    """Test correct per-employee ACP = match / compensation."""

    def test_acp_calculation(self, service_with_db):
        """ACP should be employer_match / prorated_annual_compensation."""
        service, conn, mock_resolver = service_with_db

        # HCE: match=10500, comp=210000 -> ACP = 5%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 210000.0, 210000.0, 10500.0)
        # NHCE: match=2550, comp=85000 -> ACP = 3%
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 85000.0, 85000.0, 2550.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025, include_employees=True)

        assert result.employees is not None
        hce_emp = next(e for e in result.employees if e.employee_id == "HCE1")
        nhce_emp = next(e for e in result.employees if e.employee_id == "NHCE1")
        assert abs(hce_emp.individual_acp - 0.05) < 0.001
        assert abs(nhce_emp.individual_acp - 0.03) < 0.001

    def test_non_enrolled_has_zero_acp(self, service_with_db):
        """Non-enrolled eligible employees have ACP = 0 (match = 0)."""
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 210000.0, 210000.0, 10500.0)
        # Non-enrolled NHCE: match = 0
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 85000.0, 85000.0, 0.0, enrolled=False)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025, include_employees=True)

        nhce_emp = next(e for e in result.employees if e.employee_id == "NHCE1")
        assert nhce_emp.individual_acp == 0.0
        assert nhce_emp.is_enrolled is False
        assert result.eligible_not_enrolled_count == 1


# ==============================================================================
# Test: Group Averages
# ==============================================================================


class TestGroupAverages:
    """Test correct group average computation."""

    def test_group_averages(self, service_with_db):
        """Group averages should be simple mean of individual ACPs."""
        service, conn, mock_resolver = service_with_db

        # Two HCEs: ACP = 5% and 3% -> avg = 4%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)
        _insert_employee(conn, "HCE2", 2024, 180000.0, 180000.0, 0.0)
        _insert_employee(conn, "HCE2", 2025, 200000.0, 200000.0, 6000.0)
        # Two NHCEs: ACP = 3% and 1% -> avg = 2%
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 3000.0)
        _insert_employee(conn, "NHCE2", 2024, 70000.0, 70000.0, 0.0)
        _insert_employee(conn, "NHCE2", 2025, 100000.0, 100000.0, 1000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        assert abs(result.hce_average_acp - 0.04) < 0.001
        assert abs(result.nhce_average_acp - 0.02) < 0.001


# ==============================================================================
# Test: IRS Test Thresholds
# ==============================================================================


class TestIRSThresholds:
    """Test basic and alternative test threshold computations."""

    def test_basic_threshold(self, service_with_db):
        """Basic test threshold = NHCE avg x 1.25."""
        service, conn, mock_resolver = service_with_db

        # NHCE avg ACP = 4%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 8000.0)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 4000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        # Basic: 0.04 * 1.25 = 0.05
        assert abs(result.basic_test_threshold - 0.05) < 0.001

    def test_alternative_threshold(self, service_with_db):
        """Alternative test threshold = min(NHCE x 2, NHCE + 0.02)."""
        service, conn, mock_resolver = service_with_db

        # NHCE avg ACP = 4% -> alt = min(8%, 6%) = 6%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 8000.0)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 4000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        # Alt: min(0.04*2, 0.04+0.02) = min(0.08, 0.06) = 0.06
        assert abs(result.alternative_test_threshold - 0.06) < 0.001

    def test_more_favorable_test_selected(self, service_with_db):
        """The test that produces the higher threshold (more favorable) should be selected."""
        service, conn, mock_resolver = service_with_db

        # NHCE avg = 4% -> basic = 5%, alt = 6% -> alternative is more favorable
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 4000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        assert result.applied_test == "alternative"
        assert abs(result.applied_threshold - 0.06) < 0.001

    def test_basic_test_selected_when_more_favorable(self, service_with_db):
        """When basic threshold is higher, basic test should be selected."""
        service, conn, mock_resolver = service_with_db

        # NHCE avg = 1% -> basic = 1.25%, alt = min(2%, 3%) = 2%
        # alt is more favorable here. Let's use 10%:
        # NHCE avg = 10% -> basic = 12.5%, alt = min(20%, 12%) = 12%
        # basic (12.5%) > alt (12%) -> basic selected
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 24000.0)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 10000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        # NHCE avg = 10% -> basic = 12.5%, alt = min(20%, 12%) = 12%
        assert result.applied_test == "basic"
        assert abs(result.applied_threshold - 0.125) < 0.001


# ==============================================================================
# Test: Edge Cases
# ==============================================================================


class TestEdgeCases:
    """Test edge case handling."""

    def test_no_nhce_returns_error(self, service_with_db):
        """No NHCE employees should return an error."""
        service, conn, mock_resolver = service_with_db

        # Only HCE employees
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)
        _insert_employee(conn, "HCE2", 2024, 250000.0, 250000.0, 0.0)
        _insert_employee(conn, "HCE2", 2025, 260000.0, 260000.0, 13000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "error"
        assert "NHCE" in (result.test_message or "")

    def test_no_hce_returns_pass(self, service_with_db):
        """No HCE employees should auto-pass."""
        service, conn, mock_resolver = service_with_db

        # Only NHCE employees
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 85000.0, 85000.0, 4250.0)
        _insert_employee(conn, "NHCE2", 2024, 70000.0, 70000.0, 0.0)
        _insert_employee(conn, "NHCE2", 2025, 75000.0, 75000.0, 3750.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "pass"
        assert result.hce_count == 0
        assert "No HCE" in (result.test_message or "")

    def test_no_eligible_employees_returns_error(self, service_with_db):
        """No eligible employees should return an error."""
        service, conn, mock_resolver = service_with_db

        # Employees with pending eligibility
        _insert_employee(conn, "EMP1", 2025, 100000.0, 100000.0, 5000.0, eligibility="pending")

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "error"
        assert "eligible" in (result.test_message or "").lower()

    def test_missing_hce_threshold_returns_error(self, service_with_db):
        """Missing HCE threshold in seed data should return an error."""
        service, conn, mock_resolver = service_with_db

        # Remove all IRS limits
        conn.execute("DELETE FROM config_irs_limits")

        _insert_employee(conn, "EMP1", 2025, 100000.0, 100000.0, 5000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "error"
        assert "threshold" in (result.test_message or "").lower()

    def test_database_not_found_returns_error(self, service_with_db):
        """Non-existent database should return an error."""
        service, conn, mock_resolver = service_with_db

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=None, source=None)

        result = service.run_acp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "error"
        assert "not found" in (result.test_message or "").lower()


# ==============================================================================
# Test: Available Years
# ==============================================================================


class TestAvailableYears:
    """Test available years endpoint."""

    def test_returns_sorted_years(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "EMP1", 2027, 100000.0, 100000.0, 5000.0)
        _insert_employee(conn, "EMP1", 2025, 100000.0, 100000.0, 5000.0)
        _insert_employee(conn, "EMP1", 2026, 100000.0, 100000.0, 5000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.get_available_years("ws1", "sc1")

        assert result.years == [2025, 2026, 2027]
        assert result.default_year == 2027

    def test_no_data_returns_empty(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=None, source=None)

        result = service.get_available_years("ws1", "sc1")

        assert result.years == []
        assert result.default_year is None
