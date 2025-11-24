# Story S038-05: Audit & Reporting System

**Epic**: E038 - PlanAlign Orchestrator Refactoring & Modularization
**Story Points**: 5
**Priority**: High
**Status**: 🟠 In Progress
**Dependencies**: S038-01 (Core Infrastructure Setup), S038-04 (Validation Framework)
**Assignee**: Development Team

---

## 🎯 **Goal**

Enhance reporting capabilities with modular design, providing clean separation between year-specific and multi-year reporting, with configurable templates and multiple export formats.

## 📋 **User Story**

As a **business analyst** using Fidelity PlanAlign Engine simulation results,
I want **comprehensive, configurable audit reports with export capabilities**
So that **I can analyze simulation outcomes in multiple formats and share insights with stakeholders**.

## 🛠 **Technical Tasks**

### **Task 1: Create Reporting Framework**
- Design `YearAuditor` class for single-year reporting
- Create `MultiYearReporter` class for cross-year analytics
- Implement configurable report templates
- Add statistical insights and trend analysis

### **Task 2: Export Capabilities**
- Support multiple output formats (console, JSON, CSV, HTML)
- Create formatted report templates for each output type
- Add data visualization capabilities (ASCII charts, tables)
- Implement report persistence and archival

### **Task 3: Enhanced Analytics**
- Migrate existing audit functions with improvements
- Add advanced statistical analysis (CAGR, variance analysis)
- Implement comparative reporting between scenarios
- Add automated insights and recommendations

## ✅ **Acceptance Criteria**

### **Functional Requirements**
- ✅ Clean separation between year-specific and multi-year reporting
- ✅ Export capabilities for various formats (console, JSON, CSV, HTML)
- ✅ Enhanced analytics with statistical insights
- ✅ Configurable report templates with custom sections

### **Quality Requirements**
- ✅ 95%+ test coverage including report generation scenarios
- ✅ Fast report generation (< 10 seconds for multi-year reports)
- ✅ Memory-efficient processing of large datasets
- ✅ Robust error handling for malformed data

### **Integration Requirements**
- ✅ Integration with validation framework for data quality reporting
- ✅ Compatible with existing database schema
- ✅ Supports batch report generation for multiple scenarios

## 🧪 **Testing Strategy**

### **Unit Tests**
```python
# test_reports.py
def test_year_auditor_workforce_breakdown()
def test_year_auditor_event_summary()
def test_multi_year_reporter_progression_analysis()
def test_report_export_json_format()
def test_report_export_csv_format()
def test_statistical_calculations_accuracy()
def test_configurable_report_templates()
```

### **Integration Tests**
- Generate reports with real simulation data
- Test export formats with large datasets
- Validate statistical calculations against known results
- Test report template customization

## 📊 **Definition of Done**

- [x] `reports.py` module created with reporting framework
- [x] Year-specific and multi-year reporting classes implemented
- [x] Export capabilities for JSON (year) and CSV (multi-year)
- [x] Enhanced statistical analysis integrated (CAGR, net growth)
- [x] Configurable report templates system (initial)
- [ ] Unit and integration tests achieve 95%+ coverage
- [ ] Performance benchmarks meet requirements
- [x] Documentation complete with template examples

### 🔧 Implementation Progress

- Added `planalign_orchestrator/reports.py` implementing:
  - Year reporting: `YearAuditor`, `YearAuditReport`, `WorkforceBreakdown`, `EventSummary`
  - Multi-year: `MultiYearReporter`, `MultiYearSummary`
  - Exports: `YearAuditReport.export_json(...)`, `MultiYearSummary.export_csv(...)`
  - Console formatting: `ConsoleReporter.format_year_audit(...)`
  - Template system: `ReportTemplate` with `EXECUTIVE_SUMMARY_TEMPLATE` and `DETAILED_AUDIT_TEMPLATE`
- Added tests in `tests/test_reports.py` covering:
  - Workforce breakdown, event summary, progression analysis
  - JSON and CSV export
  - Template application logic

## 🔗 **Dependencies**

### **Upstream Dependencies**
- **S038-01**: Requires `utils.py` for database connections and timing
- **S038-04**: Uses validation results in audit reports

### **Downstream Dependencies**
- **S038-06** (Pipeline Orchestration): Will integrate reporting into workflow
- **Future dashboard features**: Will consume structured report data

## 📝 **Implementation Notes**

### **Reporting Framework Design**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
import csv
from datetime import datetime

@dataclass
class WorkforceBreakdown:
    """Year-end workforce breakdown by status."""
    year: int
    total_employees: int
    active_employees: int
    breakdown_by_status: Dict[str, int]
    participation_rate: float

