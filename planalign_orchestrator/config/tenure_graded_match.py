"""Tenure-graded multi-tier employer match configuration.

Feature 099: each tenure band carries its own ordered, cumulative list of
deferral-rate match tiers (not just one flat rate + one max-deferral cap).
Supersedes the single-tier `TenureMatchTier`/`tenure_match_tiers` shape on
`EmployerMatchSettings` (see specs/099-tenure-graded-match/).

Entities defined here (see specs/099-tenure-graded-match/data-model.md):
    - TenureBandMatchTier: a single cumulative deferral-rate step within a band.
    - TenureGradedMatchBand: a tenure range plus its ordered tier schedule.
    - migrate_legacy_tenure_based_config(): one-tier backward-compat shim.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from .workforce import validate_tier_contiguity


class TenureBandMatchTier(BaseModel):
    """A single cumulative deferral-rate step within a tenure band's match schedule.

    Uses [employee_min, employee_max) interval convention on deferral percentage,
    expressed as decimals (0.02 = 2%).
    """

    employee_min: float = Field(
        ge=0,
        le=1,
        description="Lower bound of deferral % covered by this tier (inclusive, decimal e.g. 0.02)",
    )
    employee_max: float = Field(
        ge=0,
        le=1,
        description="Upper bound of deferral % covered by this tier (exclusive, decimal e.g. 0.08)",
    )
    match_rate: float = Field(
        ge=0,
        le=2.0,
        description="Match rate applied to deferral within this tier (decimal, e.g. 1.00 = 100%)",
    )

    @model_validator(mode="after")
    def validate_range(self) -> "TenureBandMatchTier":
        if self.employee_max <= self.employee_min:
            raise ValueError(
                f"employee_max ({self.employee_max}) must be greater than employee_min ({self.employee_min})"
            )
        return self


class TenureGradedMatchBand(BaseModel):
    """A tenure range and its independent, ordered, cumulative tier schedule.

    Uses [min_years, max_years) interval convention. A single-tier band
    (one-element `tiers` list) is the backward-compatible representation of
    the superseded single-tier `TenureMatchTier` shape.
    """

    min_years: int = Field(ge=0, description="Lower bound of service years (inclusive)")
    max_years: Optional[int] = Field(
        default=None,
        description="Upper bound of service years (exclusive); null = unbounded",
    )
    tiers: List[TenureBandMatchTier] = Field(
        default_factory=list,
        description="Ordered, cumulative deferral-rate match tiers for this band",
    )

    @model_validator(mode="after")
    def validate_band(self) -> "TenureGradedMatchBand":
        if self.max_years is not None and self.max_years <= self.min_years:
            raise ValueError(
                f"max_years ({self.max_years}) must be greater than min_years ({self.min_years})"
            )
        if not self.tiers:
            raise ValueError("At least one tier is required per tenure-graded band")
        validate_tier_contiguity(
            [{"employee_min": t.employee_min, "employee_max": t.employee_max} for t in self.tiers],
            min_key="employee_min",
            max_key="employee_max",
            label="tenure-graded tier",
        )
        return self


def migrate_legacy_tenure_based_config(
    employer_match_status: str,
    tenure_match_tiers: List[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, Any]]]:
    """Convert a legacy single-tier `tenure_based` config into the new shape.

    Legacy `TenureMatchTier` entries (`min_years`, `max_years`, `match_rate`,
    `max_deferral_pct`, both percentages as whole numbers) become one-tier
    `TenureGradedMatchBand` dicts (decimal form), per the backward-compatibility
    contract in specs/099-tenure-graded-match/contracts/config-schema.md.

    Returns the input unchanged (status, []) when not in legacy tenure_based mode.
    """
    if employer_match_status != "tenure_based" or not tenure_match_tiers:
        return employer_match_status, []

    migrated_bands = [
        {
            "min_years": tier.get("min_years", 0),
            "max_years": tier.get("max_years"),
            "tiers": [
                {
                    "employee_min": 0.00,
                    "employee_max": tier.get("max_deferral_pct", 6) / 100.0,
                    "match_rate": tier.get("match_rate", 0) / 100.0,
                }
            ],
        }
        for tier in tenure_match_tiers
    ]
    return "tenure_graded", migrated_bands
