"""
PlanAlign Orchestrator core package.

Provides foundational configuration models and utilities used by the
orchestration layer. Designed to be minimal, testable, and reusable.
"""

# Configure sqlparse limits for large SQL models
# sqlparse 0.5.5+ has DoS protection that limits token processing to 10,000
# Our dbt models can exceed this limit, so we increase it to 50,000
# See: https://discourse.getdbt.com/t/dbt-run-error-maximum-number-of-tokens-exceeded/20495
try:
    import sqlparse.engine.grouping
    sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
except (ImportError, AttributeError):
    pass  # Older sqlparse versions don't have this setting

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
