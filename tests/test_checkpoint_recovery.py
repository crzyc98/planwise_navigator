#!/usr/bin/env python3
"""
Tests for Enhanced Checkpoint and Recovery System

Comprehensive test suite validating checkpoint creation, integrity validation,
recovery logic, and configuration drift detection.
"""

import json
import gzip
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest
import duckdb

from navigator_orchestrator.checkpoint_manager import CheckpointManager, CheckpointValidationError
from navigator_orchestrator.recovery_orchestrator import RecoveryOrchestrator, ConfigurationDriftError


class TestCheckpointManager:
    """Test suite for CheckpointManager"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test checkpoints"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def test_db(self, temp_dir):
        """Create test database with sample data"""
        db_path = temp_dir / "test.duckdb"

        with duckdb.connect(str(db_path)) as conn:
            # Create test tables
            conn.execute("""
                CREATE TABLE fct_yearly_events (
                    employee_id VARCHAR,
                    simulation_year INTEGER,
                    event_type VARCHAR,
                    effective_date DATE
                )
            """)

            conn.execute("""
                CREATE TABLE fct_workforce_snapshot (
                    employee_id VARCHAR,
                    simulation_year INTEGER,
                    total_compensation DECIMAL
                )
            """)

            conn.execute("""
                CREATE TABLE int_employee_contributions (
                    employee_id VARCHAR,
                    simulation_year INTEGER,
                    annual_contribution_amount DECIMAL
                )
            """)

            # Insert test data
            conn.execute("""
                INSERT INTO fct_yearly_events VALUES
                ('EMP001', 2025, 'hire', '2025-01-01'),
                ('EMP002', 2025, 'termination', '2025-06-01')
            """)

            conn.execute("""
                INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 2025, 75000.00),
                ('EMP002', 2025, 65000.00)
            """)

            conn.execute("""
                INSERT INTO int_employee_contributions VALUES
                ('EMP001', 2025, 5000.00)
            """)

        return db_path

    @pytest.fixture
    def checkpoint_manager(self, temp_dir, test_db):
        """Create CheckpointManager with test configuration"""
        return CheckpointManager(
            checkpoint_dir=str(temp_dir / "checkpoints"),
            db_path=str(test_db)
        )

    def test_checkpoint_creation_basic(self, checkpoint_manager):
        """Test basic checkpoint creation"""
        year = 2025
        run_id = "test_run_001"
        config_hash = "test_config_hash"

        checkpoint_data = checkpoint_manager.save_checkpoint(year, run_id, config_hash)

        # Verify checkpoint structure
        assert checkpoint_data['metadata']['year'] == year
        assert checkpoint_data['metadata']['run_id'] == run_id
        assert checkpoint_data['metadata']['config_hash'] == config_hash
        assert checkpoint_data['metadata']['checkpoint_version'] == "2.0"
        assert 'integrity_hash' in checkpoint_data
        assert 'database_state' in checkpoint_data
        assert 'validation_data' in checkpoint_data

    def test_checkpoint_file_creation(self, checkpoint_manager):
        """Test that checkpoint files are created correctly"""
        year = 2025
        run_id = "test_run_002"
        config_hash = "test_config_hash"

        checkpoint_manager.save_checkpoint(year, run_id, config_hash)

        # Check compressed file exists
        compressed_file = checkpoint_manager.checkpoint_dir / f"year_{year}.checkpoint.gz"
        assert compressed_file.exists()

        # Check legacy file exists
        legacy_file = checkpoint_manager.checkpoint_dir / f"year_{year}.json"
        assert legacy_file.exists()

        # Check latest symlink
        latest_link = checkpoint_manager.checkpoint_dir / "latest_checkpoint.gz"
        assert latest_link.exists()
        assert latest_link.is_symlink()

    def test_checkpoint_loading(self, checkpoint_manager):
        """Test checkpoint loading and validation"""
        year = 2025
        run_id = "test_run_003"
        config_hash = "test_config_hash"

        # Save checkpoint
        original_data = checkpoint_manager.save_checkpoint(year, run_id, config_hash)

        # Load checkpoint
        loaded_data = checkpoint_manager.load_checkpoint(year)

        assert loaded_data is not None
        assert loaded_data['metadata']['year'] == year
        assert loaded_data['metadata']['run_id'] == run_id
        assert loaded_data['integrity_hash'] == original_data['integrity_hash']

    def test_checkpoint_integrity_validation(self, checkpoint_manager):
        """Test checkpoint integrity validation"""
        year = 2025
        run_id = "test_run_004"
        config_hash = "test_config_hash"

        checkpoint_data = checkpoint_manager.save_checkpoint(year, run_id, config_hash)

        # Verify integrity validation passes
        assert checkpoint_manager._validate_checkpoint_integrity(checkpoint_data)

        # Corrupt the data and verify validation fails
        corrupted_data = checkpoint_data.copy()
        corrupted_data['database_state']['table_counts']['fct_yearly_events'] = 9999

        assert not checkpoint_manager._validate_checkpoint_integrity(corrupted_data)

    def test_database_state_capture(self, checkpoint_manager):
        """Test database state capture functionality"""
        year = 2025

        state = checkpoint_manager._capture_database_state(year)

        # Verify table counts are captured
        assert 'table_counts' in state
        assert state['table_counts']['fct_yearly_events'] == 2  # 2 test records
        assert state['table_counts']['fct_workforce_snapshot'] == 2

        # Verify data quality metrics
        assert 'data_quality_metrics' in state
        assert 'duplicate_events' in state['data_quality_metrics']
        assert 'workforce_count' in state['data_quality_metrics']

    def test_validation_data_capture(self, checkpoint_manager):
        """Test validation data capture"""
        year = 2025

        validation_data = checkpoint_manager._capture_validation_data(year)

        # Verify event distribution
        assert 'event_distribution' in validation_data
        assert validation_data['event_distribution'].get('hire') == 1
        assert validation_data['event_distribution'].get('termination') == 1

        # Verify totals
        assert 'total_compensation' in validation_data
        assert validation_data['total_compensation'] == 140000.0  # 75k + 65k

        assert 'total_contributions' in validation_data
        assert validation_data['total_contributions'] == 5000.0

    def test_checkpoint_listing(self, checkpoint_manager):
        """Test checkpoint listing functionality"""
        # Create multiple checkpoints
        years = [2025, 2026, 2027]
        for year in years:
            checkpoint_manager.save_checkpoint(year, f"run_{year}", "config_hash")

        checkpoints = checkpoint_manager.list_checkpoints()

        assert len(checkpoints) == len(years)

        # Verify checkpoint data
        for cp in checkpoints:
            assert cp['year'] in years
            assert cp['format'] == 'compressed'
            assert cp['integrity_valid'] is True
            assert cp['file_size'] > 0

    def test_checkpoint_cleanup(self, checkpoint_manager):
        """Test checkpoint cleanup functionality"""
        # Create 7 checkpoints
        years = list(range(2025, 2032))
        for year in years:
            checkpoint_manager.save_checkpoint(year, f"run_{year}", "config_hash")

        # Keep only 3 latest
        removed_count = checkpoint_manager.cleanup_old_checkpoints(keep_latest=3)

        assert removed_count > 0

        # Verify only 3 remain
        remaining_checkpoints = checkpoint_manager.list_checkpoints()
        assert len(remaining_checkpoints) == 3

        # Verify correct ones remain (latest 3)
        remaining_years = [cp['year'] for cp in remaining_checkpoints]
        assert remaining_years == [2029, 2030, 2031]

    def test_configuration_compatibility(self, checkpoint_manager):
        """Test configuration compatibility checking"""
        year = 2025
        run_id = "test_run_005"
        original_config_hash = "original_hash"
        new_config_hash = "new_hash"

        # Save checkpoint with original config
        checkpoint_manager.save_checkpoint(year, run_id, original_config_hash)

        # Test compatibility with same config
        assert checkpoint_manager.can_resume_from_year(year, original_config_hash)

        # Test incompatibility with different config
        assert not checkpoint_manager.can_resume_from_year(year, new_config_hash)

    def test_error_handling(self, checkpoint_manager):
        """Test error handling in checkpoint operations"""
        # Test loading non-existent checkpoint
        result = checkpoint_manager.load_checkpoint(9999)
        assert result is None

        # Test with invalid year
        result = checkpoint_manager.can_resume_from_year(9999, "any_hash")
        assert result is False


class TestRecoveryOrchestrator:
    """Test suite for RecoveryOrchestrator"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test checkpoints"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def test_db(self, temp_dir):
        """Create test database"""
        db_path = temp_dir / "test.duckdb"

        with duckdb.connect(str(db_path)) as conn:
            # Create minimal test tables
            conn.execute("""
                CREATE TABLE fct_yearly_events (
                    employee_id VARCHAR,
                    simulation_year INTEGER,
                    event_type VARCHAR
                )
            """)

            conn.execute("""
                INSERT INTO fct_yearly_events VALUES
                ('EMP001', 2025, 'hire')
            """)

        return db_path

    @pytest.fixture
    def recovery_setup(self, temp_dir, test_db):
        """Setup recovery orchestrator with checkpoint manager"""
        checkpoint_manager = CheckpointManager(
            checkpoint_dir=str(temp_dir / "checkpoints"),
            db_path=str(test_db)
        )
        recovery_orchestrator = RecoveryOrchestrator(checkpoint_manager)
        return checkpoint_manager, recovery_orchestrator

    def test_resume_simulation_success(self, recovery_setup):
        """Test successful simulation resume"""
        checkpoint_manager, recovery_orchestrator = recovery_setup

        # Create checkpoint
        year = 2025
        config_hash = "test_config"
        checkpoint_manager.save_checkpoint(year, "test_run", config_hash)

        # Test resume
        resume_year = recovery_orchestrator.resume_simulation(2027, config_hash)

        assert resume_year == 2026  # Should resume from year after checkpoint

    def test_resume_simulation_no_checkpoint(self, recovery_setup):
        """Test resume when no checkpoints exist"""
        checkpoint_manager, recovery_orchestrator = recovery_setup

        resume_year = recovery_orchestrator.resume_simulation(2027, "any_config")

        assert resume_year is None

    def test_resume_simulation_config_drift(self, recovery_setup):
        """Test resume with configuration drift"""
        checkpoint_manager, recovery_orchestrator = recovery_setup

        # Create checkpoint with one config
        year = 2025
        original_config = "original_config"
        new_config = "new_config"

        checkpoint_manager.save_checkpoint(year, "test_run", original_config)

        # Try to resume with different config
        resume_year = recovery_orchestrator.resume_simulation(2027, new_config)

        assert resume_year is None

    def test_resume_simulation_force_restart(self, recovery_setup):
        """Test force restart ignores checkpoints"""
        checkpoint_manager, recovery_orchestrator = recovery_setup

        # Create checkpoint
        year = 2025
        config_hash = "test_config"
        checkpoint_manager.save_checkpoint(year, "test_run", config_hash)

        # Test force restart
        resume_year = recovery_orchestrator.resume_simulation(2027, config_hash, force_restart=True)

        assert resume_year is None

    def test_recovery_status(self, recovery_setup):
        """Test recovery status reporting"""
        checkpoint_manager, recovery_orchestrator = recovery_setup

        # Initially no checkpoints
        status = recovery_orchestrator.get_recovery_status("any_config")
        assert not status['checkpoints_available']
        assert status['total_checkpoints'] == 0

        # Create checkpoint
        config_hash = "test_config"
        checkpoint_manager.save_checkpoint(2025, "test_run", config_hash)

        # Check status with compatible config
        status = recovery_orchestrator.get_recovery_status(config_hash)
        assert status['checkpoints_available']
        assert status['total_checkpoints'] == 1
        assert status['config_compatible']
        assert status['resumable_year'] == 2025

    def test_recovery_plan_preparation(self, recovery_setup):
        """Test recovery plan preparation"""
        checkpoint_manager, recovery_orchestrator = recovery_setup

        config_hash = "test_config"

        # Test plan without checkpoints
        plan = recovery_orchestrator.prepare_recovery_plan(2025, 2027, config_hash)
        assert plan['recovery_mode'] == 'full_run'
        assert plan['years_to_process'] == [2025, 2026, 2027]
        assert plan['estimated_savings'] == 0

        # Create checkpoint and test plan with recovery
        checkpoint_manager.save_checkpoint(2025, "test_run", config_hash)

        plan = recovery_orchestrator.prepare_recovery_plan(2025, 2027, config_hash)
        assert plan['recovery_mode'] == 'checkpoint_resume'
        assert plan['resume_from_year'] == 2025
        assert plan['years_to_process'] == [2026, 2027]
        assert plan['estimated_savings'] == 1

    def test_recovery_environment_validation(self, recovery_setup):
        """Test recovery environment validation"""
        checkpoint_manager, recovery_orchestrator = recovery_setup

        validation = recovery_orchestrator.validate_recovery_environment()

        # Should be valid since we have proper setup
        assert validation['valid']
        assert len(validation['issues']) == 0

    def test_config_hash_calculation(self, recovery_setup, temp_dir):
        """Test configuration hash calculation"""
        checkpoint_manager, recovery_orchestrator = recovery_setup

        # Test with non-existent config file
        hash1 = recovery_orchestrator.calculate_config_hash("non_existent.yaml")
        assert hash1 == "no_config"

        # Test with existing config file
        config_file = temp_dir / "test_config.yaml"
        config_file.write_text("test: configuration")

        hash2 = recovery_orchestrator.calculate_config_hash(str(config_file))
        assert hash2 != "no_config"
        assert len(hash2) == 64  # SHA-256 hash length

        # Test consistency
        hash3 = recovery_orchestrator.calculate_config_hash(str(config_file))
        assert hash2 == hash3


