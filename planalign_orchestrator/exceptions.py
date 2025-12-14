"""
Structured exception hierarchy with execution context for PlanWise Navigator.

All exceptions include:
- correlation_id: Trace errors across multi-year simulations
- execution_context: Year, stage, model, configuration
- resolution_hints: Actionable suggestions for common issues
- severity: ERROR, WARNING, RECOVERABLE
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class ErrorSeverity(str, Enum):
    """Error severity levels for triage and alerting"""
    CRITICAL = "critical"      # Data corruption, system-wide failure
    ERROR = "error"            # Stage/year failure, requires intervention
    RECOVERABLE = "recoverable"  # Transient failure, retry possible
    WARNING = "warning"        # Non-blocking issue, may degrade quality


class ErrorCategory(str, Enum):
    """Error categories for diagnostics and resolution routing"""
    DATABASE = "database"              # DuckDB locks, query failures
    CONFIGURATION = "configuration"    # Invalid config, missing parameters
    DATA_QUALITY = "data_quality"      # Test failures, validation errors
    RESOURCE = "resource"              # Memory, CPU, disk exhaustion
    NETWORK = "network"                # Proxy, SSL, timeout issues
    DEPENDENCY = "dependency"          # Missing models, circular dependencies
    STATE = "state"                    # Checkpoint corruption, state inconsistency


@dataclass
class ExecutionContext:
    """Comprehensive execution context for error diagnosis"""

    # Primary context
    simulation_year: Optional[int] = None
    workflow_stage: Optional[str] = None
    model_name: Optional[str] = None

    # Configuration context
    scenario_id: Optional[str] = None
    plan_design_id: Optional[str] = None
    random_seed: Optional[int] = None

    # Orchestration context
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    execution_id: Optional[str] = None
    checkpoint_id: Optional[str] = None

    # Timing context
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    elapsed_seconds: Optional[float] = None

    # Resource context
    thread_count: Optional[int] = None
    memory_mb: Optional[float] = None

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize context for logging and storage"""
        return {
            k: v for k, v in self.__dict__.items()
            if v is not None and not k.startswith('_')
        }

    def format_summary(self) -> str:
        """Human-readable one-line summary"""
        parts = []
        if self.simulation_year:
            parts.append(f"year={self.simulation_year}")
        if self.workflow_stage:
            parts.append(f"stage={self.workflow_stage}")
        if self.model_name:
            parts.append(f"model={self.model_name}")
        if self.correlation_id:
            parts.append(f"correlation_id={self.correlation_id}")
        return " | ".join(parts)


@dataclass
class ResolutionHint:
    """Actionable resolution guidance for common error patterns"""

    title: str
    description: str
    steps: List[str]
    documentation_url: Optional[str] = None
    automation_available: bool = False
    estimated_resolution_time: Optional[str] = None


class NavigatorError(Exception):
    """
    Base exception for PlanWise Navigator with structured context.

    All Navigator exceptions should inherit from this class to ensure
    consistent error handling and diagnostic information.
    """

    def __init__(
        self,
        message: str,
        *,
        context: Optional[ExecutionContext] = None,
        category: ErrorCategory = ErrorCategory.DATABASE,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        resolution_hints: Optional[List[ResolutionHint]] = None,
        original_exception: Optional[Exception] = None,
        **kwargs
    ):
        super().__init__(message)
        self.message = message
        self.context = context or ExecutionContext()
        self.category = category
        self.severity = severity
        self.resolution_hints = resolution_hints or []
        self.original_exception = original_exception
        self.additional_data = kwargs

    def format_diagnostic_message(self) -> str:
        """
        Format comprehensive diagnostic message for logs and user display.

        Returns multi-line formatted error with:
        - Error message and severity
        - Execution context
        - Resolution hints
        - Original exception traceback (if available)
        """
        lines = [
            f"{'='*80}",
            f"ERROR: {self.message}",
            f"Severity: {self.severity.value.upper()} | Category: {self.category.value}",
            f"{'='*80}",
            "",
            "EXECUTION CONTEXT:",
        ]

        # Format execution context
        if self.context:
            context_dict = self.context.to_dict()
            for key, value in context_dict.items():
                if key == 'metadata' and isinstance(value, dict):
                    for meta_key, meta_value in value.items():
                        lines.append(f"  {meta_key}: {meta_value}")
                else:
                    lines.append(f"  {key}: {value}")
        else:
            lines.append("  (no context available)")

        # Add resolution hints
        if self.resolution_hints:
            lines.append("")
            lines.append("RESOLUTION HINTS:")
            for i, hint in enumerate(self.resolution_hints, 1):
                lines.append(f"\n{i}. {hint.title}")
                lines.append(f"   {hint.description}")
                if hint.steps:
                    lines.append("   Steps:")
                    for step in hint.steps:
                        lines.append(f"     - {step}")
                if hint.documentation_url:
                    lines.append(f"   Docs: {hint.documentation_url}")
                if hint.estimated_resolution_time:
                    lines.append(f"   Est. Time: {hint.estimated_resolution_time}")

        # Add original exception if available
        if self.original_exception:
            lines.append("")
            lines.append("ORIGINAL EXCEPTION:")
            lines.append(f"  {type(self.original_exception).__name__}: {str(self.original_exception)}")

        lines.append("")
        lines.append(f"{'='*80}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize exception for structured logging and storage"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context.to_dict() if self.context else {},
            "resolution_hints": [
                {
                    "title": hint.title,
                    "description": hint.description,
                    "steps": hint.steps,
                    "documentation_url": hint.documentation_url,
                    "estimated_time": hint.estimated_resolution_time
                }
                for hint in self.resolution_hints
            ],
            "original_exception": str(self.original_exception) if self.original_exception else None,
            **self.additional_data
        }


