"""Pydantic models for promotion hazard configuration management.

This module defines the data models for promotion hazard parameters
(base rate, level dampener, age multipliers, tenure multipliers)
used by the PlanAlign simulation engine.
"""

from typing import List

from pydantic import Field
from .base import APIModel


class PromotionHazardBase(APIModel):
    """Global promotion hazard parameters."""

    base_rate: float = Field(
        ..., ge=0, le=1, description="Base promotion rate (0.0-1.0)"
    )
    level_dampener_factor: float = Field(
        ..., ge=0, le=1, description="Level dampening factor (0.0-1.0)"
    )


class PromotionHazardAgeMultiplier(APIModel):
    """Per-age-band promotion hazard multiplier."""

    age_band: str = Field(..., description="Age band label (read-only)")
    multiplier: float = Field(..., ge=0, description="Promotion hazard multiplier")


class PromotionHazardTenureMultiplier(APIModel):
    """Per-tenure-band promotion hazard multiplier."""

    tenure_band: str = Field(..., description="Tenure band label (read-only)")
    multiplier: float = Field(..., ge=0, description="Promotion hazard multiplier")


class PromotionHazardConfig(APIModel):
    """Container for all promotion hazard configuration."""

    base: PromotionHazardBase
    age_multipliers: List[PromotionHazardAgeMultiplier]
    tenure_multipliers: List[PromotionHazardTenureMultiplier]


class PromotionHazardSaveResponse(APIModel):
    """Response after saving promotion hazard configuration."""

    success: bool
    errors: List[str] = Field(default_factory=list)
    message: str
