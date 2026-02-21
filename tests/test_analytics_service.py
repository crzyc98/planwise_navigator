"""Tests for AnalyticsService participation rate consistency.

Feature: 041-fix-yearly-participation-rate
Validates that per-year participation rate defaults to all participants
(active + terminated) and supports active_only toggle.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from planalign_api.services.analytics_service import AnalyticsService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath


# =============================================================================
# Fixtures
# =============================================================================


def _create_snapshot_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create fct_workforce_snapshot table with required columns."""
    conn.execute("""
        CREATE TABLE fct_workforce_snapshot (
            employee_id VARCHAR,
            scenario_id VARCHAR DEFAULT 'baseline',
            plan_design_id VARCHAR DEFAULT 'standard_401k',
            simulation_year INTEGER,
            employment_status VARCHAR,
            is_enrolled_flag BOOLEAN,
            prorated_annual_contributions DECIMAL(12,2) DEFAULT 0,
            employer_match_amount DECIMAL(12,2) DEFAULT 0,
            employer_core_amount DECIMAL(12,2) DEFAULT 0,
            current_deferral_rate DECIMAL(6,4) DEFAULT 0,
            prorated_annual_compensation DECIMAL(12,2) DEFAULT 0,
            participation_status_detail VARCHAR DEFAULT 'voluntary',
            has_deferral_escalations BOOLEAN DEFAULT FALSE,
            total_deferral_escalations INTEGER DEFAULT 0,
            total_escalation_amount DECIMAL(8,4) DEFAULT 0,
            irs_limit_reached BOOLEAN DEFAULT FALSE
        )
    """)


def _seed_employees(
    conn: duckdb.DuckDBPyConnection,
    rows: list[dict],
) -> None:
    """Insert employee rows into fct_workforce_snapshot."""
    for row in rows:
        conn.execute(
            """
            INSERT INTO fct_workforce_snapshot (
                employee_id, simulation_year, employment_status, is_enrolled_flag,
                prorated_annual_contributions, employer_match_amount, employer_core_amount,
                current_deferral_rate, prorated_annual_compensation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["employee_id"],
                row["year"],
                row["status"],
                row["enrolled"],
                row.get("contributions", 0),
                row.get("match", 0),
                row.get("core", 0),
                row.get("deferral_rate", 0.06),
                row.get("compensation", 100000),
            ],
        )


@pytest.fixture
def in_memory_conn():
    """In-memory DuckDB connection with fct_workforce_snapshot table."""
    conn = duckdb.connect(":memory:")
    _create_snapshot_table(conn)
    yield conn
    conn.close()


@pytest.fixture
def analytics_service(tmp_path):
    """AnalyticsService with mocked storage and resolver pointing to a temp DB."""
    db_path = tmp_path / "simulation.duckdb"
    # Create the database file with the snapshot table
    conn = duckdb.connect(str(db_path))
    _create_snapshot_table(conn)
    conn.close()

    mock_storage = MagicMock()
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = ResolvedDatabasePath(
        path=db_path, source="scenario"
    )

    service = AnalyticsService(storage=mock_storage, db_resolver=mock_resolver)
    return service, db_path


# =============================================================================
# T002: test_participation_rate_active_only
# =============================================================================


class TestParticipationRateDefaultAll:
    """T002: Verify per-year participation rate defaults to all employees."""

    def test_participation_rate_includes_terminated_by_default(self, in_memory_conn):
        """8 active (6 enrolled) + 2 terminated (1 enrolled) => default rate = 70.0 (7/10)."""
        _seed_employees(in_memory_conn, [
            # Active enrolled (6)
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A4", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A5", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A6", "year": 2025, "status": "ACTIVE", "enrolled": True},
            # Active not enrolled (2)
            {"employee_id": "A7", "year": 2025, "status": "ACTIVE", "enrolled": False},
            {"employee_id": "A8", "year": 2025, "status": "ACTIVE", "enrolled": False},
            # Terminated enrolled (1)
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": True},
            # Terminated not enrolled (1)
            {"employee_id": "T2", "year": 2025, "status": "TERMINATED", "enrolled": False},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn)

        assert len(results) == 1
        # Default: 7 enrolled / 10 total = 70.0%
        assert results[0].participation_rate == 70.0

    def test_participation_rate_active_only(self, in_memory_conn):
        """Same data with active_only=True => rate = 75.0 (6/8)."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A4", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A5", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A6", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A7", "year": 2025, "status": "ACTIVE", "enrolled": False},
            {"employee_id": "A8", "year": 2025, "status": "ACTIVE", "enrolled": False},
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": True},
            {"employee_id": "T2", "year": 2025, "status": "TERMINATED", "enrolled": False},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn, active_only=True)

        assert len(results) == 1
        # Active only: 6 enrolled active / 8 total active = 75.0%
        assert results[0].participation_rate == 75.0


# =============================================================================
# T003: test_zero_active_employees
# =============================================================================