# Database Errors
class DatabaseError(NavigatorError):
    """Database-related errors (locks, queries, connections)"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.DATABASE, **kwargs)


class DatabaseLockError(DatabaseError):
    """Database lock conflict (common with IDE connections)"""
    def __init__(self, message: str = "Database lock conflict detected", **kwargs):
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Close IDE Database Connections",
                    description="DuckDB does not support concurrent write connections",
                    steps=[
                        "Close database explorer in VS Code/Windsurf/DataGrip",
                        "Check for other Python processes: ps aux | grep duckdb",
                        "Kill stale connections: pkill -f 'duckdb.*simulation.duckdb'",
                        "Retry simulation"
                    ],
                    documentation_url="docs/guides/troubleshooting.md#database-locks",
                    estimated_resolution_time="1-2 minutes"
                )
            ]
        super().__init__(message, severity=ErrorSeverity.RECOVERABLE, **kwargs)


class QueryExecutionError(DatabaseError):
    """SQL query execution failure"""
    def __init__(self, message: str, query: Optional[str] = None, **kwargs):
        if query:
            kwargs["metadata"] = kwargs.get("metadata", {})
            kwargs["metadata"]["failed_query"] = query[:500]  # Truncate long queries
        super().__init__(message, **kwargs)


# Configuration Errors
class ConfigurationError(NavigatorError):
    """Configuration-related errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.CONFIGURATION, **kwargs)


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration parameter or structure"""
    def __init__(
        self,
        message: str,
        config_path: Optional[str] = None,
        invalid_value: Optional[Any] = None,
        **kwargs
    ):
        if config_path:
            message = f"{message} (config_path: {config_path})"
        if invalid_value is not None:
            message = f"{message} (value: {invalid_value})"
        super().__init__(message, severity=ErrorSeverity.ERROR, **kwargs)


class MissingConfigurationError(ConfigurationError):
    """Required configuration parameter not found"""
    def __init__(self, parameter_name: str, **kwargs):
        message = f"Required configuration parameter missing: {parameter_name}"
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Add Missing Configuration",
                    description=f"The parameter '{parameter_name}' must be defined",
                    steps=[
                        f"Open config/simulation_config.yaml",
                        f"Add {parameter_name} with appropriate value",
                        "Validate config: planwise validate",
                        "Retry simulation"
                    ],
                    documentation_url="docs/configuration.md",
                    estimated_resolution_time="5 minutes"
                )
            ]
        super().__init__(message, severity=ErrorSeverity.ERROR, **kwargs)


# Data Quality Errors
class DataQualityError(NavigatorError):
    """Data quality and validation errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.DATA_QUALITY, **kwargs)


class ValidationFailureError(DataQualityError):
    """Data validation test failure"""
    def __init__(
        self,
        message: str,
        failed_test: Optional[str] = None,
        affected_records: Optional[int] = None,
        **kwargs
    ):
        if failed_test:
            message = f"{message} (test: {failed_test})"
        if affected_records:
            message = f"{message} (affected: {affected_records} records)"
        super().__init__(message, severity=ErrorSeverity.WARNING, **kwargs)


