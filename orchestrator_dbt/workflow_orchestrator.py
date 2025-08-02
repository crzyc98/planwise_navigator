"""
Main workflow orchestrator for orchestrator_dbt package.

This is the primary entry point for the orchestration system, providing
a simplified interface to the core workflow orchestration functionality.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .core.workflow_orchestrator import WorkflowOrchestrator as CoreWorkflowOrchestrator, WorkflowResult


class WorkflowOrchestrator:
    """
    Main workflow orchestrator interface.

    Provides a simplified interface to the core orchestration functionality
    for external consumers.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize workflow orchestrator.

        Args:
            config_path: Optional path to configuration file
        """
        self._core_orchestrator = CoreWorkflowOrchestrator(config_path)

    def run_complete_setup(self) -> WorkflowResult:
        """
        Run the complete setup workflow.

        This includes:
        1. Clear database tables
        2. Load CSV seed data
        3. Run foundation staging models
        4. Run configuration staging models
        5. Validate setup results

        Returns:
            WorkflowResult with complete workflow results
        """
        return self._core_orchestrator.run_complete_setup_workflow()

    def run_quick_setup(self) -> WorkflowResult:
        """
        Run a quick setup workflow (foundation only).

        This includes:
        1. Clear database tables
        2. Load CSV seed data
        3. Run foundation staging models

        Returns:
            WorkflowResult with quick setup results
        """
        return self._core_orchestrator.run_quick_setup()

    def run_complete_setup_optimized(self) -> WorkflowResult:
        """
        Run the complete setup workflow using optimized batch operations.

        This method uses batch operations to reduce dbt startup overhead
        and should be significantly faster than the standard workflow.

        Returns:
            WorkflowResult with complete workflow results
        """
        return self._core_orchestrator.run_complete_setup_workflow_optimized()

    def run_quick_setup_optimized(self) -> WorkflowResult:
        """
        Run a quick setup workflow using optimized batch operations (foundation models only).

        This includes:
        1. Clear database tables
        2. Load CSV seed data (batch optimized)
        3. Run foundation staging models (batch optimized)

        Returns:
            WorkflowResult with quick setup results
        """
        return self._core_orchestrator.run_quick_setup_optimized()

    def get_system_status(self):
        """
        Get current system status and readiness.

        Returns:
            Dictionary with system status information
        """
        return self._core_orchestrator.get_system_status()

    @property
    def config(self):
        """Get orchestration configuration."""
        return self._core_orchestrator.config

    @property
    def database_manager(self):
        """Get database manager."""
        return self._core_orchestrator.db_manager

    @property
    def dbt_executor(self):
        """Get dbt executor."""
        return self._core_orchestrator.dbt_executor

    @property
    def validation_framework(self):
        """Get validation framework."""
        return self._core_orchestrator.validation_framework

    @property
    def seed_loader(self):
        """Get seed loader."""
        return self._core_orchestrator.seed_loader

    @property
    def staging_loader(self):
        """Get staging loader."""
        return self._core_orchestrator.staging_loader
