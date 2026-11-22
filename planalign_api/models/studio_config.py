"""Partial config schema for Studio, retaining dictionary access in services.

Only fields read directly by Studio are declared. Unknown engine settings are
preserved at every level; omitted fields must never become null overrides.
"""

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from planalign_orchestrator.config.plan_design import check_identifier
from planalign_orchestrator.config.simulation import MinimumWageStep
from planalign_orchestrator.config.participant_behavior import (
    AIPMode,
    BelowDefaultTier,
    DeferralChangeStep,
    DeferralChangeShare,
    DeferralChangeMultiplierBands,
    EasyEnrollPackage,
    Rate,
)

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    GetJsonSchemaHandler,
    ValidateAs,
    WrapSerializer,
    model_validator,
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
    raise_budget: float | None = None
    raise_budget_percent: float | None = None
    raise_coverage_percent: float | None = None
    minimum_wage: list[MinimumWageStep] | None = Field(
        default=None,
        description="Minimum wage steps (#1229): a new minimum hourly rate and its effective date, at most one per calendar year.",
    )


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
    opt_out_rate_target: Rate | None = None
    opt_out_multipliers_age: DeferralChangeMultiplierBands | None = None
    opt_out_multipliers_income: DeferralChangeMultiplierBands | None = None
    auto_enroll: bool | None = None
    reenrollment_sweep_enabled: bool | None = None
    reenrollment_sweep_interval_years: int | None = Field(
        default=None, ge=1, strict=True
    )
    reenrollment_sweep_first_year: int | None = Field(default=None, strict=True)
    reenrollment_sweep_method: Literal["enroll_at_default", "into_aip"] | None = None
    reenrollment_sweep_include_non_contributors: bool | None = None
    reenrollment_sweep_include_below_default: bool | None = None
    reenrollment_sweep_include_below_aip_cap: bool | None = None
    reenrollment_sweep_decline_probability: float | None = Field(
        default=None, ge=0, le=1
    )

    match_template: (
        Literal["simple", "tiered", "stretch", "safe_harbor", "qaca"] | None
    ) = None
    match_status: str | None = None
    match_tiers: list[StudioMatchTier] | None = None
    tenure_match_tiers: list[StudioTenureMatchTier] | None = None
    points_match_tiers: list[StudioPointsMatchTier] | None = None
    auto_escalation: bool | None = None

    escalation_mode: AIPMode | None = Field(
        default=None,
        description="Auto-increase program (AIP) membership mode when auto_escalation is enabled: automatic or participant_elected.",
    )
    escalation_participant_elected_signup_probability: Rate | None = Field(
        default=None,
        description="Probability per participant per year of signing up for escalation, 0–1.",
    )
    easy_enroll_enabled: bool | None = Field(
        default=None,
        description="Enable enrollment through preset deferral packages; false leaves results unchanged.",
    )
    easy_enroll_channel_share_without_auto_enrollment: Rate | None = Field(
        default=None,
        description="For plans without auto-enrollment, the share of employees who enroll on their own (before any auto-enrollment) who use Easy Enroll instead of choosing a rate themselves, decimal 0–1. The remainder enroll proactively online. Easy Enroll is only available before auto-enrollment happens; auto-enrolled participants never use it.",
    )
    easy_enroll_channel_share_with_auto_enrollment: Rate | None = Field(
        default=None,
        description="For plans with auto-enrollment, the share of employees who enroll on their own (before any auto-enrollment) who use Easy Enroll instead of choosing a rate themselves, decimal 0–1. The remainder enroll proactively online. Easy Enroll is only available before auto-enrollment happens; auto-enrolled participants never use it.",
    )
    easy_enroll_packages: list[EasyEnrollPackage] | None = Field(
        default=None,
        description="Ordered deferral packages; rates are decimals (0.06 = 6%) and shares must sum to 1 (±1e-6).",
    )
    easy_enroll_escalation_cap: Rate | None = Field(
        default=None,
        description="Escalation cap for Easy Enroll participants, decimal 0–1 (0.06 = 6%).",
    )
    match_magnet_downward_enabled: bool | None = Field(
        default=None,
        description="Enable reducing above-ceiling enrollment rates to the match ceiling; uses the upward match magnet probability (snap_probability), 0–1.",
    )
    below_default_share_tiers: list[BelowDefaultTier] | None = Field(
        default=None,
        description="Ordered tiers by auto-enrollment default rate, decimal 0–1 (0.06 = 6%); one final null ceiling. Each tier's share is independent and need not sum to 1.",
    )
    below_default_multipliers_age: DeferralChangeMultiplierBands | None = None
    below_default_multipliers_income: DeferralChangeMultiplierBands | None = None
    below_default_steps: list[DeferralChangeStep] | None = Field(
        default=None,
        description="Ordered below-default reductions in whole percentage points (pp); list weights must sum to 1 (±1e-6).",
    )
    deferral_rate_changes_enabled: bool | None = Field(
        default=None,
        description="Enable voluntary deferral increases, decreases, stops and restarts; false leaves results unchanged.",
    )
    deferral_rate_changes_with_escalation_increase_probability: Rate | None = Field(
        default=None,
        description="Probability per participant per year of increasing deferral while in escalation, 0–1.",
    )
    deferral_rate_changes_with_escalation_decrease_probability: Rate | None = Field(
        default=None,
        description="Probability per participant per year of decreasing deferral while in escalation, 0–1.",
    )
    deferral_rate_changes_without_escalation_increase_probability: Rate | None = Field(
        default=None,
        description="Probability per participant per year of increasing deferral without escalation, 0–1.",
    )
    deferral_rate_changes_without_escalation_decrease_probability: Rate | None = Field(
        default=None,
        description="Probability per participant per year of decreasing deferral without escalation, 0–1.",
    )
    deferral_rate_changes_multipliers_increase_age: (
        DeferralChangeMultiplierBands | None
    ) = Field(
        default=None,
        description="Increase probability multipliers by age (years); ordered inclusive min bounds starting at 0, final band open-ended. Multiplied across age, income and tenure before proportional rescaling; stop probability is preserved.",
    )
    deferral_rate_changes_multipliers_increase_income: (
        DeferralChangeMultiplierBands | None
    ) = Field(
        default=None,
        description="Increase probability multipliers by income (annual compensation dollars); ordered inclusive min bounds starting at 0, final band open-ended. Multiplied across age, income and tenure before proportional rescaling; stop probability is preserved.",
    )
    deferral_rate_changes_multipliers_increase_tenure: (
        DeferralChangeMultiplierBands | None
    ) = Field(
        default=None,
        description="Increase probability multipliers by tenure (years); ordered inclusive min bounds starting at 0, final band open-ended. Multiplied across age, income and tenure before proportional rescaling; stop probability is preserved.",
    )
    deferral_rate_changes_multipliers_decrease_age: (
        DeferralChangeMultiplierBands | None
    ) = Field(
        default=None,
        description="Decrease probability multipliers by age (years); ordered inclusive min bounds starting at 0, final band open-ended. Multiplied across age, income and tenure before proportional rescaling; stop probability is preserved.",
    )
    deferral_rate_changes_multipliers_decrease_income: (
        DeferralChangeMultiplierBands | None
    ) = Field(
        default=None,
        description="Decrease probability multipliers by income (annual compensation dollars); ordered inclusive min bounds starting at 0, final band open-ended. Multiplied across age, income and tenure before proportional rescaling; stop probability is preserved.",
    )
    deferral_rate_changes_multipliers_decrease_tenure: (
        DeferralChangeMultiplierBands | None
    ) = Field(
        default=None,
        description="Decrease probability multipliers by tenure (years); ordered inclusive min bounds starting at 0, final band open-ended. Multiplied across age, income and tenure before proportional rescaling; stop probability is preserved.",
    )
    deferral_rate_changes_multipliers_decrease_rate: (
        DeferralChangeMultiplierBands | None
    ) = Field(
        default=None,
        description="Decrease probability multipliers by current decimal deferral rate; inclusive lower bounds starting at 0.",
    )
    deferral_rate_changes_increase_steps: list[DeferralChangeStep] | None = Field(
        default=None,
        description="Ordered increases in whole percentage points (pp); list weights must sum to 1 (±1e-6).",
    )
    deferral_rate_changes_decrease_shares: list[DeferralChangeShare] | None = Field(
        default=None,
        description="Shares of the current rate cut, strictly between 0 and 1; list weights must sum to 1 (±1e-6).",
    )
    deferral_rate_changes_post_escalation_decrease_window_days: int | None = Field(
        default=None,
        ge=0,
        strict=True,
        description="Whole days after escalation during which a participant may decrease deferral; non-negative.",
    )
    deferral_rate_changes_post_escalation_decrease_leaves_escalation: bool | None = (
        Field(
            default=None,
            description="Whether a post-escalation decrease removes the participant from the auto-increase program; false retains membership.",
        )
    )
    deferral_rate_changes_stop_probability: Rate | None = Field(
        default=None,
        description="Probability per participant per year of stopping contributions, 0–1.",
    )
    deferral_rate_changes_restart_probability: Rate | None = Field(
        default=None,
        description="Probability per participant per year of restarting contributions, 0–1.",
    )


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


