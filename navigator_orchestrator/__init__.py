"""
Navigator Orchestrator core package.

Provides foundational configuration models and utilities used by the
orchestration layer. Designed to be minimal, testable, and reusable.
"""

from .config import (
    SimulationConfig,
    SimulationSettings,
    CompensationSettings,
    EnrollmentSettings,
    load_simulation_config,
    to_dbt_vars,
)
from .utils import (
    ExecutionMutex,
    DatabaseConnectionManager,
    time_block,
)
from .registries import (
    Registry,
    RegistryManager,
    EnrollmentRegistry,
    DeferralEscalationRegistry,
    RegistryValidationResult,
    SQLTemplateManager,
)
from .validation import (
    DataValidator,
    ValidationSeverity,
    ValidationResult,
    RowCountDriftRule,
    HireTerminationRatioRule,
    EventSequenceRule,
    EventSpikeRule,
)
from .reports import (
    YearAuditor,
    MultiYearReporter,
    ConsoleReporter,
    WorkforceBreakdown,
    EventSummary,
    YearAuditReport,
    MultiYearSummary,
    ReportTemplate,
    EXECUTIVE_SUMMARY_TEMPLATE,
    DETAILED_AUDIT_TEMPLATE,
)
from .factory import (
    OrchestratorBuilder,
    create_orchestrator,
)
from .migration import (
    MigrationManager,
    MigrationResult,
)

__all__ = [
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
]
