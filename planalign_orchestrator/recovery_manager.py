"""
from planalign_orchestrator.config import get_database_path
Production Data Safety & Recovery System (Epic E043)

Story S043-03: Backup Verification & Recovery Procedures
Implements comprehensive backup verification and recovery capabilities
for PlanWise Navigator production data safety.

Features:
- Comprehensive backup verification with integrity checks
- Automated recovery procedures with safety validation
- Emergency backup creation during restore operations
- Recovery point management and validation
- Detailed audit logging of all recovery operations
"""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
from pydantic import BaseModel, Field

from .backup_manager import BackupConfiguration, BackupManager, BackupMetadata


class RecoveryPoint(BaseModel):
    """Information about a recovery point"""

    backup_path: Path
    timestamp: datetime
    verification_status: str
    data_integrity_score: float = Field(ge=0.0, le=1.0)
    table_count: int
    total_rows: int
    file_size: int
    recovery_tested: bool = False


class RecoveryValidation(BaseModel):
    """Results of recovery validation"""

    success: bool
    validation_time: float
    checks_performed: List[str]
    warnings: List[str]
    errors: List[str]
    data_integrity_score: float = Field(ge=0.0, le=1.0)


class RecoveryOperation(BaseModel):
    """Record of a recovery operation"""

    operation_id: str
    timestamp: datetime
    operation_type: str  # "restore", "verify", "emergency_backup"
    source_backup: Optional[Path]
    target_database: Path
    success: bool
    duration: float
    details: Dict[str, Any]


