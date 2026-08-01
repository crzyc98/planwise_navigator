"""Result types shared by every estimator and consumed by the pack and report."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from planalign_fit.smoothing import CredibilityResult


class PromotionBasis(str, Enum):
    """How a fit arrived at its promotion rate (#511).

    A promotion is a move to a higher job level. When the census supplies the
    level that is directly observable; when it does not, level is derived from
    compensation banding and *any* band-crossing raise reads as a promotion, so
    the rate has to be recovered from the shape of the raise distribution
    instead. Where even that cannot separate promotions from ordinary raises,
    the honest answer is no rate at all.
    """

    MEASURED = "measured"
    ESTIMATED = "estimated"
    NOT_FITTED = "not_fitted"


@dataclass(frozen=True)
class LevelSeparation:
    """One job level's verdict on the estimated path.

    ``separated`` is the question "can promotions be told apart from ordinary
    raises at this level?" — not "were there promotions?". A level that fails
    keeps its configured default rate and says why.
    """

    level_id: int
    separated: bool
    exposure: float
    reason: str = ""
    estimated_rate: Optional[float] = None
    ordinary_location: Optional[float] = None
    promotion_location: Optional[float] = None
    standardized_distance: Optional[float] = None
    bic_improvement: Optional[float] = None
    converged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_id": self.level_id,
            "separated": self.separated,
            "exposure": self.exposure,
            "reason": self.reason,
            "estimated_rate": self.estimated_rate,
            "ordinary_location": self.ordinary_location,
            "promotion_location": self.promotion_location,
            "standardized_distance": self.standardized_distance,
            "bic_improvement": self.bic_improvement,
            "converged": self.converged,
        }


@dataclass(frozen=True)
class PromotionClassification:
    """Which basis produced this fit's promotion rate, and the evidence for it.

    One instance per fit. Threaded through the report, the pack manifest, and
    the ``param_pack`` provenance block so a run months later can still be
    asked whether its promotion hazard was fitted or defaulted.
    """

    basis: PromotionBasis
    level_coverage: float
    level_coverage_threshold: float
    exposure_gate: float
    reason: str
    separated_exposure_share: Optional[float] = None
    levels: list[LevelSeparation] = field(default_factory=list)

    @property
    def unseparated_levels(self) -> list[int]:
        return [level.level_id for level in self.levels if not level.separated]

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis.value,
            "level_coverage": self.level_coverage,
            "level_coverage_threshold": self.level_coverage_threshold,
            "exposure_gate": self.exposure_gate,
            "reason": self.reason,
            "separated_exposure_share": self.separated_exposure_share,
            "levels": [level.to_dict() for level in self.levels],
        }


@dataclass(frozen=True)
class FittedValue:
    """One fitted number, with the evidence and the prior it moved from."""

    name: str
    value: float
    prior: float
    exposure: float
    events: float
    observed: Optional[float]
    credibility: float
    basis: str
    note: str

    @classmethod
    def from_credibility(cls, name: str, result: CredibilityResult) -> "FittedValue":
        return cls(
            name=name,
            value=result.value,
            prior=result.prior,
            exposure=result.exposure,
            events=result.events,
            observed=result.observed,
            credibility=result.credibility,
            basis=result.basis,
            note=result.note(),
        )

    @property
    def moved_pct(self) -> Optional[float]:
        if self.prior == 0:
            return None
        return self.value / self.prior - 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "prior": self.prior,
            "observed": self.observed,
            "exposure": self.exposure,
            "events": self.events,
            "credibility": self.credibility,
            "basis": self.basis,
            "note": self.note,
        }


@dataclass(frozen=True)
class Unfittable:
    """A parameter the supplied data cannot speak to. Defaults are retained."""

    name: str
    reason: str
    default_used: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reason": self.reason,
            "default_used": self.default_used,
        }


@dataclass(frozen=True)
class HazardFit:
    """A fitted multiplicative hazard: base x age mult x tenure mult x level factor."""

    kind: str
    base_rate: FittedValue
    age_multipliers: dict[str, FittedValue]
    tenure_multipliers: dict[str, FittedValue]
    level_constants: dict[str, float]
    total_events: float
    total_exposure: float
    converged: bool
    iterations: int

    @property
    def observed_overall_rate(self) -> Optional[float]:
        if self.total_exposure <= 0:
            return None
        return self.total_events / self.total_exposure

    def values(self) -> list[FittedValue]:
        return [
            self.base_rate,
            *self.age_multipliers.values(),
            *self.tenure_multipliers.values(),
        ]


@dataclass(frozen=True)
class CellObservation:
    """One age x tenure x level cell's raw counts, for the report's evidence table."""

    age_band: str
    tenure_band: str
    level_id: int
    exposure: float
    events: float

    @property
    def observed_rate(self) -> Optional[float]:
        if self.exposure <= 0:
            return None
        return self.events / self.exposure


@dataclass
class FitResult:
    """Everything one ``planalign fit`` run produced.

    The three payload groups map onto the three things a parameter pack ships:
    hazard seed CSVs (``termination``/``promotion``), the other seed CSVs
    (``merit_by_level``, ``deferral_rates``), and the config YAML fragment
    (``config_overrides``, keyed by dotted config path).
    """

    termination: Optional[HazardFit] = None
    # ``None`` means the promotion hazard could not be fitted at all; see
    # ``promotion_classification`` for which of the three states applied.
    promotion: Optional[HazardFit] = None
    promotion_classification: Optional[PromotionClassification] = None
    termination_cells: list[CellObservation] = field(default_factory=list)
    promotion_cells: list[CellObservation] = field(default_factory=list)
    merit_by_level: dict[int, FittedValue] = field(default_factory=dict)
    deferral_rates: dict[tuple[str, str], FittedValue] = field(default_factory=dict)
    config_overrides: dict[str, FittedValue] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    unfittable: list[Unfittable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def all_fitted(self) -> list[FittedValue]:
        values: list[FittedValue] = []
        for hazard in (self.termination, self.promotion):
            if hazard is not None:
                values.extend(hazard.values())
        values.extend(self.merit_by_level.values())
        values.extend(self.deferral_rates.values())
        values.extend(self.config_overrides.values())
        return values

    @property
    def thin_cell_count(self) -> int:
        return sum(1 for v in self.all_fitted() if v.basis in ("pooled", "prior"))
