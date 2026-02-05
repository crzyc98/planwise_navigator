"""
Pipeline orchestration components for PlanWise Navigator.

This package contains modular components for workflow definition,
stage execution, and pipeline orchestration.

NOTE: The main PipelineOrchestrator class is in pipeline_orchestrator.py at the parent level.
This package contains the modular workflow definition components that will eventually
replace the monolithic pipeline_orchestrator.py file.
"""

from .workflow import (
    WorkflowStage,
    StageDefinition,
    WorkflowCheckpoint,
    WorkflowBuilder,
)
from .state_manager import StateManager
from .year_executor import YearExecutor, PipelineStageError
from .event_generation_executor import EventGenerationExecutor
from .hooks import HookManager, Hook, HookType
from .data_cleanup import DataCleanupManager
from .stage_validator import StageValidator

__all__ = [
    # Workflow components
    "WorkflowStage",
    "StageDefinition",
    "WorkflowCheckpoint",
    "WorkflowBuilder",

    # Execution components
    "YearExecutor",
    "EventGenerationExecutor",
    "PipelineStageError",

    # Validation
    "StageValidator",

    # State management
    "StateManager",

    # Hooks system
    "HookManager",
    "Hook",
    "HookType",

    # Utilities
    "DataCleanupManager",
]
