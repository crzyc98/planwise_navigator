"""Simulation and compensation settings models.

E073: Config Module Refactoring - simulation module.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NewHireSettings(BaseModel):
    """Starting-pay assumptions in first-simulation-year dollars."""

    model_config = ConfigDict(extra="allow")

    salary_growth_rate: float = Field(default=0.0, ge=0.0, le=0.25)
    # Level existing staff on job_level_compensation too, so one scale covers both.
    shared_pay_scale: bool = False
    # Hire pay as a share of start-year existing pay at the same level; 1.0 = 100%.
    hire_pay_ratio: Optional[float] = Field(default=None, ge=0.5, le=1.5)

    @model_validator(mode="after")
    def _shared_scale_needs_ranges(self) -> "NewHireSettings":
        ranges = (self.model_extra or {}).get("job_level_compensation")
        if self.shared_pay_scale and not ranges:
            raise ValueError("shared_pay_scale requires job_level_compensation")
        if self.hire_pay_ratio is not None and not self.shared_pay_scale:
            raise ValueError("hire_pay_ratio requires shared_pay_scale")
        return self


class SimulationSettings(BaseModel):
    """Core simulation parameters."""

    start_year: int = Field(..., ge=2000)
    end_year: int = Field(..., ge=2000)
    random_seed: int = Field(default=42)
    target_growth_rate: float = Field(default=0.03, ge=-1, le=1)


class PromotionCompensationSettings(BaseModel):
    """Promotion compensation increase configuration."""

    base_increase_pct: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Base (midpoint) promotion increase percentage",
    )
    distribution_range: float = Field(
        default=0.05,
        ge=0.0,
        le=0.20,
        description="Distribution range around base (+/- range)",
    )
    max_cap_pct: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Maximum promotion increase percentage",
    )
    max_cap_amount: int = Field(
        default=500000, ge=0, description="Maximum promotion increase amount in dollars"
    )
    distribution_type: str = Field(
        default="uniform",
        description="Distribution type: uniform, normal, deterministic",
    )
    level_overrides: Optional[Dict[int, float]] = Field(
        default=None, description="Level-specific base increase overrides"
    )

    class Advanced(BaseModel):
        """Advanced promotion compensation configuration."""

        normal_std_dev: float = Field(
            default=0.02,
            ge=0.0,
            le=0.20,
            description="Standard deviation for normal distribution",
        )
        market_adjustments: Optional[Dict[str, float]] = Field(
            default=None, description="Market adjustment factors"
        )

    advanced: Advanced = Field(
        default_factory=lambda: PromotionCompensationSettings.Advanced()
    )


class CompensationSettings(BaseModel):
    """Compensation settings with support for both decimal and percent formats.

    The UI saves values with _percent suffix (e.g., cola_rate_percent: 2 means 2%).
    The model normalizes these to decimal format internally (e.g., cola_rate: 0.02).
    """

    model_config = ConfigDict(extra="allow")

    cola_rate: float = Field(default=0.02, ge=0, le=1)
    merit_budget: float = Field(default=0.035, ge=0, le=1)
    # One annual raise budget, as total spend on eligible pay. When set it
    # replaces merit and COLA but keeps their shape, and scales rates to the
    # budget. Unset keeps both exactly as configured.
    raise_budget: Optional[float] = Field(default=None, ge=0, le=1)
    # Share of eligible employees who receive a raise. The budget is total
    # spend, so a lower share raises each recipient's percentage.
    raise_coverage: float = Field(default=1.0, gt=0, le=1)
    # Part of a budget everyone receives equally, as COLA did. Taken from merit
    # and COLA when the budget is set, so level differences match today's.
    raise_flat_share: Optional[float] = Field(default=None, ge=0, le=1)
    promotion_increase: float = Field(default=0.125, ge=0, le=1)
    promotion_budget: float = Field(default=0.015, ge=0, le=1)
    promotion_distribution_range: float = Field(default=0.05, ge=0, le=1)
    promotion_rate_multiplier: float = Field(default=1.0, ge=0, le=5)
    promotion_compensation: PromotionCompensationSettings = Field(
        default_factory=PromotionCompensationSettings
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_percent_fields(cls, data: Any) -> Any:
        """Convert _percent suffix fields to decimal format."""
        if not isinstance(data, dict):
            return data

        percent_fields = {
            "cola_rate_percent": "cola_rate",
            "merit_budget_percent": "merit_budget",
            "raise_budget_percent": "raise_budget",
            "raise_coverage_percent": "raise_coverage",
            "promotion_increase_percent": "promotion_increase",
            "promotion_budget_percent": "promotion_budget",
            "promotion_distribution_range_percent": "promotion_distribution_range",
        }

        for percent_key, decimal_key in percent_fields.items():
            if data.get(percent_key) is not None and decimal_key not in data:
                data[decimal_key] = data[percent_key] / 100.0

        return data

    @model_validator(mode="after")
    def apply_raise_budget(self) -> "CompensationSettings":
        """Fold a set raise budget into merit so one input drives every raise."""
        if self.raise_budget is not None:
            if self.raise_flat_share is None:
                total = self.merit_budget + self.cola_rate
                self.raise_flat_share = self.cola_rate / total if total else 0.0
            self.merit_budget = self.raise_budget
            self.cola_rate = 0.0
        return self