# dbt Errors (Enhanced from existing DbtError classes)
class DbtError(NavigatorError):
    """Base class for dbt-related errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.DATABASE, **kwargs)


class DbtCompilationError(DbtError):
    """dbt model compilation failure"""
    def __init__(self, message: str, **kwargs):
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Check Model SQL Syntax",
                    description="dbt compilation failed due to SQL syntax or Jinja errors",
                    steps=[
                        "Review error message for specific syntax issue",
                        "Check model file for missing CTEs or incorrect Jinja",
                        "Test compilation: dbt compile --select <model>",
                        "Verify dbt_vars are correct: dbt compile --vars '{...}'"
                    ],
                    documentation_url="docs/dbt/troubleshooting.md#compilation-errors",
                    estimated_resolution_time="10-15 minutes"
                )
            ]
        super().__init__(message, severity=ErrorSeverity.ERROR, **kwargs)


class DbtExecutionError(DbtError):
    """dbt model execution failure"""
    def __init__(self, message: str, **kwargs):
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Review Database Error",
                    description="dbt model execution failed during database query",
                    steps=[
                        "Check if database is locked (close IDE connections)",
                        "Verify upstream models completed successfully",
                        "Check for memory pressure: df -h and free -m",
                        "Review query plan: EXPLAIN <query>"
                    ],
                    documentation_url="docs/dbt/troubleshooting.md#execution-errors",
                    estimated_resolution_time="5-10 minutes"
                )
            ]
        super().__init__(message, severity=ErrorSeverity.RECOVERABLE, **kwargs)


class DbtDataQualityError(DbtError):
    """dbt data quality test failure"""
    def __init__(self, message: str, failed_tests: Optional[List[str]] = None, **kwargs):
        if failed_tests:
            kwargs["metadata"] = kwargs.get("metadata", {})
            kwargs["metadata"]["failed_tests"] = failed_tests
        super().__init__(message, category=ErrorCategory.DATA_QUALITY, severity=ErrorSeverity.WARNING, **kwargs)


# Pipeline Errors (Enhanced from existing PipelineStageError)
class PipelineError(NavigatorError):
    """Pipeline orchestration errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.DEPENDENCY, **kwargs)


class PipelineStageError(PipelineError):
    """Workflow stage execution failure"""
    def __init__(
        self,
        message: str,
        stage_name: Optional[str] = None,
        failed_models: Optional[List[str]] = None,
        **kwargs
    ):
        if stage_name:
            message = f"{message} (stage: {stage_name})"
        if failed_models:
            kwargs["metadata"] = kwargs.get("metadata", {})
            kwargs["metadata"]["failed_models"] = failed_models
        super().__init__(message, severity=ErrorSeverity.ERROR, **kwargs)


# Resource Errors
class ResourceError(NavigatorError):
    """Resource exhaustion errors (memory, CPU, disk)"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.RESOURCE, **kwargs)


class MemoryExhaustedError(ResourceError):
    """Out of memory condition"""
    def __init__(self, message: str, memory_used_mb: Optional[float] = None, **kwargs):
        if memory_used_mb:
            message = f"{message} (memory_used: {memory_used_mb:.1f}MB)"
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Reduce Memory Pressure",
                    description="Simulation exceeded available memory",
                    steps=[
                        "Reduce dbt threads: set orchestrator.threading.dbt_threads: 1",
                        "Enable adaptive memory: optimization.adaptive_memory.enabled: true",
                        "Reduce batch size: optimization.batch_size: 250",
                        "Close other memory-intensive applications",
                        "Consider using subset mode: --vars '{dev_employee_limit: 1000}'"
                    ],
                    documentation_url="docs/troubleshooting.md#memory-issues",
                    estimated_resolution_time="10 minutes"
                )
            ]
        super().__init__(message, severity=ErrorSeverity.CRITICAL, **kwargs)


# Network Errors
class NetworkError(NavigatorError):
    """Network-related errors (proxy, SSL, timeouts)"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.NETWORK, **kwargs)


class ProxyConfigurationError(NetworkError):
    """Corporate proxy configuration error"""
    def __init__(self, message: str, **kwargs):
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Configure Corporate Proxy",
                    description="Network requests failing due to proxy configuration",
                    steps=[
                        "Check proxy settings in config/network_config.yaml",
                        "Verify HTTP_PROXY and HTTPS_PROXY environment variables",
                        "Test connection: curl -x $HTTP_PROXY https://example.com",
                        "Add CA bundle if needed: REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt"
                    ],
                    documentation_url="docs/deployment/corporate-network.md",
                    estimated_resolution_time="15 minutes"
                )
            ]
        super().__init__(message, severity=ErrorSeverity.RECOVERABLE, **kwargs)


