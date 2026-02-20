"""Tests for NDT 401(a)(4) General Nondiscrimination Test."""

import duckdb
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from planalign_api.services.ndt_service import (
    NDTService,
    Section401a4ScenarioResult,
)
from planalign_api.services.database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
)


# ==============================================================================
# Fixtures
# ==============================================================================


def _create_test_db(conn: duckdb.DuckDBPyConnection):
    """Populate an in-memory DuckDB connection with test tables for 401(a)(4)."""
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
    match_amount: float = 0.0,
    core_amount: float = 0.0,
    eligibility: str = "eligible",
    enrolled: bool = True,
    status: str = "active",
    tenure: float = 5.0,
    contributions: float = 0.0,
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

    def get_merged_config(self, workspace_id: str, scenario_id: str):
        return {}


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
# Test 1: Ratio test pass
# ==============================================================================


class TestRatioTestPass:
    """HCE avg 8%, NHCE avg 6%, ratio 75% > 70%, passes with +5pp margin."""

    def test_ratio_test_pass(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # HCE: NEC=8000, comp=100000 -> rate=8%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 100000.0, 100000.0, core_amount=8000.0, tenure=10.0)
        # NHCE: NEC=6000, comp=100000 -> rate=6%
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, core_amount=6000.0, tenure=5.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test Scenario", 2025)

        assert result.test_result == "pass"
        assert result.applied_test == "ratio"
        assert abs(result.hce_average_rate - 0.08) < 0.001
        assert abs(result.nhce_average_rate - 0.06) < 0.001
        assert abs(result.ratio - 0.75) < 0.001
        assert result.margin > 0  # +5pp margin


# ==============================================================================
# Test 2: Ratio test fail -> general test pass
# ==============================================================================


class TestRatioFailGeneralPass:
    """NHCE avg < 70% of HCE avg but NHCE median >= 70% of HCE median."""

    def test_general_test_fallback_pass(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # HCE1: NEC=10000, comp=100000 -> 10%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 100000.0, 100000.0, core_amount=10000.0, tenure=10.0)
        # HCE2: NEC=10000, comp=100000 -> 10%
        _insert_employee(conn, "HCE2", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE2", 2025, 100000.0, 100000.0, core_amount=10000.0, tenure=8.0)
        # HCE median = 10%

        # NHCE1: NEC=1000, comp=100000 -> 1% (drags avg down)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, core_amount=1000.0, tenure=3.0)
        # NHCE2: NEC=8000, comp=100000 -> 8%
        _insert_employee(conn, "NHCE2", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE2", 2025, 100000.0, 100000.0, core_amount=8000.0, tenure=4.0)
        # NHCE3: NEC=9000, comp=100000 -> 9%
        _insert_employee(conn, "NHCE3", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE3", 2025, 100000.0, 100000.0, core_amount=9000.0, tenure=5.0)
        # NHCE avg = (1+8+9)/3 = 6%, ratio = 6/10 = 0.60 < 0.70 -> ratio FAILS
        # NHCE median = 8%, HCE median = 10%, median ratio = 8/10 = 0.80 >= 0.70 -> general PASSES

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "pass"
        assert result.applied_test == "general"


# ==============================================================================
# Test 3: Ratio test fail -> general test fail
# ==============================================================================


class TestBothTestsFail:
    """Both ratio and median checks fail."""

    def test_both_tests_fail(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # HCE: rate = 10%
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 100000.0, 100000.0, core_amount=10000.0, tenure=10.0)
        # NHCE: rate = 2%
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, core_amount=2000.0, tenure=3.0)
        # ratio = 2/10 = 0.20 < 0.70 -> ratio FAILS
        # median ratio = 2/10 = 0.20 < 0.70 -> general FAILS

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "fail"
        assert result.margin < 0


# ==============================================================================
# Test 4: Service-based risk flag
# ==============================================================================


class TestServiceRiskFlag:
    """employer_core_status='graded_by_service' AND avg HCE tenure exceeds NHCE by >3 years."""

    def test_service_risk_flag_triggered(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # HCE with high tenure
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 100000.0, 100000.0, core_amount=8000.0, tenure=15.0)
        # NHCE with low tenure
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, core_amount=6000.0, tenure=2.0)
        # HCE avg tenure = 15, NHCE avg tenure = 2, diff = 13 > 3

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        # Mock storage to return graded_by_service config
        service.storage.get_merged_config = MagicMock(return_value={
            "employer_core_contribution": {"status": "graded_by_service"}
        })

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025)

        assert result.service_risk_flag is True
        assert result.service_risk_detail is not None
        assert "15.0" in result.service_risk_detail
        assert "2.0" in result.service_risk_detail


# ==============================================================================
# Test 5: NEC-only mode (default)
# ==============================================================================


class TestNECOnlyMode:
    """Contribution rate uses employer_core_amount only (default)."""

    def test_nec_only_excludes_match(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # Employee with both NEC and match
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 100000.0, 100000.0,
                         match_amount=5000.0, core_amount=3000.0, tenure=10.0)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0,
                         match_amount=3000.0, core_amount=2000.0, tenure=5.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025,
                                            include_employees=True, include_match=False)

        # NEC-only: HCE rate = 3000/100000 = 3%
        hce_emp = next(e for e in result.employees if e.employee_id == "HCE1")
        assert abs(hce_emp.contribution_rate - 0.03) < 0.001
        assert abs(hce_emp.total_employer_amount - 3000.0) < 0.01
        assert result.include_match is False


# ==============================================================================
# Test 6: NEC+match mode
# ==============================================================================


class TestNECPlusMatchMode:
    """include_match=True adds employer_match_amount to numerator."""

    def test_include_match_mode(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 100000.0, 100000.0,
                         match_amount=5000.0, core_amount=3000.0, tenure=10.0)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0,
                         match_amount=3000.0, core_amount=2000.0, tenure=5.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025,
                                            include_employees=True, include_match=True)

        # NEC+match: HCE rate = (3000+5000)/100000 = 8%
        hce_emp = next(e for e in result.employees if e.employee_id == "HCE1")
        assert abs(hce_emp.contribution_rate - 0.08) < 0.001
        assert abs(hce_emp.total_employer_amount - 8000.0) < 0.01
        assert result.include_match is True


