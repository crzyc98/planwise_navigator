"""Configuration loading and SimulationConfig model.

E073: Config Module Refactoring - loader module.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .safety import OrchestrationConfig

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .simulation import SimulationSettings, CompensationSettings
from .workforce import (
    WorkforceSettings,
    EnrollmentSettings,
    EligibilitySettings,
    PlanEligibilitySettings,
    EmployerMatchSettings,
    DeferralMatchResponseSettings,
    validate_core_age_schedule,
)
from .permitted_disparity import (
    normalize_dc_plan_integration,
    validate_core_integration,
)
from .performance import (
    OptimizationSettings,
    OrchestratorSettings,
    E068CThreadingSettings,
)
from .ensemble import EnsembleSettings
from .plan_design import PlanDesignAssignmentSettings, PlanDesignParametersMap


def _core_integration_config(core: Any, dc_plan: Any) -> Optional[Dict[str, Any]]:
    """Return the configured integration shape, favoring an explicit Studio payload."""
    if isinstance(dc_plan, dict) and "core_integration_enabled" in dc_plan:
        rate = dc_plan.get("core_contribution_rate")
        if "core_contribution_rate_percent" in dc_plan:
            rate = float(dc_plan["core_contribution_rate_percent"]) / 100
        return {
            "status": dc_plan.get("core_status", "flat"),
            "contribution_rate": rate or 0.0,
            "graded_schedule": dc_plan.get("core_graded_schedule", []),
            "points_schedule": dc_plan.get("core_points_schedule", []),
            "age_schedule": dc_plan.get("core_age_schedule", []),
            "integration": normalize_dc_plan_integration(dc_plan),
        }
    return core if isinstance(core, dict) and "integration" in core else None


def _per_design_core_schedule(
    family: str, core: Dict[str, Any]
) -> tuple[str, list[Dict[str, Any]]] | None:
    """Translate a legacy global core schedule to the per-design schema."""
    field = {
        "graded_by_service": "graded_schedule",
        "points_based": "points_schedule",
        "age_banded": "age_schedule",
    }.get(family)
    if field is None or not isinstance(core.get(field), list):
        return None
    translated: list[Dict[str, Any]] = []
    for raw_band in core[field]:
        band = dict(raw_band)
        if family == "graded_by_service":
            translated.append(
                {
                    "min_years": band.get(
                        "min_years", band.get("service_years_min", 0)
                    ),
                    "max_years": band.get("max_years", band.get("service_years_max")),
                    "rate": band.get("contribution_rate", band.get("rate", 0.0)),
                }
            )
        else:
            rate = band.get("rate", 0.0)
            if band.get("contribution_rate") is not None:
                rate = float(band["contribution_rate"]) * 100
            band["rate"] = rate
            band.pop("contribution_rate", None)
            translated.append(band)
    return field, translated


class SimulationConfig(BaseModel):
    """Top-level config with backward compatible extras allowed."""

    model_config = ConfigDict(extra="allow")

    # Enterprise identifiers (encouraged by architecture; optional for back-compat)
    scenario_id: Optional[str] = None
    plan_design_id: Optional[str] = None
    plan_design_assignment: Optional[PlanDesignAssignmentSettings] = None
    plan_design_parameters: Optional[PlanDesignParametersMap] = None

    simulation: SimulationSettings
    compensation: CompensationSettings
    workforce: WorkforceSettings = Field(default_factory=WorkforceSettings)
    enrollment: EnrollmentSettings = Field(default_factory=EnrollmentSettings)
    eligibility: EligibilitySettings = Field(default_factory=EligibilitySettings)
    plan_eligibility: PlanEligibilitySettings = Field(
        default_factory=PlanEligibilitySettings
    )
    employer_match: Optional[EmployerMatchSettings] = Field(
        default=None, description="Employer match configuration"
    )

    # E058: Match-responsive deferral adjustments
    deferral_match_response: DeferralMatchResponseSettings = Field(
        default_factory=DeferralMatchResponseSettings,
        description="Match-responsive deferral adjustment settings",
    )

    # Performance optimization configuration (optional for backward compatibility)
    optimization: Optional[OptimizationSettings] = Field(
        default=None, description="Performance optimization settings"
    )

    # Orchestrator configuration including threading support
    orchestrator: Optional[OrchestratorSettings] = Field(
        default=None, description="Orchestrator configuration including threading"
    )

    # Feature 133: validated after-run risk thresholds. Other ensemble options
    # remain invocation concerns so ordinary simulation configs stay unchanged.
    ensemble: EnsembleSettings = Field(default_factory=EnsembleSettings)

    @model_validator(mode="after")
    def validate_core_schedules_and_integration(self) -> "SimulationConfig":
        """Reject malformed core schedules and illegal integration at load time."""
        core = getattr(self, "employer_core_contribution", None)
        if isinstance(core, dict) and core.get("status") == "age_banded":
            validate_core_age_schedule(core.get("age_schedule", []))

        dc_plan = getattr(self, "dc_plan", None)
        if isinstance(dc_plan, dict) and dc_plan.get("core_status") == "age_banded":
            validate_core_age_schedule(dc_plan.get("core_age_schedule", []))
        integration_core = _core_integration_config(core, dc_plan)
        if integration_core is not None:
            validate_core_integration(
                integration_core,
                self.simulation.start_year,
                self.simulation.end_year,
            )
        return self

    def require_identifiers(self) -> None:
        """Raise if scenario_id/plan_design_id are missing."""
        if not self.scenario_id or not (
            self.plan_design_id or self.plan_design_assignment is not None
        ):
            raise ValueError(
                "scenario_id and a plan_design_id or plan_design_assignment are required"
            )

    def get_plan_design_set(self) -> list[str]:
        """Return every plan design that can be assigned in this run."""
        if self.plan_design_assignment is not None:
            return self.plan_design_assignment.design_set()
        return [self.plan_design_id or "default"]

    def validated_plan_design_parameters(self) -> PlanDesignParametersMap:
        """Return parameters after enforcing exact assignment-design coverage."""
        if self.plan_design_parameters is None:
            raise ValueError("plan_design_parameters is not configured")
        parameters = PlanDesignParametersMap.model_validate(self.plan_design_parameters)
        expected = set(self.get_plan_design_set())
        actual = set(parameters.design_ids())
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing or extra:
            raise ValueError(
                "plan_design_parameters design set mismatch: "
                f"missing={missing}, extra={extra}"
            )
        match_family = (
            self.employer_match.employer_match_status
            if self.employer_match is not None
            else "deferral_based"
        )
        if match_family == "tenure_based":
            match_family = "tenure_graded"
        match_template = "tiered"
        dc_plan = getattr(self, "dc_plan", None)
        if isinstance(dc_plan, dict):
            match_template = str(dc_plan.get("match_template", match_template))
        core = getattr(self, "employer_core_contribution", None)
        core = core if isinstance(core, dict) else {}
        inherited_core = _core_integration_config(core, dc_plan) or core
        core_family = str(inherited_core.get("status", "flat"))
        integration = inherited_core.get("integration")
        integration = integration if isinstance(integration, dict) else {}
        resolved_payload = parameters.model_dump(mode="json")
        for design_payload in resolved_payload.values():
            match_payload = design_payload["match"]
            match_payload["family"] = match_payload.get("family") or match_family
            match_payload["match_template"] = (
                match_payload.get("match_template") or match_template
            )
            core_payload = design_payload["employer_core"]
            core_payload["family"] = core_payload.get("family") or core_family
            inherited_schedule = _per_design_core_schedule(
                core_payload["family"], inherited_core
            )
            if inherited_schedule is not None:
                schedule_field, schedule = inherited_schedule
                if not core_payload.get(schedule_field):
                    core_payload[schedule_field] = schedule
            core_payload["integration_enabled"] = (
                core_payload.get("integration_enabled")
                if core_payload.get("integration_enabled") is not None
                else bool(integration.get("enabled", False))
            )
            core_payload["integration_level_mode"] = core_payload.get(
                "integration_level_mode"
            ) or str(integration.get("level_mode", "ss_wage_base"))
            core_payload["integration_level_value"] = (
                core_payload.get("integration_level_value")
                if core_payload.get("integration_level_value") is not None
                else integration.get("level_value")
            )
            core_payload["integration_disparity_rate"] = (
                core_payload.get("integration_disparity_rate")
                if core_payload.get("integration_disparity_rate") is not None
                else float(integration.get("disparity_rate", 0.0))
            )
        parameters = PlanDesignParametersMap.model_validate(resolved_payload)
        match_schedule_fields = {
            "deferral_based": "tiers",
            "graded_by_service": "graded_schedule",
            "tenure_graded": "tenure_graded_bands",
            "points_based": "points_tiers",
        }
        core_schedule_fields = {
            "graded_by_service": "graded_schedule",
            "points_based": "points_schedule",
            "age_banded": "age_schedule",
        }
        for design_id, design_parameters in parameters.root.items():
            design_match_family = design_parameters.match.family
            if design_match_family is None:
                raise ValueError(
                    f"plan design '{design_id}' match.family did not resolve"
                )
            schedule_field = match_schedule_fields[design_match_family]
            if not getattr(design_parameters.match, schedule_field):
                raise ValueError(
                    f"plan design '{design_id}' match.{schedule_field} must be configured "
                    f"for family '{design_match_family}'"
                )
            design_core_family = design_parameters.employer_core.family
            if design_core_family is None:
                raise ValueError(
                    f"plan design '{design_id}' employer_core.family did not resolve"
                )
            core_schedule_field = core_schedule_fields.get(design_core_family)
            if core_schedule_field and not getattr(
                design_parameters.employer_core, core_schedule_field
            ):
                raise ValueError(
                    f"plan design '{design_id}' employer_core.{core_schedule_field} must "
                    f"be configured for family '{design_core_family}'"
                )
        return parameters

    def get_thread_count(self) -> int:
        """Get configured thread count with fallback to single-threaded execution."""
        if self.optimization and self.optimization.e068c_threading:
            return self.optimization.e068c_threading.dbt_threads
        elif self.orchestrator and self.orchestrator.threading.enabled:
            return self.orchestrator.threading.thread_count
        return 1

    def get_e068c_threading_config(self) -> E068CThreadingSettings:
        """Get E068C threading configuration with defaults."""
        if self.optimization and self.optimization.e068c_threading:
            return self.optimization.e068c_threading
        return E068CThreadingSettings()

    def get_event_shards(self) -> int:
        """Get configured event shards count."""
        if self.optimization and self.optimization.e068c_threading:
            return self.optimization.e068c_threading.event_shards
        return 1

    def get_max_parallel_years(self) -> int:
        """Get configured maximum parallel years."""
        if self.optimization and self.optimization.e068c_threading:
            return self.optimization.e068c_threading.max_parallel_years
        return 1

    def validate_eligibility_configuration(self) -> None:
        """Validate eligibility configuration and warn about contradictory settings.

        Note: employer_match contradictory config warnings are handled by
        EmployerMatchEligibilitySettings.resolve_allow_new_hires_default
        during Pydantic validation. Only untyped dict-based extras (e.g.,
        employer_core_contribution) need checking here.
        """
        import warnings

        # Check core contribution eligibility
        core_contrib = getattr(self, "employer_core_contribution", None)
        if core_contrib and isinstance(core_contrib, dict):
            core_elig = core_contrib.get("eligibility", {})
            if isinstance(core_elig, dict):
                core_allow = core_elig.get("allow_new_hires", False)
                core_tenure = core_elig.get("minimum_tenure_years", 0)
                if core_allow and core_tenure > 0:
                    warnings.warn(
                        f"Employer core: allow_new_hires=True with "
                        f"minimum_tenure_years={core_tenure}. "
                        f"New hires will bypass the tenure requirement.",
                        UserWarning,
                        stacklevel=2,
                    )

    def validate_threading_configuration(self) -> None:
        """Validate threading configuration and log warnings."""
        if self.optimization and self.optimization.e068c_threading:
            try:
                self.optimization.e068c_threading.validate_e068c_configuration()
            except ValueError as e:
                raise ValueError(f"Invalid E068C threading configuration: {e}")

        if self.optimization and self.optimization.event_generation:
            try:
                self.optimization.event_generation.validate_mode()
            except ValueError as e:
                raise ValueError(f"Invalid event generation configuration: {e}")

        if self.orchestrator and self.orchestrator.threading.enabled:
            try:
                self.orchestrator.threading.validate_thread_count()
            except ValueError as e:
                raise ValueError(f"Invalid orchestrator threading configuration: {e}")

            thread_count = self.orchestrator.threading.thread_count
            mode = self.orchestrator.threading.mode

            if mode == "sequential" and thread_count > 1:
                import warnings

                warnings.warn(
                    f"Threading mode is 'sequential' but thread_count is {thread_count}. Consider setting thread_count=1 or changing mode to 'selective'."
                )

            if mode == "aggressive" and thread_count == 1:
                import warnings

                warnings.warn(
                    "Threading mode is 'aggressive' but thread_count is 1. Consider increasing thread_count or changing mode to 'sequential'."
                )


def _lower_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize dictionary keys to lowercase."""
    return {k.lower(): v for k, v in d.items()}


