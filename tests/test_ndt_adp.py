"""Tests for NDT ADP (Actual Deferral Percentage) test service."""

import duckdb
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from planalign_api.services.ndt_service import (
    NDTService,
    ADPScenarioResult,
    ADPEmployeeDetail,
)
from planalign_api.services.database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
)


# ==============================================================================
# Fixtures
# ==============================================================================


def _create_test_db(conn: duckdb.DuckDBPyConnection):
    """Populate an in-memory DuckDB connection with ADP test tables."""
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
    deferrals: float,
    eligibility: str = "eligible",
    enrolled: bool = True,
    status: str = "active",
    match_amount: float = 0.0,
    core_amount: float = 0.0,
    tenure: float = 5.0,
):
    conn.execute(
        """INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [employee_id, year, compensation, prorated_comp, deferrals,
         match_amount, core_amount, eligibility, enrolled, status, tenure],
    )


class MockStorage:
    """Mock WorkspaceStorage for testing."""

    def _workspace_path(self, workspace_id: str) -> Path:
        return Path("/mock/workspaces") / workspace_id

    def _scenario_path(self, workspace_id: str, scenario_id: str) -> Path:
        return Path("/mock/workspaces") / workspace_id / "scenarios" / scenario_id


@pytest.fixture
def adp_service_with_db():
    """Create an NDTService with an in-memory DuckDB database for ADP tests."""
    conn = duckdb.connect(":memory:")
    _create_test_db(conn)

    storage = MockStorage()
    mock_resolver = MagicMock(spec=DatabasePathResolver)

    service = NDTService(storage, db_resolver=mock_resolver)
    service._ensure_seed_current = MagicMock()
    return service, conn, mock_resolver


# ==============================================================================
# T004: test_adp_basic_pass
# ==============================================================================


class TestADPBasicPass:
    """T004: HCE ADP within threshold -> pass."""

    def test_adp_basic_pass(self, adp_service_with_db):
        """HCE ADP 5%, NHCE ADP 4% -> basic threshold 5%, pass with margin 0%."""
        service, conn, mock_resolver = adp_service_with_db

        # HCE: comp $200K, deferrals $10K -> ADP 5%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)
        # NHCE: comp $100K, deferrals $4K -> ADP 4%
        _insert_employee(conn, "NHCE1", 2024, 100000.0, 100000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 4000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "pass"
        # basic threshold = 4% * 1.25 = 5%
        assert abs(result.basic_test_threshold - 0.05) < 0.001
        assert result.margin >= 0
        assert result.excess_hce_amount is None


# ==============================================================================
# T005: test_adp_basic_fail_with_excess
# ==============================================================================


class TestADPBasicFailWithExcess:
    """T005: HCE ADP exceeds threshold -> fail with excess amount."""

    def test_adp_basic_fail_with_excess(self, adp_service_with_db):
        """HCE ADP 10%, NHCE ADP 3% -> fail, excess = (10%-threshold) * sum(hce_comp)."""
        service, conn, mock_resolver = adp_service_with_db

        # HCE: comp $200K, deferrals $20K -> ADP 10%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 20000.0)
        # NHCE: comp $100K, deferrals $3K -> ADP 3%
        _insert_employee(conn, "NHCE1", 2024, 100000.0, 100000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 3000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "fail"
        assert result.margin < 0
        # Excess = (hce_avg - applied_threshold) * sum(hce_comp)
        assert result.excess_hce_amount is not None
        assert result.excess_hce_amount > 0
        # NHCE 3%: basic=3.75%, alt=min(6%,5%)=5%, applied=5%
        # excess = (0.10 - 0.05) * 200000 = 10000
        assert abs(result.excess_hce_amount - 10000.0) < 1.0


# ==============================================================================
# T006: test_adp_alternative_prong_selected
# ==============================================================================


class TestADPAlternativeProngSelected:
    """T006: Alternative test produces higher threshold than basic."""

    def test_adp_alternative_prong_selected(self, adp_service_with_db):
        """When alternative threshold > basic threshold, alternative is selected."""
        service, conn, mock_resolver = adp_service_with_db

        # NHCE ADP = 4%: basic = 5%, alt = min(8%, 6%) = 6%
        # alt (6%) > basic (5%) -> alternative selected
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)  # ADP 5%
        _insert_employee(conn, "NHCE1", 2024, 100000.0, 100000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 4000.0)  # ADP 4%

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test("ws1", "sc1", "Test", 2025)

        assert result.applied_test == "alternative"
        assert abs(result.alternative_test_threshold - 0.06) < 0.001
        assert abs(result.applied_threshold - 0.06) < 0.001


# ==============================================================================
# T007: test_adp_zero_deferrals_included
# ==============================================================================


class TestADPZeroDeferralsIncluded:
    """T007: Eligible participant with zero deferrals is included with ADP=0."""

    def test_adp_zero_deferrals_included(self, adp_service_with_db):
        """Zero-deferral participant counted with individual_adp=0.0."""
        service, conn, mock_resolver = adp_service_with_db

        # HCE with deferrals
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)
        # NHCE with zero deferrals
        _insert_employee(conn, "NHCE1", 2024, 100000.0, 100000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 0.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test(
                "ws1", "sc1", "Test", 2025, include_employees=True
            )

        assert result.nhce_count == 1
        nhce_emp = next(
            e for e in result.employees if e.employee_id == "NHCE1"
        )
        assert nhce_emp.individual_adp == 0.0
        assert nhce_emp.is_hce is False


# ==============================================================================
# T008: test_adp_no_nhce_error and test_adp_no_hce_autopass
# ==============================================================================


class TestADPEdgeCasesNoGroup:
    """T008: Edge cases for missing HCE/NHCE groups."""

    def test_adp_no_nhce_error(self, adp_service_with_db):
        """No NHCE employees returns error."""
        service, conn, mock_resolver = adp_service_with_db

        # Only HCE employees (both above $155K prior year threshold)
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)
        _insert_employee(conn, "HCE2", 2024, 250000.0, 250000.0, 0.0)
        _insert_employee(conn, "HCE2", 2025, 260000.0, 260000.0, 13000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "error"
        assert "NHCE" in (result.test_message or "")

    def test_adp_no_hce_autopass(self, adp_service_with_db):
        """No HCE employees returns auto-pass."""
        service, conn, mock_resolver = adp_service_with_db

        # Only NHCE employees
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 85000.0, 85000.0, 4250.0)
        _insert_employee(conn, "NHCE2", 2024, 70000.0, 70000.0, 0.0)
        _insert_employee(conn, "NHCE2", 2025, 75000.0, 75000.0, 3750.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "pass"
        assert result.hce_count == 0
        assert "No HCE" in (result.test_message or "")


# ==============================================================================
# T017: test_adp_employee_detail_populated
# ==============================================================================


class TestADPEmployeeDetail:
    """T017: Employee detail has correct fields when include_employees=True."""

    def test_adp_employee_detail_populated(self, adp_service_with_db):
        """Each ADPEmployeeDetail has correct individual_adp calculation."""
        service, conn, mock_resolver = adp_service_with_db

        # HCE: deferrals $12K, comp $200K -> ADP 6%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 12000.0)
        # NHCE: deferrals $3K, comp $100K -> ADP 3%
        _insert_employee(conn, "NHCE1", 2024, 100000.0, 100000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 3000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test(
                "ws1", "sc1", "Test", 2025, include_employees=True
            )

        assert result.employees is not None
        assert len(result.employees) == 2

        hce_emp = next(e for e in result.employees if e.employee_id == "HCE1")
        assert hce_emp.is_hce is True
        assert abs(hce_emp.employee_deferrals - 12000.0) < 1.0
        assert abs(hce_emp.plan_compensation - 200000.0) < 1.0
        assert abs(hce_emp.individual_adp - 0.06) < 0.001
        assert hce_emp.prior_year_compensation is not None

        nhce_emp = next(e for e in result.employees if e.employee_id == "NHCE1")
        assert nhce_emp.is_hce is False
        assert abs(nhce_emp.employee_deferrals - 3000.0) < 1.0
        assert abs(nhce_emp.individual_adp - 0.03) < 0.001


# ==============================================================================
# T020: test_adp_safe_harbor_exempt
# ==============================================================================


class TestADPSafeHarbor:
    """T020: Safe harbor returns exempt immediately."""

    def test_adp_safe_harbor_exempt(self, adp_service_with_db):
        """safe_harbor=True returns test_result='exempt' with no calculations."""
        service, conn, mock_resolver = adp_service_with_db

        result = service.run_adp_test(
            "ws1", "sc1", "Test", 2025, safe_harbor=True
        )

        assert result.test_result == "exempt"
        assert result.safe_harbor is True
        assert result.hce_count == 0
        assert result.nhce_count == 0


# ==============================================================================
# T021: test_adp_prior_year_testing_method
# ==============================================================================


class TestADPPriorYearMethod:
    """T021: Prior year testing method uses prior year NHCE baseline."""

    def test_adp_prior_year_testing_method(self, adp_service_with_db):
        """testing_method='prior' uses year-1 NHCE ADP as baseline."""
        service, conn, mock_resolver = adp_service_with_db

        # Year 2024: NHCE ADP = 2% (deferrals $2K / comp $100K)
        _insert_employee(conn, "NHCE1", 2024, 100000.0, 100000.0, 2000.0)
        # Year 2025: NHCE ADP = 6% (deferrals $6K / comp $100K)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 6000.0)

        # HCE for year 2025
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)  # ADP 5%

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test(
                "ws1", "sc1", "Test", 2025, testing_method="prior"
            )

        # With prior year method: NHCE baseline = 2024 NHCE ADP = 2%
        # basic = 2% * 1.25 = 2.5%, alt = min(4%, 4%) = 4%
        # applied = 4% (alternative), HCE avg = 5% -> FAIL
        assert result.testing_method == "prior"
        assert result.nhce_average_adp != 0.02  # nhce_average_adp is current year
        # The thresholds are based on prior year NHCE baseline (2%)
        assert abs(result.basic_test_threshold - 0.025) < 0.001


# ==============================================================================
# T022: test_adp_prior_year_fallback
# ==============================================================================


class TestADPPriorYearFallback:
    """T022: Prior year testing falls back to current when no prior data."""

    def test_adp_prior_year_fallback(self, adp_service_with_db):
        """Falls back to current year with warning when no prior year data."""
        service, conn, mock_resolver = adp_service_with_db

        # Only year 2025 data (no 2024)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 4000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test(
                "ws1", "sc1", "Test", 2025, testing_method="prior"
            )

        # Should fall back to current year
        assert result.testing_method == "current"
        assert result.test_message is not None
        assert "prior" in result.test_message.lower() or "fell back" in result.test_message.lower()


# ==============================================================================
# T025: test_adp_zero_compensation_excluded
# ==============================================================================


class TestADPZeroCompExcluded:
    """T025: Participant with zero comp is excluded."""

    def test_adp_zero_compensation_excluded(self, adp_service_with_db):
        """Zero prorated_annual_compensation -> excluded, not in HCE/NHCE groups."""
        service, conn, mock_resolver = adp_service_with_db

        # Normal HCE
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, 10000.0)
        # Normal NHCE
        _insert_employee(conn, "NHCE1", 2024, 100000.0, 100000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, 4000.0)
        # Zero comp participant (should be excluded)
        _insert_employee(conn, "ZERO1", 2024, 50000.0, 50000.0, 0.0)
        _insert_employee(conn, "ZERO1", 2025, 50000.0, 0.0, 0.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test("ws1", "sc1", "Test", 2025)

        assert result.excluded_count == 1
        assert result.hce_count + result.nhce_count == 2


# ==============================================================================
# T026: test_adp_missing_irs_limits_error
# ==============================================================================


class TestADPMissingIRSLimits:
    """T026: Missing IRS limits returns error."""

    def test_adp_missing_irs_limits_error(self, adp_service_with_db):
        """No config_irs_limits entry for year -> test_result='error'."""
        service, conn, mock_resolver = adp_service_with_db

        # Remove all IRS limits
        conn.execute("DELETE FROM config_irs_limits")

        _insert_employee(conn, "EMP1", 2025, 100000.0, 100000.0, 5000.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path(":memory:"), source="scenario"
        )

        with patch("duckdb.connect", return_value=conn):
            result = service.run_adp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "error"
        assert "threshold" in (result.test_message or "").lower()


# ==============================================================================
# T027: test_adp_database_not_found_error
# ==============================================================================


class TestADPDatabaseNotFound:
    """T027: Non-existent database returns error."""

    def test_adp_database_not_found_error(self, adp_service_with_db):
        """Resolver returning non-existent path -> test_result='error'."""
        service, conn, mock_resolver = adp_service_with_db

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=None, source=None)

        result = service.run_adp_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "error"
        assert "not found" in (result.test_message or "").lower()