# State Errors
class StateError(NavigatorError):
    """State management and checkpoint errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.STATE, **kwargs)


class CheckpointCorruptionError(StateError):
    """Checkpoint file corruption or version mismatch"""
    def __init__(self, message: str, checkpoint_path: Optional[str] = None, **kwargs):
        if checkpoint_path:
            kwargs["metadata"] = kwargs.get("metadata", {})
            kwargs["metadata"]["checkpoint_path"] = checkpoint_path
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Reset Checkpoint State",
                    description="Checkpoint file is corrupted or incompatible",
                    steps=[
                        "List checkpoints: planwise checkpoints list",
                        "Clean corrupted checkpoints: planwise checkpoints cleanup",
                        "Restart simulation from scratch (no --resume flag)",
                        "If persistent, delete .planalign_checkpoints/ directory"
                    ],
                    documentation_url="docs/recovery.md#checkpoint-corruption",
                    estimated_resolution_time="5 minutes"
                )
            ]
        super().__init__(message, severity=ErrorSeverity.ERROR, **kwargs)


class StateInconsistencyError(StateError):
    """Inconsistent state between database and checkpoints"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, severity=ErrorSeverity.CRITICAL, **kwargs)


# Initialization Errors (E006 - Self-Healing dbt Initialization)
class InitializationError(NavigatorError):
    """Base exception for database initialization failures.

    Raised when automatic database initialization fails during first-time
    simulation in a new workspace.
    """
    def __init__(
        self,
        message: str,
        *,
        step: str | None = None,
        missing_tables: list[str] | None = None,
        **kwargs
    ):
        if step:
            kwargs["metadata"] = kwargs.get("metadata", {})
            kwargs["metadata"]["failed_step"] = step
        if missing_tables:
            kwargs["metadata"] = kwargs.get("metadata", {})
            kwargs["metadata"]["missing_tables"] = missing_tables
        super().__init__(message, category=ErrorCategory.STATE, **kwargs)


class InitializationTimeoutError(InitializationError):
    """Raised when initialization exceeds the configured timeout.

    Per SC-003, initialization must complete within 60 seconds for standard
    workspace configurations.
    """
    def __init__(
        self,
        timeout_seconds: float,
        elapsed_seconds: float,
        **kwargs
    ):
        message = (
            f"Initialization exceeded {timeout_seconds}s timeout "
            f"(elapsed: {elapsed_seconds:.1f}s)"
        )
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Initialization Timeout",
                    description="Database initialization took longer than expected",
                    steps=[
                        "Check disk I/O performance",
                        "Verify dbt-duckdb is working: dbt debug",
                        "Run manual initialization: dbt seed && dbt run --select tag:foundation",
                        "Check for large seed files that may slow loading"
                    ],
                    documentation_url="docs/troubleshooting.md#initialization-timeout",
                    estimated_resolution_time="5-10 minutes"
                )
            ]
        kwargs["metadata"] = kwargs.get("metadata", {})
        kwargs["metadata"]["timeout_seconds"] = timeout_seconds
        kwargs["metadata"]["elapsed_seconds"] = elapsed_seconds
        super().__init__(message, severity=ErrorSeverity.RECOVERABLE, **kwargs)


class ConcurrentInitializationError(InitializationError):
    """Raised when another initialization is already in progress.

    Uses file-based mutex to prevent concurrent database modifications.
    """
    def __init__(self, lock_file: str, **kwargs):
        message = f"Another initialization is already in progress (lock: {lock_file})"
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Concurrent Initialization",
                    description="Another process is initializing the database",
                    steps=[
                        "Wait for the other initialization to complete",
                        "Check if another simulation is running: ps aux | grep planalign",
                        "If no other process, remove stale lock: rm <lock_file>",
                        "Retry the simulation"
                    ],
                    documentation_url="docs/troubleshooting.md#concurrent-initialization",
                    estimated_resolution_time="1-2 minutes"
                )
            ]
        kwargs["metadata"] = kwargs.get("metadata", {})
        kwargs["metadata"]["lock_file"] = lock_file
        super().__init__(message, severity=ErrorSeverity.RECOVERABLE, **kwargs)


class DatabaseCorruptionError(InitializationError):
    """Raised when the database file is corrupted.

    Detected when DuckDB cannot open or query the database file.
    """
    def __init__(
        self,
        db_path: str,
        *,
        original_exception: Exception | None = None,
        **kwargs
    ):
        message = f"Database file is corrupted: {db_path}"
        if "resolution_hints" not in kwargs:
            kwargs["resolution_hints"] = [
                ResolutionHint(
                    title="Database Corruption",
                    description="The database file is corrupted and cannot be read",
                    steps=[
                        "Back up the corrupted database file if needed",
                        "Delete or rename the corrupted database",
                        "Retry simulation - a new database will be created",
                        "If issue persists, check disk health"
                    ],
                    documentation_url="docs/troubleshooting.md#database-corruption",
                    estimated_resolution_time="2-5 minutes"
                )
            ]
        kwargs["metadata"] = kwargs.get("metadata", {})
        kwargs["metadata"]["db_path"] = db_path
        if original_exception:
            kwargs["original_exception"] = original_exception
        super().__init__(message, severity=ErrorSeverity.ERROR, **kwargs)