@dataclass
class EventSummary:
    """Event summary for a simulation year."""
    year: int
    total_events: int
    events_by_type: Dict[str, int]
    hire_termination_ratio: float

@dataclass
class YearAuditReport:
    """Complete audit report for a single year."""
    year: int
    workforce_breakdown: WorkforceBreakdown
    event_summary: EventSummary
    growth_analysis: Dict[str, Any]
    contribution_summary: Optional[Dict[str, Any]]
    data_quality_results: List[ValidationResult]
    generated_at: datetime

class YearAuditor:
    """Generates comprehensive audit reports for individual years."""

    def __init__(self, db_manager: DatabaseConnectionManager, validator: DataValidator):
        self.db_manager = db_manager
        self.validator = validator

    def generate_report(self, year: int) -> YearAuditReport:
        """Generate comprehensive audit report for specified year."""
        with self.db_manager.get_connection() as conn:
            return YearAuditReport(
                year=year,
                workforce_breakdown=self._generate_workforce_breakdown(conn, year),
                event_summary=self._generate_event_summary(conn, year),
                growth_analysis=self._calculate_growth_analysis(conn, year),
                contribution_summary=self._generate_contribution_summary(conn, year),
                data_quality_results=self.validator.validate_year_results(year),
                generated_at=datetime.utcnow()
            )

    def _generate_workforce_breakdown(self, conn, year: int) -> WorkforceBreakdown:
        """Generate workforce breakdown by employment status."""
        query = """
        SELECT
            detailed_status_code,
            COUNT(*) as employee_count,
            COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
        FROM fct_workforce_snapshot
        WHERE simulation_year = ?
        GROUP BY detailed_status_code
        ORDER BY employee_count DESC
        """
        results = conn.execute(query, [year]).fetchall()

        breakdown_by_status = {status: count for status, count, _ in results}
        total_employees = sum(breakdown_by_status.values())
        active_employees = breakdown_by_status.get('active', 0)

        # Calculate participation rate
        participation_query = """
        SELECT COUNT(*) FROM fct_workforce_snapshot
        WHERE simulation_year = ?
          AND employment_status = 'active'
          AND participation_status = 'participating'
        """
        participating = conn.execute(participation_query, [year]).fetchone()[0]
        participation_rate = participating / active_employees if active_employees > 0 else 0

        return WorkforceBreakdown(
            year=year,
            total_employees=total_employees,
            active_employees=active_employees,
            breakdown_by_status=breakdown_by_status,
            participation_rate=participation_rate
        )
```

## 📘 **Usage Examples**

```python
from planalign_orchestrator.utils import DatabaseConnectionManager
from planalign_orchestrator.validation import DataValidator, HireTerminationRatioRule
from planalign_orchestrator.reports import YearAuditor, MultiYearReporter, ConsoleReporter

db = DatabaseConnectionManager()
dv = DataValidator(db)
dv.register_rule(HireTerminationRatioRule())

# Single-year report
auditor = YearAuditor(db, dv)
report = auditor.generate_report(2026)
print(ConsoleReporter.format_year_audit(report))
report.export_json("reports/year_2026.json")

# Multi-year summary
myr = MultiYearReporter(db)
summary = myr.generate_summary([2025, 2026, 2027])
summary.export_csv("reports/multi_year_summary.csv")
```

### **Multi-Year Reporter Design**
```python
@dataclass
class MultiYearSummary:
    """Summary of multi-year simulation results."""
    start_year: int
    end_year: int
    workforce_progression: List[WorkforceBreakdown]
    growth_analysis: Dict[str, Any]
    event_trends: Dict[str, List[int]]
    participation_trends: List[float]
    generated_at: datetime

