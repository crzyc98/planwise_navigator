"""dbt variable export functions.

E073: Config Module Refactoring - export module.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from .loader import SimulationConfig


def _export_simulation_vars(cfg: "SimulationConfig") -> Dict[str, Any]:
    """Export simulation, compensation, and eligibility settings to dbt vars.

    Handles: enterprise identifiers, simulation bounds, compensation rates,
    and eligibility settings.
    """
    dbt_vars: Dict[str, Any] = {}

    # Enterprise identifiers (CRITICAL: Must match Python event factory queries)
    dbt_vars["scenario_id"] = cfg.scenario_id if cfg.scenario_id else "default"
    dbt_vars["plan_design_id"] = cfg.plan_design_id if cfg.plan_design_id else "default"

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

    # Random seed
    if cfg.simulation.random_seed is not None:
        dbt_vars["random_seed"] = cfg.simulation.random_seed

    # Growth and workforce parameters
    if cfg.simulation.target_growth_rate is not None:
        dbt_vars["target_growth_rate"] = cfg.simulation.target_growth_rate

    # Termination rates
    if hasattr(cfg, "workforce") and cfg.workforce:
        if cfg.workforce.total_termination_rate is not None:
            dbt_vars["total_termination_rate"] = cfg.workforce.total_termination_rate
        if cfg.workforce.new_hire_termination_rate is not None:
            dbt_vars["new_hire_termination_rate"] = cfg.workforce.new_hire_termination_rate

    return dbt_vars


def _export_enrollment_vars(cfg: "SimulationConfig") -> Dict[str, Any]:
    """Export enrollment settings to dbt vars.

    Handles: auto-enrollment, opt-out rates, proactive enrollment, timing.
    """
    dbt_vars: Dict[str, Any] = {}

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
    base_rate = float(age_rates.young)  # Use young as typical base case
    dbt_vars["opt_out_rate_low_income"] = base_rate * float(income_rates.low_income)
    dbt_vars["opt_out_rate_moderate"] = base_rate * float(income_rates.moderate)
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

    return dbt_vars


def _export_legacy_vars(cfg: "SimulationConfig") -> Dict[str, Any]:
    """Export legacy extra-field configuration to dbt vars.

    Handles: deferral_auto_escalation, deferral_baseline, setup.
    These are optional dict-based configs from extra="allow".
    """
    dbt_vars: Dict[str, Any] = {}

    # Deferral auto-escalation (E035)
    try:
        dae = getattr(cfg, "deferral_auto_escalation", None)
        if isinstance(dae, dict):
            if "enabled" in dae:
                dbt_vars["deferral_escalation_enabled"] = bool(dae["enabled"])
            if "effective_day" in dae and dae["effective_day"]:
                dbt_vars["deferral_escalation_effective_mmdd"] = str(dae["effective_day"])
            if "increment_amount" in dae and dae["increment_amount"] is not None:
                dbt_vars["deferral_escalation_increment"] = float(dae["increment_amount"])
            if "maximum_rate" in dae and dae["maximum_rate"] is not None:
                dbt_vars["deferral_escalation_cap"] = float(dae["maximum_rate"])
            if "hire_date_cutoff" in dae and dae["hire_date_cutoff"]:
                dbt_vars["deferral_escalation_hire_date_cutoff"] = str(dae["hire_date_cutoff"])
            if "require_active_enrollment" in dae:
                dbt_vars["deferral_escalation_require_enrollment"] = bool(dae["require_active_enrollment"])
            if "first_escalation_delay_years" in dae and dae["first_escalation_delay_years"] is not None:
                dbt_vars["deferral_escalation_first_delay_years"] = int(dae["first_escalation_delay_years"])
    except Exception:
        pass

    # Deferral baseline mode (Option A default: frozen)
    try:
        db = getattr(cfg, "deferral_baseline", None)
        if isinstance(db, dict) and "mode" in db and db["mode"]:
            dbt_vars["deferral_baseline_mode"] = str(db["mode"]).lower()
        else:
            dbt_vars["deferral_baseline_mode"] = "frozen"
    except Exception:
        dbt_vars["deferral_baseline_mode"] = "frozen"

    # Staging/setup parameters
    try:
        setup = getattr(cfg, "setup", None)
        if isinstance(setup, dict):
            # census_parquet_path: make absolute relative to repo root
            cpp = setup.get("census_parquet_path")
            if cpp:
                cpp_path = Path(cpp)
                if not cpp_path.is_absolute():
                    repo_root = Path(__file__).resolve().parent.parent.parent
                    cpp_path = (repo_root / cpp_path).resolve()
                dbt_vars["census_parquet_path"] = str(cpp_path)

            # Optional plan-year & eligibility vars
            pysd = setup.get("plan_year_start_date")
            pyed = setup.get("plan_year_end_date")
            ew = setup.get("eligibility_waiting_period_days")
            if pysd:
                dbt_vars["plan_year_start_date"] = str(pysd)
            if pyed:
                dbt_vars["plan_year_end_date"] = str(pyed)
            if ew is not None:
                dbt_vars["eligibility_waiting_period_days"] = int(ew)

            # Optional contract enforcement toggle
            enf = setup.get("enforce_contracts")
            if enf is not None:
                dbt_vars["enforce_contracts"] = bool(enf)
    except Exception:
        pass

    return dbt_vars


def _export_employer_match_vars(cfg: "SimulationConfig") -> Dict[str, Any]:
    """Export employer match configuration to dbt vars.

    Epic E058: Enhanced employer match configuration with eligibility.
    Epic E084 Phase B: Custom match tiers configuration.
    """
    dbt_vars: Dict[str, Any] = {}

    employer_match_defaults = {
        'apply_eligibility': False,
        'eligibility': {
            'minimum_tenure_years': 0,
            'require_active_at_year_end': True,
            'minimum_hours_annual': 1000,
            'allow_new_hires': True,
            'allow_terminated_new_hires': False,
            'allow_experienced_terminations': False
        }
    }

    try:
        employer_match = cfg.employer_match
        if employer_match is not None:
            # Convert Pydantic model to dict if needed
            if hasattr(employer_match, 'model_dump'):
                employer_data = employer_match.model_dump()
            else:
                employer_data = employer_match if isinstance(employer_match, dict) else {}

            # Generate nested employer_match variable structure
            dbt_employer_match = {
                'apply_eligibility': employer_data.get('apply_eligibility', False),
                'eligibility': {
                    'minimum_tenure_years': employer_data.get('eligibility', {}).get('minimum_tenure_years', 0),
                    'require_active_at_year_end': employer_data.get('eligibility', {}).get('require_active_at_year_end', True),
                    'minimum_hours_annual': employer_data.get('eligibility', {}).get('minimum_hours_annual', 1000),
                    'allow_new_hires': employer_data.get('eligibility', {}).get('allow_new_hires', True),
                    'allow_terminated_new_hires': employer_data.get('eligibility', {}).get('allow_terminated_new_hires', False),
                    'allow_experienced_terminations': employer_data.get('eligibility', {}).get('allow_experienced_terminations', False)
                }
            }
            dbt_vars["employer_match"] = dbt_employer_match

            # Backward compatibility
            active_formula = employer_data.get("active_formula")
            formulas = employer_data.get("formulas")
            if active_formula is not None:
                dbt_vars["active_match_formula"] = str(active_formula)
            if formulas is not None:
                dbt_vars["match_formulas"] = formulas
        else:
            # Try legacy configuration from extra fields
            employer_legacy = getattr(cfg, "employer_match", None)
            if employer_legacy and isinstance(employer_legacy, dict):
                dbt_employer_match = {
                    'apply_eligibility': employer_legacy.get('apply_eligibility', False),
                    'eligibility': {
                        'minimum_tenure_years': employer_legacy.get('eligibility', {}).get('minimum_tenure_years', 0),
                        'require_active_at_year_end': employer_legacy.get('eligibility', {}).get('require_active_at_year_end', True),
                        'minimum_hours_annual': employer_legacy.get('eligibility', {}).get('minimum_hours_annual', 1000),
                        'allow_new_hires': employer_legacy.get('eligibility', {}).get('allow_new_hires', True),
                        'allow_terminated_new_hires': employer_legacy.get('eligibility', {}).get('allow_terminated_new_hires', False),
                        'allow_experienced_terminations': employer_legacy.get('eligibility', {}).get('allow_experienced_terminations', False)
                    }
                }
                dbt_vars["employer_match"] = dbt_employer_match

                if "active_formula" in employer_legacy:
                    dbt_vars["active_match_formula"] = str(employer_legacy["active_formula"])
                if "formulas" in employer_legacy:
                    dbt_vars["match_formulas"] = employer_legacy["formulas"]
            else:
                dbt_vars["employer_match"] = employer_match_defaults

    except Exception as e:
        import traceback
        print(f"Warning: Error processing employer_match configuration: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        dbt_vars["employer_match"] = employer_match_defaults

    # E084 Phase B: Export custom match tiers from dc_plan config
    # These are set via PlanAlign Studio UI and saved in scenario's config_overrides
    try:
        dc_plan = getattr(cfg, "dc_plan", None)
        if dc_plan is None and hasattr(cfg, "__dict__"):
            raw_config = cfg.__dict__.get("_raw_config", {})
            dc_plan = raw_config.get("dc_plan", {})

        if dc_plan:
            if isinstance(dc_plan, dict):
                dc_plan_dict = dc_plan
            elif hasattr(dc_plan, 'model_dump'):
                dc_plan_dict = dc_plan.model_dump()
            else:
                dc_plan_dict = {}

            # Export match_template (e.g., 'simple', 'tiered', 'safe_harbor', 'qaca')
            match_template = dc_plan_dict.get("match_template")
            if match_template:
                dbt_vars["match_template"] = str(match_template)

            # Export match_tiers (array of {employee_min, employee_max, match_rate})
            match_tiers = dc_plan_dict.get("match_tiers")
            if match_tiers and len(match_tiers) > 0:
                dbt_vars["match_tiers"] = match_tiers

            # Export match_cap_percent (decimal, e.g., 0.04 for 4%)
            match_cap_percent = dc_plan_dict.get("match_cap_percent")
            if match_cap_percent is not None:
                dbt_vars["match_cap_percent"] = float(match_cap_percent)

    except Exception as e:
        import traceback
        print(f"Warning: Error processing dc_plan match configuration: {e}")
        print(f"Traceback: {traceback.format_exc()}")

    return dbt_vars


def _export_compensation_vars(cfg: "SimulationConfig") -> Dict[str, Any]:
    """Export promotion compensation and job level settings to dbt vars.

    Handles: Epic E059 (promotion compensation), E082 (job level compensation).
    """
    dbt_vars: Dict[str, Any] = {}

    # Epic E059: Promotion compensation configuration
    promotion = cfg.compensation.promotion_compensation
    # Use flat config values from UI if set, else fall back to nested config
    if cfg.compensation.promotion_increase != 0.125:  # Not default - user set it
        dbt_vars["promotion_base_increase_pct"] = cfg.compensation.promotion_increase
    else:
        dbt_vars["promotion_base_increase_pct"] = promotion.base_increase_pct

    if cfg.compensation.promotion_distribution_range != 0.05:  # Not default
        dbt_vars["promotion_distribution_range"] = cfg.compensation.promotion_distribution_range
    else:
        dbt_vars["promotion_distribution_range"] = promotion.distribution_range

    dbt_vars["promotion_max_cap_pct"] = promotion.max_cap_pct
    dbt_vars["promotion_max_cap_amount"] = promotion.max_cap_amount
    dbt_vars["promotion_distribution_type"] = promotion.distribution_type
    dbt_vars["promotion_level_overrides"] = promotion.level_overrides or {}
    dbt_vars["promotion_normal_std_dev"] = promotion.advanced.normal_std_dev

    # E082: Promotion rate multiplier
    dbt_vars["promotion_rate_multiplier"] = cfg.compensation.promotion_rate_multiplier

    # Market adjustments
    if promotion.advanced.market_adjustments:
        dbt_vars["promotion_market_adjustments"] = promotion.advanced.market_adjustments

    # E082: Job level compensation from new_hire config
    try:
        new_hire_config = getattr(cfg, "new_hire", None)
        if new_hire_config is None and hasattr(cfg, "__dict__"):
            raw_config = cfg.__dict__.get("_raw_config", {})
            new_hire_config = raw_config.get("new_hire", {})

        if new_hire_config:
            job_level_comp = new_hire_config.get("job_level_compensation") if isinstance(new_hire_config, dict) else getattr(new_hire_config, "job_level_compensation", None)
            if job_level_comp and len(job_level_comp) > 0:
                dbt_vars["job_level_compensation"] = job_level_comp

            market_scenario = new_hire_config.get("market_scenario") if isinstance(new_hire_config, dict) else getattr(new_hire_config, "market_scenario", None)
            if market_scenario:
                market_adjustments = {
                    "conservative": -5,
                    "baseline": 0,
                    "competitive": 5,
                    "aggressive": 10,
                }
                dbt_vars["market_scenario_adjustment"] = market_adjustments.get(market_scenario, 0)

            level_adjustments = new_hire_config.get("level_market_adjustments") if isinstance(new_hire_config, dict) else getattr(new_hire_config, "level_market_adjustments", None)
            if level_adjustments:
                dbt_vars["level_market_adjustments"] = level_adjustments
    except Exception as e:
        import traceback
        print(f"Warning: Error processing new_hire configuration: {e}")
        print(f"Traceback: {traceback.format_exc()}")

    return dbt_vars


def _export_threading_vars(cfg: "SimulationConfig") -> Dict[str, Any]:
    """Export threading and event generation mode settings to dbt vars.

    Handles: E068C threading, E068G event generation mode, E077 cohort engine.
    """
    dbt_vars: Dict[str, Any] = {}

    # E068C Threading configuration
    e068c_config = cfg.get_e068c_threading_config()
    dbt_vars["dbt_threads"] = e068c_config.dbt_threads
    dbt_vars["event_shards"] = e068c_config.event_shards
    dbt_vars["max_parallel_years"] = e068c_config.max_parallel_years

    # E068G Event generation mode
    event_gen_mode = cfg.get_event_generation_mode()
    polars_settings = cfg.get_polars_settings()
    dbt_vars["event_generation_mode"] = event_gen_mode
    dbt_vars["polars_enabled"] = cfg.is_polars_mode_enabled()
    if event_gen_mode == "polars":
        dbt_vars["polars_output_path"] = polars_settings.output_path
        dbt_vars["polars_max_threads"] = polars_settings.max_threads

    # E077: Polars cohort engine
    dbt_vars["use_polars_engine"] = cfg.is_cohort_engine_enabled()
    dbt_vars["polars_cohort_dir"] = str(cfg.get_cohort_output_dir()) if cfg.is_cohort_engine_enabled() else "outputs/polars_cohorts"

    return dbt_vars


def _export_core_contribution_vars(cfg: "SimulationConfig") -> Dict[str, Any]:
    """Export employer core contribution settings to dbt vars.

    Handles nested employer_core_contribution configuration.
    """
    dbt_vars: Dict[str, Any] = {}

    try:
        core_contrib = getattr(cfg, "employer_core_contribution", None)
        if core_contrib:
            enabled = core_contrib.get("enabled")
            rate = core_contrib.get("contribution_rate")
            eligibility = core_contrib.get("eligibility") or {}

            # Flat vars (backward compatibility)
            if enabled is not None:
                dbt_vars["employer_core_enabled"] = bool(enabled)
            if rate is not None:
                dbt_vars["employer_core_contribution_rate"] = float(rate)

            if eligibility:
                min_tenure = eligibility.get("minimum_tenure_years")
                require_active = eligibility.get("require_active_at_year_end")
                min_hours = eligibility.get("minimum_hours_annual")
                allow_new_hires = eligibility.get("allow_new_hires")
                allow_terminated_new_hires = eligibility.get("allow_terminated_new_hires")
                allow_experienced_terminations = eligibility.get("allow_experienced_terminations")

                if min_tenure is not None:
                    dbt_vars["core_minimum_tenure_years"] = int(min_tenure)
                if require_active is not None:
                    dbt_vars["core_require_active_eoy"] = bool(require_active)
                if min_hours is not None:
                    dbt_vars["core_minimum_hours"] = int(min_hours)
                if allow_new_hires is not None:
                    dbt_vars["core_allow_new_hires"] = bool(allow_new_hires)
                if allow_terminated_new_hires is not None:
                    dbt_vars["core_allow_terminated_new_hires"] = bool(allow_terminated_new_hires)
                if allow_experienced_terminations is not None:
                    dbt_vars["core_allow_experienced_terminations"] = bool(allow_experienced_terminations)

            # Nested var (required by int_employer_eligibility.sql)
            dbt_core_nested: Dict[str, Any] = {}
            if enabled is not None:
                dbt_core_nested["enabled"] = bool(enabled)
            if rate is not None:
                dbt_core_nested["contribution_rate"] = float(rate)

            nested_elig: Dict[str, Any] = {}
            for key in (
                "minimum_tenure_years",
                "require_active_at_year_end",
                "minimum_hours_annual",
                "allow_new_hires",
                "allow_terminated_new_hires",
                "allow_experienced_terminations",
            ):
                if key in eligibility and eligibility.get(key) is not None:
                    nested_elig[key] = eligibility.get(key)

            if nested_elig:
                dbt_core_nested["eligibility"] = nested_elig

            if dbt_core_nested:
                dbt_vars["employer_core_contribution"] = dbt_core_nested
    except Exception:
        pass

    return dbt_vars


def to_dbt_vars(cfg: "SimulationConfig") -> Dict[str, Any]:
    """Map typed config to dbt vars compatible with existing models.

    Mirrors the existing `extract_dbt_vars_from_config` behavior in a typed way.

    This function has been decomposed into focused helper functions for
    maintainability (E073 Config Refactoring). Each helper handles a specific
    domain of configuration export.
    """
    # Compose dbt_vars from focused helper functions
    dbt_vars: Dict[str, Any] = {}
    dbt_vars.update(_export_simulation_vars(cfg))
    dbt_vars.update(_export_enrollment_vars(cfg))
    dbt_vars.update(_export_legacy_vars(cfg))
    dbt_vars.update(_export_employer_match_vars(cfg))
    dbt_vars.update(_export_compensation_vars(cfg))
    dbt_vars.update(_export_threading_vars(cfg))
    dbt_vars.update(_export_core_contribution_vars(cfg))
    return dbt_vars
