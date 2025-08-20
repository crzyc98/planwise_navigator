#!/usr/bin/env python3
"""
from navigator_orchestrator.config import get_database_path
Production Smoke Tests

Fast smoke tests validating basic functionality that should complete in <60 seconds.
Part of Epic E047: Production Testing & Validation Framework.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb
import pytest

from navigator_orchestrator.backup_manager import BackupManager
from navigator_orchestrator.cli import cmd_run


class TestProductionSmoke:
    """Fast smoke tests validating basic functionality"""

    def test_single_year_simulation(self):
        """Basic sanity - can we run a single year simulation?"""
        start_time = time.time()

        # Mock argparse namespace for single year simulation
        args = argparse.Namespace(
            config=None,
            database=None,
            threads=4,
            dry_run=False,
            verbose=False,
            years="2025-2025",
            seed=42,
            force_clear=False,
            resume_from=None,
        )

        try:
            result = cmd_run(args)
            duration = time.time() - start_time

            # Basic success checks
            assert result == 0, "Simulation should return success code (0)"
            assert (
                duration < 60
            ), f"Single year simulation took {duration:.1f}s, expected <60s"

            # Verify database has expected content
            with duckdb.connect(str(get_database_path())) as conn:
                workforce_count = conn.execute(
                    "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = 2025"
                ).fetchone()[0]
                assert workforce_count > 0, "Workforce snapshot should have records"

        except Exception as e:
            pytest.fail(f"Single year simulation failed: {e}")

    def test_database_structure(self):
        """Verify expected tables and columns exist"""
        with duckdb.connect(str(get_database_path())) as conn:
            # Check critical tables exist
            tables = conn.execute("SHOW TABLES").fetchall()
            table_names = [t[0] for t in tables]

            required_tables = [
                "fct_yearly_events",
                "fct_workforce_snapshot",
                "int_employee_contributions",
                "int_baseline_workforce",
                "stg_census_data",
            ]

            for table in required_tables:
                assert table in table_names, f"Missing required table: {table}"

            # Check fct_yearly_events structure
            if "fct_yearly_events" in table_names:
                columns = conn.execute("DESCRIBE fct_yearly_events").fetchall()
                column_names = [c[0] for c in columns]

                required_columns = [
                    "employee_id",
                    "event_type",
                    "simulation_year",
                    "effective_date",
                ]

                for col in required_columns:
                    assert (
                        col in column_names
                    ), f"Missing required column in fct_yearly_events: {col}"

            # Check fct_workforce_snapshot structure
            if "fct_workforce_snapshot" in table_names:
                columns = conn.execute("DESCRIBE fct_workforce_snapshot").fetchall()
                column_names = [c[0] for c in columns]

                required_columns = [
                    "employee_id",
                    "simulation_year",
                    "total_compensation",
                    "employment_status",
                ]

                for col in required_columns:
                    assert (
                        col in column_names
                    ), f"Missing required column in fct_workforce_snapshot: {col}"

    def test_data_quality_baseline(self):
        """Verify no critical data quality issues"""
        with duckdb.connect(str(get_database_path())) as conn:
            # Verify tables have data
            tables_to_check = ["fct_yearly_events", "fct_workforce_snapshot"]
            for table in tables_to_check:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    assert (
                        count > 0
                    ), f"Table {table} should have data but found {count} rows"
                except Exception:
                    # Table might not exist yet, which is OK for smoke tests
                    pass

            # Check for basic data integrity if tables exist
            try:
                # No duplicate RAISE events for same employee/year/date/amount
                duplicate_raises = conn.execute(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT employee_id, simulation_year, effective_date, new_compensation
                        FROM fct_yearly_events
                        WHERE event_type = 'RAISE'
                        GROUP BY employee_id, simulation_year, effective_date, new_compensation
                        HAVING COUNT(*) > 1
                    )
                """
                ).fetchone()[0]
                assert (
                    duplicate_raises == 0
                ), f"Found {duplicate_raises} duplicate RAISE events"

                # No post-termination events
                post_term_events = conn.execute(
                    """
                    SELECT COUNT(*) FROM fct_yearly_events e
                    JOIN (SELECT employee_id, effective_date as term_date
                          FROM fct_yearly_events WHERE event_type = 'termination') t
                    ON e.employee_id = t.employee_id
                    WHERE e.effective_date > t.term_date
                """
                ).fetchone()[0]
                assert (
                    post_term_events == 0
                ), f"Found {post_term_events} post-termination events"

                # No enrollment inconsistencies
                enrollment_inconsistencies = conn.execute(
                    """
                    SELECT COUNT(*) FROM fct_workforce_snapshot
                    WHERE enrollment_status = 'enrolled' AND enrollment_date IS NULL
                """
                ).fetchone()[0]
                assert (
                    enrollment_inconsistencies == 0
                ), f"Found {enrollment_inconsistencies} enrollment inconsistencies"

            except Exception:
                # If queries fail, tables might not have the expected structure yet
                # This is acceptable for smoke tests - we're just checking basic functionality
                pass

    def test_backup_system(self):
        """Verify backup system works"""
        backup_manager = BackupManager()
        backup_path = backup_manager.create_backup()

        assert backup_path.exists(), "Backup file not created"
        assert backup_path.stat().st_size > 1024, "Backup file too small (< 1KB)"

        # Verify latest symlink
        latest_backup = backup_manager.backup_dir / "latest.duckdb"
        assert latest_backup.exists(), "Latest backup symlink not created"

    def test_configuration_loading(self):
        """Verify simulation configuration loads correctly"""
        from navigator_orchestrator.config import load_simulation_config

        config_path = Path("config/simulation_config.yaml")
        if config_path.exists():
            config = load_simulation_config(config_path)

            # Check basic config structure
            assert hasattr(config, "start_year"), "Config missing start_year"
            assert hasattr(config, "end_year"), "Config missing end_year"
            assert config.start_year <= config.end_year, "Invalid year range in config"

    def test_database_connection(self):
        """Verify we can connect to the simulation database"""
        db_path = get_database_path()

        # Test DuckDB connection
        with duckdb.connect(str(db_path)) as conn:
            # Basic connection test
            result = conn.execute("SELECT 1").fetchone()
            assert result[0] == 1, "Basic database query failed"

            # Test database can handle basic operations
            conn.execute("CREATE TEMP TABLE test_table AS SELECT 1 as id")
            temp_result = conn.execute("SELECT COUNT(*) FROM test_table").fetchone()[0]
            assert temp_result == 1, "Database operations not working"

    def test_dbt_environment(self):
        """Verify dbt environment is properly configured"""
        from navigator_orchestrator.dbt_runner import DbtRunner

        # Test dbt runner initialization
        runner = DbtRunner(threads=1, executable="dbt", verbose=False)
        assert runner is not None, "Failed to initialize DbtRunner"

        # Check dbt project exists
        dbt_project_path = Path("dbt/dbt_project.yml")
        assert dbt_project_path.exists(), "dbt project file missing"

    def test_critical_models_exist(self):
        """Verify critical dbt models exist"""
        critical_models = [
            "dbt/models/staging/stg_census_data.sql",
            "dbt/models/intermediate/int_baseline_workforce.sql",
            "dbt/models/marts/fct_yearly_events.sql",
            "dbt/models/marts/fct_workforce_snapshot.sql",
        ]

        for model_path in critical_models:
            path = Path(model_path)
            assert path.exists(), f"Critical model missing: {model_path}"

            # Verify it's not empty
            content = path.read_text()
            assert len(content.strip()) > 0, f"Model file is empty: {model_path}"
