#!/usr/bin/env python3
"""
Typed configuration models and loaders for Navigator Orchestrator.

Features
- Pydantic v2 models for simulation config (type safety)
- YAML loader with optional environment variable overrides
- dbt var mapping compatible with existing models
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, ConfigDict


class SimulationSettings(BaseModel):
    start_year: int = Field(..., ge=2000)
    end_year: int = Field(..., ge=2000)
    random_seed: int = Field(default=42)
    target_growth_rate: float = Field(default=0.03, ge=-1, le=1)


class CompensationSettings(BaseModel):
    cola_rate: float = Field(default=0.005, ge=0, le=1)
    merit_budget: float = Field(default=0.025, ge=0, le=1)


class WorkforceSettings(BaseModel):
    total_termination_rate: float = Field(default=0.12, ge=0, le=1)
    new_hire_termination_rate: float = Field(default=0.25, ge=0, le=1)


class OptOutRatesByAge(BaseModel):
    young: float = Field(default=0.10, ge=0, le=1)
    mid_career: float = Field(default=0.07, ge=0, le=1)
    mature: float = Field(default=0.05, ge=0, le=1)
    senior: float = Field(default=0.03, ge=0, le=1)


class OptOutRatesByIncome(BaseModel):
    low_income: float = Field(default=1.20, ge=0, le=5)
    moderate: float = Field(default=1.00, ge=0, le=5)
    high: float = Field(default=0.70, ge=0, le=5)
    executive: float = Field(default=0.50, ge=0, le=5)


class OptOutRatesSettings(BaseModel):
    by_age: OptOutRatesByAge = OptOutRatesByAge()
    by_income: OptOutRatesByIncome = OptOutRatesByIncome()


class AutoEnrollmentSettings(BaseModel):
    enabled: bool = True
    scope: Optional[str] = None
    hire_date_cutoff: Optional[str] = None
    window_days: int = 45
    default_deferral_rate: float = Field(default=0.06, ge=0, le=1)
    opt_out_grace_period: int = 30
    opt_out_rates: OptOutRatesSettings = OptOutRatesSettings()


class ProactiveEnrollmentSettings(BaseModel):
    enabled: bool = True
    class TimingWindow(BaseModel):
        min_days: int = 7
        max_days: int = 35

    timing_window: TimingWindow = TimingWindow()
    probability_by_demographics: Dict[str, float] = Field(default_factory=dict)


class EnrollmentTimingSettings(BaseModel):
    business_day_adjustment: bool = True


class EnrollmentSettings(BaseModel):
    auto_enrollment: AutoEnrollmentSettings = AutoEnrollmentSettings()
    proactive_enrollment: ProactiveEnrollmentSettings = ProactiveEnrollmentSettings()
    timing: EnrollmentTimingSettings = EnrollmentTimingSettings()


class EligibilitySettings(BaseModel):
    waiting_period_days: Optional[int] = None


class PlanEligibilitySettings(BaseModel):
    minimum_age: Optional[int] = None


class SimulationConfig(BaseModel):
    """Top-level config with backward compatible extras allowed."""

    model_config = ConfigDict(extra="allow")

    # Enterprise identifiers (encouraged by architecture; optional for back-compat)
    scenario_id: Optional[str] = None
    plan_design_id: Optional[str] = None

    simulation: SimulationSettings
    compensation: CompensationSettings
    workforce: WorkforceSettings = WorkforceSettings()
    enrollment: EnrollmentSettings = EnrollmentSettings()
    eligibility: EligibilitySettings = EligibilitySettings()
    plan_eligibility: PlanEligibilitySettings = PlanEligibilitySettings()

    def require_identifiers(self) -> None:
        """Raise if scenario_id/plan_design_id are missing."""
        if not self.scenario_id or not self.plan_design_id:
            raise ValueError(
                "scenario_id and plan_design_id are required for orchestrator runs"
            )


def _lower_keys(d: Dict[str, Any]) -> Dict[str, Any]:
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
        # Raise clear error for CLI consumption
        raise ValueError(f"Invalid simulation configuration: {e}") from e


def to_dbt_vars(cfg: SimulationConfig) -> Dict[str, Any]:
    """Map typed config to dbt vars compatible with existing models.

    Mirrors the existing `extract_dbt_vars_from_config` behavior in a typed way.
    """
    dbt_vars: Dict[str, Any] = {}

    # Simulation bounds
    if cfg.simulation.start_year is not None:
        dbt_vars["start_year"] = int(cfg.simulation.start_year)
    if cfg.simulation.end_year is not None:
        dbt_vars["end_year"] = int(cfg.simulation.end_year)

    # Compensation
    if cfg.compensation.cola_rate is not None:
        dbt_vars["cola_rate"] = cfg.compensation.cola_rate
    if cfg.compensation.merit_budget is not None:
        dbt_vars["merit_budget"] = cfg.compensation.merit_budget

    # Eligibility and plan eligibility
    if cfg.eligibility.waiting_period_days is not None:
        dbt_vars["eligibility_waiting_days"] = cfg.eligibility.waiting_period_days
        dbt_vars["minimum_service_days"] = cfg.eligibility.waiting_period_days
    if cfg.plan_eligibility.minimum_age is not None:
        dbt_vars["minimum_age"] = cfg.plan_eligibility.minimum_age

    # Auto-enrollment
    auto = cfg.enrollment.auto_enrollment
    if auto.enabled is not None:
        dbt_vars["auto_enrollment_enabled"] = bool(auto.enabled)
    if auto.scope is not None:
        dbt_vars["auto_enrollment_scope"] = str(auto.scope)
    if auto.hire_date_cutoff:
        dbt_vars["auto_enrollment_hire_date_cutoff"] = str(auto.hire_date_cutoff)
    if auto.window_days is not None:
        dbt_vars["auto_enrollment_window_days"] = int(auto.window_days)
    if auto.default_deferral_rate is not None:
        dbt_vars["auto_enrollment_default_deferral_rate"] = float(auto.default_deferral_rate)
    if auto.opt_out_grace_period is not None:
        dbt_vars["auto_enrollment_opt_out_grace_period"] = int(auto.opt_out_grace_period)

    # Opt-out rates by age
    age_rates = auto.opt_out_rates.by_age
    dbt_vars["opt_out_rate_young"] = float(age_rates.young)
    dbt_vars["opt_out_rate_mid"] = float(age_rates.mid_career)
    dbt_vars["opt_out_rate_mature"] = float(age_rates.mature)
    dbt_vars["opt_out_rate_senior"] = float(age_rates.senior)

    # Opt-out rates by income (calculate absolute rates from base + multipliers)
    income_rates = auto.opt_out_rates.by_income
    # Use moderate rate as base (typically young segment rate * moderate multiplier)
    base_rate = float(age_rates.young)  # Use young as typical base case
    moderate_rate = base_rate * float(income_rates.moderate)

    dbt_vars["opt_out_rate_low_income"] = base_rate * float(income_rates.low_income)
    dbt_vars["opt_out_rate_moderate"] = moderate_rate
    dbt_vars["opt_out_rate_high"] = base_rate * float(income_rates.high)
    dbt_vars["opt_out_rate_executive"] = base_rate * float(income_rates.executive)

    # Proactive enrollment
    pro = cfg.enrollment.proactive_enrollment
    if pro.enabled is not None:
        dbt_vars["proactive_enrollment_enabled"] = bool(pro.enabled)
    tw = pro.timing_window
    if tw.min_days is not None:
        dbt_vars["proactive_enrollment_min_days"] = int(tw.min_days)
    if tw.max_days is not None:
        dbt_vars["proactive_enrollment_max_days"] = int(tw.max_days)
    probs = pro.probability_by_demographics or {}
    for key in ("young", "mid_career", "mature", "senior"):
        if key in probs:
            dbt_vars[f"proactive_enrollment_rate_{key}"] = float(probs[key])

    # Timing
    if cfg.enrollment.timing.business_day_adjustment is not None:
        dbt_vars["enrollment_business_day_adjustment"] = bool(
            cfg.enrollment.timing.business_day_adjustment
        )

    # Random seed
    if cfg.simulation.random_seed is not None:
        dbt_vars["random_seed"] = cfg.simulation.random_seed

    # Growth and workforce parameters (CRITICAL FIX)
    if cfg.simulation.target_growth_rate is not None:
        dbt_vars["target_growth_rate"] = cfg.simulation.target_growth_rate

    # Termination rates (CRITICAL FIX)
    if hasattr(cfg, 'workforce') and cfg.workforce:
        if cfg.workforce.total_termination_rate is not None:
            dbt_vars["total_termination_rate"] = cfg.workforce.total_termination_rate
        if cfg.workforce.new_hire_termination_rate is not None:
            dbt_vars["new_hire_termination_rate"] = cfg.workforce.new_hire_termination_rate

    # Deferral auto-escalation (E035 - simplified)
    try:
        dae = getattr(cfg, 'deferral_auto_escalation', None)
        if isinstance(dae, dict):
            if 'enabled' in dae:
                dbt_vars['deferral_escalation_enabled'] = bool(dae['enabled'])
            if 'effective_day' in dae and dae['effective_day']:
                # MM-DD string
                dbt_vars['deferral_escalation_effective_mmdd'] = str(dae['effective_day'])
            if 'increment_amount' in dae and dae['increment_amount'] is not None:
                dbt_vars['deferral_escalation_increment'] = float(dae['increment_amount'])
            if 'maximum_rate' in dae and dae['maximum_rate'] is not None:
                dbt_vars['deferral_escalation_cap'] = float(dae['maximum_rate'])
            if 'hire_date_cutoff' in dae and dae['hire_date_cutoff']:
                dbt_vars['deferral_escalation_hire_date_cutoff'] = str(dae['hire_date_cutoff'])
            if 'require_active_enrollment' in dae:
                dbt_vars['deferral_escalation_require_enrollment'] = bool(dae['require_active_enrollment'])
    except Exception:
        pass

    # Deferral baseline mode (Option A default: frozen)
    try:
        db = getattr(cfg, 'deferral_baseline', None)
        if isinstance(db, dict) and 'mode' in db and db['mode']:
            dbt_vars['deferral_baseline_mode'] = str(db['mode']).lower()
        else:
            dbt_vars['deferral_baseline_mode'] = 'frozen'
    except Exception:
        dbt_vars['deferral_baseline_mode'] = 'frozen'

    # Employer match configuration (E039)
    # Map YAML employer_match block to dbt vars expected by match calculations
    try:
        employer = getattr(cfg, 'employer_match', None)
        if employer:
            # employer is likely a dict due to extra=allow
            active = employer.get('active_formula')
            formulas = employer.get('formulas')
            if active is not None:
                dbt_vars["active_match_formula"] = str(active)
            if formulas is not None:
                # Pass the full formulas mapping (JSON-serializable)
                dbt_vars["match_formulas"] = formulas
    except Exception:
        # Non-fatal: fall back to model defaults
        pass

    # Employer core contribution configuration
    # Map YAML employer_core_contribution block to dbt vars
    try:
        core_contrib = getattr(cfg, 'employer_core_contribution', None)
        if core_contrib:
            # core_contrib is likely a dict due to extra=allow
            enabled = core_contrib.get('enabled')
            rate = core_contrib.get('contribution_rate')
            eligibility = core_contrib.get('eligibility')

            if enabled is not None:
                dbt_vars["employer_core_enabled"] = bool(enabled)
            if rate is not None:
                dbt_vars["employer_core_contribution_rate"] = float(rate)

            if eligibility:
                min_tenure = eligibility.get('minimum_tenure_years')
                require_active = eligibility.get('require_active_at_year_end')
                min_hours = eligibility.get('minimum_hours_annual')

                if min_tenure is not None:
                    dbt_vars["core_minimum_tenure_years"] = int(min_tenure)
                if require_active is not None:
                    dbt_vars["core_require_active_eoy"] = bool(require_active)
                if min_hours is not None:
                    dbt_vars["core_minimum_hours"] = int(min_hours)
    except Exception:
        # Non-fatal: fall back to model defaults
        pass

    return dbt_vars