class TestZeroActiveEmployees:
    """T003: Verify participation rate handles all-terminated correctly."""

    def test_all_terminated_default_includes_them(self, in_memory_conn):
        """All terminated, default (all participants) => 2/3 = 66.67%."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": True},
            {"employee_id": "T2", "year": 2025, "status": "TERMINATED", "enrolled": True},
            {"employee_id": "T3", "year": 2025, "status": "TERMINATED", "enrolled": False},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn)

        assert len(results) == 1
        assert results[0].participation_rate == 66.67

    def test_all_terminated_active_only_returns_zero(self, in_memory_conn):
        """All terminated with active_only=True => 0.0, no division error."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": True},
            {"employee_id": "T2", "year": 2025, "status": "TERMINATED", "enrolled": True},
            {"employee_id": "T3", "year": 2025, "status": "TERMINATED", "enrolled": False},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn, active_only=True)

        assert len(results) == 0  # No active employees, no rows returned


# =============================================================================
# T004: test_all_active_enrolled
# =============================================================================


class TestAllActiveEnrolled:
    """T004: Verify participation rate when all active are enrolled."""

    def test_all_active_enrolled_default(self, in_memory_conn):
        """5 active enrolled + 2 terminated not enrolled => default rate = 71.43 (5/7)."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A4", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A5", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": False},
            {"employee_id": "T2", "year": 2025, "status": "TERMINATED", "enrolled": False},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn)

        assert len(results) == 1
        # Default: 5 enrolled / 7 total = 71.43%
        assert results[0].participation_rate == 71.43

    def test_all_active_enrolled_active_only(self, in_memory_conn):
        """Same data with active_only=True => rate = 100.0 (5/5)."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A4", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A5", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": False},
            {"employee_id": "T2", "year": 2025, "status": "TERMINATED", "enrolled": False},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn, active_only=True)

        assert len(results) == 1
        assert results[0].participation_rate == 100.0


# =============================================================================
# T005: test_contribution_totals_include_all_employees
# =============================================================================


class TestContributionTotalsIncludeAll:
    """T005: Verify contribution totals include terminated employees."""

    def test_contributions_include_terminated(self, in_memory_conn):
        """Contribution sums must include terminated employee amounts."""
        _seed_employees(in_memory_conn, [
            {
                "employee_id": "A1", "year": 2025, "status": "ACTIVE",
                "enrolled": True, "contributions": 5000, "match": 2500, "core": 1000,
            },
            {
                "employee_id": "T1", "year": 2025, "status": "TERMINATED",
                "enrolled": True, "contributions": 3000, "match": 1500, "core": 500,
            },
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn)

        assert len(results) == 1
        # Totals should include BOTH active and terminated
        assert results[0].total_employee_contributions == 8000.0  # 5000 + 3000
        assert results[0].total_employer_match == 4000.0  # 2500 + 1500
        assert results[0].total_employer_core == 1500.0  # 1000 + 500


# =============================================================================
# T008: test_final_year_matches_top_level
# =============================================================================


class TestFinalYearMatchesTopLevel:
    """T008: Verify final-year per-year rate matches top-level rate."""

    def test_multi_year_final_matches_top_level(self, analytics_service):
        """Multi-year: DCPlanAnalytics.participation_rate == contribution_by_year[-1].participation_rate."""
        service, db_path = analytics_service

        conn = duckdb.connect(str(db_path))
        # Year 2025 data
        _seed_employees(conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE", "enrolled": False},
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": True},
        ])
        # Year 2026 data (final year)
        _seed_employees(conn, [
            {"employee_id": "A1", "year": 2026, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A2", "year": 2026, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A3", "year": 2026, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A4", "year": 2026, "status": "ACTIVE", "enrolled": False},
            {"employee_id": "T1", "year": 2026, "status": "TERMINATED", "enrolled": True},
        ])
        conn.close()

        result = service.get_dc_plan_analytics("ws", "sc", "test")

        assert result is not None
        assert len(result.contribution_by_year) == 2

        # Top-level rate comes from _get_participation_summary (final year, all participants)
        # Final year 2026: 4 enrolled / 5 total = 80.0%
        top_level_rate = result.participation_rate
        final_year_rate = result.contribution_by_year[-1].participation_rate

        assert abs(top_level_rate - final_year_rate) <= 0.01


# =============================================================================
# T009: test_single_year_matches_top_level
# =============================================================================


class TestSingleYearMatchesTopLevel:
    """T009: Verify single-year per-year rate matches top-level rate."""

    def test_single_year_matches(self, analytics_service):
        """Single year: top-level and per-year rates must be identical."""
        service, db_path = analytics_service

        conn = duckdb.connect(str(db_path))
        _seed_employees(conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE", "enrolled": False},
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": True},
        ])
        conn.close()

        result = service.get_dc_plan_analytics("ws", "sc", "test")

        assert result is not None
        assert len(result.contribution_by_year) == 1

        top_level_rate = result.participation_rate
        per_year_rate = result.contribution_by_year[0].participation_rate

        assert top_level_rate == per_year_rate
