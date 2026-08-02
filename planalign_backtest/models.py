"""Immutable configuration, metric, and scorecard models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from planalign_fit.runner import FitOptions

Family = Literal["headcount", "compensation", "flows", "plan"]
Status = Literal["pass", "warn", "fail", "not_observable", "undefined"]
Period = int | Literal["cumulative"]
CumulativeRule = Literal["final", "sum"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class Threshold(FrozenModel):
    warn: float
    fail: float

    @model_validator(mode="after")
    def validate_bounds(self) -> "Threshold":
        if self.warn <= 0 or self.fail <= 0 or self.warn >= self.fail:
            raise ValueError("thresholds require 0 < warn < fail")
        return self


class MetricThresholds(FrozenModel):
    headcount: Threshold = Field(
        default_factory=lambda: Threshold(warn=0.02, fail=0.04)
    )
    compensation: Threshold = Field(
        default_factory=lambda: Threshold(warn=0.03, fail=0.06)
    )
    flows: Threshold = Field(default_factory=lambda: Threshold(warn=0.10, fail=0.20))
    plan: Threshold = Field(default_factory=lambda: Threshold(warn=0.05, fail=0.10))

    def for_family(self, family: Family) -> Threshold:
        return getattr(self, family)


class SnapshotSplit(FrozenModel):
    fit_years: tuple[int, ...]
    holdout_years: tuple[int, ...]
    boundary_year: int
    all_years: tuple[int, ...]

    @model_validator(mode="after")
    def validate_partition(self) -> "SnapshotSplit":
        if len(self.fit_years) < 2:
            raise ValueError("fit_years must contain at least 2 years")
        if not 1 <= len(self.holdout_years) <= 2:
            raise ValueError("holdout_years must contain 1 or 2 years")
        if self.boundary_year != max(self.fit_years):
            raise ValueError("boundary_year must equal max(fit_years)")
        if set(self.fit_years) & set(self.holdout_years):
            raise ValueError("fit_years and holdout_years must be disjoint")
        if tuple((*self.fit_years, *self.holdout_years)) != self.all_years:
            raise ValueError("fit and holdout years must exhaust all_years in order")
        if any(b != a + 1 for a, b in zip(self.all_years, self.all_years[1:])):
            raise ValueError("all_years must be consecutive")
        if min(self.holdout_years) != self.boundary_year + 1:
            raise ValueError("holdout must immediately follow boundary_year")
        return self


class BacktestOptions(FrozenModel):
    holdout_years: int = Field(default=1, ge=1, le=2)
    seeds: tuple[int, ...] = (42, 43, 44)
    thresholds: MetricThresholds = Field(default_factory=MetricThresholds)
    output: Optional[Path] = None
    base_config: Optional[Path] = None
    workdir: Optional[Path] = None
    fit_options: FitOptions = Field(default_factory=FitOptions)
    force: bool = False
    keep_databases: bool = False
    overridden_thresholds: tuple[Family, ...] = ()
    notes: str = ""
    verbose: bool = False

    @field_validator("seeds")
    @classmethod
    def validate_seeds(cls, seeds: tuple[int, ...]) -> tuple[int, ...]:
        if not 1 <= len(seeds) <= 5:
            raise ValueError("seeds must contain between 1 and 5 values")
        if len(set(seeds)) != len(seeds):
            duplicate = next(seed for seed in seeds if seeds.count(seed) > 1)
            raise ValueError(
                f"seed list contains duplicate seed {duplicate}; duplicate runs "
                "would narrow the reported spread without adding information"
            )
        return seeds

    @model_validator(mode="after")
    def runner_owns_split(self) -> "BacktestOptions":
        if self.fit_options.only_years is not None:
            raise ValueError("fit_options.only_years is owned by the backtest runner")
        return self


class SeedRun(FrozenModel):
    seed: int
    database: Path
    config_fingerprint: str
    years_simulated: tuple[int, ...]


class MetricValue(FrozenModel):
    metric: str
    period: Period


class SeedSpread(FrozenModel):
    seed_count: int = Field(ge=2)
    minimum: float
    maximum: float
    values: tuple[float, ...]
    actual_within_spread: bool
    distance_outside: float | None

    @model_validator(mode="after")
    def validate_spread(self) -> "SeedSpread":
        if len(self.values) != self.seed_count:
            raise ValueError("seed_count must match values")
        if self.minimum != min(self.values) or self.maximum != max(self.values):
            raise ValueError("minimum and maximum must be derived from values")
        if self.actual_within_spread != (self.distance_outside is None):
            raise ValueError(
                "distance_outside must be null exactly when actual is inside"
            )
        return self


class MetricComparison(FrozenModel):
    metric: str
    period: Period
    family: Family
    observable: bool
    unobservable_reason: str | None = None
    predicted: float | None = None
    actual: float | None = None
    absolute_error: float | None = None
    percent_error: float | None = None
    threshold: Threshold | None = None
    status: Status = "undefined"
    spread: SeedSpread | None = None

    @model_validator(mode="before")
    @classmethod
    def derive_status(cls, data):
        if not isinstance(data, dict):
            return data
        derived = dict(data)
        if not derived.get("observable", False):
            derived["status"] = "not_observable"
            return derived
        actual = derived.get("actual")
        percent = derived.get("percent_error")
        threshold = derived.get("threshold")
        if actual == 0 or percent is None:
            derived["status"] = "undefined"
            return derived
        if isinstance(threshold, Threshold):
            warn, fail = threshold.warn, threshold.fail
        elif isinstance(threshold, dict):
            warn, fail = threshold.get("warn"), threshold.get("fail")
        else:
            return derived
        magnitude = abs(float(percent))
        derived["status"] = (
            "pass" if magnitude < warn else "warn" if magnitude < fail else "fail"
        )
        return derived

    @model_validator(mode="after")
    def validate_derived_state(self) -> "MetricComparison":
        numeric = (self.predicted, self.actual, self.absolute_error, self.percent_error)
        if not self.observable:
            if self.status != "not_observable" or any(v is not None for v in numeric):
                raise ValueError("unobservable comparisons must have no numeric values")
            if not self.unobservable_reason:
                raise ValueError("unobservable comparisons require a reason")
        elif self.status == "not_observable":
            raise ValueError("observable comparisons cannot be not_observable")
        if self.actual == 0 and (
            self.percent_error is not None or self.status != "undefined"
        ):
            raise ValueError(
                "zero-actual comparisons must have undefined percent status"
            )
        return self


class SnapshotRef(FrozenModel):
    year: int
    filename: str
    sha256: str
    row_count: int = Field(ge=1)
    role: Literal["fit", "holdout"]


class BacktestProvenance(FrozenModel):
    snapshots: tuple[SnapshotRef, ...]
    source_digest: str
    pack_id: str
    pack_fingerprint: str
    promotion_basis: str
    level_basis: Literal["census_level_id", "compensation_band"]
    compensation_basis: str
    backtest_date: str
    tool_version: str


class Scorecard(FrozenModel):
    schema_version: str = "1.0.0"
    scorecard_fingerprint: str = ""
    split: SnapshotSplit
    seeds: tuple[int, ...]
    seed_runs: tuple[SeedRun, ...]
    thresholds: MetricThresholds
    overridden_thresholds: tuple[Family, ...] = ()
    comparisons: tuple[MetricComparison, ...]
    verdict: Literal["pass", "warn", "fail"] = "pass"
    verdict_summary: str = ""
    provenance: BacktestProvenance
    notes: str = ""

    @model_validator(mode="after")
    def derive_summary_and_fingerprint(self) -> "Scorecard":
        counts = {
            status: 0
            for status in ("pass", "warn", "fail", "undefined", "not_observable")
        }
        for comparison in self.comparisons:
            counts[comparison.status] += 1
        verdict = "fail" if counts["fail"] else "warn" if counts["warn"] else "pass"
        summary = ", ".join(
            f"{counts[status]} {status.replace('_', ' ')}"
            for status in ("pass", "warn", "fail", "undefined", "not_observable")
            if counts[status]
        )
        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "verdict_summary", summary)
        payload = self.model_dump(mode="json", exclude={"scorecard_fingerprint"})
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        object.__setattr__(
            self,
            "scorecard_fingerprint",
            hashlib.sha256(canonical.encode()).hexdigest(),
        )
        return self


@dataclass(frozen=True)
class MetricDefinition:
    identifier: str
    family: Family
    cumulative: CumulativeRule
    requires: str | None = None


METRIC_REGISTRY: tuple[MetricDefinition, ...] = (
    MetricDefinition("headcount.total", "headcount", "final"),
    MetricDefinition("headcount.by_level", "headcount", "final"),
    MetricDefinition("headcount.by_age_band", "headcount", "final"),
    MetricDefinition("headcount.by_tenure_band", "headcount", "final"),
    MetricDefinition("compensation.total", "compensation", "final"),
    MetricDefinition("compensation.average", "compensation", "final"),
    MetricDefinition("flows.terminations", "flows", "sum"),
    MetricDefinition("flows.hires", "flows", "sum"),
    MetricDefinition("flows.promotions", "flows", "sum", "level_coverage"),
    MetricDefinition("plan.participation_rate", "plan", "final", "enrollment"),
    MetricDefinition("plan.average_deferral_rate", "plan", "final", "deferral"),
    MetricDefinition("plan.employer_match_cost", "plan", "sum", "deferral"),
)


def metric_definition(metric: str) -> MetricDefinition:
    for definition in METRIC_REGISTRY:
        if metric == definition.identifier or metric.startswith(
            definition.identifier + "."
        ):
            return definition
    raise ValueError(f"Unknown backtest metric: {metric}")
