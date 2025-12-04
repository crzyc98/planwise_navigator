"""Workforce, enrollment, eligibility, and employer match settings.

E073: Config Module Refactoring - workforce module.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


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


class EmployerMatchSettings(BaseModel):
    """Employer match configuration with eligibility requirements."""
    active_formula: str = Field(default="simple_match", description="Active match formula name")
    apply_eligibility: bool = Field(default=False, description="Apply eligibility filtering to match calculations")
    eligibility: EmployerMatchEligibilitySettings = Field(default_factory=EmployerMatchEligibilitySettings)
    formulas: Optional[Dict[str, Any]] = Field(default=None, description="Match formula definitions")
