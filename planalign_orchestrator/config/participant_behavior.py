"""Run-global participant behavior configuration (epic #986, D5)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Rate = Annotated[float, Field(ge=0, le=1)]
AIPMode = Literal["automatic", "participant_elected"]


def validate_weights(weights: list[float]) -> None:
    """Require a probability distribution, within the documented tolerance."""
    if abs(sum(weights) - 1.0) > 1e-6:
        raise ValueError("weights/shares must sum to 1 (tolerance 1e-6)")


class EasyEnrollPackage(BaseModel):
    rate: float = Field(gt=0, le=1)
    share: Rate


class EasyEnrollSettings(BaseModel):
    enabled: bool = False
    channel_share: Rate = 0.35
    packages: list[EasyEnrollPackage] = Field(
        default_factory=lambda: [
            EasyEnrollPackage(rate=0.06, share=0.30),
            EasyEnrollPackage(rate=0.08, share=0.50),
            EasyEnrollPackage(rate=0.10, share=0.20),
        ],
        min_length=1,
    )
    aip_cap: Rate = 0.10

    @field_validator("packages")
    @classmethod
    def check_packages(
        cls, packages: list[EasyEnrollPackage]
    ) -> list[EasyEnrollPackage]:
        validate_weights([package.share for package in packages])
        return packages


class BelowDefaultTier(BaseModel):
    ae_default_max: Rate | None
    share: Rate


class BelowDefaultSettings(BaseModel):
    share_tiers: list[BelowDefaultTier] = Field(
        default_factory=lambda: [BelowDefaultTier(ae_default_max=None, share=0.0)],
        min_length=1,
    )
    step_weights: list[Rate] = Field(default_factory=lambda: [0.50, 0.30, 0.20])

    @field_validator("share_tiers")
    @classmethod
    def check_tiers(cls, tiers: list[BelowDefaultTier]) -> list[BelowDefaultTier]:
        bounds = [tier.ae_default_max for tier in tiers]
        if bounds.count(None) != 1 or bounds[-1] is not None:
            raise ValueError(
                "share_tiers must have exactly one open-ended (null) tier, last"
            )
        closed = [bound for bound in bounds if bound is not None]
        if any(left >= right for left, right in zip(closed, closed[1:])):
            raise ValueError("share_tiers must be ordered by ae_default_max ascending")
        return tiers

    @field_validator("step_weights")
    @classmethod
    def check_weights(cls, weights: list[float]) -> list[float]:
        validate_weights(weights)
        return weights


class DeferralChangeStep(BaseModel):
    pp: int = Field(gt=0, strict=True)
    weight: Rate


class DeferralChangeRates(BaseModel):
    increase_rate: Rate
    decrease_rate: Rate


class DeferralRateChangesSettings(BaseModel):
    enabled: bool = False
    in_aip: DeferralChangeRates = Field(
        default_factory=lambda: DeferralChangeRates(
            increase_rate=0.03, decrease_rate=0.15
        )
    )
    not_in_aip: DeferralChangeRates = Field(
        default_factory=lambda: DeferralChangeRates(
            increase_rate=0.25, decrease_rate=0.075
        )
    )
    increase_steps: list[DeferralChangeStep] = Field(
        default_factory=lambda: [
            DeferralChangeStep(pp=pp, weight=weight)
            for pp, weight in [
                (1, 0.15),
                (2, 0.20),
                (3, 0.15),
                (5, 0.20),
                (7, 0.15),
                (10, 0.15),
            ]
        ]
    )
    decrease_steps: list[DeferralChangeStep] = Field(
        default_factory=lambda: [
            DeferralChangeStep(pp=pp, weight=weight)
            for pp, weight in [(1, 0.15), (2, 0.25), (3, 0.20), (5, 0.20), (8, 0.20)]
        ]
    )
    aip_response_window_days: int = Field(default=90, ge=0, strict=True)
    aip_response_opts_out: bool = False
    stop_rate: Rate = 0.015
    restart_rate: Rate = 0.0

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
    participant_elected_signup_rate: Rate = 0.0
    effective_day: str | None = None
    increment_amount: Rate | None = None
    maximum_rate: Rate | None = None
    hire_date_cutoff: str | None = None
    require_active_enrollment: bool = True
    first_escalation_delay_years: int | None = Field(default=None, ge=0)


def escalation_settings(value: Any) -> DeferralAutoEscalationSettings:
    """Accept legacy callers that assign dictionaries after config loading."""
    return DeferralAutoEscalationSettings.model_validate(value)
