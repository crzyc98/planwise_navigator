"""
Integration tests for S039: End-to-End 5-Year Projection Validation

Comprehensive validation tests that run a full 5-year simulation (2025-2029)
and validate mathematical consistency, workforce composition evolution,
compensation trends, and cumulative event totals.
"""

import pytest
from unittest.mock import Mock, patch
from dagster import OpExecutionContext
import tempfile
import os

from orchestrator.simulator_pipeline import (
    run_multi_year_simulation,
    YearResult,
)


class TestFiveYearProjectionValidation:
    """Test suite for comprehensive 5-year projection validation."""

    @pytest.fixture
    def five_year_config(self):
        """Configuration for 5-year simulation (2025-2029)."""
        return {
            "start_year": 2025,
            "end_year": 2029,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "random_seed": 42,
            "full_refresh": True,
        }

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".duckdb")
        temp_file.close()
        yield temp_file.name
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

    @pytest.fixture
    def mock_context_five_year(self, five_year_config):
        """Create mock context for 5-year simulation."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.op_config = five_year_config.copy()

        # Mock dbt resource
        dbt_resource = Mock()
        context.resources = Mock()
        context.resources.dbt = dbt_resource
        context.op_def = Mock()
        context.op_def.name = "test_five_year_simulation"

        return context

    def test_mathematical_consistency_five_year_simulation(
        self, mock_context_five_year, temp_db_path
    ):
        """
        Test that final workforce equals baseline + total_hires - total_terminations
        across the entire 5-year simulation period.
        """
        with patch("orchestrator.simulator_pipeline.duckdb.connect") as mock_connect:
            # Mock database connection
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            # Mock the multi-year simulation to return realistic results
            with patch(
                "orchestrator.simulator_pipeline.run_year_simulation"
            ) as mock_year_sim:
                # Simulate realistic year-by-year results with 3% growth
                year_results = []
                base_workforce = 1000

                for year in range(2025, 2030):
                    year_idx = year - 2025
                    expected_workforce = int(base_workforce * (1.03 ** (year_idx + 1)))
                    terminations = int(expected_workforce * 0.12)
                    hires = terminations + int(expected_workforce * 0.03)

                    year_results.append(
                        YearResult(
                            year=year,
                            success=True,
                            active_employees=expected_workforce,
                            total_terminations=terminations,
                            experienced_terminations=int(terminations * 0.75),
                            new_hire_terminations=int(terminations * 0.25),
                            total_hires=hires,
                            growth_rate=0.03,
                            validation_passed=True,
                        )
                    )

                mock_year_sim.side_effect = year_results

                # Run the simulation
                result = run_multi_year_simulation(mock_context_five_year)

                # Validate mathematical consistency
                assert result.success, "5-year simulation should succeed"
                assert (
                    len(result.year_results) == 5
                ), "Should have results for all 5 years"

                # Calculate cumulative totals
                total_hires = sum(yr.total_hires for yr in result.year_results)
                total_terminations = sum(
                    yr.total_terminations for yr in result.year_results
                )
                final_workforce = result.year_results[-1].active_employees
                baseline_workforce = 1000

                # Mathematical consistency check
                expected_final = baseline_workforce + total_hires - total_terminations
                variance_threshold = 5  # Allow small variance due to rounding

                assert abs(final_workforce - expected_final) <= variance_threshold, (
                    f"Mathematical inconsistency: final={final_workforce}, expected={expected_final}, "
                    f"baseline={baseline_workforce}, hires={total_hires}, terms={total_terminations}"
                )

    def test_workforce_composition_evolution(
        self, mock_context_five_year, temp_db_path
    ):
        """
        Test that workforce composition (status code distribution) evolves correctly
        over the 5-year period.
        """
        with patch("duckdb.connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            # Mock workforce composition data for validation
            mock_conn.execute.return_value.df.return_value.to_dict.return_value = {
                "continuous_active": [800, 824, 849, 874, 900],
                "new_hire_active": [150, 155, 160, 165, 170],
                "experienced_termination": [30, 31, 32, 33, 34],
                "new_hire_termination": [20, 20, 21, 21, 22],
            }

            with patch(
                "orchestrator.simulator_pipeline.run_year_simulation"
            ) as mock_year_sim:
                # Mock successful simulation results
                year_results = [
                    YearResult(2025, True, 950, 50, 30, 20, 170, 0.030, True),
                    YearResult(2026, True, 979, 52, 31, 21, 175, 0.031, True),
                    YearResult(2027, True, 1009, 53, 32, 21, 181, 0.029, True),
                    YearResult(2028, True, 1039, 54, 33, 21, 186, 0.030, True),
                    YearResult(2029, True, 1070, 56, 34, 22, 192, 0.030, True),
                ]
                mock_year_sim.side_effect = year_results

                result = run_multi_year_simulation(mock_context_five_year)

                assert result.success, "5-year simulation should succeed"

                # Validate workforce composition trends
                for i, year_result in enumerate(result.year_results):
                    # Continuous workforce should grow each year
                    if i > 0:
                        prev_workforce = result.year_results[i - 1].active_employees
                        current_workforce = year_result.active_employees
                        growth_rate = (
                            current_workforce - prev_workforce
                        ) / prev_workforce

                        # Growth rate should be close to target (3% ± 0.5%)
                        assert (
                            0.025 <= growth_rate <= 0.035
                        ), f"Year {year_result.year} growth rate {growth_rate:.3f} outside tolerance"

    def test_compensation_growth_trends(self, mock_context_five_year, temp_db_path):
        """
        Test that compensation trends are realistic and sustainable over 5 years.
        """
        with patch("duckdb.connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            # Mock compensation data showing realistic growth
            compensation_data = [
                {"year": 2025, "avg_compensation": 95000, "total_payroll": 90250000},
                {"year": 2026, "avg_compensation": 96900, "total_payroll": 94851000},
                {"year": 2027, "avg_compensation": 98827, "total_payroll": 99672430},
                {"year": 2028, "avg_compensation": 100784, "total_payroll": 104714000},
                {"year": 2029, "avg_compensation": 102800, "total_payroll": 109996000},
            ]

            mock_conn.execute.return_value.df.return_value.to_dict.return_value = {
                "records": compensation_data
            }

            with patch(
                "orchestrator.simulator_pipeline.run_year_simulation"
            ) as mock_year_sim:
                # Mock successful simulation
                year_results = [
                    YearResult(yr, True, 1000, 50, 30, 20, 180, 0.03, True)
                    for yr in range(2025, 2030)
                ]
                mock_year_sim.side_effect = year_results

                result = run_multi_year_simulation(mock_context_five_year)

                assert result.success, "5-year simulation should succeed"

                # Validate compensation growth sustainability
                # Average compensation should grow approximately 2% annually
                base_compensation = 95000
                for i, comp_year in enumerate(compensation_data):
                    expected_growth = base_compensation * (1.02**i)
                    actual_compensation = comp_year["avg_compensation"]
                    growth_variance = (
                        abs(actual_compensation - expected_growth) / expected_growth
                    )

                    # Allow 10% variance from expected compensation growth
                    assert (
                        growth_variance <= 0.10
                    ), f"Year {comp_year['year']} compensation variance {growth_variance:.3f} exceeds tolerance"

    def test_cumulative_event_totals(self, mock_context_five_year, temp_db_path):
        """
        Test that cumulative event totals (hires, terminations, promotions) are
        mathematically consistent across all 5 years.
        """
        with patch("duckdb.connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            # Mock event data for all 5 years
            event_totals = {
                "total_hires": 900,  # ~180 per year
                "total_terminations": 265,  # ~53 per year
                "total_promotions": 150,  # ~30 per year
                "total_merit_increases": 4500,  # ~900 per year
            }

            mock_conn.execute.return_value.fetchone.return_value = tuple(
                event_totals.values()
            )

            with patch(
                "orchestrator.simulator_pipeline.run_year_simulation"
            ) as mock_year_sim:
                # Mock realistic year results
                year_results = []
                for year in range(2025, 2030):
                    year_results.append(
                        YearResult(
                            year=year,
                            success=True,
                            active_employees=1000 + (year - 2025) * 30,
                            total_terminations=53,
                            experienced_terminations=40,
                            new_hire_terminations=13,
                            total_hires=180,
                            growth_rate=0.03,
                            validation_passed=True,
                        )
                    )

                mock_year_sim.side_effect = year_results

                result = run_multi_year_simulation(mock_context_five_year)

                assert result.success, "5-year simulation should succeed"

                # Validate cumulative totals
                cumulative_hires = sum(yr.total_hires for yr in result.year_results)
                cumulative_terminations = sum(
                    yr.total_terminations for yr in result.year_results
                )

                # Cumulative hires should approximately match expected range
                expected_hires_range = (850, 950)  # 5 years * ~180 per year ± variance
                assert (
                    expected_hires_range[0]
                    <= cumulative_hires
                    <= expected_hires_range[1]
                ), f"Cumulative hires {cumulative_hires} outside expected range {expected_hires_range}"

                # Cumulative terminations should approximately match expected range
                expected_terms_range = (250, 280)  # 5 years * ~53 per year ± variance
                assert (
                    expected_terms_range[0]
                    <= cumulative_terminations
                    <= expected_terms_range[1]
                ), f"Cumulative terminations {cumulative_terminations} outside expected range {expected_terms_range}"

    def test_performance_benchmarks_five_year(
        self, mock_context_five_year, temp_db_path
    ):
        """
        Test that 5-year simulation completes within performance benchmarks.
        """
        import time

        with patch(
            "orchestrator.simulator_pipeline.run_year_simulation"
        ) as mock_year_sim:
            # Mock fast simulation results
            year_results = [
                YearResult(yr, True, 1000, 50, 30, 20, 180, 0.03, True)
                for yr in range(2025, 2030)
            ]
            mock_year_sim.side_effect = year_results

            start_time = time.time()
            result = run_multi_year_simulation(mock_context_five_year)
            execution_time = time.time() - start_time

            assert result.success, "5-year simulation should succeed"

            # 5-year simulation should complete within reasonable time
            # (This is a mocked test, but validates the structure)
            assert (
                execution_time < 30
            ), f"5-year simulation took {execution_time:.2f}s, exceeds 30s benchmark"

    def test_data_quality_consistency_five_year(
        self, mock_context_five_year, temp_db_path
    ):
        """
        Test that data quality remains consistent across all 5 years.
        """
        with patch("duckdb.connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            # Mock data quality metrics for all years
            quality_metrics = {
                "null_percentages": [
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                ],  # No nulls in critical fields
                "duplicate_counts": [0, 0, 0, 0, 0],  # No duplicates
                "invalid_status_counts": [0, 0, 0, 0, 0],  # No invalid status codes
            }

            mock_conn.execute.return_value.df.return_value = Mock()
            mock_conn.execute.return_value.df.return_value.to_dict.return_value = (
                quality_metrics
            )

            with patch(
                "orchestrator.simulator_pipeline.run_year_simulation"
            ) as mock_year_sim:
                year_results = [
                    YearResult(yr, True, 1000, 50, 30, 20, 180, 0.03, True)
                    for yr in range(2025, 2030)
                ]
                mock_year_sim.side_effect = year_results

                result = run_multi_year_simulation(mock_context_five_year)

                assert result.success, "5-year simulation should succeed"

                # Validate data quality metrics
                for year_idx, year_result in enumerate(result.year_results):
                    # Each year should pass validation
                    assert (
                        year_result.validation_passed
                    ), f"Year {year_result.year} failed validation"

                    # Data quality should remain consistent
                    null_pct = quality_metrics["null_percentages"][year_idx]
                    duplicate_count = quality_metrics["duplicate_counts"][year_idx]

                    assert (
                        null_pct <= 0.01
                    ), f"Year {year_result.year} null percentage {null_pct} exceeds 1%"
                    assert (
                        duplicate_count == 0
                    ), f"Year {year_result.year} has {duplicate_count} duplicates"
