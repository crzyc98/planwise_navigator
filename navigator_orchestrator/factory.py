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
from .pipeline import PipelineOrchestrator
from .registries import RegistryManager
from .reports import MultiYearReporter
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

        # Default rules if none provided
        dv = DataValidator(self._db)
        if not self._rules:
            self._rules = [HireTerminationRatioRule(), EventSequenceRule()]
        for r in self._rules:
            dv.register_rule(r)

        runner = DbtRunner(
            working_dir=Path("dbt"),
            threads=self._threads,
            executable=self._dbt_executable,
            database_path=str(self._db.db_path),
        )
        registries = RegistryManager(self._db)

        return PipelineOrchestrator(
            config=self._config,
            db_manager=self._db,
            dbt_runner=runner,
            registry_manager=registries,
            validator=dv,
        )


def create_orchestrator(
    config_path: Path | str,
    *,
    threads: int = 1,
    db_path: Optional[Path | str] = None,
    dbt_executable: str = "dbt",
) -> PipelineOrchestrator:
    return (
        OrchestratorBuilder()
        .with_config(config_path)
        .with_database(db_path)
        .with_dbt_threads(threads)
        .with_dbt_executable(dbt_executable)
        .build()
    )