def _apply_env_overrides(cfg: Dict[str, Any], env: Dict[str, str], prefix: str) -> None:
    """Apply simple env overrides using DOUBLE-UNDERSCORE path syntax.

    Example: NAV_SIMULATION__START_YEAR=2026 overrides simulation.start_year
    """
    plen = len(prefix)
    for key, value in env.items():
        if not key.startswith(prefix):
            continue
        path = key[plen:].lower().split("__")
        cur: Any = cfg
        for part in path[:-1]:
            if part not in cur or not isinstance(cur[part], dict):
                cur[part] = {}
            cur = cur[part]
        # Basic type coercion for ints/bools/floats
        leaf = path[-1]
        if value.lower() in {"true", "false"}:
            cur[leaf] = value.lower() == "true"
        else:
            try:
                if "." in value:
                    cur[leaf] = float(value)
                else:
                    cur[leaf] = int(value)
            except ValueError:
                cur[leaf] = value


def load_simulation_config(
    path: Path | str = Path("config/simulation_config.yaml"),
    *,
    env_overrides: bool = True,
    env: Optional[Dict[str, str]] = None,
    env_prefix: str = "NAV_",
) -> SimulationConfig:
    """Load YAML config and return a typed `SimulationConfig`.

    - Allows extra keys for backward compatibility with existing YAML
    - Optionally applies environment variable overrides
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    with open(p, "r") as fh:
        raw = yaml.safe_load(fh) or {}

    # Normalize to lowercase keys at top level for resilience
    data = _lower_keys(raw)

    if env_overrides:
        import os as _os

        _apply_env_overrides(data, env or dict(_os.environ), env_prefix)

    try:
        return SimulationConfig(**data)
    except ValidationError as e:
        raise ValueError(f"Invalid simulation configuration: {e}") from e


def load_orchestration_config(
    path: Path | str = Path("config/simulation_config.yaml"),
    *,
    env_overrides: bool = True,
    env: Optional[Dict[str, str]] = None,
    env_prefix: str = "NAV_",
) -> "OrchestrationConfig":
    """Load YAML config and return a typed `OrchestrationConfig`.

    This is an alias for loading OrchestrationConfig with production safety settings.
    """
    from .safety import OrchestrationConfig

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    with open(p, "r") as fh:
        raw = yaml.safe_load(fh) or {}

    data = _lower_keys(raw)

    if env_overrides:
        import os as _os

        _apply_env_overrides(data, env or dict(_os.environ), env_prefix)

    try:
        return OrchestrationConfig(**data)
    except ValidationError as e:
        raise ValueError(f"Invalid orchestration configuration: {e}") from e
