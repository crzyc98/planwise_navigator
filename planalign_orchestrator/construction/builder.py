"""Canonical simulation-orchestrator builder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from planalign_orchestrator.config import OptimizationSettings
from planalign_orchestrator.dbt_runner import DbtRunner
from planalign_orchestrator.exceptions import (
    ExecutionContext,
    InitializationError,
    ResolutionHint,
)
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator
from planalign_orchestrator.registries import RegistryManager
from planalign_orchestrator.self_healing import AutoInitializer
from planalign_orchestrator.utils import DatabaseConnectionManager
from planalign_orchestrator.validation import (
    DataValidator,
    EventSequenceRule,
    HireTerminationRatioRule,
)

from .signature import ConstructionSignature, WorkSchedule
from .spec import ConstructionSpec, ExecutionEngineOption, InitializationPolicy


@dataclass(frozen=True)
class ConstructionResult:
    """Constructed orchestrator and its observable signature."""

    orchestrator: PipelineOrchestrator
    signature: ConstructionSignature
    work_schedule: WorkSchedule


def execute_initialization(
    policy: InitializationPolicy,
    initializer: Any,
) -> None:
    """Execute explicit self-healing outside error-isolating hooks."""
    if policy is InitializationPolicy.NONE:
        return
    result = initializer.ensure_initialized()
    if result.success:
        return
    raise InitializationError(
        f"Database initialization failed: {result.error}",
        step="pre_simulation",
        missing_tables=result.missing_tables_found,
        context=ExecutionContext(
            workflow_stage="pre_simulation",
            metadata={
                "failed_step": "pre_simulation",
                "missing_tables": result.missing_tables_found,
            },
        ),
        resolution_hints=[
            ResolutionHint(
                title="Repair fresh-database initialization",
                description="The explicit initialization sequence did not complete.",
                steps=[
                    "Review the failing initialization step in the diagnostic context",
                    "Run planalign health to check database locks and dbt availability",
                    "Retry after resolving the reported initialization failure",
                ],
                documentation_url="docs/guides/error_troubleshooting.md",
            )
        ],
    )


def _resolve_database(spec: ConstructionSpec) -> DatabaseConnectionManager:
    if spec.db_manager_override is not None:
        return spec.db_manager_override
    if isinstance(spec.database, DatabaseConnectionManager):
        return spec.database
    return DatabaseConnectionManager(spec.database)


def _validate_shared_database_guard(
    spec: ConstructionSpec,
    db_manager: DatabaseConnectionManager,
) -> None:
    if not spec.validation_mode:
        return
    if Path(db_manager.db_path).resolve() == Path("dbt/simulation.duckdb").resolve():
        raise ValueError(
            "Feature validation must use an isolated database; "
            "dbt/simulation.duckdb is the shared development database"
        )


def _build_runner(
    spec: ConstructionSpec,
    db_manager: DatabaseConnectionManager,
) -> Any:
    if spec.runner_override is not None:
        return spec.runner_override
    threading_enabled = True
    threading_mode = "selective"
    if spec.config.orchestrator and spec.config.orchestrator.threading:
        threading_enabled = spec.config.orchestrator.threading.enabled
        threading_mode = spec.config.orchestrator.threading.mode
    return DbtRunner(
        threads=spec.threads,
        executable="echo" if spec.dry_run else spec.dbt_executable,
        verbose=spec.verbose,
        threading_enabled=threading_enabled,
        threading_mode=threading_mode,
        db_manager=db_manager,
        database_path=str(db_manager.db_path),
        project_dir=spec.dbt_project_dir,
    )


def _hook_names(orchestrator: PipelineOrchestrator) -> tuple[str, ...]:
    hooks = orchestrator.hook_manager.list_hooks()
    return tuple(sorted(name for names in hooks.values() for name in names))


def build_orchestrator(spec: ConstructionSpec) -> ConstructionResult:
    """Build production-equivalent orchestration through one canonical seam."""
    if spec.config.optimization is None:
        spec.config.optimization = OptimizationSettings()
    resolved_engine = ExecutionEngineOption(
        engine=spec.config.optimization.execution_engine
    )
    spec.config.optimization.event_generation.mode = "sql"
    spec.config.validate_threading_configuration()
    spec.config.validate_eligibility_configuration()

    db_manager = _resolve_database(spec)
    _validate_shared_database_guard(spec, db_manager)
    runner = _build_runner(spec, db_manager)
    work_schedule = WorkSchedule()
    if hasattr(runner, "configure_work_schedule"):
        runner.configure_work_schedule(work_schedule, runner_kind="dbt")

    validator = DataValidator(db_manager)
    rules = spec.validation_rules or (
        HireTerminationRatioRule(),
        EventSequenceRule(),
    )
    for rule in rules:
        validator.register_rule(rule)

    initializer = None
    if spec.initialization is InitializationPolicy.SELF_HEALING:
        initializer = AutoInitializer(
            db_manager=db_manager,
            dbt_runner=runner,
            verbose=spec.verbose,
            start_year=spec.config.simulation.start_year,
        )

    orchestrator = PipelineOrchestrator(
        config=spec.config,
        db_manager=db_manager,
        dbt_runner=runner,
        registry_manager=RegistryManager(db_manager),
        validator=validator,
        reports_dir=spec.reports_dir,
        verbose=spec.verbose,
        initialization_callback=None,
    )
    if initializer is not None:

        def initialize_required_sources() -> None:
            orchestrator.enrollment_projection.ensure_table()
            execute_initialization(spec.initialization, initializer)

        orchestrator._initialization_callback = initialize_required_sources
    signature = ConstructionSignature(
        entry_point=spec.entry_point,
        runner_kind="dbt",
        database_path=str(db_manager.db_path),
        dbt_project_dir=(
            str(spec.dbt_project_dir) if spec.dbt_project_dir is not None else None
        ),
        thread_count=spec.threads,
        initialization_policy=spec.initialization.value,
        installed_hook_names=_hook_names(orchestrator),
        execution_engine=resolved_engine.engine,
    )
    orchestrator.construction_signature = signature
    orchestrator.work_schedule = work_schedule
    return ConstructionResult(
        orchestrator=orchestrator,
        signature=signature,
        work_schedule=work_schedule,
    )