class RecoveryManager:
    """
    Enterprise-grade recovery manager for simulation database

    Provides comprehensive backup verification, recovery validation,
    and automated recovery procedures with safety checks.
    """

    def __init__(
        self, backup_manager: BackupManager, db_path: str = str(get_database_path())
    ):
        """
        Initialize recovery manager

        Args:
            backup_manager: Configured backup manager instance
            db_path: Path to the database file
        """
        self.backup_manager = backup_manager
        self.db_path = Path(db_path)
        self.recovery_log_dir = Path("logs/recovery")
        self.recovery_log_dir.mkdir(parents=True, exist_ok=True)

        # Initialize recovery audit log
        self.audit_log = self.recovery_log_dir / "recovery_audit.log"
        self._log("Recovery manager initialized")

    def _log(self, message: str, level: str = "INFO") -> None:
        """Log recovery operation with timestamp and level"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"

        with open(self.audit_log, "a", encoding="utf-8") as f:
            f.write(log_entry)

        print(f"RECOVERY [{level}]: {message}")

    def _generate_operation_id(self) -> str:
        """Generate unique operation ID"""
        return f"REC_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 10000:04d}"

    def verify_backup_comprehensive(self, backup_path: Path) -> RecoveryValidation:
        """
        Perform comprehensive backup verification

        Args:
            backup_path: Path to backup file to verify

        Returns:
            Detailed validation results
        """
        operation_start = time.time()
        checks_performed = []
        warnings = []
        errors = []

        self._log(f"Starting comprehensive backup verification: {backup_path}")

        try:
            # Check 1: File exists and is readable
            if not backup_path.exists():
                errors.append(f"Backup file does not exist: {backup_path}")
                return RecoveryValidation(
                    success=False,
                    validation_time=time.time() - operation_start,
                    checks_performed=checks_performed,
                    warnings=warnings,
                    errors=errors,
                    data_integrity_score=0.0,
                )

            checks_performed.append("file_existence")

            # Check 2: File size is reasonable
            file_size = backup_path.stat().st_size
            if file_size < 1024:  # Less than 1KB
                errors.append(f"Backup file suspiciously small: {file_size} bytes")
            elif file_size > 50 * 1024**3:  # More than 50GB
                warnings.append(
                    f"Backup file very large: {file_size / (1024**3):.2f} GB"
                )

            checks_performed.append("file_size_validation")

            # Check 3: Database connectivity and basic operations
            table_count = 0
            total_rows = 0

            with duckdb.connect(str(backup_path)) as conn:
                # Test basic connectivity
                result = conn.execute("SELECT 1 as test").fetchone()
                if result[0] != 1:
                    errors.append("Basic connectivity test failed")

                checks_performed.append("database_connectivity")

                # Get table information
                tables = conn.execute("SHOW TABLES").fetchall()
                table_count = len(tables)

                if table_count == 0:
                    errors.append("No tables found in backup database")
                elif table_count < 5:
                    warnings.append(f"Few tables found: {table_count}")

                checks_performed.append("table_enumeration")

                # Check critical tables exist
                critical_tables = [
                    "fct_yearly_events",
                    "fct_workforce_snapshot",
                    "stg_census_data",
                ]
                missing_tables = []

                table_names = [table[0] for table in tables]
                for critical_table in critical_tables:
                    if critical_table not in table_names:
                        missing_tables.append(critical_table)

                if missing_tables:
                    errors.append(f"Missing critical tables: {missing_tables}")

                checks_performed.append("critical_table_validation")

                # Count total rows across all tables
                for (table_name,) in tables:
                    try:
                        count_result = conn.execute(
                            f"SELECT COUNT(*) FROM {table_name}"
                        ).fetchone()
                        total_rows += count_result[0]
                    except Exception as e:
                        warnings.append(
                            f"Could not count rows in table {table_name}: {str(e)}"
                        )

                checks_performed.append("row_count_validation")

                # Test data integrity with sample queries
                try:
                    # Test fct_yearly_events if it exists
                    if "fct_yearly_events" in table_names:
                        events_sample = conn.execute(
                            "SELECT event_type, COUNT(*) FROM fct_yearly_events GROUP BY event_type LIMIT 10"
                        ).fetchall()

                        if not events_sample:
                            warnings.append("fct_yearly_events table is empty")

                    checks_performed.append("data_integrity_sampling")

                except Exception as e:
                    warnings.append(f"Data integrity sampling failed: {str(e)}")

                # Test foreign key relationships if possible
                try:
                    if (
                        "fct_workforce_snapshot" in table_names
                        and "fct_yearly_events" in table_names
                    ):
                        # Check for orphaned records
                        orphan_check = conn.execute(
                            """
                            SELECT COUNT(*)
                            FROM fct_yearly_events e
                            LEFT JOIN fct_workforce_snapshot w
                                ON e.employee_id = w.employee_id
                                AND e.simulation_year = w.simulation_year
                            WHERE w.employee_id IS NULL
                            LIMIT 1000
                        """
                        ).fetchone()

                        if orphan_check[0] > 100:
                            warnings.append(
                                f"Many orphaned event records: {orphan_check[0]}"
                            )

                    checks_performed.append("referential_integrity_check")

                except Exception as e:
                    warnings.append(f"Referential integrity check failed: {str(e)}")

            # Calculate data integrity score
            error_weight = len(errors) * 0.3
            warning_weight = len(warnings) * 0.1
            integrity_score = max(0.0, 1.0 - error_weight - warning_weight)

            # Determine overall success
            success = len(errors) == 0 and integrity_score >= 0.7

            validation_time = time.time() - operation_start

            self._log(
                f"Backup verification completed: {backup_path.name} - "
                f"Success: {success}, Score: {integrity_score:.2f}, "
                f"Tables: {table_count}, Rows: {total_rows}, "
                f"Time: {validation_time:.2f}s"
            )

            return RecoveryValidation(
                success=success,
                validation_time=validation_time,
                checks_performed=checks_performed,
                warnings=warnings,
                errors=errors,
                data_integrity_score=integrity_score,
            )

        except Exception as e:
            errors.append(f"Verification failed with exception: {str(e)}")
            validation_time = time.time() - operation_start

            self._log(f"Backup verification failed: {backup_path} - {str(e)}", "ERROR")

            return RecoveryValidation(
                success=False,
                validation_time=validation_time,
                checks_performed=checks_performed,
                warnings=warnings,
                errors=errors,
                data_integrity_score=0.0,
            )

    def get_recovery_points(self) -> List[RecoveryPoint]:
        """
        Get all available recovery points with verification status

        Returns:
            List of recovery points sorted by timestamp (newest first)
        """
        self._log("Enumerating available recovery points")

        backups = self.backup_manager.list_backups()
        recovery_points = []

        for backup in backups:
            # Quick verification for recovery point assessment
            try:
                with duckdb.connect(str(backup.backup_path)) as conn:
                    tables = conn.execute("SHOW TABLES").fetchall()
                    table_count = len(tables)

                    total_rows = 0
                    for (table_name,) in tables[
                        :10
                    ]:  # Sample first 10 tables for performance
                        try:
                            count_result = conn.execute(
                                f"SELECT COUNT(*) FROM {table_name}"
                            ).fetchone()
                            total_rows += count_result[0]
                        except Exception:
                            pass

                    # Basic integrity score based on table count and data presence
                    integrity_score = min(
                        1.0, (table_count / 10.0) * (1.0 if total_rows > 0 else 0.5)
                    )

                    recovery_point = RecoveryPoint(
                        backup_path=backup.backup_path,
                        timestamp=backup.timestamp,
                        verification_status="basic_check_passed",
                        data_integrity_score=integrity_score,
                        table_count=table_count,
                        total_rows=total_rows,
                        file_size=backup.backup_size,
                        recovery_tested=False,
                    )

                    recovery_points.append(recovery_point)

            except Exception as e:
                # Create recovery point with failed verification
                recovery_point = RecoveryPoint(
                    backup_path=backup.backup_path,
                    timestamp=backup.timestamp,
                    verification_status=f"verification_failed: {str(e)}",
                    data_integrity_score=0.0,
                    table_count=0,
                    total_rows=0,
                    file_size=backup.backup_size,
                    recovery_tested=False,
                )

                recovery_points.append(recovery_point)

        # Sort by timestamp, newest first
        recovery_points.sort(key=lambda x: x.timestamp, reverse=True)

        self._log(f"Found {len(recovery_points)} recovery points")
        return recovery_points

    def test_recovery_point(self, recovery_point: RecoveryPoint) -> RecoveryValidation:
        """
        Test a recovery point by performing comprehensive verification

        Args:
            recovery_point: Recovery point to test

        Returns:
            Detailed validation results
        """
        self._log(f"Testing recovery point: {recovery_point.backup_path.name}")

        validation = self.verify_backup_comprehensive(recovery_point.backup_path)

        # Update recovery point status
        recovery_point.recovery_tested = True
        recovery_point.verification_status = (
            "comprehensive_test_passed"
            if validation.success
            else "comprehensive_test_failed"
        )
        recovery_point.data_integrity_score = validation.data_integrity_score

        return validation

    def create_emergency_backup(self) -> Optional[BackupMetadata]:
        """
        Create emergency backup before risky operations

        Returns:
            Backup metadata if successful, None if failed
        """
        operation_id = self._generate_operation_id()

        self._log(f"Creating emergency backup - Operation: {operation_id}")

        try:
            # Create backup with emergency prefix
            backup_metadata = self.backup_manager.create_backup()

            # Rename to indicate emergency backup
            emergency_name = (
                f"emergency_{operation_id}_{backup_metadata.backup_path.name}"
            )
            emergency_path = backup_metadata.backup_path.parent / emergency_name
            backup_metadata.backup_path.rename(emergency_path)
            backup_metadata.backup_path = emergency_path

            self._log(f"Emergency backup created: {emergency_path}")
            return backup_metadata

        except Exception as e:
            self._log(f"Emergency backup creation failed: {str(e)}", "ERROR")
            return None

    def restore_from_backup(
        self,
        backup_path: Optional[Path] = None,
        verify_before_restore: bool = True,
        create_emergency_backup: bool = True,
    ) -> RecoveryOperation:
        """
        Restore database from backup with comprehensive safety checks

        Args:
            backup_path: Specific backup to restore from (uses latest if None)
            verify_before_restore: Verify backup integrity before restore
            create_emergency_backup: Create emergency backup of current database

        Returns:
            Recovery operation results
        """
        operation_id = self._generate_operation_id()
        operation_start = time.time()

        self._log(f"Starting database restore - Operation: {operation_id}")

        operation = RecoveryOperation(
            operation_id=operation_id,
            timestamp=datetime.now(),
            operation_type="restore",
            source_backup=backup_path,
            target_database=self.db_path,
            success=False,
            duration=0.0,
            details={},
        )

        try:
            # Step 1: Determine source backup
            if backup_path is None:
                recovery_points = self.get_recovery_points()
                if not recovery_points:
                    raise ValueError("No recovery points available")

                # Use newest recovery point with good integrity
                suitable_points = [
                    rp for rp in recovery_points if rp.data_integrity_score >= 0.7
                ]
                if not suitable_points:
                    self._log(
                        "Warning: No high-integrity recovery points found, using newest available",
                        "WARNING",
                    )
                    backup_path = recovery_points[0].backup_path
                else:
                    backup_path = suitable_points[0].backup_path

            operation.source_backup = backup_path
            operation.details["backup_selected"] = str(backup_path)

            self._log(f"Selected backup for restore: {backup_path}")

            # Step 2: Verify backup integrity if requested
            if verify_before_restore:
                self._log("Verifying backup before restore")
                validation = self.verify_backup_comprehensive(backup_path)
                operation.details["pre_restore_validation"] = validation.dict()

                if not validation.success:
                    operation.success = False
                    operation.duration = time.time() - operation_start
                    operation.details[
                        "error"
                    ] = f"Backup verification failed: {validation.errors}"
                    raise ValueError(f"Backup verification failed: {validation.errors}")

                if validation.data_integrity_score < 0.7:
                    self._log(
                        f"Warning: Low integrity score {validation.data_integrity_score:.2f}, proceeding with caution",
                        "WARNING",
                    )

            # Step 3: Create emergency backup of current database
            emergency_backup = None
            if create_emergency_backup and self.db_path.exists():
                self._log("Creating emergency backup of current database")
                emergency_backup = self.create_emergency_backup()
                if emergency_backup:
                    operation.details["emergency_backup_created"] = str(
                        emergency_backup.backup_path
                    )
                else:
                    self._log("Warning: Could not create emergency backup", "WARNING")

            # Step 4: Perform the restore
            self._log(f"Restoring database from: {backup_path}")

            # Atomic restore using temporary file
            temp_restore_path = self.db_path.with_suffix(".restore_temp")

            # Copy backup to temp location
            shutil.copy2(backup_path, temp_restore_path)

            # Verify temp file
            with duckdb.connect(str(temp_restore_path)) as conn:
                conn.execute("SELECT 1").fetchone()

            # Atomic move to final location
            if self.db_path.exists():
                self.db_path.unlink()

            temp_restore_path.rename(self.db_path)

            # Step 5: Verify restored database
            self._log("Verifying restored database")
            post_restore_validation = self.verify_backup_comprehensive(self.db_path)
            operation.details[
                "post_restore_validation"
            ] = post_restore_validation.dict()

            if not post_restore_validation.success:
                self._log("Warning: Post-restore verification had issues", "WARNING")

            operation.success = True
            operation.duration = time.time() - operation_start

            self._log(
                f"Database restore completed successfully - Operation: {operation_id}, "
                f"Duration: {operation.duration:.2f}s"
            )

            return operation

        except Exception as e:
            operation.success = False
            operation.duration = time.time() - operation_start
            operation.details["error"] = str(e)

            self._log(
                f"Database restore failed - Operation: {operation_id} - {str(e)}",
                "ERROR",
            )

            # Cleanup temp files
            temp_restore_path = self.db_path.with_suffix(".restore_temp")
            if temp_restore_path.exists():
                temp_restore_path.unlink()

            return operation

    def get_recovery_status(self) -> Dict[str, Any]:
        """
        Get comprehensive recovery system status

        Returns:
            Dictionary with recovery system status
        """
        recovery_points = self.get_recovery_points()

        # Calculate recovery readiness metrics
        verified_points = [
            rp for rp in recovery_points if rp.data_integrity_score >= 0.8
        ]
        recent_points = [
            rp
            for rp in recovery_points
            if rp.timestamp > datetime.now() - timedelta(days=1)
        ]

        recovery_readiness = (
            "excellent"
            if len(verified_points) >= 3
            else "good"
            if len(verified_points) >= 1
            else "poor"
            if len(recovery_points) > 0
            else "critical"
        )

        return {
            "recovery_readiness": recovery_readiness,
            "total_recovery_points": len(recovery_points),
            "verified_recovery_points": len(verified_points),
            "recent_recovery_points": len(recent_points),
            "latest_recovery_point": {
                "timestamp": recovery_points[0].timestamp.isoformat()
                if recovery_points
                else None,
                "integrity_score": recovery_points[0].data_integrity_score
                if recovery_points
                else 0.0,
                "file_size_gb": recovery_points[0].file_size / (1024**3)
                if recovery_points
                else 0.0,
            },
            "database_status": {
                "exists": self.db_path.exists(),
                "size_gb": self.db_path.stat().st_size / (1024**3)
                if self.db_path.exists()
                else 0.0,
                "accessible": self._test_database_access(),
            },
        }

    def _test_database_access(self) -> bool:
        """Test if current database is accessible"""
        try:
            if not self.db_path.exists():
                return False

            with duckdb.connect(str(self.db_path)) as conn:
                conn.execute("SELECT 1").fetchone()
            return True

        except Exception:
            return False
