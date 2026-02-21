"""Tests for results_reader module."""

import pytest

from planalign_api.services.simulation.results_reader import (
    _calc_cagr,
    _compute_cagr_metrics,
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
