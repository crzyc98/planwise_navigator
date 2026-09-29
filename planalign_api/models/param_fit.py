"""API models for Studio parameter fit & backtest jobs (#588).

Bounds mirror the ``planalign fit`` / ``planalign backtest`` CLI validation so a
request the API accepts is one the CLI engine behind it will too.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from planalign_fit.promotion import (
    DEFAULT_LEVEL_COVERAGE_THRESHOLD,
    DEFAULT_SEPARATION_EXPOSURE_GATE,
)
from planalign_fit.smoothing import DEFAULT_CREDIBILITY_K, DEFAULT_MIN_EXPOSURE

from .base import APIModel
from .comparison import ConfigDelta

JobMode = Literal["fit", "backtest"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
JobStage = Literal[
    "queued",
    "loading_history",
    "fitting",
    "simulating",
    "scoring",
    "writing_pack",
]
ErrorKind = Literal[
    "invalid_input",
    "invalid_history",
    "output_conflict",
    "simulation_failure",
    "interrupted",
    "unexpected",
]
StaleKind = Literal["history_changed", "pack_modified", "base_scenario_changed"]
Acknowledgement = Literal[
    "thin_cells", "unfittable", "no_backtest", "backtest_warn", "backtest_fail"
]
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class SnapshotInfo(APIModel):
    year: int
    filename: str
    row_count: int
    sha256: str
    as_of_date: date
    columns_present: list[str] = Field(default_factory=list)


class SplitPreview(APIModel):
    fit_years: list[int]
    holdout_years: list[int]
    boundary_year: int
    simulation_effective_date: date


class SplitOption(APIModel):
    """The backtest split one holdout choice produces, or why it cannot."""

    holdout_years: int
    split: Optional[SplitPreview] = None
    error: Optional[str] = None


class HistorySet(APIModel):
    history_id: str
    created_at: datetime
    snapshots: list[SnapshotInfo]
    source_digest: str
    splits: list[SplitOption]


# ---------------------------------------------------------------------------
# Launch request
# ---------------------------------------------------------------------------


class FitOptionsModel(APIModel):
    credibility_k: float = Field(default=DEFAULT_CREDIBILITY_K, ge=0)
    min_exposure: float = Field(default=DEFAULT_MIN_EXPOSURE, ge=0)
    level_coverage_threshold: float = Field(
        default=DEFAULT_LEVEL_COVERAGE_THRESHOLD, gt=0, le=1
    )
    separation_exposure_gate: float = Field(
        default=DEFAULT_SEPARATION_EXPOSURE_GATE, gt=0, le=1
    )


class ThresholdPair(APIModel):
    warn: float = Field(gt=0)
    fail: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> "ThresholdPair":
        if not self.warn < self.fail:
            raise ValueError("warn must be less than fail")
        return self


class ThresholdsModel(APIModel):
    """Backtest pass/warn/fail bands — defaults match the CLI."""

    headcount: ThresholdPair = Field(
        default_factory=lambda: ThresholdPair(warn=0.02, fail=0.04)
    )
    compensation: ThresholdPair = Field(
        default_factory=lambda: ThresholdPair(warn=0.03, fail=0.06)
    )
    flows: ThresholdPair = Field(
        default_factory=lambda: ThresholdPair(warn=0.10, fail=0.20)
    )
    plan: ThresholdPair = Field(
        default_factory=lambda: ThresholdPair(warn=0.05, fail=0.10)
    )


class ParamFitRequest(APIModel):
    history_id: str = Field(min_length=1)
    base_scenario_id: str = Field(min_length=1)
    mode: JobMode = "fit"
    holdout_years: int = Field(default=1, ge=1, le=2)
    seeds: list[int] = Field(default_factory=lambda: [42, 43, 44])
    thresholds: ThresholdsModel = Field(default_factory=ThresholdsModel)
    fit_options: FitOptionsModel = Field(default_factory=FitOptionsModel)
    notes: str = Field(default="", max_length=500)

    @field_validator("seeds")
    @classmethod
    def _distinct_seeds(cls, seeds: list[int]) -> list[int]:
        if not 1 <= len(seeds) <= 5:
            raise ValueError("seeds must contain between 1 and 5 values")
        if len(set(seeds)) != len(seeds):
            raise ValueError(
                "seeds must be distinct; duplicate runs would narrow the "
                "reported spread without adding information"
            )
        return seeds


# ---------------------------------------------------------------------------
# Job record
# ---------------------------------------------------------------------------


class JobInputs(APIModel):
    history_id: str
    source_digest: str
    snapshots: list[SnapshotInfo]
    split: Optional[SplitPreview] = None
    base_scenario_id: str
    base_scenario_name: str
    base_scenario_fingerprint: str
    moved_settings: dict[str, Any] = Field(default_factory=dict)


class JobProgress(APIModel):
    stage: JobStage = "queued"
    seed: Optional[int] = None
    index: Optional[int] = None
    total: Optional[int] = None
    updated_at: Optional[datetime] = None


class JobError(APIModel):
    kind: ErrorKind
    message: str
    status: int
    failed_seed: Optional[int] = None
    failed_year: Optional[int] = None


class StaleReason(APIModel):
    reason: StaleKind
    message: str


class ParamFitResult(APIModel):
    """What a completed job produced, read back from its pack."""

    summary: dict[str, Any]
    diagnostics: dict[str, list[dict[str, Any]]]
    unfittable: list[dict[str, Any]]
    warnings: list[str]
    promotion_classification: Optional[dict[str, Any]] = None
    provenance: dict[str, Any]
    scorecard: Optional[dict[str, Any]] = None
    scorecard_current: bool = False
    has_fit_report: bool = False
    stale: list[StaleReason] = Field(default_factory=list)


class ParamFitJob(APIModel):
    job_id: str
    workspace_id: str
    mode: JobMode
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    request: ParamFitRequest
    inputs: JobInputs
    progress: JobProgress = Field(default_factory=JobProgress)
    error: Optional[JobError] = None
    result: Optional[ParamFitResult] = None


class ParamFitJobSummary(APIModel):
    job_id: str
    mode: JobMode
    status: JobStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    history_id: str
    snapshot_years: list[int]
    base_scenario_id: str
    base_scenario_name: str
    progress: JobProgress
    error: Optional[JobError] = None
    pack_id: Optional[str] = None
    verdict: Optional[str] = None


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


class ApplyPreview(APIModel):
    source_scenario_id: str
    source_config_fingerprint: str
    pack_id: str
    pack_fingerprint: str
    backtest_verdict: Optional[str] = None
    required_acknowledgements: list[Acknowledgement]
    diff: list[ConfigDelta]
    seed_files: list[str]
    suggested_name: str


class ApplyRequest(APIModel):
    source_scenario_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    pack_fingerprint: str = Field(min_length=1)
    source_config_fingerprint: str = Field(min_length=1)
    acknowledgements: list[Acknowledgement] = Field(default_factory=list)
