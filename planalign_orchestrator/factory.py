#!/usr/bin/env python3
"""
Orchestrator builder/factory utilities.

Creates a fully wired PipelineOrchestrator with sensible defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from .config import SimulationConfig, load_simulation_config, get_database_path
from .dbt_runner import DbtRunner
from .pipeline_orchestrator import PipelineOrchestrator
from .pipeline.hooks import Hook, HookType
from .registries import RegistryManager
from .reports import MultiYearReporter
from .self_healing import AutoInitializer
from .utils import DatabaseConnectionManager
from .validation import (DataValidator, EventSequenceRule,
                         HireTerminationRatioRule, ValidationRule)


class OrchestratorBuilder:
    def __init__(self):
        self._config: Optional[SimulationConfig] = None
        self._db: Optional[DatabaseConnectionManager] = None
        self._rules: list[ValidationRule] = []
        self._threads: int = 1
        self._dbt_executable: str = "dbt"

    def with_config(self, path: Path | str) -> "OrchestratorBuilder":
        self._config = load_simulation_config(Path(path))
        return self

    def with_database(
        self, db_path: Optional[Path | str] = None
    ) -> "OrchestratorBuilder":
        self._db = DatabaseConnectionManager(
            Path(db_path) if db_path else get_database_path()
        )
        return self

    def with_rules(self, rules: Iterable[ValidationRule]) -> "OrchestratorBuilder":
        self._rules.extend(list(rules))
        return self

    def with_dbt_threads(self, threads: int) -> "OrchestratorBuilder":
        self._threads = threads
        return self

    def with_dbt_executable(self, exe: str) -> "OrchestratorBuilder":
        self._dbt_executable = exe
        return self

    def build(self) -> PipelineOrchestrator:
        if not self._config:
            raise ValueError("Configuration must be provided before build")
        if not self._db:
            self._db = DatabaseConnectionManager()

        # Extract E068C threading configuration
        performance_config = getattr(self._config, 'performance', None)
        thread_count = 6  # Default
        event_shards = 1
        max_parallel_years = 1

        if performance_config:
            thread_count = getattr(performance_config, 'dbt_threads', 6)
            event_sharding_config = getattr(performance_config, 'event_sharding', None)
            if event_sharding_config and getattr(event_sharding_config, 'enabled', False):
                event_shards = getattr(event_sharding_config, 'shard_count', 1)
            max_parallel_years = getattr(performance_config, 'max_parallel_years', 1)

        # Legacy orchestrator threading settings (for backward compatibility)
        threading_enabled = True
        threading_mode = "selective"

        if hasattr(self._config, 'orchestrator') and self._config.orchestrator and hasattr(self._config.orchestrator, 'threading'):
            threading_enabled = self._config.orchestrator.threading.enabled
            threading_mode = self._config.orchestrator.threading.mode

        # Override with builder settings if explicitly provided
        if hasattr(self, '_threads') and self._threads != 1:
            thread_count = self._threads

        # Default rules if none provided
        dv = DataValidator(self._db)
        if not self._rules:
            self._rules = [HireTerminationRatioRule(), EventSequenceRule()]
        for r in self._rules:
            dv.register_rule(r)

        runner = DbtRunner(
            working_dir=Path("dbt"),  # Use relative dbt path
            threads=thread_count,
            executable=self._dbt_executable,
            database_path=str(self._db.db_path),
            threading_enabled=threading_enabled,
            threading_mode=threading_mode,
            verbose=True,  # Enable verbose mode for threading performance logging
        )
        registries = RegistryManager(self._db)

        # PipelineOrchestrator will extract E068C threading config directly from self._config
        return PipelineOrchestrator(
            config=self._config,
            db_manager=self._db,
            dbt_runner=runner,
            registry_manager=registries,
            validator=dv,
        )


def create_orchestrator(
    config_or_path: SimulationConfig | Path | str,
    db_manager: Optional[DatabaseConnectionManager] = None,
    *,
    threads: int = 1,
    db_path: Optional[Path | str] = None,
    dbt_executable: str = "dbt",
    auto_initialize: bool = True,
    verbose: bool = False,
) -> PipelineOrchestrator:
    """Create a PipelineOrchestrator with E068C threading support.

    Args:
        config_or_path: Either a SimulationConfig object or path to configuration file
        db_manager: Optional DatabaseConnectionManager (for scenario batch processing)
        threads: Legacy thread count (overridden by E068C config if present)
        db_path: Database path (optional, ignored if db_manager provided)
        dbt_executable: dbt executable path
        auto_initialize: Enable self-healing database initialization (default: True)
        verbose: Enable verbose output for initialization

    Returns:
        Configured PipelineOrchestrator with E068C threading settings
    """
    builder = OrchestratorBuilder()

    # Handle config input
    if isinstance(config_or_path, SimulationConfig):
        builder._config = config_or_path
    else:
        builder.with_config(config_or_path)

    # Handle database manager
    if db_manager:
        builder._db = db_manager
    else:
        builder.with_database(db_path)

    orchestrator = (
        builder
        .with_dbt_threads(threads)  # Will be overridden by E068C config if present
        .with_dbt_executable(dbt_executable)
        .build()
    )

    # Register self-healing initialization hook if enabled
    if auto_initialize:
        auto_initializer = AutoInitializer(
            db_manager=orchestrator.db_manager,
            dbt_runner=orchestrator.dbt_runner,
            verbose=verbose,
        )

        def init_hook(context: dict) -> None:
            """Pre-simulation hook that ensures database is initialized."""
            result = auto_initializer.ensure_initialized()
            if not result.success:
                from planalign_orchestrator.exceptions import InitializationError
                raise InitializationError(
                    f"Database initialization failed: {result.error}",
                    step="pre_simulation",
                    missing_tables=result.missing_tables_found,
                )

        hook = Hook(
            hook_type=HookType.PRE_SIMULATION,
            callback=init_hook,
            name="self_healing_initializer",
        )
        orchestrator.hook_manager.register_hook(hook)

    return orchestrator
