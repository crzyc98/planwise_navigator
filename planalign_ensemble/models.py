"""Validated entities shared by seed-ensemble planning and reporting."""

from __future__ import annotations

from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CANONICAL_METRICS = (
    "active_headcount",
    "total_compensation",
    "employer_match_cost",
    "total_employer_plan_cost",
    "participation_rate",
    "avg_deferral_rate",
)


class Subsystem(str, Enum):
    """Known sources of stochasticity and their attribution status."""

    TERMINATION = "termination"
    HIRING = "hiring"
    PROMOTION = "promotion"
    ENROLLMENT = "enrollment"
    MERIT = "merit"

    @property
    def dbt_var(self) -> str | None:
        """Return the optional dbt override used to freeze this subsystem."""
        if self in {
            Subsystem.TERMINATION,
            Subsystem.HIRING,
            Subsystem.PROMOTION,
        }:
            return f"random_seed_{self.value}"
        return None

    @property
    def is_seed_variant(self) -> bool:
        """Whether the production path has an independent seeded draw today."""
        return self.dbt_var is not None


class Threshold(BaseModel):
    """A threshold evaluated against one canonical headline metric."""

    model_config = ConfigDict(frozen=True)

    metric: str = Field(min_length=1)
    value: float
    label: str | None = None


class EnsembleSpec(BaseModel):
    """User request for a deterministic set of isolated seed runs."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(min_length=1)
    seed_count: int = Field(ge=1)
    base_seed: int = 42
    seed_list: tuple[int, ...] | None = None
    start_year: int
    end_year: int
    thresholds: tuple[Threshold, ...] = Field(default_factory=tuple)
    min_seeds: int = Field(default=10, ge=1)
    attribution: bool = False
    attribution_seed_count: int | None = Field(default=None, ge=1)
    attribution_anchor_count: int | None = Field(default=None, ge=1)
    discard_seed_dbs: bool = False
    config_path: Path | None = None
    dbt_project_dir: Path | None = None

    @model_validator(mode="after")
    def validate_request(self) -> "EnsembleSpec":
        """Reject ambiguous seed lists and invalid paired-attribution requests."""
        if self.end_year < self.start_year:
            raise ValueError("end_year must be greater than or equal to start_year")
        if self.seed_list is not None:
            repeated = sorted(
                seed for seed, count in Counter(self.seed_list).items() if count > 1
            )
            if repeated:
                rendered = ", ".join(str(seed) for seed in repeated)
                raise ValueError(f"seed_list contains duplicate seed(s): {rendered}")
            if len(self.seed_list) != self.seed_count:
                raise ValueError(
                    "seed_count must equal the number of explicit seed_list values"
                )
        if (
            self.attribution_seed_count is not None
            and self.attribution_seed_count > self.seed_count
        ):
            raise ValueError("attribution_seed_count must be <= seed_count")
        return self

    @property
    def resolved_attribution_seed_count(self) -> int:
        """Return the bounded default requested for attribution, when enabled."""
        if not self.attribution:
            return 0
        return self.attribution_seed_count or min(self.seed_count, self.min_seeds)

    @property
    def resolved_attribution_anchor_count(self) -> int:
        """Return the number of anchor seeds averaged per subsystem, when enabled.

        Averaging over multiple anchors (rather than pinning to one) is what
        makes the estimate a defensible approximation of the first-order
        Sobol index for that subsystem instead of an arbitrary single-anchor
        conditional variance (#543).
        """
        if not self.attribution:
            return 0
        return self.attribution_anchor_count or 5


class SeedPlan(BaseModel):
    """Fully-resolved inputs and output locations known before workers start."""

    model_config = ConfigDict(frozen=True)

    ensemble_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    seeds: tuple[int, ...] = Field(min_length=1)
    seed_db_paths: dict[int, Path]
    ensemble_db_path: Path
    config_fingerprint: str = ""
    total_run_count: int = Field(ge=1)
    estimated_disk_mib: float = Field(ge=0)
    spec: EnsembleSpec

    @model_validator(mode="after")
    def validate_seed_paths(self) -> "SeedPlan":
        """Ensure each resolved seed has exactly one isolated output path."""
        if tuple(self.seed_db_paths) != self.seeds:
            raise ValueError("seed_db_paths must contain every seed in order")
        return self


class SeedRunOutcome(BaseModel):
    """Terminal outcome of one seed's isolated simulation."""

    model_config = ConfigDict(frozen=True)

    seed: int
    db_path: Path
    status: Literal["completed", "failed"]
    error: str | None = None
    duration_seconds: float = Field(default=0.0, ge=0)
    config_fingerprint: str = ""

    @property
    def succeeded(self) -> bool:
        """Return whether this seed produced an immutable result database."""
        return self.status == "completed"


class MetricSeedValue(BaseModel):
    """One headline metric extracted from one completed seed database."""

    model_config = ConfigDict(frozen=True)

    ensemble_id: str
    scenario_id: str
    metric: str
    simulation_year: int
    seed: int
    value: float | None = None


class MetricDistribution(BaseModel):
    """A seed-sufficient (or explicitly insufficient) metric distribution."""

    model_config = ConfigDict(frozen=True)

    ensemble_id: str
    scenario_id: str
    metric: str
    simulation_year: int
    p10: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    p90: float | None = None
    mean: float | None = None
    stddev: float | None = None
    n_seeds: int = Field(ge=0)
    n_seeds_requested: int = Field(ge=1)
    is_sufficient: bool
    percentile_method: Literal["linear"] = "linear"

    @model_validator(mode="after")
    def validate_sufficiency(self) -> "MetricDistribution":
        """Keep absent statistics structurally distinct from valid zero values."""
        statistics = (
            self.p10,
            self.p25,
            self.p50,
            self.p75,
            self.p90,
            self.mean,
            self.stddev,
        )
        if self.n_seeds > self.n_seeds_requested:
            raise ValueError("n_seeds cannot exceed n_seeds_requested")
        if self.is_sufficient and any(value is None for value in statistics):
            raise ValueError("sufficient distributions require all statistics")
        if not self.is_sufficient and any(value is not None for value in statistics):
            raise ValueError("insufficient distributions must withhold all statistics")
        return self


class RiskStatement(BaseModel):
    """One threshold result for one metric and simulation year."""

    model_config = ConfigDict(frozen=True)

    metric: str
    threshold_value: float
    simulation_year: int | None = None
    exceedance_probability: float | None = None
    n_seeds: int = Field(default=0, ge=0)
    is_evaluable: bool
    reason: str | None = None


class AttributionShare(BaseModel):
    """Anchor-averaged conditional variance share for one metric and subsystem.

    `variance_share` is the average, across `n_anchors` independently pinned
    anchor seeds, of `1 - Var(Y | subsystem seed = anchor) / Var(Y)`. By the law
    of total variance this approximates the first-order Sobol index for the
    subsystem: the share of outcome variance associated with that subsystem's
    draw, averaged rather than measured at one arbitrary anchor (#543). It
    captures only this subsystem's main effect — pinning one subsystem's seed
    also fixes the population later subsystems draw from, so interaction effects
    are not decomposed and shares across subsystems need not sum to 1. This is
    still not a causal attribution or a full variance decomposition.

    `ci_low`/`ci_high` are a paired bootstrap interval: each replicate resamples
    the paired (baseline, frozen) seed values within every anchor with
    replacement, recomputes the anchor-averaged share, and the interval is the
    2.5th/97.5th percentile of those replicates. The bootstrap RNG is seeded
    deterministically from (metric, simulation_year, subsystem), so re-running
    the same evidence reproduces the same interval.
    """

    model_config = ConfigDict(frozen=True)

    metric: str
    simulation_year: int
    subsystem: Subsystem
    variance_share: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    baseline_variance: float | None = None
    frozen_variance: float | None = None
    anchor_seeds: tuple[int, ...] = Field(default_factory=tuple)
    n_anchors: int = Field(default=0, ge=0)
    n_seeds: int = Field(ge=0)
    bootstrap_iterations: int = Field(default=0, ge=0)
    baselines_reused: int = Field(default=0, ge=0)
    baselines_executed: int = Field(default=0, ge=0)
    stochastic_status: Literal["stochastic", "not_stochastic"]

    @model_validator(mode="after")
    def validate_stochastic_status(self) -> "AttributionShare":
        """Avoid rendering structural non-stochasticity as a measured zero."""
        if self.stochastic_status == "not_stochastic" and (
            self.variance_share is not None
            or self.ci_low is not None
            or self.ci_high is not None
        ):
            raise ValueError(
                "not_stochastic attribution shares must have no measured statistics"
            )
        return self


class EnsembleResult(BaseModel):
    """Complete aggregate result returned by an ensemble execution."""

    model_config = ConfigDict(frozen=True)

    plan: SeedPlan
    outcomes: tuple[SeedRunOutcome, ...]
    distributions: tuple[MetricDistribution, ...] = Field(default_factory=tuple)
    risk_statements: tuple[RiskStatement, ...] = Field(default_factory=tuple)
    attribution: tuple[AttributionShare, ...] = Field(default_factory=tuple)


__all__ = [
    "AttributionShare",
    "CANONICAL_METRICS",
    "EnsembleResult",
    "EnsembleSpec",
    "MetricDistribution",
    "MetricSeedValue",
    "RiskStatement",
    "SeedPlan",
    "SeedRunOutcome",
    "Subsystem",
    "Threshold",
]
