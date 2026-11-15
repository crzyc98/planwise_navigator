"""API models for Studio seed-ensemble jobs.

A job runs ``planalign simulate --seed-list`` for one scenario's effective
config. Its record carries everything a later screen needs to read the result
through the existing ``/api/ensembles/*`` reader endpoints, so no client ever
types a filesystem path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from .base import APIModel

# Bands need at least this many successful seeds (passed as --min-seeds).
MIN_SEED_COUNT = 5
MAX_SEED_COUNT = 50

EnsembleJobStatus = Literal[
    "queued", "running", "completed", "partial", "failed", "cancelled"
]
EnsembleErrorKind = Literal["seeds_failed", "no_seeds", "interrupted", "unexpected"]
TimeBasis = Literal["measured", "default"]
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "partial", "failed", "cancelled"}
)


class EnsembleRequest(APIModel):
    seed_count: int = Field(default=10, ge=MIN_SEED_COUNT, le=MAX_SEED_COUNT)


class EnsembleEstimate(APIModel):
    """What an ensemble will cost, known before any seed starts."""

    seed_count: int
    seeds: list[int]
    start_year: int
    end_year: int
    run_count: int = Field(description="Seed runs, one at a time")
    seconds_per_run: float
    estimated_seconds: float
    time_basis: TimeBasis = Field(
        description=(
            "'measured' scales the scenario's last completed run; 'default' "
            "uses a fixed per-run-year rate because no run was found"
        )
    )
    estimated_disk_mib: float = Field(
        description="Peak disk while seeds run; only the aggregate is kept after"
    )


class EnsembleProgress(APIModel):
    seeds_total: int
    seeds_completed: int = 0
    seeds_failed: int = 0
    current_seed: Optional[int] = None
    updated_at: Optional[datetime] = None


class EnsembleError(APIModel):
    kind: EnsembleErrorKind
    message: str


class EnsembleOutput(APIModel):
    """Where a finished ensemble's aggregate lives, for the reader endpoints."""

    database_path: str
    ensemble_id: str
    ensemble_scenario_id: str


class EnsembleJob(APIModel):
    job_id: str
    workspace_id: str
    scenario_id: str
    scenario_name: str
    status: EnsembleJobStatus
    seed_count: int
    seeds: list[int]
    start_year: int
    end_year: int
    estimate: EnsembleEstimate
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: EnsembleProgress
    failed_seeds: list[int] = Field(default_factory=list)
    error: Optional[EnsembleError] = None
    output: Optional[EnsembleOutput] = None


class CostBand(APIModel):
    """P10-P90 of one scenario's employer cost across its ensemble's seeds."""

    p10: float
    p90: float
    n_seeds: int


class YearCostBand(CostBand):
    year: int


class DifferenceRange(APIModel):
    """Spread of (scenario - anchor) employer cost, differenced seed by seed."""

    min: float
    max: float
    p10: float
    p90: float
    n_seeds: int


class YearDifferenceRange(DifferenceRange):
    year: int


class ScenarioCostRange(APIModel):
    """Seed ranges for one compared scenario; empty when there are none."""

    scenario_id: str
    job_id: Optional[str] = None
    completed_at: Optional[datetime] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    current: bool = Field(
        default=False,
        description=(
            "Whether the ensemble ran on the same settings (config fingerprint) "
            "as the scenario's results shown; ranges are only given when it did"
        ),
    )
    years: list[YearCostBand] = Field(
        default_factory=list, description="Annual employer cost, P10-P90"
    )
    total: Optional[CostBand] = Field(
        default=None, description="Employer cost summed over the ensemble's years"
    )
    paired: bool = Field(
        default=False,
        description="Whether differences from the anchor were taken seed by seed",
    )
    difference_years: list[YearDifferenceRange] = Field(default_factory=list)
    difference_total: Optional[DifferenceRange] = None
    reason: Optional[str] = Field(
        default=None, description="Why ranges or pairing are missing, in one line"
    )


class EnsembleCostRanges(APIModel):
    """Seed ranges beside Cost Comparison's gross employer cost.

    The metric is ``total_employer_plan_cost``: the sum of employer match and
    core over every snapshot row, the same quantity as the page's gross
    employer cost for all employees.
    """

    anchor_scenario_id: str
    scenarios: list[ScenarioCostRange]
