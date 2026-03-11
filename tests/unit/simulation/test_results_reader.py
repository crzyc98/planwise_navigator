"""Tests for results_reader module."""

import duckdb
import pytest

from planalign_api.services.simulation.results_reader import (
    _calc_cagr,
    _compute_cagr_metrics,
    _query_workforce_progression,
    _query_participation_rate,
)


@pytest.mark.fast
class TestCalcCagr:
    """Test the _calc_cagr helper."""

    def test_positive_growth(self):
        result = _calc_cagr(100, 110, 1)
        assert abs(result - 10.0) < 0.01

    def test_multi_year_growth(self):
        # 100 -> 121 over 2 years = 10% CAGR
        result = _calc_cagr(100, 121, 2)
        assert abs(result - 10.0) < 0.1

    def test_zero_start_returns_zero(self):
        assert _calc_cagr(0, 100, 1) == 0.0

    def test_zero_years_returns_zero(self):
        assert _calc_cagr(100, 200, 0) == 0.0

    def test_negative_start_returns_zero(self):
        assert _calc_cagr(-10, 100, 1) == 0.0


@pytest.mark.fast
class TestComputeCagrMetrics:
    """Test _compute_cagr_metrics function."""

    def test_empty_progression_returns_defaults(self):
        metrics, summary = _compute_cagr_metrics([])
        assert metrics == []
        assert summary["final_headcount"] == 0
        assert summary["start_year"] == 2025
        assert summary["end_year"] == 2027

    def test_single_year_progression(self):
        progression = [
            {
                "simulation_year": 2025,
                "headcount": 100,
                "total_compensation": 10_000_000,
                "active_avg_compensation": 100_000,
            }
        ]
        metrics, summary = _compute_cagr_metrics(progression)
        assert summary["final_headcount"] == 100
        assert summary["start_year"] == 2025
        assert summary["end_year"] == 2025
        # years = 0, so CAGR = 0
        assert summary["cagr"] == 0.0
        assert len(metrics) == 3

    def test_multi_year_progression(self):
        progression = [
            {
                "simulation_year": 2025,
                "headcount": 100,
                "total_compensation": 10_000_000,
                "active_avg_compensation": 100_000,
            },
            {
                "simulation_year": 2026,
                "headcount": 105,
                "total_compensation": 10_500_000,
                "active_avg_compensation": 100_000,
            },
            {
                "simulation_year": 2027,
                "headcount": 110,
                "total_compensation": 11_000_000,
                "active_avg_compensation": 100_000,
            },
        ]
        metrics, summary = _compute_cagr_metrics(progression)

        assert summary["start_year"] == 2025
        assert summary["end_year"] == 2027
        assert summary["final_headcount"] == 110
        assert summary["total_growth_pct"] == pytest.approx(10.0)

        # Should have 3 metric entries
        assert len(metrics) == 3
        metric_names = [m["metric"] for m in metrics]
        assert "Total Headcount" in metric_names
        assert "Total Compensation" in metric_names
        assert "Average Compensation" in metric_names

    def test_handles_none_compensation_values(self):
        """Should handle None values in compensation fields."""
        progression = [
            {
                "simulation_year": 2025,
                "headcount": 100,
                "total_compensation": None,
                "active_avg_compensation": None,
            },
            {
                "simulation_year": 2027,
                "headcount": 110,
                "total_compensation": 11_000_000,
                "active_avg_compensation": 100_000,
            },
        ]
        metrics, summary = _compute_cagr_metrics(progression)
        assert summary["final_headcount"] == 110
        # Comp CAGR should be 0 since start is 0
        comp_metric = next(m for m in metrics if m["metric"] == "Total Compensation")
        assert comp_metric["start_value"] == 0


@pytest.mark.fast
class TestWorkforceProgressionQuery:
    """Test _query_workforce_progression respects the pop_filter."""

    def _make_db(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect()
        conn.execute("""
            CREATE TABLE fct_workforce_snapshot (
                employee_id VARCHAR,
                simulation_year INTEGER,
                employment_status VARCHAR,
                prorated_annual_compensation DOUBLE
            )
        """)
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                -- 2025: 3 active, 2 terminated
                ('E001', 2025, 'active', 100000),
                ('E002', 2025, 'active', 110000),
                ('E003', 2025, 'active', 90000),
                ('E004', 2025, 'terminated', 80000),
                ('E005', 2025, 'terminated', 70000),
                -- 2026: 4 active, 1 terminated
                ('E001', 2026, 'active', 104000),
                ('E002', 2026, 'active', 114000),
                ('E003', 2026, 'active', 93000),
                ('E006', 2026, 'active', 95000),
                ('E007', 2026, 'terminated', 60000)
        """)
        return conn

    def test_active_filter_counts_only_active_employees(self):
        conn = self._make_db()
        active_filter = " AND LOWER(employment_status) = 'active'"
        result = _query_workforce_progression(conn, 2025, 2026, active_filter)
        conn.close()

        assert len(result) == 2
        row_2025 = next(r for r in result if r["simulation_year"] == 2025)
        row_2026 = next(r for r in result if r["simulation_year"] == 2026)
        assert row_2025["headcount"] == 3, "active filter: 2025 should count 3"
        assert row_2026["headcount"] == 4, "active filter: 2026 should count 4"

    def test_no_filter_counts_all_employees(self):
        conn = self._make_db()
        result = _query_workforce_progression(conn, 2025, 2026, pop_filter="")
        conn.close()

        row_2025 = next(r for r in result if r["simulation_year"] == 2025)
        assert row_2025["headcount"] == 5, "no filter: 2025 should count all 5"

    def test_active_filter_compensation_excludes_terminated(self):
        conn = self._make_db()
        active_filter = " AND LOWER(employment_status) = 'active'"
        result = _query_workforce_progression(conn, 2025, 2025, active_filter)
        conn.close()

        row = result[0]
        expected_avg = (100000 + 110000 + 90000) / 3
        assert abs(row["avg_compensation"] - expected_avg) < 0.01


@pytest.mark.fast
class TestParticipationRateQuery:
    """Test that _query_participation_rate respects the pop_filter."""

    def _make_db(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect()
        conn.execute("""
            CREATE TABLE fct_workforce_snapshot (
                employee_id VARCHAR,
                simulation_year INTEGER,
                employment_status VARCHAR,
                participation_status VARCHAR,
                prorated_annual_compensation DOUBLE
            )
        """)
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('E001', 2026, 'active', 'participating', 100000),
                ('E002', 2026, 'active', 'participating', 100000),
                ('E003', 2026, 'active', 'not_participating', 100000),
                ('E004', 2026, 'terminated', 'participating', 100000),
                ('E005', 2026, 'terminated', 'not_participating', 100000)
        """)
        return conn

    def test_active_filter_excludes_terminated_from_denominator(self):
        active_filter = " AND LOWER(employment_status) = 'active'"
        conn = self._make_db()
        rate = _query_participation_rate(conn, 2026, active_filter)
        conn.close()

        # 2 participating active / 3 active = 66.7%, not 2/5 = 40%
        assert abs(rate - 2 / 3) < 0.001, f"Expected ~66.7% but got {rate:.1%}"
