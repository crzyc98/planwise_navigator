"""
Data models for audit and reporting.

This module contains the dataclasses used throughout the reports package.
It has no internal dependencies to serve as a stable foundation layer.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..validation import ValidationResult


@dataclass
class WorkforceBreakdown:
    """Breakdown of workforce by employment status."""

    year: int
    total_employees: int
    active_employees: int
    breakdown_by_status: Dict[str, int]
    participation_rate: float


@dataclass
class EventSummary:
    """Summary of events for a simulation year."""

    year: int
    total_events: int
    events_by_type: Dict[str, int]
    hire_termination_ratio: float


@dataclass
class YearAuditReport:
    """Complete audit report for a single simulation year."""

    year: int
    workforce_breakdown: WorkforceBreakdown
    event_summary: EventSummary
    growth_analysis: Dict[str, Any]
    contribution_summary: Optional[Dict[str, Any]]
    data_quality_results: List["ValidationResult"]
    generated_at: datetime

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        return {
            "year": self.year,
            "workforce_breakdown": asdict(self.workforce_breakdown),
            "event_summary": asdict(self.event_summary),
            "growth_analysis": self.growth_analysis,
            "contribution_summary": self.contribution_summary,
            "data_quality_results": [asdict(r) for r in self.data_quality_results],
            "generated_at": self.generated_at.isoformat(),
        }

    def export_json(self, path: Path | str) -> None:
        """Export report to JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as fh:
            json.dump(self.to_json_dict(), fh, indent=2)


@dataclass
class MultiYearSummary:
    """Summary report spanning multiple simulation years."""

    start_year: int
    end_year: int
    workforce_progression: List[WorkforceBreakdown]
    growth_analysis: Dict[str, Any]
    event_trends: Dict[str, List[int]]
    participation_trends: List[float]
    generated_at: datetime

    def export_csv(self, path: Path | str) -> None:
        """Export workforce progression to CSV file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["Year", "Total Employees", "Active Employees", "Participation Rate"]
            )
            for wb in self.workforce_progression:
                writer.writerow(
                    [
                        wb.year,
                        wb.total_employees,
                        wb.active_employees,
                        f"{wb.participation_rate:.1%}",
                    ]
                )
