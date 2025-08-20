"""
Integration Tests for Hiring Calculation Formula Fix

This module contains integration tests to verify that the unified hiring
calculation formula works properly across the entire simulation pipeline,
including Python-SQL consistency and end-to-end simulation validation.

Test Coverage:
- Python-SQL calculation consistency
- Full simulation pipeline with unified formula
- Multi-year simulation consistency
- Configuration scenario testing
- End-to-end growth rate validation
"""

import os
# Import simulation components
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import duckdb
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator_mvp"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from orchestrator.simulator_pipeline import (
    _log_hiring_calculation_debug, run_year_simulation_for_multi_year,
    validate_year_results)
from orchestrator_mvp.core.workforce_calculations import \
    calculate_workforce_requirements

# Test configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent
TEST_DB_PATH = PROJECT_ROOT / "test_simulation.duckdb"


class TestHiringCalculationIntegration:
    """Integration test suite for the unified hiring calculation formula."""

    @pytest.fixture(autouse=True)
    def setup_test_database(self):
        """Set up a clean test database for each test."""
        # Clean up any existing test database
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

        # Create test database with minimal required tables
        conn = duckdb.connect(str(TEST_DB_PATH))

        # Create baseline workforce table
        conn.execute(
            """
            CREATE TABLE int_baseline_workforce (
                employee_id VARCHAR,
                employment_status VARCHAR,
                current_compensation DECIMAL,
                current_age INTEGER
            )
        """
        )

        # Insert test baseline data
        conn.execute(
            """
            INSERT INTO int_baseline_workforce
            SELECT
                'EMP_' || i::VARCHAR as employee_id,
                'active' as employment_status,
                50000 + (i % 100000) as current_compensation,
                25 + (i % 40) as current_age
            FROM range(1, 1001) t(i)
        """
        )

        # Create required tables for simulation
        conn.execute(
            """
            CREATE TABLE fct_yearly_events (
                simulation_year INTEGER,
                event_type VARCHAR,
                event_category VARCHAR,
                employee_id VARCHAR,
                effective_date DATE
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE fct_workforce_snapshot (
                simulation_year INTEGER,
                employee_id VARCHAR,
                employment_status VARCHAR,
                detailed_status_code VARCHAR
            )
        """
        )

        conn.close()
        yield

        # Cleanup
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def test_python_sql_calculation_consistency(self):
        """Test that Python and SQL calculations produce identical results."""
        # Test parameters
        workforce_count = 1000
        target_growth_rate = 0.03
        total_termination_rate = 0.12
        new_hire_termination_rate = 0.25

        # Python calculation using unified function
        python_result = calculate_workforce_requirements(
            workforce_count,
            target_growth_rate,
            total_termination_rate,
            new_hire_termination_rate,
        )

        # SQL calculation using the unified formula
        conn = duckdb.connect(str(TEST_DB_PATH))

        sql_result = conn.execute(
            """
            WITH workforce_count AS (
                SELECT 1000 AS workforce_count
            ),
            calculation AS (
                SELECT
                    workforce_count,
                    workforce_count * 0.12 AS experienced_terminations_exact,
                    CEIL(workforce_count * 0.12) AS experienced_terminations,
                    workforce_count * 0.03 AS growth_amount,

                    -- UNIFIED FORMULA: Calculate net hires needed then apply termination rate
                    CEIL(workforce_count * 0.12) + (workforce_count * 0.03) AS net_hires_needed,
                    CEIL((CEIL(workforce_count * 0.12) + (workforce_count * 0.03)) / (1 - 0.25)) AS total_hires_needed,

                    -- Derived fields for reporting
                    CEIL(workforce_count * 0.12) AS replacement_hires
                FROM workforce_count
            ),
            final_calc AS (
                SELECT
                    *,
                    total_hires_needed - replacement_hires AS growth_hires
                FROM calculation
            )
            SELECT
                experienced_terminations,
                growth_amount,
                replacement_hires,
                growth_hires,
                total_hires_needed,
                ROUND(total_hires_needed * 0.25) AS expected_new_hire_terminations
            FROM final_calc
        """
        ).fetchone()

        conn.close()

        # Verify consistency
        assert python_result["experienced_terminations"] == sql_result[0]
        assert python_result["growth_amount"] == sql_result[1]
        assert python_result["replacement_hires"] == sql_result[2]
        assert python_result["growth_hires"] == sql_result[3]
        assert python_result["total_hires_needed"] == sql_result[4]
        assert python_result["expected_new_hire_terminations"] == sql_result[5]

    def test_multiple_scenario_consistency(self):
        """Test Python-SQL consistency across multiple scenarios."""
        scenarios = [
            (1000, 0.03, 0.12, 0.25),
            (500, 0.05, 0.10, 0.20),
            (2000, 0.02, 0.15, 0.30),
            (5036, 0.03, 0.12, 0.25),  # User's specific case
        ]

        for workforce, growth_rate, term_rate, new_hire_rate in scenarios:
            # Python calculation
            python_result = calculate_workforce_requirements(
                workforce, growth_rate, term_rate, new_hire_rate
            )

            # SQL calculation using unified formula
            conn = duckdb.connect(str(TEST_DB_PATH))
            sql_result = conn.execute(
                f"""
                WITH calculation AS (
                    SELECT
                        CEIL({workforce} * {term_rate}) AS experienced_terminations,
                        {workforce} * {growth_rate} AS growth_amount,
                        CEIL((CEIL({workforce} * {term_rate}) + ({workforce} * {growth_rate})) / (1 - {new_hire_rate})) AS total_hires_needed
                ),
                final_calc AS (
                    SELECT
                        experienced_terminations AS replacement_hires,
                        total_hires_needed - experienced_terminations AS growth_hires,
                        total_hires_needed
                    FROM calculation
                )
                SELECT
                    replacement_hires,
                    growth_hires,
                    total_hires_needed
                FROM final_calc
            """
            ).fetchone()
            conn.close()

            # Verify consistency
            assert python_result["replacement_hires"] == sql_result[0]
            assert python_result["growth_hires"] == sql_result[1]
            assert python_result["total_hires_needed"] == sql_result[2]

    def test_unified_formula_vs_separated_formula(self):
        """Demonstrate the difference between unified and separated formulas."""
        workforce = 5036
        growth_rate = 0.03
        term_rate = 0.12
        new_hire_rate = 0.25

        # Unified formula (current implementation)
        unified = calculate_workforce_requirements(
            workforce, growth_rate, term_rate, new_hire_rate
        )

        # Separated formula (previous approach that was mathematically incorrect)
        import math

        experienced_terms = math.ceil(workforce * term_rate)
        growth_amount = workforce * growth_rate
        separated_replacement = experienced_terms
        separated_growth = math.ceil(growth_amount / (1 - new_hire_rate))
        separated_total = separated_replacement + separated_growth

        # The unified formula should produce MORE hires than separated
        increase = unified["total_hires_needed"] - separated_total

        # For the user's scenario, unified should be 1009, separated would be 807
        assert unified["total_hires_needed"] == 1009
        assert separated_total == 807
        assert increase == 202  # Should be exactly 202 more hires

        # Unified total should achieve target growth more accurately
        expected_net_growth = workforce * growth_rate  # ~151
        actual_net_growth = (
            unified["net_hiring_impact"] - unified["experienced_terminations"]
        )

        # Should be close to target growth
        assert abs(actual_net_growth - expected_net_growth) < 10

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_simulation_pipeline_integration(self, mock_connect):
        """Test that the corrected formula integrates properly with simulation pipeline."""
        # Setup mock database connection
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        # Mock baseline workforce count
        mock_conn.execute.return_value.fetchone.return_value = [1000]

        # Create test context
        from dagster import build_op_context

        context = build_op_context(
            op_config={
                "start_year": 2025,
                "target_growth_rate": 0.03,
                "total_termination_rate": 0.12,
                "new_hire_termination_rate": 0.25,
                "random_seed": 42,
                "full_refresh": False,
            },
            resources={"dbt": Mock()},
        )

        # Test the debug logging function
        config = {
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
        }

        debug_result = _log_hiring_calculation_debug(context, 2025, config)

        # Verify the debug result uses unified calculations
        assert debug_result["workforce_count"] == 1000
        assert debug_result["total_hires_needed"] == 200  # Unified: CEIL(150 / 0.75)
        assert debug_result["experienced_terms"] == 120
        assert debug_result["net_hiring_impact"] == 150

    def test_end_to_end_growth_rate_validation(self):
        """Test that corrected formula achieves target growth rates in practice."""
        test_scenarios = [
            {"workforce": 1000, "target_growth": 0.03, "tolerance": 0.005},
            {"workforce": 2000, "target_growth": 0.05, "tolerance": 0.005},
            {"workforce": 500, "target_growth": 0.02, "tolerance": 0.01},
        ]

        for scenario in test_scenarios:
            workforce = scenario["workforce"]
            target_growth = scenario["target_growth"]
            tolerance = scenario["tolerance"]

            # Calculate hiring requirements
            result = calculate_workforce_requirements(
                workforce,
                target_growth,
                total_termination_rate=0.12,
                new_hire_termination_rate=0.25,
            )

            # Simulate the net effect
            starting_workforce = workforce
            experienced_terminations = result["experienced_terminations"]
            total_hires = result["total_hires_needed"]
            new_hire_terminations = result["expected_new_hire_terminations"]

            # Calculate ending workforce
            ending_workforce = (
                starting_workforce
                - experienced_terminations
                + total_hires
                - new_hire_terminations
            )

            # Calculate actual growth rate
            actual_growth_rate = (
                ending_workforce - starting_workforce
            ) / starting_workforce

            # Verify it's close to target
            assert abs(actual_growth_rate - target_growth) <= tolerance

    def test_multi_year_consistency(self):
        """Test that the corrected formula maintains consistency across multiple years."""
        # Simulate a 3-year progression
        years = [2025, 2026, 2027]
        workforce_progression = []
        initial_workforce = 1000
        current_workforce = initial_workforce

        for year in years:
            result = calculate_workforce_requirements(
                current_workforce,
                target_growth_rate=0.03,
                total_termination_rate=0.12,
                new_hire_termination_rate=0.25,
            )

            # Calculate year-end workforce
            year_end_workforce = (
                current_workforce
                - result["experienced_terminations"]
                + result["total_hires_needed"]
                - result["expected_new_hire_terminations"]
            )

            workforce_progression.append(
                {
                    "year": year,
                    "starting_workforce": current_workforce,
                    "ending_workforce": year_end_workforce,
                    "growth_rate": (year_end_workforce - current_workforce)
                    / current_workforce,
                    "total_hires": result["total_hires_needed"],
                }
            )

            current_workforce = year_end_workforce

        # Verify consistent growth rates
        for progression in workforce_progression:
            assert abs(progression["growth_rate"] - 0.03) < 0.005

        # Verify compound growth
        final_workforce = workforce_progression[-1]["ending_workforce"]
        compound_growth = (final_workforce / initial_workforce) ** (1 / 3) - 1
        assert abs(compound_growth - 0.03) < 0.01

    def test_extreme_parameter_handling(self):
        """Test integration with extreme but valid parameter combinations."""
        extreme_scenarios = [
            {
                "name": "high_growth_low_termination",
                "workforce": 1000,
                "growth_rate": 0.15,
                "term_rate": 0.05,
                "new_hire_rate": 0.10,
            },
            {
                "name": "low_growth_high_termination",
                "workforce": 1000,
                "growth_rate": 0.01,
                "term_rate": 0.25,
                "new_hire_rate": 0.40,
            },
            {
                "name": "high_new_hire_termination",
                "workforce": 1000,
                "growth_rate": 0.05,
                "term_rate": 0.12,
                "new_hire_rate": 0.80,
            },
        ]

        for scenario in extreme_scenarios:
            result = calculate_workforce_requirements(
                scenario["workforce"],
                scenario["growth_rate"],
                scenario["term_rate"],
                scenario["new_hire_rate"],
            )

            # Basic sanity checks
            assert result["total_hires_needed"] > 0
            assert result["replacement_hires"] == result["experienced_terminations"]
            assert result["total_hires_needed"] == (
                result["replacement_hires"] + result["growth_hires"]
            )

            # For high new hire termination rates, ensure we hire enough
            if scenario["new_hire_rate"] > 0.5:
                assert result["growth_hires"] > result["growth_amount"]

    def test_real_world_configuration_scenarios(self):
        """Test with realistic configuration combinations from different industries."""
        industry_scenarios = [
            {
                "name": "technology_startup",
                "workforce": 150,
                "growth_rate": 0.25,  # High growth
                "term_rate": 0.15,  # Moderate turnover
                "new_hire_rate": 0.30,  # High new hire turnover
            },
            {
                "name": "mature_enterprise",
                "workforce": 10000,
                "growth_rate": 0.02,  # Conservative growth
                "term_rate": 0.08,  # Low turnover
                "new_hire_rate": 0.15,  # Low new hire turnover
            },
            {
                "name": "consulting_firm",
                "workforce": 2500,
                "growth_rate": 0.08,  # Moderate growth
                "term_rate": 0.20,  # High turnover
                "new_hire_rate": 0.25,  # Moderate new hire turnover
            },
        ]

        for scenario in industry_scenarios:
            result = calculate_workforce_requirements(
                scenario["workforce"],
                scenario["growth_rate"],
                scenario["term_rate"],
                scenario["new_hire_rate"],
            )

            # Verify reasonable hiring ratios
            hiring_ratio = result["total_hires_needed"] / scenario["workforce"]

            # Should not exceed 50% of workforce in most realistic scenarios
            assert hiring_ratio <= 0.5

            # Should be at least the termination rate
            assert hiring_ratio >= scenario["term_rate"]

            # Net impact should approximate growth target
            net_ratio = result["net_hiring_impact"] / scenario["workforce"]
            assert abs(net_ratio - scenario["growth_rate"]) <= 0.02

    def test_database_integration_end_to_end(self):
        """Test the corrected formula with actual database operations."""
        conn = duckdb.connect(str(TEST_DB_PATH))

        # Insert test hiring calculation using corrected SQL formula
        conn.execute(
            """
            CREATE TABLE test_hiring_calculation AS
            WITH workforce_count AS (
                SELECT 1000 AS workforce_count
            ),
            parameters AS (
                SELECT
                    workforce_count,
                    0.03 AS target_growth_rate,
                    0.12 AS total_termination_rate,
                    0.25 AS new_hire_termination_rate
                FROM workforce_count
            ),
            corrected_calculation AS (
                SELECT
                    workforce_count,
                    target_growth_rate,
                    total_termination_rate,
                    new_hire_termination_rate,

                    -- UNIFIED FORMULA: Calculate net hires needed then apply termination rate
                    CEIL(workforce_count * total_termination_rate) + (workforce_count * target_growth_rate) AS net_hires_needed,
                    CEIL((CEIL(workforce_count * total_termination_rate) + (workforce_count * target_growth_rate)) / (1 - new_hire_termination_rate)) AS total_hires_needed,

                    -- Derived fields for reporting
                    CEIL(workforce_count * total_termination_rate) AS replacement_hires,
                    CEIL((CEIL(workforce_count * total_termination_rate) + (workforce_count * target_growth_rate)) / (1 - new_hire_termination_rate)) - CEIL(workforce_count * total_termination_rate) AS growth_hires
                FROM parameters
            )
            SELECT * FROM corrected_calculation
        """
        )

        # Retrieve the calculated values
        db_result = conn.execute(
            """
            SELECT
                replacement_hires,
                growth_hires,
                total_hires_needed
            FROM test_hiring_calculation
        """
        ).fetchone()

        conn.close()

        # Compare with Python calculation
        python_result = calculate_workforce_requirements(1000, 0.03, 0.12, 0.25)

        assert db_result[0] == python_result["replacement_hires"]
        assert db_result[1] == python_result["growth_hires"]
        assert db_result[2] == python_result["total_hires_needed"]
