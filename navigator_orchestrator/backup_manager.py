"""
Production Data Safety & Backup System (Epic E043)

Story S043-01: Automated Backup System
Implements enterprise-grade backup management with atomic operations,
verification, and automated cleanup for PlanWise Navigator.

Features:
- Timestamped backups with atomic copy operations
- Backup integrity verification
- Automated cleanup with configurable retention
- Latest symlink management
- Comprehensive error handling and rollback
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import duckdb
from pydantic import BaseModel, Field


class BackupConfiguration(BaseModel):
    """Configuration for backup operations"""
    backup_dir: Path = Field(default=Path("backups"), description="Directory for backup storage")
    retention_days: int = Field(default=7, description="Number of days to retain backups")
    verify_backups: bool = Field(default=True, description="Enable backup verification")
    max_backup_size_gb: float = Field(default=10.0, description="Maximum backup size in GB")


class BackupMetadata(BaseModel):
    """Metadata for backup operations"""
    backup_path: Path
    timestamp: datetime
    original_size: int
    backup_size: int
    verification_status: str
    creation_time: float


class BackupManager:
    """
    Enterprise-grade backup manager for simulation database

    Provides atomic backup operations with verification and cleanup
    """

    def __init__(self, config: Optional[BackupConfiguration] = None, db_path: str = "simulation.duckdb"):
        """
        Initialize backup manager

        Args:
            config: Backup configuration, uses defaults if None
            db_path: Path to the database file to backup
        """
        self.config = config or BackupConfiguration()
        self.db_path = Path(db_path)
        self.backup_dir = self.config.backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Initialize logging
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Setup basic logging for backup operations"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        self.log_file = log_dir / "backup_manager.log"

    def _log(self, message: str) -> None:
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)

        print(f"BACKUP: {message}")

    def create_backup(self) -> BackupMetadata:
        """
        Create timestamped backup with atomic operations

        Returns:
            BackupMetadata: Metadata about the created backup

        Raises:
            FileNotFoundError: If database file doesn't exist
            OSError: If backup operation fails
            ValueError: If backup verification fails
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        start_time = datetime.now()
        timestamp = start_time.strftime('%Y%m%d_%H%M%S_%f')[:19]  # Add microseconds for uniqueness
        backup_filename = f"simulation_{timestamp}.duckdb"
        backup_path = self.backup_dir / backup_filename
        temp_backup_path = self.backup_dir / f"{backup_filename}.tmp"

        self._log(f"Starting backup creation: {backup_filename}")

        try:
            # Get original file size
            original_size = self.db_path.stat().st_size
            self._log(f"Original database size: {original_size / (1024**3):.2f} GB")

            # Check available disk space
            self._check_disk_space(original_size)

            # Atomic copy with temporary file
            self._log(f"Copying database to temporary file: {temp_backup_path}")
            shutil.copy2(self.db_path, temp_backup_path)

            # Verify backup integrity
            if self.config.verify_backups:
                self._verify_backup(temp_backup_path)

            # Atomic rename to final location
            temp_backup_path.rename(backup_path)

            # Get backup file size
            backup_size = backup_path.stat().st_size

            # Update latest symlink
            self._update_latest_link(backup_path)

            # Cleanup old backups
            self._cleanup_old_backups()

            creation_time = (datetime.now() - start_time).total_seconds()

            metadata = BackupMetadata(
                backup_path=backup_path,
                timestamp=start_time,
                original_size=original_size,
                backup_size=backup_size,
                verification_status="verified" if self.config.verify_backups else "skipped",
                creation_time=creation_time
            )

            self._log(f"Backup created successfully in {creation_time:.2f}s: {backup_path}")
            return metadata

        except Exception as e:
            # Cleanup temporary file on failure
            if temp_backup_path.exists():
                temp_backup_path.unlink()

            self._log(f"Backup creation failed: {str(e)}")
            raise

    def _check_disk_space(self, required_size: int) -> None:
        """
        Check available disk space for backup

        Args:
            required_size: Required space in bytes

        Raises:
            OSError: If insufficient disk space
        """
        # Add 20% buffer for safety
        required_with_buffer = int(required_size * 1.2)

        # Get available disk space
        statvfs = os.statvfs(self.backup_dir)
        available_space = statvfs.f_bavail * statvfs.f_frsize

        if available_space < required_with_buffer:
            available_gb = available_space / (1024**3)
            required_gb = required_with_buffer / (1024**3)
            raise OSError(
                f"Insufficient disk space. Available: {available_gb:.2f} GB, "
                f"Required: {required_gb:.2f} GB"
            )

    def _verify_backup(self, backup_path: Path) -> None:
        """
        Verify backup integrity

        Args:
            backup_path: Path to backup file to verify

        Raises:
            ValueError: If backup verification fails
        """
        self._log(f"Verifying backup integrity: {backup_path}")

        try:
            # Test DuckDB connection and basic query
            with duckdb.connect(str(backup_path)) as conn:
                # Test basic connectivity
                result = conn.execute("SELECT 1 as test").fetchone()
                if result[0] != 1:
                    raise ValueError("Basic connectivity test failed")

                # Get table count for basic integrity check
                tables = conn.execute("SHOW TABLES").fetchall()
                table_count = len(tables)

                self._log(f"Backup verification passed: {table_count} tables found")

        except Exception as e:
            raise ValueError(f"Backup verification failed: {str(e)}")

    def _update_latest_link(self, backup_path: Path) -> None:
        """
        Update latest symlink to point to newest backup

        Args:
            backup_path: Path to the latest backup
        """
        latest_link = self.backup_dir / "latest.duckdb"

        try:
            # Remove existing symlink if it exists
            if latest_link.is_symlink():
                latest_link.unlink()
            elif latest_link.exists():
                # If it's a regular file, remove it
                latest_link.unlink()

            # Create new symlink
            latest_link.symlink_to(backup_path.name)
            self._log(f"Updated latest symlink to: {backup_path.name}")

        except Exception as e:
            self._log(f"Warning: Could not update latest symlink: {str(e)}")

    def _cleanup_old_backups(self) -> None:
        """
        Remove backups older than retention period
        """
        cutoff_date = datetime.now() - timedelta(days=self.config.retention_days)
        removed_count = 0
        total_size_removed = 0

        # Find backup files (exclude latest symlink and other non-backup files)
        backup_pattern = "simulation_*.duckdb"

        for backup_file in self.backup_dir.glob(backup_pattern):
            try:
                # Extract timestamp from filename
                filename_parts = backup_file.stem.split('_')
                if len(filename_parts) >= 3:
                    timestamp_str = f"{filename_parts[1]}_{filename_parts[2]}"
                    file_timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')

                    if file_timestamp < cutoff_date:
                        file_size = backup_file.stat().st_size
                        backup_file.unlink()
                        removed_count += 1
                        total_size_removed += file_size
                        self._log(f"Removed old backup: {backup_file.name}")

            except (ValueError, OSError) as e:
                self._log(f"Warning: Could not process backup file {backup_file}: {str(e)}")

        if removed_count > 0:
            size_mb = total_size_removed / (1024**2)
            self._log(f"Cleanup completed: {removed_count} files removed, {size_mb:.1f} MB freed")

    def list_backups(self) -> List[BackupMetadata]:
        """
        List all available backups with metadata

        Returns:
            List of backup metadata sorted by timestamp (newest first)
        """
        backups = []
        backup_pattern = "simulation_*.duckdb"

        for backup_file in self.backup_dir.glob(backup_pattern):
            try:
                # Extract timestamp from filename
                filename_parts = backup_file.stem.split('_')
                if len(filename_parts) >= 3:
                    timestamp_str = f"{filename_parts[1]}_{filename_parts[2]}"
                    file_timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')

                    file_size = backup_file.stat().st_size

                    metadata = BackupMetadata(
                        backup_path=backup_file,
                        timestamp=file_timestamp,
                        original_size=0,  # Not stored in filename
                        backup_size=file_size,
                        verification_status="unknown",
                        creation_time=0.0  # Not stored in filename
                    )
                    backups.append(metadata)

            except (ValueError, OSError) as e:
                self._log(f"Warning: Could not process backup file {backup_file}: {str(e)}")

        # Sort by timestamp, newest first
        return sorted(backups, key=lambda x: x.timestamp, reverse=True)

    def restore_backup(self, backup_path: Optional[Path] = None) -> None:
        """
        Restore database from backup

        Args:
            backup_path: Specific backup to restore, uses latest if None

        Raises:
            FileNotFoundError: If backup file doesn't exist
            OSError: If restore operation fails
        """
        if backup_path is None:
            # Use latest backup
            latest_link = self.backup_dir / "latest.duckdb"
            if latest_link.exists():
                backup_path = latest_link.resolve()
            else:
                backups = self.list_backups()
                if not backups:
                    raise FileNotFoundError("No backups available for restore")
                backup_path = backups[0].backup_path

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        self._log(f"Restoring database from backup: {backup_path}")

        try:
            # Verify backup before restore
            if self.config.verify_backups:
                self._verify_backup(backup_path)

            # Create backup of current database if it exists
            if self.db_path.exists():
                emergency_backup = self.db_path.with_suffix('.emergency_backup')
                shutil.copy2(self.db_path, emergency_backup)
                self._log(f"Created emergency backup: {emergency_backup}")

            # Restore from backup
            shutil.copy2(backup_path, self.db_path)

            self._log(f"Database restored successfully from: {backup_path}")

        except Exception as e:
            self._log(f"Restore operation failed: {str(e)}")
            raise

    def get_backup_status(self) -> dict:
        """
        Get comprehensive backup system status

        Returns:
            Dictionary with backup system status information
        """
        backups = self.list_backups()

        total_size = sum(backup.backup_size for backup in backups)

        latest_backup = backups[0] if backups else None

        return {
            "backup_count": len(backups),
            "total_size_gb": total_size / (1024**3),
            "latest_backup": {
                "path": str(latest_backup.backup_path) if latest_backup else None,
                "timestamp": latest_backup.timestamp.isoformat() if latest_backup else None,
                "size_gb": latest_backup.backup_size / (1024**3) if latest_backup else 0
            },
            "retention_days": self.config.retention_days,
            "backup_dir": str(self.backup_dir),
            "database_exists": self.db_path.exists(),
            "database_size_gb": self.db_path.stat().st_size / (1024**3) if self.db_path.exists() else 0
        }
