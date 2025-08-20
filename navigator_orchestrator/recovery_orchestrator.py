#!/usr/bin/env python3
"""
Recovery Orchestrator

Provides comprehensive recovery logic for resuming multi-year simulations from
checkpoints. Handles validation, configuration drift detection, and safe resume
operations.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .checkpoint_manager import CheckpointManager, CheckpointValidationError

logger = logging.getLogger(__name__)


class RecoveryValidationError(Exception):
    """Raised when recovery validation fails"""

    pass


class ConfigurationDriftError(Exception):
    """Raised when configuration has changed incompatibly since checkpoint"""

    pass


class RecoveryOrchestrator:
    """Orchestrates recovery operations for multi-year simulations"""

    def __init__(self, checkpoint_manager: CheckpointManager, logger_instance=None):
        self.checkpoint_manager = checkpoint_manager
        self.logger = logger_instance or logger

    def resume_simulation(
        self, target_end_year: int, config_hash: str, force_restart: bool = False
    ) -> Optional[int]:
        """Resume simulation from latest valid checkpoint

        Returns:
            int: Year to resume from (next year after checkpoint), or None if no valid checkpoint
        """

        if force_restart:
            self.logger.warning("Force restart requested - ignoring all checkpoints")
            return None

        # Find resumption point
        resume_year = self.checkpoint_manager.find_latest_resumable_checkpoint(
            config_hash
        )

        if not resume_year:
            self.logger.warning("No valid checkpoint found. Starting from beginning.")
            return None

        if resume_year >= target_end_year:
            self.logger.info(
                f"Simulation already completed through year {resume_year}. Target: {target_end_year}"
            )
            return None

        self.logger.info(f"Resuming simulation from year {resume_year}")

        # Validate resume point
        checkpoint = self.checkpoint_manager.load_checkpoint(resume_year)
        if not checkpoint:
            self.logger.error(f"Failed to load checkpoint for year {resume_year}")
            return None

        if not self._validate_resume_conditions(checkpoint, config_hash):
            self.logger.error(f"Resume validation failed for year {resume_year}")
            return None

        # Log resume context
        self.logger.info(
            "Resume validation successful",
            extra={
                "resume_year": resume_year,
                "target_end_year": target_end_year,
                "checkpoint_timestamp": checkpoint["metadata"]["timestamp"],
                "config_hash": config_hash,
            },
        )

        # Return the next year to start processing
        return resume_year + 1

    def _validate_resume_conditions(
        self, checkpoint: Dict[str, Any], current_config_hash: str
    ) -> bool:
        """Validate that resume conditions are met"""

        try:
            # Check configuration compatibility
            checkpoint_config_hash = checkpoint["metadata"].get("config_hash")
            if checkpoint_config_hash != current_config_hash:
                raise ConfigurationDriftError(
                    f"Configuration has changed since checkpoint. "
                    f"Checkpoint: {checkpoint_config_hash}, Current: {current_config_hash}"
                )

            # Check checkpoint version compatibility
            checkpoint_version = checkpoint["metadata"].get("checkpoint_version", "1.0")
            if not self._is_version_compatible(checkpoint_version):
                raise RecoveryValidationError(
                    f"Checkpoint version {checkpoint_version} is not compatible with current recovery system"
                )

            # Check database state consistency
            year = checkpoint["metadata"]["year"]
            if not self._validate_database_state(year, checkpoint):
                raise RecoveryValidationError("Database state validation failed")

            # Validate data quality metrics
            if not self._validate_data_quality(checkpoint):
                raise RecoveryValidationError("Data quality validation failed")

            return True

        except (ConfigurationDriftError, RecoveryValidationError) as e:
            self.logger.error(f"Resume validation failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during resume validation: {e}")
            return False

    def _is_version_compatible(self, checkpoint_version: str) -> bool:
        """Check if checkpoint version is compatible with current system"""
        compatible_versions = ["2.0", "1.0"]  # List of compatible versions
        return checkpoint_version in compatible_versions

    def _validate_database_state(self, year: int, checkpoint: Dict[str, Any]) -> bool:
        """Validate that current database state matches checkpoint"""
        expected_counts = checkpoint.get("database_state", {}).get("table_counts", {})

        if not expected_counts:
            self.logger.warning("Checkpoint missing database state information")
            return False

        # Use checkpoint manager's validation method
        return self.checkpoint_manager._validate_database_consistency(year, checkpoint)

    def _validate_data_quality(self, checkpoint: Dict[str, Any]) -> bool:
        """Validate data quality metrics from checkpoint"""
        validation_data = checkpoint.get("validation_data", {})

        if not validation_data:
            self.logger.warning("Checkpoint missing validation data")
            return True  # Don't fail on missing validation data for older checkpoints

        # Check for data quality errors in checkpoint
        if "error" in validation_data:
            self.logger.error(
                f"Data quality error in checkpoint: {validation_data['error']}"
            )
            return False

        # Validate key metrics are reasonable
        total_compensation = validation_data.get("total_compensation", 0)
        if total_compensation < 0:
            self.logger.error(
                f"Invalid total compensation in checkpoint: {total_compensation}"
            )
            return False

        baseline_count = validation_data.get("baseline_employee_count", 0)
        if baseline_count < 0:
            self.logger.error(
                f"Invalid baseline employee count in checkpoint: {baseline_count}"
            )
            return False

        return True

    def calculate_config_hash(
        self, config_path: str = "config/simulation_config.yaml"
    ) -> str:
        """Calculate hash of current configuration for drift detection"""
        config_file = Path(config_path)

        if not config_file.exists():
            self.logger.warning(f"Configuration file not found: {config_path}")
            return "no_config"

        try:
            # Read and hash the configuration file
            config_content = config_file.read_text()
            return hashlib.sha256(config_content.encode("utf-8")).hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculating config hash: {e}")
            return "error"

    def get_recovery_status(self, config_hash: str) -> Dict[str, Any]:
        """Get comprehensive recovery status and recommendations"""
        status = {
            "checkpoints_available": False,
            "latest_checkpoint_year": None,
            "resumable_year": None,
            "config_compatible": False,
            "recommendations": [],
        }

        # List available checkpoints
        checkpoints = self.checkpoint_manager.list_checkpoints()
        status["checkpoints_available"] = len(checkpoints) > 0
        status["total_checkpoints"] = len(checkpoints)

        if checkpoints:
            latest = max(checkpoints, key=lambda x: x["year"])
            status["latest_checkpoint_year"] = latest["year"]
            status["latest_checkpoint_timestamp"] = latest["timestamp"]
            status["latest_checkpoint_format"] = latest["format"]

        # Check for resumable checkpoint
        resumable_year = self.checkpoint_manager.find_latest_resumable_checkpoint(
            config_hash
        )
        if resumable_year:
            status["resumable_year"] = resumable_year
            status["config_compatible"] = True
            status["recommendations"].append(f"Can resume from year {resumable_year}")
        else:
            if checkpoints:
                status["recommendations"].append(
                    "No resumable checkpoints due to configuration changes"
                )
                status["recommendations"].append("Use --force-restart to start fresh")
            else:
                status["recommendations"].append(
                    "No checkpoints available - will start from beginning"
                )

        return status

    def prepare_recovery_plan(
        self, start_year: int, end_year: int, config_hash: str
    ) -> Dict[str, Any]:
        """Prepare a detailed recovery plan for the simulation"""
        plan = {
            "start_year": start_year,
            "end_year": end_year,
            "config_hash": config_hash,
            "recovery_mode": "full_run",
            "resume_from_year": None,
            "years_to_process": list(range(start_year, end_year + 1)),
            "estimated_savings": 0,
            "warnings": [],
        }

        # Check for recovery opportunities
        resumable_year = self.checkpoint_manager.find_latest_resumable_checkpoint(
            config_hash
        )

        if resumable_year and resumable_year >= start_year:
            if resumable_year < end_year:
                plan["recovery_mode"] = "checkpoint_resume"
                plan["resume_from_year"] = resumable_year
                plan["years_to_process"] = list(range(resumable_year + 1, end_year + 1))
                years_saved = resumable_year - start_year + 1
                plan["estimated_savings"] = years_saved
                plan["warnings"].append(
                    f"Resuming from year {resumable_year}, skipping {years_saved} completed years"
                )
            else:
                plan["recovery_mode"] = "already_complete"
                plan["years_to_process"] = []
                plan["warnings"].append(
                    f"Simulation already complete through year {resumable_year}"
                )

        # Add warnings for configuration issues
        if resumable_year and resumable_year < start_year:
            plan["warnings"].append(
                f"Checkpoint available for year {resumable_year} but before requested start year {start_year}"
            )

        return plan

    def validate_recovery_environment(self) -> Dict[str, Any]:
        """Validate that the environment is ready for recovery operations"""
        validation = {"valid": True, "issues": [], "warnings": []}

        # Check checkpoint directory
        if not self.checkpoint_manager.checkpoint_dir.exists():
            validation["issues"].append("Checkpoint directory does not exist")
            validation["valid"] = False
        elif not self.checkpoint_manager.checkpoint_dir.is_dir():
            validation["issues"].append("Checkpoint path is not a directory")
            validation["valid"] = False

        # Check database file
        db_path = Path(self.checkpoint_manager.db_path)
        if not db_path.exists():
            validation["issues"].append(f"Database file does not exist: {db_path}")
            validation["valid"] = False

        # Check for write permissions
        try:
            test_file = self.checkpoint_manager.checkpoint_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except Exception as e:
            validation["issues"].append(f"Cannot write to checkpoint directory: {e}")
            validation["valid"] = False

        # Check available checkpoints
        checkpoints = self.checkpoint_manager.list_checkpoints()
        if not checkpoints:
            validation["warnings"].append("No checkpoints available")
        else:
            # Check for integrity issues
            for checkpoint in checkpoints:
                if not checkpoint.get("integrity_valid", True):
                    validation["warnings"].append(
                        f"Checkpoint for year {checkpoint['year']} has no integrity validation"
                    )

        return validation
