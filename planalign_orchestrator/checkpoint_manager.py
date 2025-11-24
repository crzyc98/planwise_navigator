#!/usr/bin/env python3
"""
Enhanced Checkpoint Manager

Provides comprehensive state capture, integrity validation, and recovery capabilities
for multi-year simulations. Transforms the existing checkpoint system from simple
logging into a robust recovery framework.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
from planalign_orchestrator.config import get_database_path

logger = logging.getLogger(__name__)


class CheckpointValidationError(Exception):
    """Raised when checkpoint validation fails"""

    pass


class CheckpointManager:
    """Enhanced checkpoint manager with comprehensive state capture and recovery"""

    def __init__(
        self,
        checkpoint_dir: str = ".navigator_checkpoints",
        db_path: Optional[str] = None,
    ):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)
        self.db_path = db_path or str(get_database_path())
        self.checkpoint_version = "2.0"

    def save_checkpoint(
        self, year: int, run_id: str, config_hash: str
    ) -> Dict[str, Any]:
        """Save comprehensive checkpoint with full state validation"""

        logger.info(f"Creating checkpoint for year {year}")

        # Gather comprehensive state data
        checkpoint_data = {
            "metadata": {
                "year": year,
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "config_hash": config_hash,
                "checkpoint_version": self.checkpoint_version,
            },
            "database_state": self._capture_database_state(year),
            "validation_data": self._capture_validation_data(year),
            "performance_metrics": self._capture_performance_metrics(year),
            "configuration_snapshot": self._capture_configuration(),
        }

        # Add integrity hash
        checkpoint_data["integrity_hash"] = self._calculate_integrity_hash(
            checkpoint_data
        )

        # Save with atomic operations
        return self._save_atomic_checkpoint(year, checkpoint_data)

    def _capture_database_state(self, year: int) -> Dict[str, Any]:
        """Capture comprehensive database state for the year"""
        state = {"table_counts": {}, "data_quality_metrics": {}, "key_aggregates": {}}

        try:
            with duckdb.connect(self.db_path) as conn:
                # Critical table row counts
                tables = [
                    "fct_yearly_events",
                    "fct_workforce_snapshot",
                    "int_employee_contributions",
                    "int_baseline_workforce",
                    "int_employee_compensation_by_year",
                    "int_workforce_needs",
                ]

                for table in tables:
                    try:
                        count = conn.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE simulation_year = ?",
                            [year],
                        ).fetchone()[0]
                        state["table_counts"][table] = count
                    except Exception as e:
                        state["table_counts"][table] = f"ERROR: {str(e)}"

                # Data quality metrics
                try:
                    # Check for duplicate events
                    duplicate_count = conn.execute(
                        """
                        SELECT COUNT(*) FROM (
                            SELECT employee_id, simulation_year, event_type, effective_date
                            FROM fct_yearly_events
                            WHERE simulation_year = ?
                            GROUP BY employee_id, simulation_year, event_type, effective_date
                            HAVING COUNT(*) > 1
                        )
                    """,
                        [year],
                    ).fetchone()[0]
                    state["data_quality_metrics"]["duplicate_events"] = duplicate_count

                    # Check workforce balance
                    workforce_count = conn.execute(
                        "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    state["data_quality_metrics"]["workforce_count"] = workforce_count

                    # Check event type distribution
                    event_types = conn.execute(
                        """
                        SELECT event_type, COUNT(*)
                        FROM fct_yearly_events
                        WHERE simulation_year = ?
                        GROUP BY event_type
                    """,
                        [year],
                    ).fetchall()
                    state["data_quality_metrics"]["event_type_distribution"] = dict(
                        event_types
                    )

                except Exception as e:
                    state["data_quality_metrics"]["error"] = str(e)

        except Exception as e:
            logger.error(f"Error capturing database state: {e}")
            state["capture_error"] = str(e)

        return state

    def _capture_validation_data(self, year: int) -> Dict[str, Any]:
        """Capture validation checksums and key metrics"""
        validation = {}

        try:
            with duckdb.connect(self.db_path) as conn:
                # Event type distribution
                event_dist = conn.execute(
                    """
                    SELECT event_type, COUNT(*)
                    FROM fct_yearly_events
                    WHERE simulation_year = ?
                    GROUP BY event_type
                """,
                    [year],
                ).fetchall()
                validation["event_distribution"] = dict(event_dist)

                # Compensation totals
                comp_total = conn.execute(
                    """
                    SELECT SUM(total_compensation)
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                """,
                    [year],
                ).fetchone()[0]
                validation["total_compensation"] = (
                    float(comp_total) if comp_total else 0
                )

                # Contribution totals
                contrib_total = conn.execute(
                    """
                    SELECT SUM(annual_contribution_amount)
                    FROM int_employee_contributions
                    WHERE simulation_year = ?
                """,
                    [year],
                ).fetchone()[0]
                validation["total_contributions"] = (
                    float(contrib_total) if contrib_total else 0
                )

                # Employee count validation
                baseline_count = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM int_baseline_workforce
                    WHERE simulation_year = ?
                """,
                    [year],
                ).fetchone()[0]
                validation["baseline_employee_count"] = int(baseline_count)

                # Workforce needs validation
                hires_needed = conn.execute(
                    """
                    SELECT COALESCE(SUM(hires_needed), 0)
                    FROM int_workforce_needs_by_level
                    WHERE simulation_year = ?
                """,
                    [year],
                ).fetchone()[0]
                validation["total_hires_needed"] = int(hires_needed)

        except Exception as e:
            validation["error"] = str(e)

        return validation

    def _capture_performance_metrics(self, year: int) -> Dict[str, Any]:
        """Capture performance metrics for the simulation year"""
        metrics = {"checkpoint_creation_time": datetime.now().isoformat(), "year": year}

        try:
            with duckdb.connect(self.db_path) as conn:
                # Database file size (approximate)
                db_stats = conn.execute("PRAGMA database_size").fetchone()
                if db_stats:
                    metrics["database_size_blocks"] = db_stats[0]

                # Table count
                table_count = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'main'
                """
                ).fetchone()[0]
                metrics["total_tables"] = int(table_count)

        except Exception as e:
            metrics["error"] = str(e)

        return metrics

    def _capture_configuration(self) -> Dict[str, Any]:
        """Capture current configuration snapshot"""
        config = {
            "checkpoint_version": self.checkpoint_version,
            "database_path": self.db_path,
            "checkpoint_dir": str(self.checkpoint_dir),
        }

        # Try to capture simulation config if available
        try:
            config_path = Path("config/simulation_config.yaml")
            if config_path.exists():
                config["simulation_config_exists"] = True
                config["simulation_config_size"] = config_path.stat().st_size
            else:
                config["simulation_config_exists"] = False
        except Exception as e:
            config["config_capture_error"] = str(e)

        return config

    def _calculate_integrity_hash(self, checkpoint_data: Dict[str, Any]) -> str:
        """Calculate integrity hash for checkpoint validation"""
        # Create a deterministic string representation for hashing
        # Exclude the integrity_hash field itself and timestamps that change
        hash_data = checkpoint_data.copy()
        hash_data.pop("integrity_hash", None)

        # Remove timestamp fields that change between identical states
        if "metadata" in hash_data:
            metadata = hash_data["metadata"].copy()
            metadata.pop("timestamp", None)
            hash_data["metadata"] = metadata

        if "performance_metrics" in hash_data:
            perf = hash_data["performance_metrics"].copy()
            perf.pop("checkpoint_creation_time", None)
            hash_data["performance_metrics"] = perf

        # Create deterministic JSON string
        json_str = json.dumps(hash_data, sort_keys=True, separators=(",", ":"))

        # Calculate SHA-256 hash
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def _save_atomic_checkpoint(
        self, year: int, checkpoint_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Save checkpoint with atomic operations and compression"""

        # Serialize and compress
        json_data = json.dumps(checkpoint_data, indent=2)
        compressed_data = gzip.compress(json_data.encode("utf-8"))

        # Write to temporary file first
        temp_path = self.checkpoint_dir / f"year_{year}.checkpoint.tmp"
        final_path = self.checkpoint_dir / f"year_{year}.checkpoint.gz"

        try:
            # Atomic write
            with open(temp_path, "wb") as f:
                f.write(compressed_data)

            # Atomic rename
            temp_path.rename(final_path)

            # Update latest checkpoint link
            latest_path = self.checkpoint_dir / "latest_checkpoint.gz"
            if latest_path.exists():
                latest_path.unlink()
            latest_path.symlink_to(final_path.name)

            # Also save uncompressed legacy format for compatibility
            legacy_path = self.checkpoint_dir / f"year_{year}.json"
            legacy_data = {
                "year": year,
                "stage": "cleanup",
                "timestamp": checkpoint_data["metadata"]["timestamp"],
                "state_hash": checkpoint_data["integrity_hash"],
            }
            with open(legacy_path, "w") as f:
                json.dump(legacy_data, f)

            logger.info(
                f"Checkpoint saved: {final_path} ({len(compressed_data)} bytes compressed)"
            )

        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            raise

        return checkpoint_data

    def load_checkpoint(self, year: int) -> Optional[Dict[str, Any]]:
        """Load and validate checkpoint for specific year"""
        checkpoint_path = self.checkpoint_dir / f"year_{year}.checkpoint.gz"

        if not checkpoint_path.exists():
            logger.warning(f"No checkpoint found for year {year}")
            return None

        try:
            # Load compressed checkpoint
            with open(checkpoint_path, "rb") as f:
                compressed_data = f.read()

            json_data = gzip.decompress(compressed_data).decode("utf-8")
            checkpoint_data = json.loads(json_data)

            # Validate integrity
            if not self._validate_checkpoint_integrity(checkpoint_data):
                raise CheckpointValidationError(
                    f"Checkpoint integrity validation failed for year {year}"
                )

            logger.info(f"Checkpoint loaded successfully for year {year}")
            return checkpoint_data

        except Exception as e:
            logger.error(f"Error loading checkpoint for year {year}: {e}")
            return None

    def _validate_checkpoint_integrity(self, checkpoint_data: Dict[str, Any]) -> bool:
        """Validate checkpoint integrity using stored hash"""
        if "integrity_hash" not in checkpoint_data:
            logger.error("Checkpoint missing integrity hash")
            return False

        stored_hash = checkpoint_data["integrity_hash"]
        calculated_hash = self._calculate_integrity_hash(checkpoint_data)

        if stored_hash != calculated_hash:
            logger.error(
                f"Checkpoint integrity hash mismatch: stored={stored_hash[:8]}..., calculated={calculated_hash[:8]}..."
            )
            return False

        return True

    def can_resume_from_year(self, year: int, current_config_hash: str) -> bool:
        """Check if simulation can safely resume from specified year"""
        checkpoint = self.load_checkpoint(year)

        if not checkpoint:
            return False

        # Check configuration compatibility
        checkpoint_config_hash = checkpoint["metadata"].get("config_hash")
        if checkpoint_config_hash != current_config_hash:
            logger.warning(
                f"Configuration changed since checkpoint. Checkpoint: {checkpoint_config_hash}, Current: {current_config_hash}"
            )
            return False

        # Validate database state matches checkpoint
        return self._validate_database_consistency(year, checkpoint)

    def _validate_database_consistency(
        self, year: int, checkpoint: Dict[str, Any]
    ) -> bool:
        """Validate that current database state matches checkpoint"""
        expected_counts = checkpoint.get("database_state", {}).get("table_counts", {})

        if not expected_counts:
            logger.warning("Checkpoint missing table count data")
            return False

        try:
            with duckdb.connect(self.db_path) as conn:
                for table, expected_count in expected_counts.items():
                    if isinstance(expected_count, str) and "ERROR" in expected_count:
                        continue  # Skip tables that had errors during checkpoint

                    try:
                        actual_count = conn.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE simulation_year = ?",
                            [year],
                        ).fetchone()[0]

                        if actual_count != expected_count:
                            logger.error(
                                f"Database inconsistency: {table} has {actual_count} rows, expected {expected_count}"
                            )
                            return False

                    except Exception as e:
                        logger.error(f"Error validating table {table}: {e}")
                        return False

        except Exception as e:
            logger.error(f"Error validating database consistency: {e}")
            return False

        return True

    def find_latest_resumable_checkpoint(
        self, current_config_hash: str
    ) -> Optional[int]:
        """Find the latest year that can be safely resumed from"""
        checkpoint_files = list(self.checkpoint_dir.glob("year_*.checkpoint.gz"))

        # Extract years and sort in descending order
        years = []
        for file_path in checkpoint_files:
            try:
                year = int(file_path.stem.split("_")[1].split(".")[0])
                years.append(year)
            except (ValueError, IndexError):
                continue

        years.sort(reverse=True)

        # Find latest resumable year
        for year in years:
            if self.can_resume_from_year(year, current_config_hash):
                logger.info(f"Found resumable checkpoint at year {year}")
                return year

        logger.warning("No resumable checkpoints found")
        return None

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all available checkpoints with basic metadata"""
        checkpoints = []

        # Check both compressed and legacy formats
        compressed_files = list(self.checkpoint_dir.glob("year_*.checkpoint.gz"))
        legacy_files = list(self.checkpoint_dir.glob("year_*.json"))

        # Process compressed files first (preferred)
        for file_path in compressed_files:
            try:
                year = int(file_path.stem.split("_")[1].split(".")[0])
                checkpoint = self.load_checkpoint(year)
                if checkpoint:
                    checkpoints.append(
                        {
                            "year": year,
                            "timestamp": checkpoint["metadata"]["timestamp"],
                            "format": "compressed",
                            "file_size": file_path.stat().st_size,
                            "integrity_valid": True,
                        }
                    )
            except Exception as e:
                logger.warning(f"Error processing checkpoint {file_path}: {e}")

        # Add legacy files that don't have compressed versions
        compressed_years = {cp["year"] for cp in checkpoints}
        for file_path in legacy_files:
            try:
                year = int(file_path.stem.split("_")[1])
                if year not in compressed_years:
                    with open(file_path, "r") as f:
                        data = json.load(f)
                    checkpoints.append(
                        {
                            "year": year,
                            "timestamp": data.get("timestamp", "unknown"),
                            "format": "legacy",
                            "file_size": file_path.stat().st_size,
                            "integrity_valid": False,  # Legacy format has no integrity validation
                        }
                    )
            except Exception as e:
                logger.warning(f"Error processing legacy checkpoint {file_path}: {e}")

        # Sort by year
        checkpoints.sort(key=lambda x: x["year"])
        return checkpoints

    def cleanup_old_checkpoints(self, keep_latest: int = 5) -> int:
        """Clean up old checkpoints, keeping only the latest N"""
        checkpoints = self.list_checkpoints()

        if len(checkpoints) <= keep_latest:
            return 0

        # Sort by year and keep only the latest
        checkpoints.sort(key=lambda x: x["year"], reverse=True)
        to_remove = checkpoints[keep_latest:]

        removed_count = 0
        for checkpoint in to_remove:
            year = checkpoint["year"]
            try:
                # Remove both compressed and legacy files
                compressed_path = self.checkpoint_dir / f"year_{year}.checkpoint.gz"
                legacy_path = self.checkpoint_dir / f"year_{year}.json"

                if compressed_path.exists():
                    compressed_path.unlink()
                    removed_count += 1

                if legacy_path.exists():
                    legacy_path.unlink()
                    removed_count += 1

                logger.info(f"Removed checkpoint for year {year}")

            except Exception as e:
                logger.error(f"Error removing checkpoint for year {year}: {e}")

        return removed_count
