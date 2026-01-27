"""
Reports package for PlanAlign Engine audit and reporting.

Generates single-year and multi-year reports, supports basic export formats,
and integrates data quality validation results.
"""

from .data_models import (
    WorkforceBreakdown,
    EventSummary,
    YearAuditReport,
    MultiYearSummary,
)
from .formatters import (
    ConsoleReporter,
    ReportTemplate,
    EXECUTIVE_SUMMARY_TEMPLATE,
    DETAILED_AUDIT_TEMPLATE,
)
from .year_auditor import YearAuditor
from .multi_year_reporter import MultiYearReporter

__all__ = [
    # Data models
    "WorkforceBreakdown",
    "EventSummary",
    "YearAuditReport",
    "MultiYearSummary",
    # Reporters
    "YearAuditor",
    "MultiYearReporter",
    # Formatters
    "ConsoleReporter",
    "ReportTemplate",
    # Templates
    "EXECUTIVE_SUMMARY_TEMPLATE",
    "DETAILED_AUDIT_TEMPLATE",
]