_VALID_AUTO_ENROLL_SCOPES = frozenset({"all_eligible_employees", "new_hires_only"})
_VALID_STUDIO_AUTO_ENROLL_SCOPES = frozenset(
    {"all_eligible", "all_eligible_employees", "new_hires_only"}
)
_VALID_MATCH_TEMPLATES = frozenset(
    {"simple", "tiered", "stretch", "safe_harbor", "qaca"}
)


def _check_allowed(field: str, value: Any, allowed: frozenset[str]) -> None:
    if value is not None and (not isinstance(value, str) or value not in allowed):
        raise ValueError(f"{field} must be one of {sorted(allowed)}")


def _validate_optional_identifier(field: str, value: Any) -> None:
    if value is None or value == "":
        return
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    check_identifier(value)


def _validate_plan_design_assignment(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise ValueError("plan_design_assignment must be a mapping")
    default_id = value.get("default_plan_design_id")
    if default_id is not None:
        if not isinstance(default_id, str):
            raise ValueError("default_plan_design_id must be a string")
        check_identifier(default_id)
    rules = value.get("rules")
    if rules is None:
        return
    if not isinstance(rules, list):
        raise ValueError("plan_design_assignment.rules must be a list")
    for rule in rules:
        rule_id = rule.get("plan_design_id") if isinstance(rule, Mapping) else None
        if rule_id is not None:
            if not isinstance(rule_id, str):
                raise ValueError(
                    "plan_design_assignment rule plan_design_id must be a string"
                )
            check_identifier(rule_id)


def _validate_plan_design_parameters(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise ValueError("plan_design_parameters must be a mapping")
    for design_id, params in value.items():
        if not isinstance(design_id, str):
            raise ValueError("plan_design_parameters keys must be strings")
        check_identifier(design_id)
        if not isinstance(params, Mapping):
            continue
        match = params.get("match")
        if isinstance(match, Mapping):
            _check_allowed(
                "match_template", match.get("match_template"), _VALID_MATCH_TEMPLATES
            )
        auto = params.get("auto_enrollment")
        if isinstance(auto, Mapping):
            _check_allowed(
                "auto_enrollment.scope", auto.get("scope"), _VALID_AUTO_ENROLL_SCOPES
            )


def _validate_dc_plan(value: Any) -> None:
    if not isinstance(value, Mapping):
        return
    _check_allowed(
        "dc_plan.auto_enroll_scope",
        value.get("auto_enroll_scope"),
        _VALID_STUDIO_AUTO_ENROLL_SCOPES,
    )
    _check_allowed(
        "dc_plan.match_template",
        value.get("match_template"),
        _VALID_MATCH_TEMPLATES,
    )


def _validate_enrollment(value: Any) -> None:
    auto = value.get("auto_enrollment") if isinstance(value, Mapping) else None
    if isinstance(auto, Mapping):
        _check_allowed(
            "enrollment.auto_enrollment.scope",
            auto.get("scope"),
            _VALID_AUTO_ENROLL_SCOPES,
        )


def validate_studio_config_values(config: Mapping[str, Any]) -> None:
    """Validate identifiers and bounded options carried in partial API configs."""
    for key, value in config.items():
        if not isinstance(key, str):
            continue
        lower = key.lower()
        if lower in {"scenario_id", "plan_design_id"}:
            _validate_optional_identifier(key, value)
        elif lower == "plan_design_assignment":
            _validate_plan_design_assignment(value)
        elif lower == "plan_design_parameters":
            _validate_plan_design_parameters(value)
        elif lower == "dc_plan":
            _validate_dc_plan(value)
        elif lower == "enrollment":
            _validate_enrollment(value)


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

    @model_validator(mode="after")
    def _validate_config_identifiers(self) -> "StudioConfig":
        validate_studio_config_values(self.model_dump(exclude_unset=True))
        return self


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