class TestIntegrationScenarios:
    """Integration tests for complete recovery scenarios"""

    @pytest.fixture
    def simulation_environment(self):
        """Setup complete simulation environment"""
        temp_dir = tempfile.mkdtemp()
        temp_path = Path(temp_dir)

        # Create test database
        db_path = temp_path / "simulation.duckdb"
        with duckdb.connect(str(db_path)) as conn:
            conn.execute("""
                CREATE TABLE fct_yearly_events (
                    employee_id VARCHAR,
                    simulation_year INTEGER,
                    event_type VARCHAR
                )
            """)

            conn.execute("""
                CREATE TABLE fct_workforce_snapshot (
                    employee_id VARCHAR,
                    simulation_year INTEGER,
                    total_compensation DECIMAL
                )
            """)

        checkpoint_manager = CheckpointManager(
            checkpoint_dir=str(temp_path / "checkpoints"),
            db_path=str(db_path)
        )
        recovery_orchestrator = RecoveryOrchestrator(checkpoint_manager)

        yield checkpoint_manager, recovery_orchestrator, temp_path

        shutil.rmtree(temp_dir)

    def test_multi_year_simulation_recovery(self, simulation_environment):
        """Test complete multi-year simulation with recovery"""
        checkpoint_manager, recovery_orchestrator, temp_path = simulation_environment

        config_hash = "simulation_config_v1"

        # Simulate multi-year run with checkpoints
        for year in range(2025, 2028):
            # Simulate adding data for the year
            with duckdb.connect(checkpoint_manager.db_path) as conn:
                conn.execute(
                    "INSERT INTO fct_yearly_events VALUES (?, ?, ?)",
                    [f"EMP{year}", year, "hire"]
                )
                conn.execute(
                    "INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?)",
                    [f"EMP{year}", year, 75000.0]
                )

            # Create checkpoint
            checkpoint_manager.save_checkpoint(year, f"run_{year}", config_hash)

        # Verify recovery status
        status = recovery_orchestrator.get_recovery_status(config_hash)
        assert status['checkpoints_available']
        assert status['total_checkpoints'] == 3
        assert status['latest_checkpoint_year'] == 2027
        assert status['resumable_year'] == 2027

        # Test recovery plan for extending simulation
        plan = recovery_orchestrator.prepare_recovery_plan(2025, 2030, config_hash)
        assert plan['recovery_mode'] == 'checkpoint_resume'
        assert plan['resume_from_year'] == 2027
        assert plan['years_to_process'] == [2028, 2029, 2030]
        assert plan['estimated_savings'] == 3

    def test_configuration_change_scenario(self, simulation_environment):
        """Test scenario where configuration changes invalidate checkpoints"""
        checkpoint_manager, recovery_orchestrator, temp_path = simulation_environment

        original_config = "original_config_v1"
        new_config = "updated_config_v2"

        # Create checkpoints with original config
        checkpoint_manager.save_checkpoint(2025, "run_2025", original_config)
        checkpoint_manager.save_checkpoint(2026, "run_2026", original_config)

        # Verify recovery works with original config
        status = recovery_orchestrator.get_recovery_status(original_config)
        assert status['config_compatible']
        assert status['resumable_year'] == 2026

        # Verify recovery fails with new config
        status = recovery_orchestrator.get_recovery_status(new_config)
        assert not status['config_compatible']
        assert status['resumable_year'] is None
        assert "configuration changes" in status['recommendations'][0]

    def test_checkpoint_corruption_recovery(self, simulation_environment):
        """Test recovery from checkpoint corruption"""
        checkpoint_manager, recovery_orchestrator, temp_path = simulation_environment

        config_hash = "test_config"

        # Create multiple checkpoints
        checkpoint_manager.save_checkpoint(2025, "run_2025", config_hash)
        checkpoint_manager.save_checkpoint(2026, "run_2026", config_hash)
        checkpoint_manager.save_checkpoint(2027, "run_2027", config_hash)

        # Corrupt the latest checkpoint file
        latest_checkpoint_path = checkpoint_manager.checkpoint_dir / "year_2027.checkpoint.gz"
        with open(latest_checkpoint_path, 'wb') as f:
            f.write(b"corrupted data")

        # Should fall back to previous valid checkpoint
        resume_year = recovery_orchestrator.resume_simulation(2030, config_hash)
        assert resume_year == 2027  # Should find 2026 as latest valid, resume from 2027

    def test_recovery_environment_issues(self, simulation_environment):
        """Test detection of recovery environment issues"""
        checkpoint_manager, recovery_orchestrator, temp_path = simulation_environment

        # Remove database file to simulate corruption
        db_path = Path(checkpoint_manager.db_path)
        db_path.unlink()

        validation = recovery_orchestrator.validate_recovery_environment()
        assert not validation['valid']
        assert any("Database file does not exist" in issue for issue in validation['issues'])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
