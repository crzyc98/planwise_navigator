"""
Report formatting utilities.

Contains console output formatting and report templates for
customizing report content and display.
"""

from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .data_models import YearAuditReport


class ConsoleReporter:
    """Formats audit reports for console output."""

    @staticmethod
    def format_year_audit(report: "YearAuditReport") -> str:
        """Format a year audit report for console display."""
        lines: List[str] = []
        lines.append(f"\n📊 YEAR {report.year} AUDIT RESULTS")
        lines.append("=" * 50)

        lines.append("\n📋 Year-end Employment Makeup by Status:")
        wb = report.workforce_breakdown
        for status, count in wb.breakdown_by_status.items():
            pct = (count / wb.total_employees * 100) if wb.total_employees > 0 else 0
            lines.append(f"   {status:25}: {count:4,} ({pct:4.1f}%)")
        lines.append(f"   {'TOTAL':25}: {wb.total_employees:4,} (100.0%)")

        lines.append(f"\n📈 Year {report.year} Event Summary:")
        es = report.event_summary
        for event_type, count in es.events_by_type.items():
            lines.append(f"   {event_type:15}: {count:4,}")
        lines.append(f"   {'TOTAL':15}: {es.total_events:4,}")

        lines.append("\n🔍 Data Quality Results:")
        for r in report.data_quality_results:
            status = "✅" if r.passed else "❌"
            lines.append(f"   {status} {r.rule_name}: {r.message}")

        return "\n".join(lines)


class ReportTemplate:
    """Configurable template for filtering report sections."""

    def __init__(self, template_config: Dict[str, Any]):
        self.config = template_config

    def apply_template(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply template to filter report sections."""
        sections = self.config.get("sections", [])
        filtered: Dict[str, Any] = {}
        for section in sections:
            name = section["name"]
            if section.get("enabled", True) and name in report_data:
                filtered[name] = report_data[name]
        return filtered


# Pre-defined report templates
EXECUTIVE_SUMMARY_TEMPLATE = {
    "name": "Executive Summary",
    "sections": [
        {"name": "workforce_breakdown", "enabled": True},
        {"name": "growth_analysis", "enabled": True},
        {"name": "event_summary", "enabled": False},
        {"name": "data_quality_results", "enabled": False},
    ],
}


DETAILED_AUDIT_TEMPLATE = {
    "name": "Detailed Audit",
    "sections": [
        {"name": "workforce_breakdown", "enabled": True},
        {"name": "event_summary", "enabled": True},
        {"name": "growth_analysis", "enabled": True},
        {"name": "contribution_summary", "enabled": True},
        {"name": "data_quality_results", "enabled": True},
    ],
}
