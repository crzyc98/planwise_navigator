"""Run-global participant behavior configuration (epic #986, D5)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

Rate = Annotated[float, Field(ge=0, le=1)]
AIPMode = Literal["automatic", "participant_elected"]


def validate_weights(weights: list[float]) -> None:
    """Require a probability distribution, within the documented tolerance."""
    if abs(sum(weights) - 1.0) > 1e-6:
        raise ValueError("weights/shares must sum to 1 (tolerance 1e-6)")


class EasyEnrollPackage(BaseModel):
    rate: float = Field(
        gt=0, le=1, description="Decimal 0–1 (0.06 = 6%) of pay deferred."
    )
    share: Rate = Field(
        description="Package share, decimal 0–1; package shares must sum to 1 (±1e-6)."
    )


class EasyEnrollSettings(BaseModel):
    enabled: bool = True
    channel_share_without_auto_enrollment: Rate = 0.45
    channel_share_with_auto_enrollment: Rate = 0.57
    packages: list[EasyEnrollPackage] = Field(
        default_factory=lambda: [
            EasyEnrollPackage(rate=0.06, share=0.30),
            EasyEnrollPackage(rate=0.08, share=0.50),
            EasyEnrollPackage(rate=0.10, share=0.20),
        ],
        min_length=1,
    )
    escalation_cap: Rate = 0.10

    @field_validator("packages")
    @classmethod
    def check_packages(
        cls, packages: list[EasyEnrollPackage]
    ) -> list[EasyEnrollPackage]:
        validate_weights([package.share for package in packages])
        return packages


class BelowDefaultTier(BaseModel):
    max_auto_enroll_default_rate: Rate | None = Field(
        description="Inclusive auto-enrollment default rate ceiling, decimal 0–1 (0.06 = 6%); null is the final open-ended tier."
    )
    share: Rate = Field(
        description="Share of enrollees choosing a rate below the default in this tier, decimal 0–1; tier shares are independent and need not sum to 1."
    )


class DeferralChangeStep(BaseModel):
    pp: int = Field(
        gt=0,
        strict=True,
        description="Whole percentage points; 1 means a one-percentage-point change.",
    )
    weight: Rate = Field(
        description="Step probability weight, decimal 0–1; list weights must sum to 1 (±1e-6)."
    )


class DeferralChangeRates(BaseModel):
    increase_probability: Rate
    decrease_probability: Rate

    @model_validator(mode="after")
    def check_total_probability(self) -> "DeferralChangeRates":
        if self.increase_probability + self.decrease_probability > 1.0:
            raise ValueError(
                "increase and decrease probabilities must sum to at most 1"
            )
        return self


class DeferralChangeMultiplierBand(BaseModel):
    min: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Inclusive lower bound: age/tenure in years or annual compensation in dollars. The final band is open-ended.",
    )
    multiplier: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Non-negative probability multiplier; 1 preserves the base probability.",
    )


def validate_multiplier_bands(
    bands: list[DeferralChangeMultiplierBand],
) -> list[DeferralChangeMultiplierBand]:
    """Require complete, ordered lower-bound coverage for demographic lookup."""
    if not bands or bands[0].min != 0:
        raise ValueError("multiplier bands must start at min 0")
    if any(left.min >= right.min for left, right in zip(bands, bands[1:])):
        raise ValueError("multiplier band min values must be strictly ascending")
    return bands


DeferralChangeMultiplierBands = Annotated[
    list[DeferralChangeMultiplierBand],
    Field(min_length=1),
    AfterValidator(validate_multiplier_bands),
]


class BelowDefaultMultipliers(BaseModel):
    age: DeferralChangeMultiplierBands = Field(
        default_factory=lambda: [
            DeferralChangeMultiplierBand(min=lower, multiplier=factor)
            for lower, factor in [
                (0, 1.4),
                (30, 1.1),
                (40, 0.9),
                (50, 0.75),
                (60, 0.65),
            ]
        ]
    )
    income: DeferralChangeMultiplierBands = Field(
        default_factory=lambda: [
            DeferralChangeMultiplierBand(min=lower, multiplier=factor)
            for lower, factor in [
                (0, 1.6),
                (40000, 1.2),
                (60000, 1.0),
                (100000, 0.7),
                (150000, 0.5),
            ]
        ]
    )


class BelowDefaultSettings(BaseModel):
    multipliers: BelowDefaultMultipliers = Field(
        default_factory=BelowDefaultMultipliers
    )
    share_tiers: list[BelowDefaultTier] = Field(
        default_factory=lambda: [
            BelowDefaultTier(max_auto_enroll_default_rate=0.03, share=0.10),
            BelowDefaultTier(max_auto_enroll_default_rate=None, share=0.15),
        ],
        min_length=1,
    )
    steps: list[DeferralChangeStep] = Field(
        default_factory=lambda: [
            DeferralChangeStep(pp=pp, weight=weight)
            for pp, weight in [(1, 0.50), (2, 0.30), (3, 0.20)]
        ]
    )

    @field_validator("share_tiers")
    @classmethod
    def check_tiers(cls, tiers: list[BelowDefaultTier]) -> list[BelowDefaultTier]:
        bounds = [tier.max_auto_enroll_default_rate for tier in tiers]
        if bounds.count(None) != 1 or bounds[-1] is not None:
            raise ValueError(
                "share_tiers must have exactly one open-ended (null) tier, last"
            )
        closed = [bound for bound in bounds if bound is not None]
        if any(left >= right for left, right in zip(closed, closed[1:])):
            raise ValueError(
                "share_tiers must be ordered by max_auto_enroll_default_rate ascending"
            )
        return tiers

    @field_validator("steps")
    @classmethod
    def check_steps(cls, steps: list[DeferralChangeStep]) -> list[DeferralChangeStep]:
        validate_weights([step.weight for step in steps])
        return steps


def neutral_multiplier_bands() -> list[DeferralChangeMultiplierBand]:
    return [DeferralChangeMultiplierBand(min=0, multiplier=1.0)]


class DeferralChangeDirectionMultipliers(BaseModel):
    age: DeferralChangeMultiplierBands = Field(default_factory=neutral_multiplier_bands)
    income: DeferralChangeMultiplierBands = Field(
        default_factory=neutral_multiplier_bands
    )
    tenure: DeferralChangeMultiplierBands = Field(
        default_factory=neutral_multiplier_bands
    )


class DeferralChangeIncreaseMultipliers(DeferralChangeDirectionMultipliers):
    age: DeferralChangeMultiplierBands = Field(
        default_factory=lambda: [
            DeferralChangeMultiplierBand(min=lower, multiplier=factor)
            for lower, factor in [
                (0, 0.8),
                (30, 0.95),
                (40, 1.05),
                (50, 1.25),
                (60, 1.3),
                (70, 0.8),
            ]
        ]
    )
    income: DeferralChangeMultiplierBands = Field(
        default_factory=lambda: [
            DeferralChangeMultiplierBand(min=lower, multiplier=factor)
            for lower, factor in [
                (0, 0.5),
                (25000, 0.65),
                (50000, 0.75),
                (60000, 0.9),
                (75000, 1.0),
                (100000, 1.15),
                (125000, 1.2),
                (150000, 1.35),
                (200000, 1.3),
                (250000, 1.2),
            ]
        ]
    )
    tenure: DeferralChangeMultiplierBands = Field(
        default_factory=lambda: [
            DeferralChangeMultiplierBand(min=lower, multiplier=factor)
            for lower, factor in [
                (0, 1.05),
                (2, 0.9),
                (5, 0.95),
                (10, 1.1),
                (15, 1.15),
                (20, 1.2),
                (25, 1.25),
                (30, 1.15),
            ]
        ]
    )


class DeferralChangeDecreaseMultipliers(DeferralChangeDirectionMultipliers):
    age: DeferralChangeMultiplierBands = Field(
        default_factory=lambda: [
            DeferralChangeMultiplierBand(min=lower, multiplier=factor)
            for lower, factor in [
                (0, 0.95),
                (30, 1.1),
                (40, 1.0),
                (50, 0.85),
                (60, 0.75),
                (70, 0.5),
            ]
        ]
    )
    income: DeferralChangeMultiplierBands = Field(
        default_factory=lambda: [
            DeferralChangeMultiplierBand(min=lower, multiplier=factor)
            for lower, factor in [
                (0, 0.5),
                (25000, 0.65),
                (40000, 0.6),
                (50000, 0.75),
                (60000, 0.85),
                (75000, 0.95),
                (100000, 1.05),
                (125000, 1.25),
                (150000, 1.4),
                (200000, 1.55),
                (250000, 1.25),
            ]
        ]
    )
    tenure: DeferralChangeMultiplierBands = Field(
        default_factory=lambda: [
            DeferralChangeMultiplierBand(min=lower, multiplier=factor)
            for lower, factor in [
                (0, 0.9),
                (2, 0.95),
                (3, 1.05),
                (4, 1.1),
                (5, 1.05),
                (15, 1.0),
                (20, 0.9),
                (25, 0.85),
                (30, 0.75),
            ]
        ]
    )


class DeferralChangeMultipliers(BaseModel):
    increase: DeferralChangeIncreaseMultipliers = Field(
        default_factory=DeferralChangeIncreaseMultipliers
    )
    decrease: DeferralChangeDecreaseMultipliers = Field(
        default_factory=DeferralChangeDecreaseMultipliers
    )


class DeferralRateChangesSettings(BaseModel):
    enabled: bool = True
    multipliers: DeferralChangeMultipliers = Field(
        default_factory=DeferralChangeMultipliers
    )
    with_escalation: DeferralChangeRates = Field(
        default_factory=lambda: DeferralChangeRates(
            increase_probability=0.085, decrease_probability=0.082
        )
    )
    without_escalation: DeferralChangeRates = Field(
        default_factory=lambda: DeferralChangeRates(
            increase_probability=0.085, decrease_probability=0.082
        )
    )
    increase_steps: list[DeferralChangeStep] = Field(
        default_factory=lambda: [
            DeferralChangeStep(pp=pp, weight=weight)
            for pp, weight in [
                (1, 0.1),
                (2, 0.1),
                (3, 0.15),
                (5, 0.2),
                (7, 0.2),
                (10, 0.25),
            ]
        ]
    )
    decrease_steps: list[DeferralChangeStep] = Field(
        default_factory=lambda: [
            DeferralChangeStep(pp=pp, weight=weight)
            for pp, weight in [
                (1, 0.1),
                (2, 0.15),
                (3, 0.15),
                (5, 0.2),
                (8, 0.2),
                (12, 0.2),
            ]
        ]
    )
    post_escalation_decrease_window_days: int = Field(default=90, ge=0, strict=True)
    post_escalation_decrease_leaves_escalation: bool = False
    stop_probability: Rate = 0.015
    restart_probability: Rate = 0.40

    @model_validator(mode="after")
    def check_stop_probability_mass(self) -> "DeferralRateChangesSettings":
        if self.enabled:
            for rates in (self.with_escalation, self.without_escalation):
                if (
                    rates.increase_probability
                    + rates.decrease_probability
                    + self.stop_probability
                    > 1.0
                ):
                    raise ValueError(
                        "increase, decrease and stop probabilities must sum to at most 1"
                    )
        return self

    @field_validator("increase_steps", "decrease_steps")
    @classmethod
    def check_steps(cls, steps: list[DeferralChangeStep]) -> list[DeferralChangeStep]:
        validate_weights([step.weight for step in steps])
        return steps


class DeferralAutoEscalationSettings(BaseModel):
    """Typed legacy fields; only explicitly supplied legacy keys are exported."""

    model_config = ConfigDict(validate_assignment=True)

    enabled: bool = True
    mode: AIPMode = "automatic"
    participant_elected_signup_probability: Rate = 0.01
    effective_day: str | None = None
    increment_amount: Rate | None = None
    maximum_rate: Rate | None = None
    hire_date_cutoff: str | None = None
    require_active_enrollment: bool = True
    first_escalation_delay_years: int | None = Field(default=None, ge=0)

    @field_validator("effective_day", "hire_date_cutoff", mode="before")
    @classmethod
    def normalize_dates(cls, value: Any) -> Any:
        """Preserve ISO strings for YAML's unquoted date/timestamp values."""
        return value.isoformat() if isinstance(value, (date, datetime)) else value


def escalation_settings(value: Any) -> DeferralAutoEscalationSettings:
    """Accept legacy callers that assign dictionaries after config loading."""
    return DeferralAutoEscalationSettings.model_validate(value)