# ==============================================================================
# Test 7: Edge case - all HCE
# ==============================================================================


class TestAllHCE:
    """All HCE returns informational message."""

    def test_all_hce_population(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, core_amount=10000.0, tenure=10.0)
        _insert_employee(conn, "HCE2", 2024, 250000.0, 250000.0, 0.0)
        _insert_employee(conn, "HCE2", 2025, 250000.0, 250000.0, core_amount=12500.0, tenure=8.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "pass"
        assert result.test_message is not None
        assert "nhce" in result.test_message.lower() or "no nhce" in result.test_message.lower()


# ==============================================================================
# Test 8: Edge case - all NHCE
# ==============================================================================


class TestAllNHCE:
    """All NHCE auto-passes."""

    def test_all_nhce_auto_pass(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 80000.0, 80000.0, core_amount=4000.0, tenure=5.0)
        _insert_employee(conn, "NHCE2", 2024, 70000.0, 70000.0, 0.0)
        _insert_employee(conn, "NHCE2", 2025, 70000.0, 70000.0, core_amount=3500.0, tenure=3.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025)

        assert result.test_result == "pass"
        assert result.nhce_count == 2
        assert result.hce_count == 0


# ==============================================================================
# Test 9: Edge case - no employer contributions
# ==============================================================================


class TestNoEmployerContributions:
    """No employer contributions — all employees filtered out as non-benefiting."""

    def test_no_employer_contributions(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0,
                         core_amount=0.0, match_amount=0.0, tenure=10.0)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 80000.0, 80000.0,
                         core_amount=0.0, match_amount=0.0, tenure=5.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025)

        # Non-benefiting employees excluded → no rows → error
        assert result.test_result == "error"
        assert "no eligible employees" in result.test_message.lower()


# ==============================================================================
# Test 10: Edge case - zero compensation excluded
# ==============================================================================


class TestNonBenefitingExcluded:
    """Employees with zero employer match AND zero core are excluded from population."""

    def test_non_benefiting_excluded(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        # HCE with core contribution (benefiting)
        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 100000.0, 100000.0, core_amount=8000.0, tenure=10.0)
        # NHCE with core contribution (benefiting)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0, core_amount=6000.0, tenure=5.0)
        # NHCE with zero match AND zero core (non-benefiting — should be excluded)
        _insert_employee(conn, "NHCE2", 2024, 60000.0, 60000.0, 0.0)
        _insert_employee(conn, "NHCE2", 2025, 60000.0, 60000.0,
                         core_amount=0.0, match_amount=0.0, tenure=3.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025)

        # NHCE2 excluded: only 2 benefiting employees remain
        assert result.hce_count == 1
        assert result.nhce_count == 1
        # NHCE avg should be 6% (only NHCE1), not diluted to 3% by zero-contribution NHCE2
        assert abs(result.nhce_average_rate - 0.06) < 0.001

    def test_match_only_employee_included(self, service_with_db):
        """Employee with match but no core is still benefiting."""
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 100000.0, 100000.0,
                         match_amount=5000.0, core_amount=0.0, tenure=10.0)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 100000.0, 100000.0,
                         match_amount=3000.0, core_amount=0.0, tenure=5.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025, include_match=True)

        # Both included — match-only counts as benefiting
        assert result.hce_count == 1
        assert result.nhce_count == 1


# ==============================================================================
# Test 11: Edge case - zero compensation excluded
# ==============================================================================


class TestZeroCompExcluded:
    """Zero compensation employees excluded from calculation."""

    def test_zero_comp_excluded(self, service_with_db):
        service, conn, mock_resolver = service_with_db

        _insert_employee(conn, "HCE1", 2024, 200000.0, 200000.0, 0.0)
        _insert_employee(conn, "HCE1", 2025, 200000.0, 200000.0, core_amount=10000.0, tenure=10.0)
        _insert_employee(conn, "NHCE1", 2024, 80000.0, 80000.0, 0.0)
        _insert_employee(conn, "NHCE1", 2025, 80000.0, 80000.0, core_amount=4000.0, tenure=5.0)
        # Zero comp employee with a core contribution — benefiting but zero comp
        _insert_employee(conn, "ZERO1", 2024, 0.0, 0.0, 0.0)
        _insert_employee(conn, "ZERO1", 2025, 0.0, 0.0, core_amount=100.0, tenure=1.0)

        mock_resolver.resolve.return_value = ResolvedDatabasePath(path=Path(":memory:"), source="scenario")

        with patch("duckdb.connect", return_value=conn):
            result = service.run_401a4_test("ws1", "sc1", "Test", 2025)

        # Zero-comp employee passes benefiting filter but excluded by comp check
        assert result.hce_count + result.nhce_count == 2
        assert result.excluded_count >= 1
