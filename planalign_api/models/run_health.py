"""Run-health summary models derived from archived validation evidence."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RunHealthStatus = Literal[
    "clean",
    "warnings",
    "failed",
    "missing_provenance",
    "unavailable",
]


class RunHealthCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: int = Field(ge=0)
    warning: int = Field(ge=0)
    failed: int = Field(ge=0)
    total: int = Field(ge=0)


class RunHealthFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_name: str
    severity: str
    simulation_year: int
    stage: str
    passed: bool
    affected_record_count: Optional[int] = Field(default=None, ge=0)
    message: str


class RunHealthReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: RunHealthStatus
    scenario_id: str
    run_id: str
    disposition: Optional[str] = None
    counts: RunHealthCounts
    findings: List[RunHealthFinding] = Field(default_factory=list)
