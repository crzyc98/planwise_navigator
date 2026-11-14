"""Run-health summary models derived from archived validation evidence."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import ConfigDict, Field
from .base import APIModel

RunHealthStatus = Literal[
    "clean",
    "warnings",
    "failed",
    "missing_provenance",
    "unavailable",
]


class RunHealthCounts(APIModel):
    model_config = ConfigDict(frozen=True)

    passed: int = Field(ge=0)
    warning: int = Field(ge=0)
    failed: int = Field(ge=0)
    total: int = Field(ge=0)


class RunHealthFinding(APIModel):
    model_config = ConfigDict(frozen=True)

    check_name: str
    severity: str
    simulation_year: int
    stage: str
    passed: bool
    affected_record_count: Optional[int] = Field(default=None, ge=0)
    message: str


class RunHealthTieOut(APIModel):
    """Census tie-out rows that differ from the census (gaps only)."""

    model_config = ConfigDict(frozen=True)

    labels: List[str] = Field(description="Labels of the rows with a gap.")
    message: str


class RunHealthReport(APIModel):
    model_config = ConfigDict(frozen=True)

    status: RunHealthStatus
    scenario_id: str
    run_id: str
    disposition: Optional[str] = None
    counts: RunHealthCounts
    findings: List[RunHealthFinding] = Field(default_factory=list)
    census_tie_out: Optional[RunHealthTieOut] = Field(
        default=None,
        description=(
            "Set when the selected run's census tie-out has a gap; null when "
            "it ties, is unavailable, or the run isn't the selected result."
        ),
    )
