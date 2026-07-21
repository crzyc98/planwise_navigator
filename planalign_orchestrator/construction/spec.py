"""Typed inputs for canonical orchestrator construction."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.utils import DatabaseConnectionManager


class InitializationPolicy(str, Enum):
    """Explicit fresh-database initialization behavior."""

    NONE = "none"
    SELF_HEALING = "self_healing"


class ExecutionEngineOption(BaseModel):
    """Validated execution-engine selection."""

    engine: Literal["dbt"] = "dbt"

    @field_validator("engine", mode="before")
    @classmethod
    def reject_unsupported_engine(cls, value: Any) -> Any:
        if value != "dbt":
            raise ValueError(
                "optimization.execution_engine supports only 'dbt'; "
                f"received {value!r}"
            )
        return value


EntryPoint = Literal[
    "cli.simulate",
    "batch",
    "studio",
    "parity",
    "invariant_test",
    "perf_harness",
]


class ConstructionSpec(BaseModel):
    """Validated input to the one canonical construction seam."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    config: SimulationConfig
    database: Path | DatabaseConnectionManager
    threads: int = Field(default=1, ge=1, le=16)
    dbt_project_dir: Path | None = None
    reports_dir: Path = Path("var/reports")
    initialization: InitializationPolicy = InitializationPolicy.NONE
    execution_engine: ExecutionEngineOption = Field(
        default_factory=ExecutionEngineOption
    )
    entry_point: EntryPoint = "cli.simulate"
    validation_mode: bool = False
    verbose: bool = False
    dry_run: bool = False
    dbt_executable: str = "dbt"
    runner_override: Any | None = None
    db_manager_override: DatabaseConnectionManager | None = None
    validation_rules: tuple[Any, ...] = ()
