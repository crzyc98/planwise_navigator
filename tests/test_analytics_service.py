"""Tests for AnalyticsService participation rate consistency.

Feature: 041-fix-yearly-participation-rate
Validates that per-year participation rate defaults to all participants
(active + terminated) and supports active_only toggle.

Extended with comprehensive coverage for:
- _compute_grand_totals (E066 contribution rate calculations)
- get_dc_plan_analytics (full flow + error handling)
- _get_participation_summary (active_only toggle + error fallback)
- _get_contribution_by_year (E066 contribution rate percentages + error fallback)
- _get_deferral_distribution and _get_deferral_distribution_all_years
- _get_escalation_metrics and _get_irs_limit_metrics
- Error/fallback branches
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from planalign_api.models.analytics import ContributionYearSummary
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
                current_deferral_rate, prorated_annual_compensation,
                participation_status_detail, has_deferral_escalations,
                total_deferral_escalations, total_escalation_amount, irs_limit_reached
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                row.get("participation_detail", "voluntary"),
                row.get("has_escalations", False),
                row.get("escalation_count", 0),
                row.get("escalation_amount", 0),
                row.get("irs_limit_reached", False),
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


# =============================================================================
# _compute_grand_totals
# =============================================================================


class TestComputeGrandTotals:
    """Test _compute_grand_totals static method including E066 contribution rates."""

    @pytest.mark.fast
    def test_grand_totals_basic_aggregation(self):
        """Grand totals sum employee, match, core across years."""
        years = [
            ContributionYearSummary(
                year=2025,
                total_employee_contributions=5000.0,
                total_employer_match=2500.0,
                total_employer_core=1000.0,
                total_all_contributions=8500.0,
                participant_count=10,
                average_deferral_rate=0.06,
                total_compensation=200000.0,
            ),
            ContributionYearSummary(
                year=2026,
                total_employee_contributions=6000.0,
                total_employer_match=3000.0,
                total_employer_core=1200.0,
                total_all_contributions=10200.0,
                participant_count=12,
                average_deferral_rate=0.07,
                total_compensation=250000.0,
            ),
        ]
        totals = AnalyticsService._compute_grand_totals(years)

        assert totals["total_employee"] == 11000.0
        assert totals["total_match"] == 5500.0
        assert totals["total_core"] == 2200.0
        assert totals["total_all"] == 18700.0
        assert totals["total_employer_cost"] == 7700.0  # 5500 + 2200

    @pytest.mark.fast
    def test_grand_totals_weighted_avg_deferral_rate(self):
        """Average deferral rate is weighted by participant count."""
        years = [
            ContributionYearSummary(
                year=2025,
                total_employee_contributions=0,
                total_employer_match=0,
                total_employer_core=0,
                total_all_contributions=0,
                participant_count=10,
                average_deferral_rate=0.04,
                total_compensation=100000.0,
            ),
            ContributionYearSummary(
                year=2026,
                total_employee_contributions=0,
                total_employer_match=0,
                total_employer_core=0,
                total_all_contributions=0,
                participant_count=30,
                average_deferral_rate=0.08,
                total_compensation=100000.0,
            ),
        ]
        totals = AnalyticsService._compute_grand_totals(years)
        # Weighted: (0.04*10 + 0.08*30) / 40 = (0.4 + 2.4) / 40 = 0.07
        assert abs(totals["avg_deferral_rate"] - 0.07) < 1e-9

    @pytest.mark.fast
    def test_grand_totals_zero_participants(self):
        """Zero participants yields 0 avg deferral rate without division error."""
        years = [
            ContributionYearSummary(
                year=2025,
                total_employee_contributions=0,
                total_employer_match=0,
                total_employer_core=0,
                total_all_contributions=0,
                participant_count=0,
                average_deferral_rate=0.0,
                total_compensation=0.0,
            ),
        ]
        totals = AnalyticsService._compute_grand_totals(years)
        assert totals["avg_deferral_rate"] == 0.0

    @pytest.mark.fast
    def test_grand_totals_contribution_rate_percentages(self):
        """E066: Contribution rates computed as percentage of total compensation."""
        years = [
            ContributionYearSummary(
                year=2025,
                total_employee_contributions=6000.0,
                total_employer_match=3000.0,
                total_employer_core=1000.0,
                total_all_contributions=10000.0,
                participant_count=5,
                average_deferral_rate=0.06,
                total_compensation=100000.0,
            ),
        ]
        totals = AnalyticsService._compute_grand_totals(years)

        assert totals["employee_contribution_rate"] == 6.0  # 6000/100000*100
        assert totals["match_contribution_rate"] == 3.0  # 3000/100000*100
        assert totals["core_contribution_rate"] == 1.0  # 1000/100000*100
        assert totals["total_contribution_rate"] == 10.0  # 6+3+1
        assert totals["employer_cost_rate"] == 4.0  # (3000+1000)/100000*100

    @pytest.mark.fast
    def test_grand_totals_zero_compensation(self):
        """Zero total compensation yields 0 rates without division error."""
        years = [
            ContributionYearSummary(
                year=2025,
                total_employee_contributions=500.0,
                total_employer_match=200.0,
                total_employer_core=100.0,
                total_all_contributions=800.0,
                participant_count=2,
                average_deferral_rate=0.06,
                total_compensation=0.0,
            ),
        ]
        totals = AnalyticsService._compute_grand_totals(years)
        assert totals["employer_cost_rate"] == 0.0
        assert totals["employee_contribution_rate"] == 0.0
        assert totals["match_contribution_rate"] == 0.0
        assert totals["core_contribution_rate"] == 0.0
        assert totals["total_contribution_rate"] == 0.0

    @pytest.mark.fast
    def test_grand_totals_empty_list(self):
        """Empty contribution list yields all zeros."""
        totals = AnalyticsService._compute_grand_totals([])
        assert totals["total_employee"] == 0
        assert totals["total_match"] == 0
        assert totals["total_core"] == 0
        assert totals["total_all"] == 0
        assert totals["avg_deferral_rate"] == 0.0
        assert totals["total_contribution_rate"] == 0.0


# =============================================================================
# _contribution_rates (static helper)
# =============================================================================


class TestContributionRates:
    """Test _contribution_rates static helper for rate calculations."""

    @pytest.mark.fast
    def test_contribution_rates_normal(self):
        """Rates computed as percentage of total compensation."""
        rates = AnalyticsService._contribution_rates(
            total_employee=6000.0,
            total_match=3000.0,
            total_core=1000.0,
            total_compensation=100000.0,
        )
        assert rates["employee_contribution_rate"] == 6.0
        assert rates["match_contribution_rate"] == 3.0
        assert rates["core_contribution_rate"] == 1.0
        assert rates["total_contribution_rate"] == 10.0

    @pytest.mark.fast
    def test_contribution_rates_zero_compensation(self):
        """Zero compensation yields all-zero rates without division error."""
        rates = AnalyticsService._contribution_rates(
            total_employee=5000.0,
            total_match=2000.0,
            total_core=500.0,
            total_compensation=0.0,
        )
        assert rates["employee_contribution_rate"] == 0.0
        assert rates["match_contribution_rate"] == 0.0
        assert rates["core_contribution_rate"] == 0.0
        assert rates["total_contribution_rate"] == 0.0

    @pytest.mark.fast
    def test_contribution_rates_rounding(self):
        """Rates are rounded to 2 decimal places."""
        rates = AnalyticsService._contribution_rates(
            total_employee=3333.0,
            total_match=1111.0,
            total_core=777.0,
            total_compensation=100000.0,
        )
        assert rates["employee_contribution_rate"] == 3.33
        assert rates["match_contribution_rate"] == 1.11
        assert rates["core_contribution_rate"] == 0.78
        # Total also rounded independently
        assert rates["total_contribution_rate"] == round(3.33 + 1.11 + 0.78, 2)

    @pytest.mark.fast
    def test_contribution_rates_all_zero_amounts(self):
        """Zero contributions with positive compensation yields zero rates."""
        rates = AnalyticsService._contribution_rates(
            total_employee=0.0,
            total_match=0.0,
            total_core=0.0,
            total_compensation=500000.0,
        )
        assert rates["employee_contribution_rate"] == 0.0
        assert rates["match_contribution_rate"] == 0.0
        assert rates["core_contribution_rate"] == 0.0
        assert rates["total_contribution_rate"] == 0.0

    @pytest.mark.fast
    def test_grand_totals_delegates_to_contribution_rates(self):
        """_compute_grand_totals uses _contribution_rates for rate fields."""
        years = [
            ContributionYearSummary(
                year=2025,
                total_employee_contributions=8000.0,
                total_employer_match=4000.0,
                total_employer_core=2000.0,
                total_all_contributions=14000.0,
                participant_count=20,
                average_deferral_rate=0.05,
                total_compensation=200000.0,
            ),
            ContributionYearSummary(
                year=2026,
                total_employee_contributions=10000.0,
                total_employer_match=5000.0,
                total_employer_core=3000.0,
                total_all_contributions=18000.0,
                participant_count=25,
                average_deferral_rate=0.06,
                total_compensation=300000.0,
            ),
        ]
        totals = AnalyticsService._compute_grand_totals(years)

        # Verify aggregation (lines 61-65)
        assert totals["total_employee"] == 18000.0
        assert totals["total_match"] == 9000.0
        assert totals["total_core"] == 5000.0
        assert totals["total_all"] == 32000.0
        assert totals["total_employer_cost"] == 14000.0

        # Verify weighted avg deferral (lines 67-73)
        # (0.05*20 + 0.06*25) / 45 = (1.0 + 1.5) / 45 ≈ 0.05556
        expected_avg = (0.05 * 20 + 0.06 * 25) / 45
        assert abs(totals["avg_deferral_rate"] - expected_avg) < 1e-9

        # Verify employer cost rate (lines 75-80)
        # 14000 / 500000 * 100 = 2.8
        assert totals["employer_cost_rate"] == pytest.approx(2.8)

        # Verify rates match _contribution_rates output
        expected_rates = AnalyticsService._contribution_rates(
            18000.0, 9000.0, 5000.0, 500000.0,
        )
        assert totals["employee_contribution_rate"] == expected_rates["employee_contribution_rate"]
        assert totals["match_contribution_rate"] == expected_rates["match_contribution_rate"]
        assert totals["core_contribution_rate"] == expected_rates["core_contribution_rate"]
        assert totals["total_contribution_rate"] == expected_rates["total_contribution_rate"]


# =============================================================================
# _get_participation_summary
# =============================================================================


class TestGetParticipationSummary:
    """Test _get_participation_summary including active_only and error fallback."""

    @pytest.mark.fast
    def test_participation_summary_default_all(self, in_memory_conn):
        """Default includes all employees (active + terminated)."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE", "enrolled": True,
             "participation_detail": "auto_enrolled"},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE", "enrolled": True,
             "participation_detail": "voluntary"},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE", "enrolled": False,
             "participation_detail": "not_enrolled"},
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": True,
             "participation_detail": "census_baseline"},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        result = service._get_participation_summary(in_memory_conn, active_only=False)

        assert result["total_eligible"] == 4
        assert result["total_enrolled"] == 3
        assert result["participation_rate"] == 75.0  # 3/4
        assert result["by_method"].auto_enrolled == 1
        assert result["by_method"].voluntary_enrolled == 1
        assert result["by_method"].census_enrolled == 1

    @pytest.mark.fast
    def test_participation_summary_active_only(self, in_memory_conn):
        """active_only=True filters out terminated employees."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE", "enrolled": False},
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED", "enrolled": True},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        result = service._get_participation_summary(in_memory_conn, active_only=True)

        assert result["total_eligible"] == 2  # Only active
        assert result["total_enrolled"] == 1
        assert result["participation_rate"] == 50.0

    @pytest.mark.fast
    def test_participation_summary_empty_table(self, in_memory_conn):
        """Empty table returns zeros with no error."""
        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        result = service._get_participation_summary(in_memory_conn)

        # DuckDB MAX on empty table returns NULL, COUNT returns 0
        assert result["total_eligible"] == 0
        assert result["total_enrolled"] == 0
        assert result["participation_rate"] == 0.0

    @pytest.mark.fast
    def test_participation_summary_error_fallback(self):
        """Query error returns default zeros."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("DB error")

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        result = service._get_participation_summary(mock_conn)

        assert result["total_eligible"] == 0
        assert result["total_enrolled"] == 0
        assert result["participation_rate"] == 0.0
        assert result["by_method"].auto_enrolled == 0

    @pytest.mark.fast
    def test_participation_summary_uses_final_year(self, in_memory_conn):
        """Summary is computed from the final (max) simulation year only."""
        _seed_employees(in_memory_conn, [
            # Year 2025: 2 enrolled / 3 total
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE", "enrolled": False},
            # Year 2026: 1 enrolled / 2 total
            {"employee_id": "A1", "year": 2026, "status": "ACTIVE", "enrolled": True},
            {"employee_id": "A3", "year": 2026, "status": "ACTIVE", "enrolled": False},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        result = service._get_participation_summary(in_memory_conn)

        # Should use 2026 data only
        assert result["total_eligible"] == 2
        assert result["total_enrolled"] == 1
        assert result["participation_rate"] == 50.0


# =============================================================================
# _get_contribution_by_year - E066 contribution rate percentages
# =============================================================================


class TestContributionByYearRates:
    """Test E066 contribution rate percentage calculations."""

    @pytest.mark.fast
    def test_contribution_rate_percentages(self, in_memory_conn):
        """Contribution rates are computed as percentage of total compensation."""
        _seed_employees(in_memory_conn, [
            {
                "employee_id": "A1", "year": 2025, "status": "ACTIVE",
                "enrolled": True, "contributions": 6000, "match": 3000,
                "core": 1000, "compensation": 100000,
            },
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn)

        assert len(results) == 1
        r = results[0]
        assert r.employee_contribution_rate == 6.0
        assert r.match_contribution_rate == 3.0
        assert r.core_contribution_rate == 1.0
        assert r.total_contribution_rate == 10.0
        assert r.employer_cost_rate == 4.0  # (3000+1000)/100000*100

    @pytest.mark.fast
    def test_contribution_rates_zero_compensation(self, in_memory_conn):
        """Zero compensation yields 0 rates without division error."""
        _seed_employees(in_memory_conn, [
            {
                "employee_id": "A1", "year": 2025, "status": "ACTIVE",
                "enrolled": True, "contributions": 500, "match": 200,
                "core": 100, "compensation": 0,
            },
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn)

        assert len(results) == 1
        r = results[0]
        assert r.employee_contribution_rate == 0.0
        assert r.match_contribution_rate == 0.0
        assert r.core_contribution_rate == 0.0
        assert r.total_contribution_rate == 0.0
        assert r.employer_cost_rate == 0.0

    @pytest.mark.fast
    def test_contribution_by_year_multi_year(self, in_memory_conn):
        """Multi-year returns one ContributionYearSummary per year, ordered."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "contributions": 5000, "compensation": 100000},
            {"employee_id": "A1", "year": 2026, "status": "ACTIVE",
             "enrolled": True, "contributions": 6000, "compensation": 120000},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(in_memory_conn)

        assert len(results) == 2
        assert results[0].year == 2025
        assert results[1].year == 2026
        assert results[0].total_employee_contributions == 5000.0
        assert results[1].total_employee_contributions == 6000.0

    @pytest.mark.fast
    def test_contribution_by_year_error_fallback(self):
        """Query error returns empty list."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("DB error")

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        results = service._get_contribution_by_year(mock_conn)

        assert results == []


# =============================================================================
# _get_deferral_distribution
# =============================================================================


class TestDeferralDistribution:
    """Test _get_deferral_distribution bucket computation."""

    @pytest.mark.fast
    def test_deferral_distribution_buckets(self, in_memory_conn):
        """Deferral rates are bucketed correctly (11 buckets)."""
        _seed_employees(in_memory_conn, [
            # 0% bucket
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "deferral_rate": 0.0},
            # 3% bucket (0.025 <= rate < 0.035)
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "deferral_rate": 0.03},
            # 6% bucket (0.055 <= rate < 0.065)
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "deferral_rate": 0.06},
            {"employee_id": "A4", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "deferral_rate": 0.06},
            # 10%+ bucket (>= 0.095)
            {"employee_id": "A5", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "deferral_rate": 0.15},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        dist = service._get_deferral_distribution(in_memory_conn)

        assert len(dist) == 11
        # Check bucket names
        assert dist[0].bucket == "0%"
        assert dist[10].bucket == "10%+"

        bucket_map = {b.bucket: b for b in dist}
        assert bucket_map["0%"].count == 1
        assert bucket_map["3%"].count == 1
        assert bucket_map["6%"].count == 2
        assert bucket_map["10%+"].count == 1
        # Zero buckets
        assert bucket_map["1%"].count == 0
        assert bucket_map["2%"].count == 0

        # Percentages sum to ~100
        total_pct = sum(b.percentage for b in dist)
        assert abs(total_pct - 100.0) < 0.1

    @pytest.mark.fast
    def test_deferral_distribution_excludes_terminated(self, in_memory_conn):
        """Only active enrolled employees appear in deferral distribution."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "deferral_rate": 0.06},
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED",
             "enrolled": True, "deferral_rate": 0.06},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE",
             "enrolled": False, "deferral_rate": 0.06},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        dist = service._get_deferral_distribution(in_memory_conn)

        total_count = sum(b.count for b in dist)
        assert total_count == 1  # Only A1

    @pytest.mark.fast
    def test_deferral_distribution_error_fallback(self):
        """Query error returns 11 zero-count buckets."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("DB error")

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        dist = service._get_deferral_distribution(mock_conn)

        assert len(dist) == 11
        assert all(b.count == 0 for b in dist)
        assert all(b.percentage == 0.0 for b in dist)


# =============================================================================
# _get_deferral_distribution_all_years
# =============================================================================


class TestDeferralDistributionAllYears:
    """Test _get_deferral_distribution_all_years multi-year distribution."""

    @pytest.mark.fast
    def test_deferral_distribution_all_years(self, in_memory_conn):
        """Returns one DeferralDistributionYear per year with 11 buckets each."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "deferral_rate": 0.03},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "deferral_rate": 0.06},
            {"employee_id": "A1", "year": 2026, "status": "ACTIVE",
             "enrolled": True, "deferral_rate": 0.08},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        result = service._get_deferral_distribution_all_years(in_memory_conn)

        assert len(result) == 2
        assert result[0].year == 2025
        assert result[1].year == 2026
        assert len(result[0].distribution) == 11
        assert len(result[1].distribution) == 11

        # Year 2025: 3% bucket has 1, 6% bucket has 1
        y2025_map = {b.bucket: b for b in result[0].distribution}
        assert y2025_map["3%"].count == 1
        assert y2025_map["6%"].count == 1

        # Year 2026: 8% bucket has 1
        y2026_map = {b.bucket: b for b in result[1].distribution}
        assert y2026_map["8%"].count == 1

    @pytest.mark.fast
    def test_deferral_distribution_all_years_error_fallback(self):
        """Query error returns empty list."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("DB error")

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        result = service._get_deferral_distribution_all_years(mock_conn)

        assert result == []


# =============================================================================
# _get_escalation_metrics
# =============================================================================


class TestEscalationMetrics:
    """Test _get_escalation_metrics."""

    @pytest.mark.fast
    def test_escalation_metrics_basic(self, in_memory_conn):
        """Escalation metrics computed from final year active enrolled employees."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "has_escalations": True,
             "escalation_count": 2, "escalation_amount": 0.02},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "has_escalations": True,
             "escalation_count": 1, "escalation_amount": 0.01},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "has_escalations": False,
             "escalation_count": 0, "escalation_amount": 0},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        metrics = service._get_escalation_metrics(in_memory_conn)

        assert metrics.employees_with_escalations == 2
        # avg escalations for those with escalations: (2+1)/2 = 1.5
        assert metrics.avg_escalation_count == 1.5
        assert abs(metrics.total_escalation_amount - 0.03) < 1e-4

    @pytest.mark.fast
    def test_escalation_metrics_no_escalations(self, in_memory_conn):
        """No escalations yields zeros."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "has_escalations": False,
             "escalation_count": 0, "escalation_amount": 0},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        metrics = service._get_escalation_metrics(in_memory_conn)

        assert metrics.employees_with_escalations == 0
        assert metrics.avg_escalation_count == 0.0
        assert metrics.total_escalation_amount == 0.0

    @pytest.mark.fast
    def test_escalation_metrics_error_fallback(self):
        """Query error returns default zeros."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("DB error")

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        metrics = service._get_escalation_metrics(mock_conn)

        assert metrics.employees_with_escalations == 0
        assert metrics.avg_escalation_count == 0.0
        assert metrics.total_escalation_amount == 0.0


# =============================================================================
# _get_irs_limit_metrics
# =============================================================================


class TestIRSLimitMetrics:
    """Test _get_irs_limit_metrics."""

    @pytest.mark.fast
    def test_irs_limit_metrics_basic(self, in_memory_conn):
        """IRS limit metrics from final year active enrolled employees."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "irs_limit_reached": True},
            {"employee_id": "A2", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "irs_limit_reached": False},
            {"employee_id": "A3", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "irs_limit_reached": True},
            {"employee_id": "A4", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "irs_limit_reached": False},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        metrics = service._get_irs_limit_metrics(in_memory_conn)

        assert metrics.employees_at_irs_limit == 2
        assert metrics.irs_limit_rate == 50.0  # 2/4*100

    @pytest.mark.fast
    def test_irs_limit_metrics_none_at_limit(self, in_memory_conn):
        """No employees at IRS limit."""
        _seed_employees(in_memory_conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "irs_limit_reached": False},
        ])

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        metrics = service._get_irs_limit_metrics(in_memory_conn)

        assert metrics.employees_at_irs_limit == 0
        assert metrics.irs_limit_rate == 0.0

    @pytest.mark.fast
    def test_irs_limit_metrics_error_fallback(self):
        """Query error returns default zeros."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("DB error")

        service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
        metrics = service._get_irs_limit_metrics(mock_conn)

        assert metrics.employees_at_irs_limit == 0
        assert metrics.irs_limit_rate == 0.0


# =============================================================================
# get_dc_plan_analytics (full flow)
# =============================================================================


class TestGetDCPlanAnalyticsFull:
    """Test get_dc_plan_analytics end-to-end including error handling."""

    @pytest.mark.fast
    def test_full_flow_returns_dc_plan_analytics(self, analytics_service):
        """Full flow returns a DCPlanAnalytics object with all fields populated."""
        service, db_path = analytics_service

        conn = duckdb.connect(str(db_path))
        _seed_employees(conn, [
            {
                "employee_id": "A1", "year": 2025, "status": "ACTIVE",
                "enrolled": True, "contributions": 6000, "match": 3000,
                "core": 1000, "compensation": 100000, "deferral_rate": 0.06,
                "participation_detail": "auto_enrolled",
                "has_escalations": True, "escalation_count": 1,
                "escalation_amount": 0.01, "irs_limit_reached": False,
            },
            {
                "employee_id": "A2", "year": 2025, "status": "ACTIVE",
                "enrolled": True, "contributions": 8000, "match": 4000,
                "core": 1500, "compensation": 150000, "deferral_rate": 0.05,
                "participation_detail": "voluntary",
                "has_escalations": False, "escalation_count": 0,
                "escalation_amount": 0, "irs_limit_reached": True,
            },
            {
                "employee_id": "A3", "year": 2025, "status": "ACTIVE",
                "enrolled": False, "compensation": 80000,
            },
        ])
        conn.close()

        result = service.get_dc_plan_analytics("ws", "sc", "Test Scenario")

        assert result is not None
        assert result.scenario_id == "sc"
        assert result.scenario_name == "Test Scenario"

        # Participation: 2 enrolled / 3 eligible = 66.67%
        assert result.total_eligible == 3
        assert result.total_enrolled == 2
        assert result.participation_rate == 66.67

        # Contributions
        assert result.total_employee_contributions == 14000.0  # 6000+8000
        assert result.total_employer_match == 7000.0  # 3000+4000
        assert result.total_employer_core == 2500.0  # 1000+1500

        # E066: Contribution rates
        total_comp = 100000 + 150000 + 80000  # 330000
        assert result.employee_contribution_rate == round(14000 / total_comp * 100, 2)
        assert result.match_contribution_rate == round(7000 / total_comp * 100, 2)
        assert result.core_contribution_rate == round(2500 / total_comp * 100, 2)

        # Deferral distribution
        assert len(result.deferral_rate_distribution) == 11

        # Escalation
        assert result.escalation_metrics.employees_with_escalations == 1

        # IRS limits
        assert result.irs_limit_metrics.employees_at_irs_limit == 1

    @pytest.mark.fast
    def test_database_not_found_returns_none(self):
        """When database doesn't exist, returns None."""
        mock_storage = MagicMock()
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = ResolvedDatabasePath(
            path=Path("/nonexistent/path.duckdb"), source="scenario"
        )

        service = AnalyticsService(storage=mock_storage, db_resolver=mock_resolver)
        result = service.get_dc_plan_analytics("ws", "sc", "test")

        assert result is None

    @pytest.mark.fast
    def test_duckdb_connect_error_returns_none(self):
        """Any exception during analytics retrieval returns None."""
        mock_storage = MagicMock()
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = Exception("resolve failed")

        service = AnalyticsService(storage=mock_storage, db_resolver=mock_resolver)
        result = service.get_dc_plan_analytics("ws", "sc", "test")

        assert result is None

    @pytest.mark.fast
    def test_full_flow_active_only(self, analytics_service):
        """active_only=True filters participation and contributions to active employees."""
        service, db_path = analytics_service

        conn = duckdb.connect(str(db_path))
        _seed_employees(conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "contributions": 5000, "match": 2000,
             "core": 500, "compensation": 100000},
            {"employee_id": "T1", "year": 2025, "status": "TERMINATED",
             "enrolled": True, "contributions": 3000, "match": 1000,
             "core": 300, "compensation": 80000},
        ])
        conn.close()

        result_all = service.get_dc_plan_analytics("ws", "sc", "test", active_only=False)
        result_active = service.get_dc_plan_analytics("ws", "sc", "test", active_only=True)

        assert result_all is not None
        assert result_active is not None

        # All: 2 enrolled, Active only: 1 enrolled
        assert result_all.total_eligible == 2
        assert result_active.total_eligible == 1

        # Contributions differ based on filter
        assert result_all.total_employee_contributions == 8000.0  # 5000+3000
        assert result_active.total_employee_contributions == 5000.0  # active only

    @pytest.mark.fast
    def test_full_flow_multi_year_contribution_rates(self, analytics_service):
        """Multi-year scenario computes aggregate contribution rates correctly."""
        service, db_path = analytics_service

        conn = duckdb.connect(str(db_path))
        _seed_employees(conn, [
            {"employee_id": "A1", "year": 2025, "status": "ACTIVE",
             "enrolled": True, "contributions": 5000, "match": 2000,
             "core": 1000, "compensation": 100000},
            {"employee_id": "A1", "year": 2026, "status": "ACTIVE",
             "enrolled": True, "contributions": 6000, "match": 2500,
             "core": 1200, "compensation": 110000},
        ])
        conn.close()

        result = service.get_dc_plan_analytics("ws", "sc", "test")

        assert result is not None
        assert len(result.contribution_by_year) == 2

        # Grand totals
        assert result.total_employee_contributions == 11000.0
        assert result.total_employer_match == 4500.0
        assert result.total_employer_core == 2200.0

        # Aggregate rates: total_comp = 100000+110000 = 210000
        assert result.employee_contribution_rate == round(11000 / 210000 * 100, 2)
        assert result.match_contribution_rate == round(4500 / 210000 * 100, 2)
        assert result.core_contribution_rate == round(2200 / 210000 * 100, 2)
