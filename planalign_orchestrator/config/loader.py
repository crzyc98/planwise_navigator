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


class SimulationConfig(BaseModel):
    """Top-level config with backward compatible extras allowed."""

    model_config = ConfigDict(extra="allow")

    # Enterprise identifiers (encouraged by architecture; optional for back-compat)
    scenario_id: Optional[str] = None
    plan_design_id: Optional[str] = None

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
        if not self.scenario_id or not self.plan_design_id:
            raise ValueError(
                "scenario_id and plan_design_id are required for orchestrator runs"
            )

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
