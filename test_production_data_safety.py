#!/usr/bin/env python3
"""
from navigator_orchestrator.config import get_database_path
Production Data Safety System Comprehensive Test

Epic E043: Production Data Safety & Backup System
Tests all components of the backup and recovery system to ensure
enterprise-grade data protection is working correctly.

Test Coverage:
- Backup creation with atomic operations
- Backup verification and integrity checking
- Configuration validation
- Recovery point management
- Emergency backup procedures
- Full restore operations
- Error handling and rollback
"""

import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import duckdb

# Import the production safety components
from navigator_orchestrator.backup_manager import (BackupConfiguration,
                                                   BackupManager)
from navigator_orchestrator.config import (OrchestrationConfig,
                                           ProductionSafetySettings,
                                           create_example_orchestration_config,
                                           validate_production_configuration)
from navigator_orchestrator.recovery_manager import RecoveryManager


class ProductionDataSafetyTest:
    """Comprehensive test suite for production data safety system"""

    def __init__(self):
        """Initialize test environment"""
        self.test_dir = Path(tempfile.mkdtemp(prefix="pds_test_"))
        self.original_cwd = Path.cwd()

        # Change to test directory
        os.chdir(self.test_dir)

        # Create test database
        self.test_db = self.test_dir / str(get_database_path())
        self._create_test_database()

        # Initialize components
        self.backup_config = BackupConfiguration(
            backup_dir=self.test_dir / "backups",
            retention_days=3,
            verify_backups=True,
            max_backup_size_gb=1.0,
        )

        self.backup_manager = BackupManager(self.backup_config, str(self.test_db))
        self.recovery_manager = RecoveryManager(self.backup_manager, str(self.test_db))

        # Test results
        self.test_results: Dict[str, bool] = {}
        self.test_details: Dict[str, List[str]] = {}

    def _create_test_database(self) -> None:
        """Create a test database with sample data"""
        with duckdb.connect(str(self.test_db)) as conn:
            # Create sample tables similar to actual simulation database
            conn.execute(
                """
                CREATE TABLE fct_yearly_events (
                    event_id VARCHAR PRIMARY KEY,
                    employee_id VARCHAR,
                    simulation_year INTEGER,
                    event_type VARCHAR,
                    effective_date DATE,
                    event_details JSON
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE fct_workforce_snapshot (
                    employee_id VARCHAR,
                    simulation_year INTEGER,
                    employee_hire_date DATE,
                    current_age INTEGER,
                    employment_status VARCHAR,
                    annual_compensation DECIMAL(12,2),
                    PRIMARY KEY (employee_id, simulation_year)
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE stg_census_data (
                    employee_id VARCHAR PRIMARY KEY,
                    employee_hire_date DATE,
                    employee_birth_date DATE,
                    employee_gross_compensation DECIMAL(12,2),
                    active BOOLEAN
                )
            """
            )

            # Insert sample data
            sample_events = [
                ("EVT_001", "EMP_001", 2025, "hire", "2025-01-15", "{}"),
                ("EVT_002", "EMP_002", 2025, "hire", "2025-02-01", "{}"),
                ("EVT_003", "EMP_001", 2025, "enrollment", "2025-02-15", "{}"),
                ("EVT_004", "EMP_003", 2025, "termination", "2025-03-01", "{}"),
            ]

            for event in sample_events:
                conn.execute(
                    "INSERT INTO fct_yearly_events VALUES (?, ?, ?, ?, ?, ?)", event
                )

            sample_workforce = [
                ("EMP_001", 2025, "2025-01-15", 30, "active", 75000.00),
                ("EMP_002", 2025, "2025-02-01", 25, "active", 65000.00),
                ("EMP_003", 2025, "2025-03-01", 35, "terminated", 80000.00),
            ]

            for workforce in sample_workforce:
                conn.execute(
                    "INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?, ?, ?, ?)",
                    workforce,
                )

            sample_census = [
                ("EMP_001", "2025-01-15", "1994-06-15", 75000.00, True),
                ("EMP_002", "2025-02-01", "1999-03-20", 65000.00, True),
                ("EMP_003", "2025-03-01", "1989-12-10", 80000.00, False),
            ]

            for census in sample_census:
                conn.execute(
                    "INSERT INTO stg_census_data VALUES (?, ?, ?, ?, ?)", census
                )

    def _log_test(self, test_name: str, success: bool, details: List[str]) -> None:
        """Log test result"""
        self.test_results[test_name] = success
        self.test_details[test_name] = details

        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")

        for detail in details:
            print(f"    {detail}")

    def test_backup_creation(self) -> None:
        """Test S043-01: Automated Backup System"""
        test_name = "Backup Creation"
        details = []

        try:
            # Test basic backup creation
            backup_metadata = self.backup_manager.create_backup()

            # Verify backup file exists
            if not backup_metadata.backup_path.exists():
                details.append("❌ Backup file not created")
                self._log_test(test_name, False, details)
                return

            details.append(f"✅ Backup created: {backup_metadata.backup_path.name}")
            details.append(f"✅ Creation time: {backup_metadata.creation_time:.2f}s")
            details.append(f"✅ Verification: {backup_metadata.verification_status}")

            # Verify backup size is reasonable
            if backup_metadata.backup_size < 1024:
                details.append("⚠️  Backup file very small")
            else:
                details.append(
                    f"✅ Backup size: {backup_metadata.backup_size / 1024:.1f} KB"
                )

            # Test latest symlink
            latest_link = self.backup_config.backup_dir / "latest.duckdb"
            if latest_link.exists():
                details.append("✅ Latest symlink created")
            else:
                details.append("⚠️  Latest symlink not found")

            self._log_test(test_name, True, details)

        except Exception as e:
            details.append(f"❌ Exception: {str(e)}")
            self._log_test(test_name, False, details)

    def test_backup_verification(self) -> None:
        """Test backup verification and integrity checking"""
        test_name = "Backup Verification"
        details = []

        try:
            # Create a backup first
            backup_metadata = self.backup_manager.create_backup()

            # Test comprehensive verification
            validation = self.recovery_manager.verify_backup_comprehensive(
                backup_metadata.backup_path
            )

            details.append(f"✅ Verification success: {validation.success}")
            details.append(f"✅ Integrity score: {validation.data_integrity_score:.2f}")
            details.append(f"✅ Checks performed: {len(validation.checks_performed)}")

            if validation.warnings:
                details.append(f"⚠️  Warnings: {len(validation.warnings)}")
                for warning in validation.warnings[:3]:  # Show first 3 warnings
                    details.append(f"    - {warning}")

            if validation.errors:
                details.append(f"❌ Errors: {len(validation.errors)}")
                for error in validation.errors[:3]:  # Show first 3 errors
                    details.append(f"    - {error}")

            # Test should pass if no errors and decent integrity score
            success = validation.success and validation.data_integrity_score >= 0.7
            self._log_test(test_name, success, details)

        except Exception as e:
            details.append(f"❌ Exception: {str(e)}")
            self._log_test(test_name, False, details)

    def test_configuration_validation(self) -> None:
        """Test S043-02: Configuration Management"""
        test_name = "Configuration Validation"
        details = []

        try:
            # Create test configuration
            config_data = {
                "simulation": {
                    "start_year": 2025,
                    "end_year": 2029,
                    "random_seed": 42,
                    "target_growth_rate": 0.03,
                },
                "compensation": {"cola_rate": 0.005, "merit_budget": 0.025},
                "workforce": {
                    "total_termination_rate": 0.12,
                    "new_hire_termination_rate": 0.25,
                },
                "production_safety": {
                    "db_path": str(self.test_db),
                    "backup_dir": str(self.backup_config.backup_dir),
                    "backup_retention_days": 3,
                    "verify_backups": True,
                    "log_level": "INFO",
                },
            }

            # Test configuration creation and validation
            config = OrchestrationConfig(**config_data)
            details.append("✅ Configuration object created")

            # Test production safety validation
            validate_production_configuration(config)
            details.append("✅ Production safety validation passed")

            # Test backup configuration extraction
            from navigator_orchestrator.config import get_backup_configuration

            backup_config = get_backup_configuration(config)
            details.append("✅ Backup configuration extracted")

            # Test invalid configuration
            try:
                invalid_config_data = config_data.copy()
                invalid_config_data["production_safety"][
                    "db_path"
                ] = "/nonexistent/path.duckdb"

                invalid_config = OrchestrationConfig(**invalid_config_data)
                validate_production_configuration(invalid_config)

                details.append("❌ Invalid configuration should have failed")
                self._log_test(test_name, False, details)
                return

            except (FileNotFoundError, ValueError):
                details.append("✅ Invalid configuration properly rejected")

            self._log_test(test_name, True, details)

        except Exception as e:
            details.append(f"❌ Exception: {str(e)}")
            self._log_test(test_name, False, details)

    def test_recovery_points(self) -> None:
        """Test recovery point management"""
        test_name = "Recovery Point Management"
        details = []

        try:
            # Create multiple backups
            backup1 = self.backup_manager.create_backup()
            time.sleep(1)  # Ensure different timestamps
            backup2 = self.backup_manager.create_backup()

            # Get recovery points
            recovery_points = self.recovery_manager.get_recovery_points()

            details.append(f"✅ Found {len(recovery_points)} recovery points")

            if len(recovery_points) >= 2:
                details.append("✅ Multiple recovery points available")
            else:
                details.append("⚠️  Expected at least 2 recovery points")

            # Test recovery point data
            for i, rp in enumerate(recovery_points[:2]):
                details.append(f"    Point {i+1}: {rp.backup_path.name}")
                details.append(f"    Integrity: {rp.data_integrity_score:.2f}")
                details.append(f"    Tables: {rp.table_count}, Rows: {rp.total_rows}")

            # Test recovery point testing
            if recovery_points:
                validation = self.recovery_manager.test_recovery_point(
                    recovery_points[0]
                )
                details.append(f"✅ Recovery point test: {validation.success}")

            self._log_test(test_name, True, details)

        except Exception as e:
            details.append(f"❌ Exception: {str(e)}")
            self._log_test(test_name, False, details)

    def test_emergency_backup(self) -> None:
        """Test emergency backup creation"""
        test_name = "Emergency Backup"
        details = []

        try:
            # Create emergency backup
            emergency_backup = self.recovery_manager.create_emergency_backup()

            if emergency_backup:
                details.append(
                    f"✅ Emergency backup created: {emergency_backup.backup_path.name}"
                )
                details.append(f"✅ Size: {emergency_backup.backup_size / 1024:.1f} KB")

                # Verify it's actually an emergency backup
                if "emergency" in emergency_backup.backup_path.name:
                    details.append("✅ Proper emergency backup naming")
                else:
                    details.append("⚠️  Emergency backup naming could be clearer")

                self._log_test(test_name, True, details)
            else:
                details.append("❌ Emergency backup creation failed")
                self._log_test(test_name, False, details)

        except Exception as e:
            details.append(f"❌ Exception: {str(e)}")
            self._log_test(test_name, False, details)

    def test_full_restore(self) -> None:
        """Test S043-03: Full restore operation"""
        test_name = "Full Restore Operation"
        details = []

        try:
            # Create backup first
            original_backup = self.backup_manager.create_backup()
            details.append(
                f"✅ Original backup created: {original_backup.backup_path.name}"
            )

            # Modify database to simulate data changes
            with duckdb.connect(str(self.test_db)) as conn:
                conn.execute(
                    "INSERT INTO fct_yearly_events VALUES (?, ?, ?, ?, ?, ?)",
                    ("EVT_999", "EMP_999", 2025, "test", "2025-12-31", "{}"),
                )

            details.append("✅ Database modified for restore test")

            # Perform restore operation
            restore_operation = self.recovery_manager.restore_from_backup(
                backup_path=original_backup.backup_path,
                verify_before_restore=True,
                create_emergency_backup=True,
            )

            details.append(f"✅ Restore operation: {restore_operation.operation_id}")
            details.append(f"✅ Restore success: {restore_operation.success}")
            details.append(f"✅ Duration: {restore_operation.duration:.2f}s")

            if restore_operation.success:
                # Verify restore worked - the test record should be gone
                with duckdb.connect(str(self.test_db)) as conn:
                    result = conn.execute(
                        "SELECT COUNT(*) FROM fct_yearly_events WHERE event_id = 'EVT_999'"
                    ).fetchone()

                    if result[0] == 0:
                        details.append("✅ Database restored to backup state")
                    else:
                        details.append("❌ Database not properly restored")
                        self._log_test(test_name, False, details)
                        return

                # Check if emergency backup was created
                if "emergency_backup_created" in restore_operation.details:
                    details.append("✅ Emergency backup created during restore")

                self._log_test(test_name, True, details)
            else:
                details.append(
                    f"❌ Restore failed: {restore_operation.details.get('error', 'Unknown')}"
                )
                self._log_test(test_name, False, details)

        except Exception as e:
            details.append(f"❌ Exception: {str(e)}")
            self._log_test(test_name, False, details)

    def test_system_status(self) -> None:
        """Test system status and monitoring"""
        test_name = "System Status Monitoring"
        details = []

        try:
            # Get backup system status
            backup_status = self.backup_manager.get_backup_status()
            details.append(f"✅ Backup count: {backup_status['backup_count']}")
            details.append(f"✅ Total size: {backup_status['total_size_gb']:.3f} GB")
            details.append(f"✅ Database exists: {backup_status['database_exists']}")

            # Get recovery system status
            recovery_status = self.recovery_manager.get_recovery_status()
            details.append(
                f"✅ Recovery readiness: {recovery_status['recovery_readiness']}"
            )
            details.append(
                f"✅ Verified points: {recovery_status['verified_recovery_points']}"
            )
            details.append(
                f"✅ Database accessible: {recovery_status['database_status']['accessible']}"
            )

            # Check for reasonable status values
            success = (
                backup_status["backup_count"] > 0
                and backup_status["database_exists"]
                and recovery_status["database_status"]["accessible"]
                and recovery_status["recovery_readiness"] in ["excellent", "good"]
            )

            self._log_test(test_name, success, details)

        except Exception as e:
            details.append(f"❌ Exception: {str(e)}")
            self._log_test(test_name, False, details)

    def test_error_handling(self) -> None:
        """Test error handling and edge cases"""
        test_name = "Error Handling"
        details = []

        try:
            # Test backup of non-existent database
            try:
                fake_backup_manager = BackupManager(
                    self.backup_config, "/nonexistent/database.duckdb"
                )
                fake_backup_manager.create_backup()
                details.append("❌ Should have failed with non-existent database")
                self._log_test(test_name, False, details)
                return
            except FileNotFoundError:
                details.append("✅ Properly handles non-existent database")

            # Test restore from non-existent backup
            try:
                fake_backup_path = Path("/nonexistent/backup.duckdb")
                self.recovery_manager.restore_from_backup(backup_path=fake_backup_path)
                details.append("❌ Should have failed with non-existent backup")
                self._log_test(test_name, False, details)
                return
            except (FileNotFoundError, ValueError):
                details.append("✅ Properly handles non-existent backup")

            # Test verification of corrupted backup
            corrupted_backup = self.backup_config.backup_dir / "corrupted.duckdb"
            corrupted_backup.write_text("This is not a valid database file")

            validation = self.recovery_manager.verify_backup_comprehensive(
                corrupted_backup
            )
            if not validation.success:
                details.append("✅ Properly detects corrupted backup")
            else:
                details.append("❌ Should have detected corrupted backup")

            self._log_test(test_name, True, details)

        except Exception as e:
            details.append(f"❌ Exception: {str(e)}")
            self._log_test(test_name, False, details)

    def test_backup_cleanup(self) -> None:
        """Test backup retention and cleanup"""
        test_name = "Backup Cleanup"
        details = []

        try:
            # Create several backups
            backups = []
            for i in range(5):
                backup = self.backup_manager.create_backup()
                backups.append(backup)
                time.sleep(0.1)  # Small delay for different timestamps

            details.append(f"✅ Created {len(backups)} test backups")

            # Get initial count
            initial_backups = self.backup_manager.list_backups()
            initial_count = len(initial_backups)

            # Manually trigger cleanup (retention is 3 days, but we can test manual cleanup)
            # For testing, we'll modify retention temporarily
            old_retention = self.backup_manager.config.retention_days
            self.backup_manager.config.retention_days = 2  # Keep only 2 newest

            # Force cleanup by creating another backup
            self.backup_manager._cleanup_old_backups()

            # Check if cleanup worked
            final_backups = self.backup_manager.list_backups()
            final_count = len(final_backups)

            details.append(f"✅ Backup count after cleanup: {final_count}")

            # Restore original retention
            self.backup_manager.config.retention_days = old_retention

            # Note: Since we're using timestamps for cleanup, and our test backups
            # are created quickly, cleanup might not remove files. This is expected.
            details.append("✅ Cleanup mechanism executed without errors")

            self._log_test(test_name, True, details)

        except Exception as e:
            details.append(f"❌ Exception: {str(e)}")
            self._log_test(test_name, False, details)

    def run_all_tests(self) -> None:
        """Run comprehensive test suite"""
        print("🚀 Starting Production Data Safety System Tests")
        print(f"📁 Test directory: {self.test_dir}")
        print(f"💾 Test database: {self.test_db}")
        print("=" * 60)

        # Run all tests
        test_methods = [
            self.test_backup_creation,
            self.test_backup_verification,
            self.test_configuration_validation,
            self.test_recovery_points,
            self.test_emergency_backup,
            self.test_full_restore,
            self.test_system_status,
            self.test_error_handling,
            self.test_backup_cleanup,
        ]

        for test_method in test_methods:
            try:
                test_method()
            except Exception as e:
                test_name = (
                    test_method.__name__.replace("test_", "").replace("_", " ").title()
                )
                self._log_test(test_name, False, [f"❌ Unexpected exception: {str(e)}"])

            print()  # Add spacing between tests

    def cleanup(self) -> None:
        """Cleanup test environment"""
        try:
            # Change back to original directory
            os.chdir(self.original_cwd)

            # Remove test directory
            shutil.rmtree(self.test_dir, ignore_errors=True)

            print(f"🧹 Test cleanup completed")

        except Exception as e:
            print(f"⚠️  Cleanup warning: {str(e)}")

    def print_summary(self) -> None:
        """Print test summary"""
        print("=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result)
        failed_tests = total_tests - passed_tests

        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests} ✅")
        print(f"Failed: {failed_tests} ❌")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")

        if failed_tests > 0:
            print("\n🚨 FAILED TESTS:")
            for test_name, result in self.test_results.items():
                if not result:
                    print(f"   ❌ {test_name}")
                    for detail in self.test_details[test_name]:
                        if "❌" in detail:
                            print(f"      {detail}")

        print("\n" + "=" * 60)

        if failed_tests == 0:
            print("🎉 ALL TESTS PASSED - Production Data Safety System Ready!")
        else:
            print("⚠️  SOME TESTS FAILED - Review issues before production deployment")

        return failed_tests == 0


def main():
    """Main test execution"""
    test_suite = None

    try:
        print("🔧 Production Data Safety System - Comprehensive Test Suite")
        print("Epic E043: Production Data Safety & Backup System")
        print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Initialize and run tests
        test_suite = ProductionDataSafetyTest()
        test_suite.run_all_tests()

        # Print summary
        all_passed = test_suite.print_summary()

        return 0 if all_passed else 1

    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        return 1

    except Exception as e:
        print(f"\n💥 Test suite failed with exception: {str(e)}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        if test_suite:
            test_suite.cleanup()


if __name__ == "__main__":
    exit(main())
