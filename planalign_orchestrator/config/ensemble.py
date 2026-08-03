"""Typed configuration for seed-ensemble risk thresholds."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


_FREEZABLE_SUBSYSTEMS = frozenset({"termination", "hiring", "promotion"})


class EnsembleThresholdSettings(BaseModel):
    """One configured metric threshold evaluated after ensemble aggregation."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    metric: str = Field(min_length=1)
    value: float
    label: str | None = None

    @field_validator("metric")
    @classmethod
    def require_nonblank_metric(cls, value: str) -> str:
        """Normalize metric names while rejecting empty threshold targets."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("metric must not be blank")
        return normalized


class EnsembleSettings(BaseModel):
    """Optional ensemble settings that are safe to validate during config load."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thresholds: tuple[EnsembleThresholdSettings, ...] = Field(default_factory=tuple)
    # This is populated only by the attribution runner. Keeping it empty by
    # default is intentional: config export must not grow the ordinary dbt var
    # set, or the existing seed-independent fingerprint would drift.
    frozen_subsystem_seeds: dict[str, int] = Field(default_factory=dict)

    @field_validator("frozen_subsystem_seeds")
    @classmethod
    def validate_frozen_subsystem_seeds(cls, values: dict[str, int]) -> dict[str, int]:
        """Restrict internal freeze overrides to independently seeded draws."""
        unsupported = sorted(set(values) - _FREEZABLE_SUBSYSTEMS)
        if unsupported:
            rendered = ", ".join(unsupported)
            raise ValueError(f"unsupported frozen subsystem(s): {rendered}")
        return values


__all__ = ["EnsembleSettings", "EnsembleThresholdSettings"]
