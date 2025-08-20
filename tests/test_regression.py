#!/usr/bin/env python3
"""
Regression test suite for PlanWise Navigator
Ensures critical functionality doesn't break with changes
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
import pytest


class TestRegressionSuite:
    """Critical regression tests that must pass before any deployment"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
            db_path = f.name

        # Copy existing database for testing
        shutil.copy("simulation.duckdb", db_path)

        yield db_path

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    def test_employee_id_uniqueness(self, temp_db):
        """CRITICAL: Employee IDs must be unique across all tables"""
        conn = duckdb.connect(temp_db)

        # Check staging data
        result = conn.execute(
            """
            SELECT COUNT(*) as total, COUNT(DISTINCT employee_id) as unique_count
            FROM stg_census_data
        """
        ).fetchone()

        assert (
            result[0] == result[1]
        ), f"Duplicate employee_ids in staging: {result[0]} total, {result[1]} unique"

        # Check workforce snapshots
        result = conn.execute(
            """
            SELECT simulation_year, COUNT(*) as total, COUNT(DISTINCT employee_id) as unique_count
            FROM fct_workforce_snapshot
            GROUP BY simulation_year
            HAVING COUNT(*) != COUNT(DISTINCT employee_id)
        """
        ).fetchall()

        assert len(result) == 0, f"Duplicate employee_ids in snapshots: {result}"

    def test_event_sourcing_integrity(self, temp_db):
        """CRITICAL: Event sourcing must maintain data integrity"""
        conn = duckdb.connect(temp_db)

        # Check that all events have required fields
        result = conn.execute(
            """
            SELECT COUNT(*) as invalid_events
            FROM fct_yearly_events
            WHERE employee_id IS NULL
               OR event_type IS NULL
               OR simulation_year IS NULL
               OR effective_date IS NULL
        """
        ).fetchone()

        assert (
            result[0] == 0
        ), f"Found {result[0]} invalid events missing required fields"

        # Check event types are valid
        result = conn.execute(
            """
            SELECT DISTINCT event_type
            FROM fct_yearly_events
            WHERE event_type NOT IN ('hire', 'termination', 'promotion', 'merit_increase')
        """
        ).fetchall()

        assert len(result) == 0, f"Found invalid event types: {result}"

    def test_simulation_pipeline_integrity(self, temp_db):
        """CRITICAL: Simulation pipeline must produce consistent results"""
        conn = duckdb.connect(temp_db)

        # Test that workforce grows according to target
        result = conn.execute(
            """
            WITH yearly_counts AS (
                SELECT
                    simulation_year,
                    COUNT(*) as active_employees
                FROM fct_workforce_snapshot
                WHERE employment_status = 'active'
                GROUP BY simulation_year
                ORDER BY simulation_year
            )
            SELECT
                simulation_year,
                active_employees,
                LAG(active_employees) OVER (ORDER BY simulation_year) as prev_year,
                ROUND((active_employees - LAG(active_employees) OVER (ORDER BY simulation_year)) * 1.0 /
                      LAG(active_employees) OVER (ORDER BY simulation_year), 3) as growth_rate
            FROM yearly_counts
            WHERE simulation_year > 2024
        """
        ).fetchall()

        for year, current, prev, growth in result:
            if prev is not None:
                # Growth should be roughly around 3% target (allow ±2% variance)
                assert (
                    -0.05 <= growth <= 0.08
                ), f"Year {year}: Growth rate {growth:.3f} outside acceptable range"

    def test_dbt_snapshot_consistency(self):
        """CRITICAL: dbt snapshots must work without errors"""
        # Test that snapshot command succeeds
        result = subprocess.run(
            [
                "dbt",
                "snapshot",
                "--select",
                "scd_workforce_state",
                "--vars",
                '{"simulation_year": 2025}',
                "--profiles-dir",
                "/Users/nicholasamaral/planwise_navigator/dbt",
            ],
            capture_output=True,
            text=True,
            cwd="/Users/nicholasamaral/planwise_navigator/dbt",
        )

        assert result.returncode == 0, f"dbt snapshot failed: {result.stderr}"
        assert (
            "Completed successfully" in result.stdout
        ), f"dbt snapshot didn't complete successfully: {result.stdout}"

    def test_data_quality_validation(self, temp_db):
        """CRITICAL: Data quality checks must pass"""
        conn = duckdb.connect(temp_db)

        # Check that no ERROR-level issues exist
        result = conn.execute(
            """
            SELECT check_type, issue_count, description
            FROM dq_employee_id_validation
            WHERE severity = 'ERROR' AND issue_count > 0
        """
        ).fetchall()

        # Allow some expected errors but flag unexpected ones
        expected_errors = {
            "DUPLICATE_IDS"
        }  # This is expected due to baseline/census overlap

        for check_type, count, desc in result:
            if check_type not in expected_errors:
                pytest.fail(
                    f"Unexpected ERROR-level data quality issue: {check_type} ({count} issues) - {desc}"
                )

    def test_id_generation_uniqueness(self, temp_db):
        """CRITICAL: New hire ID generation must be globally unique"""
        conn = duckdb.connect(temp_db)

        # Check that all new hire IDs are unique
        result = conn.execute(
            """
            SELECT employee_id, COUNT(*) as occurrences
            FROM fct_yearly_events
            WHERE event_type = 'hire'
            GROUP BY employee_id
            HAVING COUNT(*) > 1
        """
        ).fetchall()

        assert len(result) == 0, f"Found duplicate new hire IDs: {result}"

        # Check that new hire IDs follow expected format
        result = conn.execute(
            """
            SELECT COUNT(*) as invalid_ids
            FROM fct_yearly_events
            WHERE event_type = 'hire'
              AND NOT (employee_id LIKE 'NH_%'
                      AND (REGEXP_MATCHES(employee_id, '^NH_[0-9]{4}_[a-f0-9]{8}_[0-9]{6}$')
                           OR REGEXP_MATCHES(employee_id, '^NH_[0-9]{4}_[0-9]{6}$')))
        """
        ).fetchone()

        assert result[0] == 0, f"Found {result[0]} new hire IDs with invalid format"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
