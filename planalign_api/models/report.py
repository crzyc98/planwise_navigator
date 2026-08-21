"""Traceable executive report contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReportWarning(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"


class ReportYearMetrics(BaseModel):
    year: int
    headcount: int | None = None
    average_compensation: float | None = None
    participation_rate: float | None = None
    employer_cost: float | None = None
    estimated: bool = False


class ReportProvenance(BaseModel):
    workspace_id: str
    scenario_id: str
    scenario_name: str
    run_id: str | None = None
    config_fingerprint: str | None = None
    random_seed: int | None = None
    git_sha: str | None = None
    run_timestamp: datetime | None = None
    source_result: str | None = None


class ScenarioReport(BaseModel):
    title: str
    generated_at: datetime
    years: list[ReportYearMetrics] = Field(default_factory=list)
    comparison_years: dict[str, list[ReportYearMetrics]] = Field(default_factory=dict)
    provenance: list[ReportProvenance] = Field(default_factory=list)
    warnings: list[ReportWarning] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    comparison_scenario_ids: list[str] = Field(default_factory=list)
