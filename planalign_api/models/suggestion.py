"""Pydantic models for termination rate suggestion API response."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class TerminationRateSuggestion(BaseModel):
    """User-facing termination rate suggestion with confidence and statistics."""

    scenario_id: str = Field(..., description="Scenario identifier")
    plan_design_id: str = Field(..., description="Benefit plan identifier")
    snapshot_date: str = Field(..., description="Census snapshot date (YYYY-MM-DD)")

    # Suggestion (user-facing)
    suggested_rate: Optional[Decimal] = Field(
        None,
        ge=0,
        lt=100,
        description="Suggested rate as decimal (0.0-99.9), null if error. NOT 100%.",
    )

    # Confidence & Details
    confidence: Optional[Literal["HIGH", "MEDIUM", "LOW"]] = Field(
        None,
        description="Confidence level based on sample size: HIGH (>100), MEDIUM (10-100), LOW (<10)",
    )

    sample_size: int = Field(
        default=0,
        ge=0,
        description="Total active employees used in calculation",
    )

    # Transparency
    error_message: Optional[str] = Field(
        None,
        description="User-friendly error message if calculation failed. Only set if suggested_rate is null.",
    )

    suggested_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when suggestion was generated",
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {Decimal: str, datetime: lambda v: v.isoformat()}

    @field_validator("suggested_rate", "confidence", mode="before")
    @classmethod
    def validate_rate_and_confidence(cls, v):
        """Handle conversion of string decimals to Decimal."""
        if isinstance(v, str) and v:
            try:
                return Decimal(v)
            except (ValueError, TypeError, ArithmeticError):
                return v
        return v

    @field_validator("error_message")
    @classmethod
    def validate_error_consistency(cls, v, info):
        """Ensure error_message is present iff suggested_rate is null."""
        # This validation is limited in Pydantic v2, but we document the constraint
        return v

    def model_post_init(self, __context):
        """Post-validation check: error_message iff suggested_rate is None."""
        if self.suggested_rate is None and self.error_message is None:
            raise ValueError("error_message must be set when suggested_rate is None")
        if self.suggested_rate is not None and self.error_message is not None:
            raise ValueError(
                "error_message must be null when suggested_rate is not None"
            )
