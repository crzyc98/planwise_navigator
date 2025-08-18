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
import os

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


class ProductionSafetySettings(BaseModel):
    """Production data safety and backup configuration"""

    # Database configuration
    db_path: str = Field(default="simulation.duckdb", description="Path to simulation database")

    # Backup configuration
    backup_enabled: bool = Field(default=True, description="Enable automatic backups")
    backup_dir: str = Field(default="backups", description="Backup directory path")
    backup_retention_days: int = Field(default=7, ge=1, description="Backup retention period")
    backup_before_simulation: bool = Field(default=True, description="Create backup before each simulation")

    # Verification settings
    verify_backups: bool = Field(default=True, description="Enable backup verification")
    max_backup_size_gb: float = Field(default=10.0, ge=0.1, description="Maximum backup size in GB")

    # Logging configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_dir: str = Field(default="logs", description="Log directory path")

    # Safety checks
    require_backup_before_run: bool = Field(default=True, description="Require backup before simulation")
    enable_emergency_backups: bool = Field(default=True, description="Create emergency backup on restore")


class OrchestrationConfig(BaseModel):
    """Complete orchestration configuration including production safety"""

    model_config = ConfigDict(extra="allow")

    # Core simulation configuration
    simulation: SimulationSettings
    compensation: CompensationSettings
    workforce: WorkforceSettings = WorkforceSettings()
    enrollment: EnrollmentSettings = EnrollmentSettings()
    eligibility: EligibilitySettings = EligibilitySettings()
    plan_eligibility: PlanEligibilitySettings = PlanEligibilitySettings()

    # Production safety configuration
    production_safety: ProductionSafetySettings = ProductionSafetySettings()

    # Enterprise identifiers
    scenario_id: Optional[str] = None
    plan_design_id: Optional[str] = None

    def require_identifiers(self) -> None:
        """Raise if scenario_id/plan_design_id are missing."""
        if not self.scenario_id or not self.plan_design_id:
            raise ValueError(
                "scenario_id and plan_design_id are required for orchestrator runs"
            )


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


def validate_production_configuration(config: OrchestrationConfig) -> None:
    """
    Validate production configuration for safety requirements

    Story S043-02: Configuration Management

    Args:
        config: Complete orchestration configuration

    Raises:
        ValueError: If configuration validation fails
        FileNotFoundError: If required files don't exist
    """
    safety = config.production_safety

    # Validate database path exists
    db_path = Path(safety.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    # Validate database is accessible
    try:
        import duckdb
        with duckdb.connect(str(db_path)) as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as e:
        raise ValueError(f"Database connection failed: {str(e)}")

    # Validate backup directory is writable
    backup_dir = Path(safety.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Test write permissions
    test_file = backup_dir / ".write_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        raise ValueError(f"Backup directory not writable: {backup_dir} - {str(e)}")

    # Validate log directory is writable
    log_dir = Path(safety.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Test log directory write permissions
    test_log = log_dir / ".write_test"
    try:
        test_log.write_text("test")
        test_log.unlink()
    except Exception as e:
        raise ValueError(f"Log directory not writable: {log_dir} - {str(e)}")

    # Validate disk space
    db_size = db_path.stat().st_size
    required_space = db_size * 2  # Database + backup + 100% buffer

    import shutil
    available_space = shutil.disk_usage(backup_dir).free

    if available_space < required_space:
        required_gb = required_space / (1024**3)
        available_gb = available_space / (1024**3)
        raise ValueError(
            f"Insufficient disk space. Required: {required_gb:.2f} GB, "
            f"Available: {available_gb:.2f} GB"
        )

    # Validate log level
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if safety.log_level.upper() not in valid_levels:
        raise ValueError(f"Invalid log level: {safety.log_level}. Must be one of {valid_levels}")


def load_orchestration_config(
    path: Path | str = Path("config/orchestration_config.yaml"),
    *,
    validate_production: bool = True,
    env_overrides: bool = True,
    env: Optional[Dict[str, str]] = None,
    env_prefix: str = "NAV_",
) -> OrchestrationConfig:
    """
    Load complete orchestration configuration with production safety validation

    Args:
        path: Path to configuration file
        validate_production: Enable production safety validation
        env_overrides: Enable environment variable overrides
        env: Environment variables (uses os.environ if None)
        env_prefix: Prefix for environment variable overrides

    Returns:
        Validated orchestration configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If configuration is invalid
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Configuration file not found: {p}")

    with open(p, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    # Normalize to lowercase keys at top level for resilience
    data = _lower_keys(raw)

    if env_overrides:
        _apply_env_overrides(data, env or dict(os.environ), env_prefix)

    try:
        config = OrchestrationConfig(**data)
    except ValidationError as e:
        raise ValueError(f"Invalid orchestration configuration: {e}") from e

    # Production safety validation
    if validate_production:
        validate_production_configuration(config)

    return config


def get_backup_configuration(config: OrchestrationConfig) -> 'BackupConfiguration':
    """
    Extract backup configuration for BackupManager

    Args:
        config: Complete orchestration configuration

    Returns:
        BackupConfiguration object suitable for BackupManager initialization
    """
    # Import here to avoid circular imports
    from .backup_manager import BackupConfiguration

    safety = config.production_safety

    return BackupConfiguration(
        backup_dir=Path(safety.backup_dir),
        retention_days=safety.backup_retention_days,
        verify_backups=safety.verify_backups,
        max_backup_size_gb=safety.max_backup_size_gb,
    )


def create_example_orchestration_config() -> str:
    """
    Create example orchestration configuration with production safety settings

    Returns:
        YAML configuration string
    """
    return """# PlanWise Navigator Orchestration Configuration
# Epic E043: Production Data Safety & Backup System

# Core simulation settings
simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 42
  target_growth_rate: 0.03

# Compensation parameters
compensation:
  cola_rate: 0.005
  merit_budget: 0.025

# Workforce modeling
workforce:
  total_termination_rate: 0.12
  new_hire_termination_rate: 0.25

# Production data safety settings
production_safety:
  # Database configuration
  db_path: "simulation.duckdb"

  # Backup settings
  backup_enabled: true
  backup_dir: "backups"
  backup_retention_days: 7
  backup_before_simulation: true
  verify_backups: true
  max_backup_size_gb: 10.0

  # Logging configuration
  log_level: "INFO"
  log_dir: "logs"

  # Safety requirements
  require_backup_before_run: true
  enable_emergency_backups: true

# Enterprise identifiers (optional)
scenario_id: "default"
plan_design_id: "standard_401k"

# Enrollment settings
enrollment:
  auto_enrollment:
    enabled: true
    scope: "all_eligible_employees"
    hire_date_cutoff: null
    window_days: 45
    default_deferral_rate: 0.06
    opt_out_grace_period: 30
    opt_out_rates:
      by_age:
        young: 0.10
        mid_career: 0.07
        mature: 0.05
        senior: 0.03
      by_income:
        low_income: 1.20
        moderate: 1.00
        high: 0.70
        executive: 0.50

# Plan eligibility
eligibility:
  waiting_period_days: null

plan_eligibility:
  minimum_age: null
"""
