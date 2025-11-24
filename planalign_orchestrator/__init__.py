"""
PlanAlign Orchestrator core package.

Provides foundational configuration models and utilities used by the
orchestration layer. Designed to be minimal, testable, and reusable.
"""

from _version import __version__, get_full_version, get_version_dict

from .config import (CompensationSettings, EnrollmentSettings,
                     SimulationConfig, SimulationSettings,
                     load_simulation_config, to_dbt_vars)
from .factory import OrchestratorBuilder, create_orchestrator
from .logger import JSONFormatter, ProductionLogger, get_logger
from .migration import MigrationManager, MigrationResult
from .observability import (ObservabilityManager, create_observability_manager,
                            observability_session)
from .performance_monitor import PerformanceMetrics, PerformanceMonitor
from .registries import (DeferralEscalationRegistry, EnrollmentRegistry,
                         Registry, RegistryManager, RegistryValidationResult,
                         SQLTemplateManager)
from .reports import (DETAILED_AUDIT_TEMPLATE, EXECUTIVE_SUMMARY_TEMPLATE,
                      ConsoleReporter, EventSummary, MultiYearReporter,
                      MultiYearSummary, ReportTemplate, WorkforceBreakdown,
                      YearAuditor, YearAuditReport)
from .run_summary import RunIssue, RunMetadata, RunSummaryGenerator
from .utils import DatabaseConnectionManager, ExecutionMutex, time_block
from .validation import (DataValidator, EventSequenceRule, EventSpikeRule,
                         HireTerminationRatioRule, RowCountDriftRule,
                         ValidationResult, ValidationSeverity)

__all__ = [
    # Version
    "__version__",
    "get_full_version",
    "get_version_dict",
    # Config
    "SimulationConfig",
    "SimulationSettings",
    "CompensationSettings",
    "EnrollmentSettings",
    "load_simulation_config",
    "to_dbt_vars",
    # Utils
    "ExecutionMutex",
    "DatabaseConnectionManager",
    "time_block",
    # Registries
    "Registry",
    "RegistryManager",
    "EnrollmentRegistry",
    "DeferralEscalationRegistry",
    "RegistryValidationResult",
    "SQLTemplateManager",
    # Validation
    "DataValidator",
    "ValidationSeverity",
    "ValidationResult",
    "RowCountDriftRule",
    "HireTerminationRatioRule",
    "EventSequenceRule",
    "EventSpikeRule",
    # Reporting
    "YearAuditor",
    "MultiYearReporter",
    "ConsoleReporter",
    "WorkforceBreakdown",
    "EventSummary",
    "YearAuditReport",
    "MultiYearSummary",
    "ReportTemplate",
    "EXECUTIVE_SUMMARY_TEMPLATE",
    "DETAILED_AUDIT_TEMPLATE",
    # Factory
    "OrchestratorBuilder",
    "create_orchestrator",
    # Migration
    "MigrationManager",
    "MigrationResult",
    # Observability
    "ProductionLogger",
    "JSONFormatter",
    "get_logger",
    "PerformanceMonitor",
    "PerformanceMetrics",
    "RunSummaryGenerator",
    "RunIssue",
    "RunMetadata",
    "ObservabilityManager",
    "create_observability_manager",
    "observability_session",
]
