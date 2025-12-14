"""
Self-Healing Database Initialization Module

Provides automatic detection of missing database tables and triggers dbt
initialization to create them before simulation runs. This eliminates
"table does not exist" errors for first-time simulations in new workspaces.

Main Components:
- TableExistenceChecker: Detects missing required tables
- AutoInitializer: Orchestrates automatic database initialization
- InitializationState: Tracks initialization lifecycle state
- InitializationResult: Complete result of initialization attempt

Usage:
    from planalign_orchestrator.self_healing import (
        AutoInitializer,
        TableExistenceChecker,
        InitializationState,
        InitializationResult,
    )

    # Check if initialization is needed
    checker = TableExistenceChecker(db_manager)
    if not checker.is_initialized():
        initializer = AutoInitializer(db_manager, dbt_runner)
        result = initializer.ensure_initialized()
"""

from planalign_orchestrator.self_healing.initialization_state import (
    InitializationState,
    InitializationStep,
    InitializationResult,
    TableTier,
    RequiredTable,
    REQUIRED_TABLES,
    create_standard_steps,
)
from planalign_orchestrator.self_healing.table_checker import TableExistenceChecker
from planalign_orchestrator.self_healing.auto_initializer import AutoInitializer

__all__ = [
    # State and models
    "InitializationState",
    "InitializationStep",
    "InitializationResult",
    "TableTier",
    "RequiredTable",
    "REQUIRED_TABLES",
    "create_standard_steps",
    # Classes
    "TableExistenceChecker",
    "AutoInitializer",
]
