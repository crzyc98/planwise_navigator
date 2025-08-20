#!/usr/bin/env python3
"""
Database Location Migration Utility - Epic E050, Story S050-02

This utility safely migrates existing simulation databases from the legacy root location
(simulation.duckdb) to the standardized location (dbt/simulation.duckdb) with data
integrity validation and rollback capability.

Usage:
    python scripts/migrate_database_location.py [--dry-run] [--force] [--create-symlink]

Options:
    --dry-run: Show what would be done without making changes
    --force: Overwrite existing target database if it exists
    --create-symlink: Create compatibility symlink for transition period
"""

import argparse
import hashlib
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import duckdb


class DatabaseMigrator:
    """Handles safe migration of simulation database between locations."""

    def __init__(self, project_root: Path = None):
        """Initialize migrator with project paths."""
        self.project_root = project_root or Path.cwd()
        self.root_path = self.project_root / "simulation.duckdb"
        self.target_path = self.project_root / "dbt" / "simulation.duckdb"
        self.backup_dir = self.project_root / "backups"

        # Migration tracking
        self.migration_log = []

    def log(self, message: str, level: str = "INFO") -> None:
        """Log migration activity with timestamp."""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {level}: {message}"
        self.migration_log.append(log_entry)
        print(log_entry)

    def check_preconditions(self) -> Tuple[bool, str]:
        """Check if migration is needed and safe to proceed."""
        # Check if source database exists
        if not self.root_path.exists():
            return False, "No migration needed - no database at root location"

        # Check if target already exists
        if self.target_path.exists():
            return False, "Target database already exists at dbt/simulation.duckdb"

        # Check if target directory can be created
        try:
            self.target_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Cannot create target directory: {e}"

        # Check available disk space
        source_size = self.root_path.stat().st_size
        available_space = shutil.disk_usage(self.target_path.parent).free
        required_space = source_size * 2  # Source + backup + buffer

        if available_space < required_space:
            return False, f"Insufficient disk space. Need {required_space / (1024**3):.2f} GB, have {available_space / (1024**3):.2f} GB"

        return True, "Migration preconditions satisfied"

    def create_backup(self) -> Path:
        """Create timestamped backup of source database."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"simulation_backup_{timestamp}.duckdb"

        self.log(f"Creating backup: {backup_path}")
        shutil.copy2(self.root_path, backup_path)

        # Verify backup integrity
        if self._verify_database_integrity(backup_path):
            self.log("Backup created and verified successfully")
            return backup_path
        else:
            backup_path.unlink(missing_ok=True)
            raise RuntimeError("Backup verification failed")

    def _verify_database_integrity(self, db_path: Path) -> bool:
        """Verify database can be opened and contains expected tables."""
        try:
            with duckdb.connect(str(db_path)) as conn:
                # Check database is accessible
                conn.execute("SELECT 1").fetchone()

                # Check critical tables exist
                tables = conn.execute("SHOW TABLES").fetchall()
                table_names = {t[0] for t in tables}

                # Look for any of the expected simulation tables
                expected_tables = {
                    'fct_yearly_events', 'fct_workforce_snapshot',
                    'stg_census_data', 'int_baseline_workforce'
                }

                if not any(table in table_names for table in expected_tables):
                    self.log(f"Warning: No expected simulation tables found. Tables: {table_names}", "WARN")
                    # Don't fail if no expected tables - might be empty database

                return True

        except Exception as e:
            self.log(f"Database integrity check failed: {e}", "ERROR")
            return False

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file for integrity verification."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def migrate_database(self, force: bool = False) -> bool:
        """Perform the database migration with validation."""
        try:
            # Check preconditions
            can_migrate, message = self.check_preconditions()
            if not can_migrate:
                if "No migration needed" in message:
                    self.log(message)
                    return True
                elif "already exists" in message and not force:
                    self.log(f"Migration blocked: {message}. Use --force to overwrite.", "ERROR")
                    return False
                elif "already exists" in message and force:
                    self.log("Forcing migration - removing existing target database", "WARN")
                    self.target_path.unlink()
                else:
                    self.log(f"Migration failed: {message}", "ERROR")
                    return False

            # Create backup
            backup_path = self.create_backup()

            # Calculate source hash for verification
            source_hash = self._calculate_file_hash(self.root_path)
            self.log(f"Source database hash: {source_hash}")

            # Copy database to target location
            self.log(f"Copying database: {self.root_path} -> {self.target_path}")
            shutil.copy2(self.root_path, self.target_path)

            # Verify target database
            target_hash = self._calculate_file_hash(self.target_path)
            if source_hash != target_hash:
                self.log("Hash mismatch - migration verification failed", "ERROR")
                self._rollback(backup_path)
                return False

            # Verify database functionality
            if not self._verify_database_integrity(self.target_path):
                self.log("Target database integrity check failed", "ERROR")
                self._rollback(backup_path)
                return False

            self.log("✅ Database migration completed successfully")
            self.log(f"New database location: {self.target_path}")
            self.log(f"Backup available at: {backup_path}")

            return True

        except Exception as e:
            self.log(f"Migration failed with exception: {e}", "ERROR")
            return False

    def _rollback(self, backup_path: Path) -> None:
        """Rollback migration by restoring from backup."""
        self.log("Rolling back migration", "WARN")
        try:
            if self.target_path.exists():
                self.target_path.unlink()
            shutil.copy2(backup_path, self.root_path)
            self.log("Rollback completed successfully")
        except Exception as e:
            self.log(f"Rollback failed: {e}", "ERROR")

    def create_compatibility_symlink(self) -> bool:
        """Create symlink from old location to new location for transition period."""
        if self.root_path.exists():
            self.log("Cannot create symlink - root database file still exists", "ERROR")
            return False

        if not self.target_path.exists():
            self.log("Cannot create symlink - target database does not exist", "ERROR")
            return False

        try:
            # Create relative symlink
            relative_target = os.path.relpath(self.target_path, self.root_path.parent)
            self.root_path.symlink_to(relative_target)
            self.log(f"Created compatibility symlink: {self.root_path} -> {relative_target}")
            return True
        except Exception as e:
            self.log(f"Failed to create symlink: {e}", "ERROR")
            return False

    def cleanup_old_database(self, confirm: bool = False) -> bool:
        """Remove old database file after successful migration."""
        if not confirm:
            self.log("Use --confirm flag to actually delete old database file", "WARN")
            return False

        if not self.root_path.exists():
            self.log("No old database file to clean up")
            return True

        try:
            # Final verification that target exists and works
            if not self.target_path.exists() or not self._verify_database_integrity(self.target_path):
                self.log("Cannot cleanup - target database not verified", "ERROR")
                return False

            self.root_path.unlink()
            self.log(f"Cleaned up old database: {self.root_path}")
            return True
        except Exception as e:
            self.log(f"Cleanup failed: {e}", "ERROR")
            return False

    def generate_migration_report(self) -> str:
        """Generate comprehensive migration report."""
        report_lines = [
            "=" * 60,
            "DATABASE LOCATION MIGRATION REPORT",
            "=" * 60,
            f"Project Root: {self.project_root}",
            f"Source: {self.root_path}",
            f"Target: {self.target_path}",
            f"Migration Time: {datetime.now().isoformat()}",
            "",
            "Migration Log:",
            "-" * 40,
        ]

        report_lines.extend(self.migration_log)

        report_lines.extend([
            "",
            "Post-Migration Status:",
            "-" * 40,
            f"Source exists: {self.root_path.exists()}",
            f"Target exists: {self.target_path.exists()}",
            f"Target size: {self.target_path.stat().st_size if self.target_path.exists() else 'N/A'} bytes",
            "",
            "Next Steps:",
            "-" * 40,
            "1. Test applications with new database location",
            "2. Update any remaining hardcoded paths",
            "3. Consider creating compatibility symlink if needed",
            "4. Update team documentation and notify developers",
            "=" * 60
        ])

        return "\n".join(report_lines)


def main():
    """Main migration script entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate simulation database to standardized location",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check what would be migrated
    python scripts/migrate_database_location.py --dry-run

    # Perform migration
    python scripts/migrate_database_location.py

    # Force migration overwriting existing target
    python scripts/migrate_database_location.py --force

    # Create transition symlink after migration
    python scripts/migrate_database_location.py --create-symlink
        """
    )

    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing target database if it exists"
    )
    parser.add_argument(
        "--create-symlink", action="store_true",
        help="Create compatibility symlink for transition period"
    )
    parser.add_argument(
        "--cleanup", action="store_true",
        help="Remove old database file after migration (requires --confirm)"
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Confirm destructive operations"
    )
    parser.add_argument(
        "--project-root", type=Path,
        help="Project root directory (default: current directory)"
    )

    args = parser.parse_args()

    # Initialize migrator
    migrator = DatabaseMigrator(args.project_root)

    # Handle dry run
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
        print("-" * 40)

        can_migrate, message = migrator.check_preconditions()
        print(f"Migration check: {message}")

        if migrator.root_path.exists():
            size_mb = migrator.root_path.stat().st_size / (1024 * 1024)
            print(f"Source database: {migrator.root_path} ({size_mb:.2f} MB)")

        print(f"Target location: {migrator.target_path}")
        print(f"Backup location: {migrator.backup_dir}")

        if can_migrate:
            print("\n✅ Migration would proceed")
        else:
            print("\n❌ Migration would be blocked")

        return 0 if can_migrate else 1

    # Handle symlink creation
    if args.create_symlink:
        success = migrator.create_compatibility_symlink()
        return 0 if success else 1

    # Handle cleanup
    if args.cleanup:
        success = migrator.cleanup_old_database(args.confirm)
        return 0 if success else 1

    # Perform migration
    success = migrator.migrate_database(args.force)

    # Generate and save report
    report = migrator.generate_migration_report()
    print("\n" + report)

    # Save report to file
    report_path = migrator.project_root / "migration_report.txt"
    try:
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\nMigration report saved to: {report_path}")
    except Exception as e:
        print(f"Warning: Could not save report: {e}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
