"""Partial config schema for Studio, retaining dictionary access in services.

Only fields read directly by Studio are declared. Unknown engine settings are
preserved at every level; omitted fields must never become null overrides.
"""

from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    GetJsonSchemaHandler,
    ValidateAs,
    WrapSerializer,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .bands import Band
from .promotion_hazard import (
    PromotionHazardAgeMultiplier,
    PromotionHazardTenureMultiplier,
)


class PartialConfig(BaseModel):
    """An open config section with optional known fields."""

    model_config = ConfigDict(extra="allow")


class StudioSimulationConfig(PartialConfig):
    start_year: int | None = None
    end_year: int | None = None
    seed: int | None = None
    random_seed: int | None = None
    growth_target: float | None = None
    target_growth_rate: float | None = None


class StudioWorkforceConfig(PartialConfig):
    total_termination_rate: float | None = None
    new_hire_termination_rate: float | None = None


class StudioCompensationConfig(PartialConfig):
    merit_budget: float | None = None
    merit_budget_percent: float | None = None
    cola_rate_percent: float | None = None


class StudioTurnoverConfig(PartialConfig):
    base_rate: float | None = None


class StudioMatchTier(PartialConfig):
    employee_min: float | None = None
    employee_max: float | None = None
    match_rate: float | None = None


class StudioTenureMatchTier(PartialConfig):
    min_years: float | None = None
    max_years: float | None = None
    match_rate: float | None = None
    max_deferral_pct: float | None = None


class StudioPointsMatchTier(PartialConfig):
    min_points: float | None = None
    max_points: float | None = None
    match_rate: float | None = None
    max_deferral_pct: float | None = None


class StudioDCPlanConfig(PartialConfig):
    auto_enroll: bool | None = None
    match_template: str | None = None
    match_status: str | None = None
    match_tiers: list[StudioMatchTier] | None = None
    tenure_match_tiers: list[StudioTenureMatchTier] | None = None
    points_match_tiers: list[StudioPointsMatchTier] | None = None
    auto_escalation: bool | None = None


class StudioAgeMultiplier(PromotionHazardAgeMultiplier):
    model_config = ConfigDict(extra="allow")


class StudioTenureMultiplier(PromotionHazardTenureMultiplier):
    model_config = ConfigDict(extra="allow")


class StudioBand(Band):
    model_config = ConfigDict(extra="allow")


class StudioPromotionHazardConfig(PartialConfig):
    base_rate: float | None = None
    level_dampener_factor: float | None = None
    age_multipliers: list[StudioAgeMultiplier] | None = None
    tenure_multipliers: list[StudioTenureMultiplier] | None = None


class StudioConfig(PartialConfig):
    """Partial simulation config exposed in scenario, template and run APIs."""

    simulation: StudioSimulationConfig | None = None
    workforce: StudioWorkforceConfig | None = None
    compensation: StudioCompensationConfig | None = None
    turnover: StudioTurnoverConfig | None = None
    dc_plan: StudioDCPlanConfig | None = None
    promotion_hazard: StudioPromotionHazardConfig | None = None
    age_bands: list[StudioBand] | None = None
    tenure_bands: list[StudioBand] | None = None


def _as_overrides(config: StudioConfig) -> dict[str, Any]:
    return config.model_dump(exclude_unset=True)


def _serialize_overrides(value: dict[str, Any], _handler: Any) -> dict[str, Any]:
    # ValidateAs returns a dict, so bypass the underlying model serializer.
    return value


class _StudioConfigSchema:
    """Expose the partial model while serializing the service-facing dictionary."""

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return handler(StudioConfig.__pydantic_core_schema__)


StudioConfigDict = Annotated[
    dict[str, Any],
    ValidateAs(StudioConfig, _as_overrides),
    WrapSerializer(_serialize_overrides),
    _StudioConfigSchema,
]
