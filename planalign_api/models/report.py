"""Plan-design comparison report contracts.

One model feeds every output format (HTML, PDF, PPTX), so a figure on a slide
is the same number as in the PDF by construction. Unknown values are ``None``
and render as a dash, never as zero.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .base import APIModel

MAX_REPORT_SCENARIOS = 6


class ReportWarning(APIModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"


class ReportDefinition(APIModel):
    """A footnote defining one figure; ``term`` is a stable key."""

    term: Literal[
        "employer_cost", "capped_pay", "difference", "participation", "design"
    ]
    text: str


class ReportPlanDesign(APIModel):
    """One scenario's plan design in plain words."""

    eligibility: str
    auto_enrollment: str
    escalation: str
    match: str
    core: str


class ReportYear(APIModel):
    """One plan year of figures for one scenario."""

    year: int
    employer_cost: float | None = None
    cost_pct_of_capped_pay: float | None = None
    participation_rate: float | None = Field(
        default=None, description="Percent of all employees enrolled (0-100)"
    )
    average_deferral_rate: float | None = Field(
        default=None, description="Percent of pay, non-participants count as 0"
    )
    difference_from_anchor: float | None = None


class ReportScenario(APIModel):
    """One selected scenario: its design and, when it has a result, its figures."""

    scenario_id: str
    name: str
    is_anchor: bool = False
    missing_reason: str | None = Field(
        default=None, description="Why the scenario has no usable result"
    )
    design: ReportPlanDesign | None = None
    years: list[ReportYear] = Field(default_factory=list)
    total_employer_cost: float | None = None
    total_cost_pct_of_capped_pay: float | None = None
    total_difference_from_anchor: float | None = None
    total_difference_pct_of_anchor: float | None = None

    @property
    def available(self) -> bool:
        return self.missing_reason is None


class ReportProvenance(APIModel):
    workspace_id: str
    scenario_id: str
    scenario_name: str
    run_id: str | None = None
    config_fingerprint: str | None = None
    random_seed: int | None = None
    git_sha: str | None = None
    run_timestamp: datetime | None = None
    source_result: str | None = None


class ScenarioReport(APIModel):
    """A client brief comparing plan designs and what they cost."""

    title: str
    generated_at: datetime
    anchor_scenario_id: str
    scenarios: list[ReportScenario] = Field(default_factory=list)
    definitions: list[ReportDefinition] = Field(default_factory=list)
    provenance: list[ReportProvenance] = Field(default_factory=list)
    warnings: list[ReportWarning] = Field(default_factory=list)

    @property
    def anchor(self) -> ReportScenario:
        return next(s for s in self.scenarios if s.is_anchor)

    @property
    def is_comparison(self) -> bool:
        return len(self.scenarios) > 1

    def note(self, term: str) -> int | None:
        """1-based footnote number for ``term``, or None when not defined."""
        return next(
            (i for i, d in enumerate(self.definitions, 1) if d.term == term), None
        )

    @property
    def years(self) -> list[int]:
        return sorted({y.year for s in self.scenarios for y in s.years})
