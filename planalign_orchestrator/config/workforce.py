"""Workforce, enrollment, eligibility, and employer match settings.

E073: Config Module Refactoring - workforce module.
E046: Tenure-based and points-based employer match modes.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class WorkforceSettings(BaseModel):
    """Workforce termination rate settings."""
    total_termination_rate: float = Field(default=0.12, ge=0, le=1)
    new_hire_termination_rate: float = Field(default=0.25, ge=0, le=1)


# =============================================================================
# Opt-Out Rate Settings
# =============================================================================

class OptOutRatesByAge(BaseModel):
    """Opt-out rates by age demographic."""
    young: float = Field(default=0.10, ge=0, le=1)
    mid_career: float = Field(default=0.07, ge=0, le=1)
    mature: float = Field(default=0.05, ge=0, le=1)
    senior: float = Field(default=0.03, ge=0, le=1)


class OptOutRatesByIncome(BaseModel):
    """Opt-out rate multipliers by income level."""
    low_income: float = Field(default=1.20, ge=0, le=5)
    moderate: float = Field(default=1.00, ge=0, le=5)
    high: float = Field(default=0.70, ge=0, le=5)
    executive: float = Field(default=0.50, ge=0, le=5)


class OptOutRatesSettings(BaseModel):
    """Combined opt-out rate settings."""
    by_age: OptOutRatesByAge = Field(default_factory=OptOutRatesByAge)
    by_income: OptOutRatesByIncome = Field(default_factory=OptOutRatesByIncome)


# =============================================================================
# Enrollment Settings
# =============================================================================

class AutoEnrollmentSettings(BaseModel):
    """Auto-enrollment configuration."""
    enabled: bool = True
    scope: Optional[str] = None
    hire_date_cutoff: Optional[str] = None
    window_days: int = 45
    default_deferral_rate: float = Field(default=0.06, ge=0, le=1)
    opt_out_grace_period: int = 30
    opt_out_rates: OptOutRatesSettings = Field(default_factory=OptOutRatesSettings)


class ProactiveEnrollmentSettings(BaseModel):
    """Proactive enrollment configuration."""
    enabled: bool = True

    class TimingWindow(BaseModel):
        min_days: int = 7
        max_days: int = 35

    timing_window: TimingWindow = Field(default_factory=TimingWindow)
    probability_by_demographics: Dict[str, float] = Field(default_factory=dict)


class EnrollmentTimingSettings(BaseModel):
    """Enrollment timing configuration."""
    business_day_adjustment: bool = True


class EnrollmentSettings(BaseModel):
    """Combined enrollment settings."""
    auto_enrollment: AutoEnrollmentSettings = Field(default_factory=AutoEnrollmentSettings)
    proactive_enrollment: ProactiveEnrollmentSettings = Field(default_factory=ProactiveEnrollmentSettings)
    timing: EnrollmentTimingSettings = Field(default_factory=EnrollmentTimingSettings)


# =============================================================================
# Eligibility Settings
# =============================================================================

class EligibilitySettings(BaseModel):
    """Basic eligibility settings."""
    waiting_period_days: Optional[int] = None


class PlanEligibilitySettings(BaseModel):
    """Plan eligibility settings."""
    minimum_age: Optional[int] = None


# =============================================================================
# Employer Match Settings
# =============================================================================

class EmployerMatchEligibilitySettings(BaseModel):
    """Employer match eligibility requirements configuration."""
    minimum_tenure_years: int = Field(default=0, ge=0, description="Minimum years of service")
    require_active_at_year_end: bool = Field(default=True, description="Must be active on Dec 31")
    minimum_hours_annual: int = Field(default=1000, ge=0, description="Minimum hours worked annually")
    allow_new_hires: bool = Field(default=True, description="Allow new hires to qualify")
    allow_terminated_new_hires: bool = Field(default=False, description="Allow new-hire terminations to qualify")
    allow_experienced_terminations: bool = Field(default=False, description="Allow experienced terminations to qualify")

    @model_validator(mode='before')
    @classmethod
    def resolve_allow_new_hires_default(cls, data: Any) -> Any:
        """Conditionally default allow_new_hires based on minimum_tenure_years.

        When allow_new_hires is not explicitly provided:
        - minimum_tenure_years == 0 → allow_new_hires = True (backward compat)
        - minimum_tenure_years > 0  → allow_new_hires = False (enforce tenure)

        When allow_new_hires is explicitly True with minimum_tenure_years > 0,
        emits a warning about contradictory configuration.
        """
        if isinstance(data, dict):
            min_tenure = data.get('minimum_tenure_years', 0)
            if 'allow_new_hires' not in data:
                data['allow_new_hires'] = (min_tenure == 0)
            elif data['allow_new_hires'] is True and min_tenure > 0:
                warnings.warn(
                    f"Contradictory eligibility configuration: allow_new_hires=True "
                    f"with minimum_tenure_years={min_tenure}. New hires (tenure=0) "
                    f"will bypass the tenure requirement. Set allow_new_hires=False "
                    f"or minimum_tenure_years=0 to resolve.",
                    UserWarning,
                    stacklevel=2,
                )
        return data


def validate_tier_contiguity(
    tiers: list,
    *,
    min_key: str = "min",
    max_key: str = "max",
    label: str = "tier",
) -> None:
    """Validate that a list of tier dicts is contiguous with no gaps or overlaps.

    Args:
        tiers: List of dicts, each having min_key and max_key fields.
        min_key: Dict key for the lower bound (inclusive).
        max_key: Dict key for the upper bound (exclusive, or None for unbounded).
        label: Human-readable name for error messages (e.g., 'tenure', 'points').

    Raises:
        ValueError: If tiers have gaps, overlaps, or don't start at 0.
    """
    if not tiers:
        return

    # Sort by min value
    sorted_tiers = sorted(tiers, key=lambda t: t[min_key])

    # First tier must start at 0
    if sorted_tiers[0][min_key] != 0:
        raise ValueError(
            f"{label} tiers must start at 0, but first tier starts at {sorted_tiers[0][min_key]}"
        )

    # Check contiguity between consecutive tiers
    for i in range(len(sorted_tiers) - 1):
        current_max = sorted_tiers[i][max_key]
        next_min = sorted_tiers[i + 1][min_key]

        if current_max is None:
            raise ValueError(
                f"{label} tier {i + 1} has unbounded max (null) but is not the last tier"
            )

        if current_max < next_min:
            raise ValueError(
                f"Gap detected between {label} tier {i + 1} "
                f"(max={current_max}) and tier {i + 2} (min={next_min})"
            )
        if current_max > next_min:
            raise ValueError(
                f"Overlap detected between {label} tier {i + 1} "
                f"(max={current_max}) and tier {i + 2} (min={next_min})"
            )


# E046: Tenure-based match tier configuration
class TenureMatchTier(BaseModel):
    """A match rate bracket based on employee years of service.

    Uses [min_years, max_years) interval convention.
    """

    min_years: int = Field(ge=0, description="Lower bound of service years (inclusive)")
    max_years: Optional[int] = Field(
        default=None, description="Upper bound of service years (exclusive); null = unbounded"
    )
    match_rate: float = Field(
        ge=0, le=100, description="Match rate as percentage (e.g., 50 = 50%)"
    )
    max_deferral_pct: float = Field(
        ge=0, le=100, description="Maximum employee deferral % eligible for match (e.g., 6 = 6%)"
    )

    @model_validator(mode="after")
    def validate_range(self) -> "TenureMatchTier":
        if self.max_years is not None and self.max_years <= self.min_years:
            raise ValueError(
                f"max_years ({self.max_years}) must be greater than min_years ({self.min_years})"
            )
        return self


# E046: Points-based match tier configuration
class PointsMatchTier(BaseModel):
    """A match rate bracket based on employee age+tenure points.

    Points = FLOOR(age) + FLOOR(tenure). Uses [min_points, max_points) interval convention.
    """

    min_points: int = Field(ge=0, description="Lower bound of points (inclusive)")
    max_points: Optional[int] = Field(
        default=None, description="Upper bound of points (exclusive); null = unbounded"
    )
    match_rate: float = Field(
        ge=0, le=100, description="Match rate as percentage (e.g., 50 = 50%)"
    )
    max_deferral_pct: float = Field(
        ge=0, le=100, description="Maximum employee deferral % eligible for match (e.g., 6 = 6%)"
    )

    @model_validator(mode="after")
    def validate_range(self) -> "PointsMatchTier":
        if self.max_points is not None and self.max_points <= self.min_points:
            raise ValueError(
                f"max_points ({self.max_points}) must be greater than min_points ({self.min_points})"
            )
        return self


_VALID_MATCH_STATUSES = ("deferral_based", "graded_by_service", "tenure_based", "points_based")


class EmployerMatchSettings(BaseModel):
    """Employer match configuration with eligibility requirements."""
    active_formula: str = Field(default="simple_match", description="Active match formula name")
    apply_eligibility: bool = Field(default=False, description="Apply eligibility filtering to match calculations")
    eligibility: EmployerMatchEligibilitySettings = Field(default_factory=EmployerMatchEligibilitySettings)
    formulas: Optional[Dict[str, Any]] = Field(default=None, description="Match formula definitions")
    # E046: New match mode fields
    employer_match_status: str = Field(
        default="deferral_based",
        description="Match calculation mode: deferral_based, graded_by_service, tenure_based, or points_based",
    )
    tenure_match_tiers: List[TenureMatchTier] = Field(
        default_factory=list, description="Tenure-based match tiers (used when status = tenure_based)"
    )
    points_match_tiers: List[PointsMatchTier] = Field(
        default_factory=list, description="Points-based match tiers (used when status = points_based)"
    )

    @model_validator(mode="after")
    def validate_match_mode(self) -> "EmployerMatchSettings":
        # Validate employer_match_status is a recognized value
        if self.employer_match_status not in _VALID_MATCH_STATUSES:
            raise ValueError(
                f"Invalid employer_match_status '{self.employer_match_status}'. "
                f"Valid options: {', '.join(_VALID_MATCH_STATUSES)}"
            )

        # Validate tenure tiers when tenure_based mode is active
        if self.employer_match_status == "tenure_based":
            if not self.tenure_match_tiers:
                raise ValueError(
                    "At least one tenure tier is required when employer_match_status = 'tenure_based'"
                )
            validate_tier_contiguity(
                [{"min": t.min_years, "max": t.max_years} for t in self.tenure_match_tiers],
                min_key="min",
                max_key="max",
                label="tenure",
            )

        # Validate points tiers when points_based mode is active
        if self.employer_match_status == "points_based":
            if not self.points_match_tiers:
                raise ValueError(
                    "At least one points tier is required when employer_match_status = 'points_based'"
                )
            validate_tier_contiguity(
                [{"min": t.min_points, "max": t.max_points} for t in self.points_match_tiers],
                min_key="min",
                max_key="max",
                label="points",
            )

        return self