class MultiYearReporter:
    """Generates comprehensive multi-year analysis reports."""

    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager

    def generate_summary(self, years: List[int]) -> MultiYearSummary:
        """Generate multi-year summary report."""
        if len(years) < 2:
            raise ValueError("Multi-year analysis requires at least 2 years")

        with self.db_manager.get_connection() as conn:
            return MultiYearSummary(
                start_year=min(years),
                end_year=max(years),
                workforce_progression=self._calculate_workforce_progression(conn, years),
                growth_analysis=self._calculate_overall_growth(conn, years),
                event_trends=self._analyze_event_trends(conn, years),
                participation_trends=self._analyze_participation_trends(conn, years),
                generated_at=datetime.utcnow()
            )

    def _calculate_overall_growth(self, conn, years: List[int]) -> Dict[str, Any]:
        """Calculate compound annual growth rate and other metrics."""
        first_year, last_year = min(years), max(years)

        # Get active employee counts for first and last year
        query = """
        SELECT simulation_year, COUNT(*) as active_count
        FROM fct_workforce_snapshot
        WHERE simulation_year IN (?, ?) AND employment_status = 'active'
        GROUP BY simulation_year
        ORDER BY simulation_year
        """
        results = dict(conn.execute(query, [first_year, last_year]).fetchall())

        start_count = results.get(first_year, 0)
        end_count = results.get(last_year, 0)

        years_elapsed = last_year - first_year
        if start_count > 0 and years_elapsed > 0:
            cagr = ((end_count / start_count) ** (1 / years_elapsed) - 1) * 100
            total_growth = ((end_count - start_count) / start_count) * 100
        else:
            cagr = 0
            total_growth = 0

        return {
            "starting_workforce": start_count,
            "ending_workforce": end_count,
            "total_growth_pct": total_growth,
            "compound_annual_growth_rate": cagr,
            "years_analyzed": years_elapsed
        }
```

### **Export System Design**
```python
class ReportExporter:
    """Handles export of reports to various formats."""

    @staticmethod
    def export_to_json(report: Any, output_path: Path):
        """Export report to JSON format."""
        with open(output_path, 'w') as f:
            json.dump(asdict(report), f, indent=2, default=str)

    @staticmethod
    def export_to_csv(multi_year_summary: MultiYearSummary, output_path: Path):
        """Export multi-year summary to CSV format."""
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)

            # Write workforce progression
            writer.writerow(['Year', 'Total Employees', 'Active Employees', 'Participation Rate'])
            for breakdown in multi_year_summary.workforce_progression:
                writer.writerow([
                    breakdown.year,
                    breakdown.total_employees,
                    breakdown.active_employees,
                    f"{breakdown.participation_rate:.1%}"
                ])

    @staticmethod
    def export_to_html(report: YearAuditReport, template_path: Path, output_path: Path):
        """Export report to HTML using template."""
        # Implementation would use Jinja2 or similar templating
        pass

class ConsoleReporter:
    """Formats reports for console output."""

    @staticmethod
    def format_year_audit(report: YearAuditReport) -> str:
        """Format year audit report for console display."""
        lines = []
        lines.append(f"\n📊 YEAR {report.year} AUDIT RESULTS")
        lines.append("=" * 50)

        # Workforce breakdown
        lines.append("\n📋 Year-end Employment Makeup by Status:")
        wb = report.workforce_breakdown
        for status, count in wb.breakdown_by_status.items():
            pct = (count / wb.total_employees) * 100
            lines.append(f"   {status:25}: {count:4,} ({pct:4.1f}%)")
        lines.append(f"   {'TOTAL':25}: {wb.total_employees:4,} (100.0%)")

        # Event summary
        lines.append(f"\n📈 Year {report.year} Event Summary:")
        es = report.event_summary
        for event_type, count in es.events_by_type.items():
            lines.append(f"   {event_type:15}: {count:4,}")
        lines.append(f"   {'TOTAL':15}: {es.total_events:4,}")

        # Data quality results
        lines.append("\n🔍 Data Quality Results:")
        for result in report.data_quality_results:
            status = "✅" if result.passed else "❌"
            lines.append(f"   {status} {result.rule_name}: {result.message}")

        return "\n".join(lines)
```

### **Template System**
```python
class ReportTemplate:
    """Configurable report template system."""

    def __init__(self, template_config: Dict[str, Any]):
        self.config = template_config

    def apply_template(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply template configuration to report data."""
        sections = self.config.get('sections', [])
        filtered_data = {}

        for section in sections:
            section_name = section['name']
            if section.get('enabled', True) and section_name in report_data:
                filtered_data[section_name] = report_data[section_name]

        return filtered_data

# Example template configuration
EXECUTIVE_SUMMARY_TEMPLATE = {
    "name": "Executive Summary",
    "sections": [
        {"name": "workforce_breakdown", "enabled": True},
        {"name": "growth_analysis", "enabled": True},
        {"name": "event_summary", "enabled": False},
        {"name": "data_quality_results", "enabled": False}
    ]
}

DETAILED_AUDIT_TEMPLATE = {
    "name": "Detailed Audit",
    "sections": [
        {"name": "workforce_breakdown", "enabled": True},
        {"name": "event_summary", "enabled": True},
        {"name": "growth_analysis", "enabled": True},
        {"name": "contribution_summary", "enabled": True},
        {"name": "data_quality_results", "enabled": True}
    ]
}
```

---

**This story provides comprehensive, configurable reporting capabilities with multiple export formats and enhanced analytics to support business decision-making.**
