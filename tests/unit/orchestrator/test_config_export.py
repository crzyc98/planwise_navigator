"""Tests for planalign_orchestrator.config.export module.

Covers the individual _export_* helper functions and the to_dbt_vars
composer, with focus on dc_plan processing, tier transformations,
and _REMOVE_KEY sentinel handling.
"""

import pytest

from planalign_orchestrator.config import load_simulation_config, to_dbt_vars
from planalign_orchestrator.config.export import (
    _REMOVE_KEY,
    _export_compensation_vars,
    _export_core_contribution_vars,
    _export_deferral_match_response_vars,
    _export_employer_match_vars,
    _export_enrollment_vars,
    _export_legacy_vars,
    _export_simulation_vars,
    _export_threading_vars,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    """Load the real config and apply overrides for test isolation."""
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.scenario_id = overrides.pop("scenario_id", "test")
    cfg.plan_design_id = overrides.pop("plan_design_id", "test_plan")
    cfg.simulation.start_year = overrides.pop("start_year", 2025)
    cfg.simulation.end_year = overrides.pop("end_year", 2026)
    cfg.simulation.random_seed = overrides.pop("random_seed", 42)
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


# ===========================================================================
# _export_simulation_vars
# ===========================================================================

class TestExportSimulationVars:

    def test_enterprise_identifiers_present(self):
        cfg = _make_config(scenario_id="sc1", plan_design_id="pd1")
        result = _export_simulation_vars(cfg)
        assert result["scenario_id"] == "sc1"
        assert result["plan_design_id"] == "pd1"

    def test_enterprise_identifiers_default_when_empty(self):
        cfg = _make_config()
        cfg.scenario_id = ""
        cfg.plan_design_id = ""
        result = _export_simulation_vars(cfg)
        assert result["scenario_id"] == "default"
        assert result["plan_design_id"] == "default"

    def test_enterprise_identifiers_default_when_none(self):
        cfg = _make_config()
        cfg.scenario_id = None
        cfg.plan_design_id = None
        result = _export_simulation_vars(cfg)
        assert result["scenario_id"] == "default"
        assert result["plan_design_id"] == "default"

    def test_simulation_bounds(self):
        cfg = _make_config(start_year=2026, end_year=2030)
        result = _export_simulation_vars(cfg)
        assert result["start_year"] == 2026
        assert result["end_year"] == 2030

    def test_compensation_rates(self):
        cfg = _make_config()
        cfg.compensation.cola_rate = 0.03
        cfg.compensation.merit_budget = 0.04
        result = _export_simulation_vars(cfg)
        assert result["cola_rate"] == 0.03
        assert result["merit_budget"] == 0.04

    def test_eligibility_vars(self):
        cfg = _make_config()
        cfg.eligibility.waiting_period_days = 60
        cfg.plan_eligibility.minimum_age = 21
        result = _export_simulation_vars(cfg)
        assert result["eligibility_waiting_days"] == 60
        assert result["minimum_service_days"] == 60
        assert result["minimum_age"] == 21

    def test_random_seed(self):
        cfg = _make_config(random_seed=99)
        result = _export_simulation_vars(cfg)
        assert result["random_seed"] == 99

    def test_growth_rate(self):
        cfg = _make_config()
        cfg.simulation.target_growth_rate = 0.05
        result = _export_simulation_vars(cfg)
        assert result["target_growth_rate"] == 0.05

    def test_workforce_termination_rates(self):
        cfg = _make_config()
        cfg.workforce.total_termination_rate = 0.15
        cfg.workforce.new_hire_termination_rate = 0.30
        result = _export_simulation_vars(cfg)
        assert result["total_termination_rate"] == 0.15
        assert result["new_hire_termination_rate"] == 0.30


# ===========================================================================
# _export_enrollment_vars
# ===========================================================================

class TestExportEnrollmentVars:

    def test_auto_enrollment_basics(self):
        cfg = _make_config()
        auto = cfg.enrollment.auto_enrollment
        auto.enabled = True
        auto.scope = "new_hires_only"
        auto.hire_date_cutoff = "2024-01-01"
        auto.window_days = 30
        auto.default_deferral_rate = 0.05
        auto.opt_out_grace_period = 15
        result = _export_enrollment_vars(cfg)
        assert result["auto_enrollment_enabled"] is True
        assert result["auto_enrollment_scope"] == "new_hires_only"
        assert result["auto_enrollment_hire_date_cutoff"] == "2024-01-01"
        assert result["auto_enrollment_window_days"] == 30
        assert result["auto_enrollment_default_deferral_rate"] == 0.05
        assert result["auto_enrollment_opt_out_grace_period"] == 15

    def test_opt_out_rates_by_age(self):
        cfg = _make_config()
        age_rates = cfg.enrollment.auto_enrollment.opt_out_rates.by_age
        age_rates.young = 0.12
        age_rates.mid_career = 0.08
        age_rates.mature = 0.06
        age_rates.senior = 0.04
        result = _export_enrollment_vars(cfg)
        assert result["opt_out_rate_young"] == 0.12
        assert result["opt_out_rate_mid"] == 0.08
        assert result["opt_out_rate_mature"] == 0.06
        assert result["opt_out_rate_senior"] == 0.04

    def test_opt_out_rates_by_income_computed(self):
        cfg = _make_config()
        age_rates = cfg.enrollment.auto_enrollment.opt_out_rates.by_age
        age_rates.young = 0.10
        income = cfg.enrollment.auto_enrollment.opt_out_rates.by_income
        income.low_income = 1.5
        income.moderate = 1.0
        income.high = 0.8
        income.executive = 0.5
        result = _export_enrollment_vars(cfg)
        assert result["opt_out_rate_low_income"] == pytest.approx(0.15)
        assert result["opt_out_rate_moderate"] == pytest.approx(0.10)
        assert result["opt_out_rate_high"] == pytest.approx(0.08)
        assert result["opt_out_rate_executive"] == pytest.approx(0.05)

    def test_proactive_enrollment(self):
        cfg = _make_config()
        pro = cfg.enrollment.proactive_enrollment
        pro.enabled = True
        pro.timing_window.min_days = 5
        pro.timing_window.max_days = 40
        pro.probability_by_demographics = {
            "young": 0.25,
            "mid_career": 0.45,
            "mature": 0.65,
            "senior": 0.75,
        }
        result = _export_enrollment_vars(cfg)
        assert result["proactive_enrollment_enabled"] is True
        assert result["proactive_enrollment_min_days"] == 5
        assert result["proactive_enrollment_max_days"] == 40
        assert result["proactive_enrollment_rate_young"] == 0.25
        assert result["proactive_enrollment_rate_senior"] == 0.75

    def test_enrollment_timing(self):
        cfg = _make_config()
        cfg.enrollment.timing.business_day_adjustment = False
        result = _export_enrollment_vars(cfg)
        assert result["enrollment_business_day_adjustment"] is False

    def test_dc_plan_auto_enrollment_overrides(self):
        """dc_plan dict overrides enrollment settings (UI path)."""
        cfg = _make_config()
        cfg.dc_plan = {
            "auto_enroll": True,
            "default_deferral_percent": 5.0,
            "auto_enroll_scope": "all_eligible",
            "auto_enroll_hire_date_cutoff": "2023-06-01",
            "auto_enroll_window_days": 60,
            "auto_enroll_opt_out_grace_period": 20,
        }
        result = _export_enrollment_vars(cfg)
        assert result["auto_enrollment_enabled"] is True
        assert result["auto_enrollment_default_deferral_rate"] == pytest.approx(0.05)
        assert result["auto_enrollment_scope"] == "all_eligible_employees"
        assert result["auto_enrollment_hire_date_cutoff"] == "2023-06-01"
        assert result["auto_enrollment_window_days"] == 60
        assert result["auto_enrollment_opt_out_grace_period"] == 20

    def test_dc_plan_scope_mapping_new_hires(self):
        cfg = _make_config()
        cfg.dc_plan = {"auto_enroll_scope": "new_hires_only"}
        result = _export_enrollment_vars(cfg)
        assert result["auto_enrollment_scope"] == "new_hires_only"

    def test_dc_plan_scope_mapping_unknown_passthrough(self):
        cfg = _make_config()
        cfg.dc_plan = {"auto_enroll_scope": "custom_scope"}
        result = _export_enrollment_vars(cfg)
        assert result["auto_enrollment_scope"] == "custom_scope"

    def test_dc_plan_opt_out_rate_overrides(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "opt_out_rate_young": 0.20,
            "opt_out_rate_mid": 0.15,
            "opt_out_rate_mature": 0.10,
            "opt_out_rate_senior": 0.05,
            "opt_out_rate_low_income": 0.25,
            "opt_out_rate_moderate": 0.18,
            "opt_out_rate_high": 0.12,
            "opt_out_rate_executive": 0.08,
        }
        result = _export_enrollment_vars(cfg)
        assert result["opt_out_rate_young"] == 0.20
        assert result["opt_out_rate_mid"] == 0.15
        assert result["opt_out_rate_mature"] == 0.10
        assert result["opt_out_rate_senior"] == 0.05
        assert result["opt_out_rate_low_income"] == 0.25
        assert result["opt_out_rate_executive"] == 0.08

    def test_dc_plan_escalation_settings(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "auto_escalation": True,
            "escalation_rate_percent": 1.0,
            "escalation_cap_percent": 10.0,
            "escalation_effective_day": "01-01",
            "escalation_delay_years": 1,
        }
        result = _export_enrollment_vars(cfg)
        assert result["deferral_escalation_enabled"] is True
        assert result["deferral_escalation_increment"] == pytest.approx(0.01)
        assert result["deferral_escalation_cap"] == pytest.approx(0.10)
        assert result["deferral_escalation_effective_mmdd"] == "01-01"
        assert result["deferral_escalation_first_delay_years"] == 1

    def test_dc_plan_escalation_hire_date_cutoff_with_value(self):
        cfg = _make_config()
        cfg.dc_plan = {"escalation_hire_date_cutoff": "2024-01-01"}
        result = _export_enrollment_vars(cfg)
        assert result["deferral_escalation_hire_date_cutoff"] == "2024-01-01"

    def test_dc_plan_escalation_hire_date_cutoff_empty_sets_remove_key(self):
        """When user clears the cutoff, sentinel marks key for removal."""
        cfg = _make_config()
        cfg.dc_plan = {"escalation_hire_date_cutoff": ""}
        result = _export_enrollment_vars(cfg)
        assert result["deferral_escalation_hire_date_cutoff"] is _REMOVE_KEY

    def test_dc_plan_escalation_hire_date_cutoff_none_sets_remove_key(self):
        cfg = _make_config()
        cfg.dc_plan = {"escalation_hire_date_cutoff": None}
        result = _export_enrollment_vars(cfg)
        assert result["deferral_escalation_hire_date_cutoff"] is _REMOVE_KEY

    def test_dc_plan_eligibility_months_conversion(self):
        cfg = _make_config()
        cfg.dc_plan = {"eligibility_months": 6}
        result = _export_enrollment_vars(cfg)
        assert result["eligibility_waiting_period_days"] == 180
        assert result["plan_eligibility_waiting_period_days"] == 180

    def test_dc_plan_model_dump_path(self):
        """When dc_plan has model_dump method (Pydantic model)."""
        class FakeDCPlan:
            def model_dump(self):
                return {"auto_enroll": False}
        cfg = _make_config()
        cfg.dc_plan = FakeDCPlan()
        result = _export_enrollment_vars(cfg)
        assert result["auto_enrollment_enabled"] is False

    def test_dc_plan_unknown_object_ignored(self):
        """When dc_plan is an object without model_dump, treat as empty."""
        cfg = _make_config()
        cfg.dc_plan = 42  # non-dict, no model_dump
        result = _export_enrollment_vars(cfg)
        # Should still have base enrollment vars from the typed config
        assert "opt_out_rate_young" in result


# ===========================================================================
# _export_legacy_vars
# ===========================================================================

class TestExportLegacyVars:

    def test_deferral_auto_escalation_full(self):
        cfg = _make_config()
        cfg.deferral_auto_escalation = {
            "enabled": True,
            "effective_day": "01-01",
            "increment_amount": 0.01,
            "maximum_rate": 0.10,
            "hire_date_cutoff": "2023-01-01",
            "require_active_enrollment": True,
            "first_escalation_delay_years": 2,
        }
        result = _export_legacy_vars(cfg)
        assert result["deferral_escalation_enabled"] is True
        assert result["deferral_escalation_effective_mmdd"] == "01-01"
        assert result["deferral_escalation_increment"] == 0.01
        assert result["deferral_escalation_cap"] == 0.10
        assert result["deferral_escalation_hire_date_cutoff"] == "2023-01-01"
        assert result["deferral_escalation_require_enrollment"] is True
        assert result["deferral_escalation_first_delay_years"] == 2

    def test_deferral_auto_escalation_missing(self):
        cfg = _make_config()
        result = _export_legacy_vars(cfg)
        # Should still set deferral_baseline_mode default
        assert result["deferral_baseline_mode"] == "frozen"

    def test_deferral_auto_escalation_partial(self):
        cfg = _make_config()
        cfg.deferral_auto_escalation = {"enabled": False}
        result = _export_legacy_vars(cfg)
        assert result["deferral_escalation_enabled"] is False
        assert "deferral_escalation_increment" not in result

    def test_deferral_auto_escalation_none_values_skipped(self):
        cfg = _make_config()
        cfg.deferral_auto_escalation = {
            "enabled": True,
            "effective_day": "",
            "increment_amount": None,
            "maximum_rate": None,
            "hire_date_cutoff": "",
        }
        result = _export_legacy_vars(cfg)
        assert result["deferral_escalation_enabled"] is True
        assert "deferral_escalation_effective_mmdd" not in result
        assert "deferral_escalation_increment" not in result
        assert "deferral_escalation_cap" not in result
        assert "deferral_escalation_hire_date_cutoff" not in result

    def test_deferral_baseline_mode_from_config(self):
        cfg = _make_config()
        cfg.deferral_baseline = {"mode": "CENSUS"}
        result = _export_legacy_vars(cfg)
        assert result["deferral_baseline_mode"] == "census"

    def test_deferral_baseline_default_frozen(self):
        cfg = _make_config()
        cfg.deferral_baseline = {"mode": ""}
        result = _export_legacy_vars(cfg)
        assert result["deferral_baseline_mode"] == "frozen"

    def test_deferral_baseline_not_dict(self):
        cfg = _make_config()
        cfg.deferral_baseline = "invalid"
        result = _export_legacy_vars(cfg)
        assert result["deferral_baseline_mode"] == "frozen"

    def test_setup_census_parquet_path_absolute(self):
        cfg = _make_config()
        cfg.setup = {"census_parquet_path": "/absolute/path.parquet"}
        result = _export_legacy_vars(cfg)
        assert result["census_parquet_path"] == "/absolute/path.parquet"

    def test_setup_census_parquet_path_relative(self):
        cfg = _make_config()
        cfg.setup = {"census_parquet_path": "data/census.parquet"}
        result = _export_legacy_vars(cfg)
        assert "census_parquet_path" in result
        # Should have been made absolute
        assert result["census_parquet_path"].startswith("/")

    def test_setup_plan_year_dates_and_eligibility(self):
        cfg = _make_config()
        cfg.setup = {
            "plan_year_start_date": "2025-01-01",
            "plan_year_end_date": "2025-12-31",
            "eligibility_waiting_period_days": 90,
            "enforce_contracts": True,
        }
        result = _export_legacy_vars(cfg)
        assert result["plan_year_start_date"] == "2025-01-01"
        assert result["plan_year_end_date"] == "2025-12-31"
        assert result["eligibility_waiting_period_days"] == 90
        assert result["enforce_contracts"] is True

    def test_setup_missing_gracefully(self):
        """When setup is not set as an extra, no setup vars are exported."""
        cfg = _make_config()
        # Remove any setup that the production config may have loaded
        if hasattr(cfg, "setup"):
            delattr(cfg, "setup")
        result = _export_legacy_vars(cfg)
        assert "census_parquet_path" not in result


# ===========================================================================
# _export_employer_match_vars
# ===========================================================================

class TestExportEmployerMatchVars:

    def test_employer_match_none_uses_defaults(self):
        cfg = _make_config()
        cfg.employer_match = None
        result = _export_employer_match_vars(cfg)
        assert "employer_match" in result
        em = result["employer_match"]
        assert em["apply_eligibility"] is False
        assert em["eligibility"]["minimum_hours_annual"] == 1000

    def test_employer_match_pydantic_model(self):
        from planalign_orchestrator.config.workforce import EmployerMatchSettings
        cfg = _make_config()
        cfg.employer_match = EmployerMatchSettings(
            apply_eligibility=True,
            active_formula="tiered_match",
            formulas={"tiered_match": {"type": "tiered", "tiers": []}},
        )
        result = _export_employer_match_vars(cfg)
        em = result["employer_match"]
        assert em["apply_eligibility"] is True
        assert result["active_match_formula"] == "tiered_match"
        assert "match_formulas" in result

    def test_employer_match_status_exported(self):
        from planalign_orchestrator.config.workforce import EmployerMatchSettings
        cfg = _make_config()
        cfg.employer_match = EmployerMatchSettings(
            employer_match_status="graded_by_service",
        )
        result = _export_employer_match_vars(cfg)
        assert result["employer_match_status"] == "graded_by_service"

    def test_employer_match_tenure_tiers(self):
        from planalign_orchestrator.config.workforce import (
            EmployerMatchSettings,
            TenureMatchTier,
        )
        cfg = _make_config()
        cfg.employer_match = EmployerMatchSettings(
            employer_match_status="tenure_based",
            tenure_match_tiers=[
                TenureMatchTier(min_years=0, max_years=5, match_rate=50, max_deferral_pct=6),
                TenureMatchTier(min_years=5, max_years=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        result = _export_employer_match_vars(cfg)
        tiers = result["tenure_match_tiers"]
        assert len(tiers) == 2
        assert tiers[0]["min_years"] == 0
        assert tiers[0]["rate"] == 50
        assert tiers[1]["rate"] == 100

    def test_employer_match_points_tiers(self):
        from planalign_orchestrator.config.workforce import (
            EmployerMatchSettings,
            PointsMatchTier,
        )
        cfg = _make_config()
        cfg.employer_match = EmployerMatchSettings(
            employer_match_status="points_based",
            points_match_tiers=[
                PointsMatchTier(min_points=0, max_points=50, match_rate=25, max_deferral_pct=4),
                PointsMatchTier(min_points=50, max_points=None, match_rate=75, max_deferral_pct=6),
            ],
        )
        result = _export_employer_match_vars(cfg)
        tiers = result["points_match_tiers"]
        assert len(tiers) == 2
        assert tiers[0]["min_points"] == 0
        assert tiers[0]["rate"] == 25
        assert tiers[1]["rate"] == 75

    def test_dc_plan_match_template(self):
        cfg = _make_config()
        cfg.dc_plan = {"match_template": "safe_harbor"}
        result = _export_employer_match_vars(cfg)
        assert result["match_template"] == "safe_harbor"

    def test_dc_plan_match_tiers(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "match_tiers": [
                {"employee_min": 0, "employee_max": 0.03, "match_rate": 1.0},
                {"employee_min": 0.03, "employee_max": 0.05, "match_rate": 0.5},
            ]
        }
        result = _export_employer_match_vars(cfg)
        assert len(result["match_tiers"]) == 2

    def test_dc_plan_match_cap_percent(self):
        cfg = _make_config()
        cfg.dc_plan = {"match_cap_percent": 0.04}
        result = _export_employer_match_vars(cfg)
        assert result["match_cap_percent"] == pytest.approx(0.04)

    def test_dc_plan_match_graded_schedule_decimal_conversion(self):
        """Decimal rates (<= 1) are converted to percentage for dbt macro."""
        cfg = _make_config()
        cfg.dc_plan = {
            "match_graded_schedule": [
                {
                    "service_years_min": 0,
                    "service_years_max": 5,
                    "match_rate": 0.50,
                    "max_deferral_pct": 0.06,
                },
                {
                    "service_years_min": 5,
                    "service_years_max": None,
                    "match_rate": 1.0,
                    "max_deferral_pct": 0.06,
                },
            ]
        }
        result = _export_employer_match_vars(cfg)
        schedule = result["employer_match_graded_schedule"]
        assert len(schedule) == 2
        assert schedule[0]["min_years"] == 0
        assert schedule[0]["max_years"] == 5
        assert schedule[0]["rate"] == pytest.approx(50.0)
        assert schedule[0]["max_deferral_pct"] == pytest.approx(6.0)
        assert schedule[1]["rate"] == pytest.approx(100.0)

    def test_dc_plan_match_graded_schedule_percentage_passthrough(self):
        """Percentage rates (> 1) pass through without conversion."""
        cfg = _make_config()
        cfg.dc_plan = {
            "match_graded_schedule": [
                {
                    "min_years": 0,
                    "max_years": None,
                    "rate": 50.0,
                    "max_deferral_pct": 6.0,
                },
            ]
        }
        result = _export_employer_match_vars(cfg)
        schedule = result["employer_match_graded_schedule"]
        assert schedule[0]["rate"] == 50.0
        assert schedule[0]["max_deferral_pct"] == 6.0

    def test_dc_plan_tenure_match_tiers_decimal_conversion(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "tenure_match_tiers": [
                {"min_years": 0, "max_years": None, "match_rate": 0.50, "max_deferral_pct": 0.06},
            ]
        }
        result = _export_employer_match_vars(cfg)
        tiers = result["tenure_match_tiers"]
        assert tiers[0]["rate"] == pytest.approx(50.0)
        assert tiers[0]["max_deferral_pct"] == pytest.approx(6.0)

    def test_dc_plan_points_match_tiers_decimal_conversion(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "points_match_tiers": [
                {"min_points": 0, "max_points": None, "match_rate": 0.75, "max_deferral_pct": 0.08},
            ]
        }
        result = _export_employer_match_vars(cfg)
        tiers = result["points_match_tiers"]
        assert tiers[0]["rate"] == pytest.approx(75.0)
        assert tiers[0]["max_deferral_pct"] == pytest.approx(8.0)

    def test_dc_plan_match_eligibility_overrides(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "match_min_tenure_years": 1,
            "match_require_year_end_active": False,
            "match_min_hours_annual": 500,
            "match_allow_terminated_new_hires": True,
            "match_allow_experienced_terminations": True,
            "match_allow_new_hires": False,
        }
        result = _export_employer_match_vars(cfg)
        em = result["employer_match"]
        elig = em["eligibility"]
        assert elig["minimum_tenure_years"] == 1
        assert elig["require_active_at_year_end"] is False
        assert elig["minimum_hours_annual"] == 500
        assert elig["allow_terminated_new_hires"] is True
        assert elig["allow_experienced_terminations"] is True
        assert elig["allow_new_hires"] is False
        assert em["apply_eligibility"] is True

    def test_dc_plan_match_tenure_rederives_allow_new_hires(self):
        """When tenure changes but allow_new_hires not set, re-derive it."""
        cfg = _make_config()
        cfg.dc_plan = {
            "match_min_tenure_years": 2,
            # allow_new_hires NOT set -> should be re-derived as False
        }
        result = _export_employer_match_vars(cfg)
        elig = result["employer_match"]["eligibility"]
        assert elig["allow_new_hires"] is False

    def test_dc_plan_match_tenure_zero_rederives_allow_new_hires_true(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "match_min_tenure_years": 0,
        }
        result = _export_employer_match_vars(cfg)
        elig = result["employer_match"]["eligibility"]
        assert elig["allow_new_hires"] is True

    def test_dc_plan_match_status_from_dc_plan(self):
        cfg = _make_config()
        cfg.dc_plan = {"match_status": "graded_by_service"}
        result = _export_employer_match_vars(cfg)
        assert result["employer_match_status"] == "graded_by_service"


# ===========================================================================
# _export_compensation_vars
# ===========================================================================

class TestExportCompensationVars:

    def test_promotion_compensation_defaults(self):
        cfg = _make_config()
        result = _export_compensation_vars(cfg)
        assert "promotion_base_increase_pct" in result
        assert "promotion_distribution_range" in result
        assert "promotion_max_cap_pct" in result
        assert "promotion_max_cap_amount" in result
        assert "promotion_distribution_type" in result
        assert "promotion_normal_std_dev" in result
        assert "promotion_rate_multiplier" in result

    def test_promotion_increase_user_override(self):
        cfg = _make_config()
        cfg.compensation.promotion_increase = 0.20  # Not default 0.125
        result = _export_compensation_vars(cfg)
        assert result["promotion_base_increase_pct"] == 0.20

    def test_promotion_distribution_range_user_override(self):
        cfg = _make_config()
        cfg.compensation.promotion_distribution_range = 0.10  # Not default 0.05
        result = _export_compensation_vars(cfg)
        assert result["promotion_distribution_range"] == 0.10

    def test_promotion_level_overrides_empty(self):
        cfg = _make_config()
        result = _export_compensation_vars(cfg)
        assert result["promotion_level_overrides"] == {} or result["promotion_level_overrides"] is None or isinstance(result["promotion_level_overrides"], dict)

    def test_market_adjustments(self):
        cfg = _make_config()
        cfg.compensation.promotion_compensation.advanced.market_adjustments = {
            "engineering": 1.1,
            "sales": 0.9,
        }
        result = _export_compensation_vars(cfg)
        assert result["promotion_market_adjustments"]["engineering"] == 1.1

    def test_new_hire_job_level_compensation(self):
        cfg = _make_config()
        cfg.new_hire = {
            "job_level_compensation": [
                {"level": 1, "min": 50000, "max": 70000},
                {"level": 2, "min": 70000, "max": 90000},
            ]
        }
        result = _export_compensation_vars(cfg)
        assert len(result["job_level_compensation"]) == 2

    def test_new_hire_market_scenario(self):
        cfg = _make_config()
        cfg.new_hire = {"market_scenario": "aggressive"}
        result = _export_compensation_vars(cfg)
        assert result["market_scenario_adjustment"] == 10

    def test_new_hire_market_scenario_conservative(self):
        cfg = _make_config()
        cfg.new_hire = {"market_scenario": "conservative"}
        result = _export_compensation_vars(cfg)
        assert result["market_scenario_adjustment"] == -5

    def test_new_hire_market_scenario_unknown(self):
        cfg = _make_config()
        cfg.new_hire = {"market_scenario": "unknown_scenario"}
        result = _export_compensation_vars(cfg)
        assert result["market_scenario_adjustment"] == 0

    def test_new_hire_level_market_adjustments(self):
        cfg = _make_config()
        cfg.new_hire = {
            "level_market_adjustments": {"1": 5, "2": 10}
        }
        result = _export_compensation_vars(cfg)
        assert result["level_market_adjustments"] == {"1": 5, "2": 10}


# ===========================================================================
# _export_threading_vars
# ===========================================================================

class TestExportThreadingVars:

    def test_threading_defaults(self):
        cfg = _make_config()
        result = _export_threading_vars(cfg)
        assert "dbt_threads" in result
        assert "event_shards" in result
        assert "max_parallel_years" in result
        assert result["event_generation_mode"] == "sql"


# ===========================================================================
# _export_core_contribution_vars
# ===========================================================================

class TestExportCoreContributionVars:

    def test_core_contribution_basic(self):
        cfg = _make_config()
        cfg.employer_core_contribution = {
            "enabled": True,
            "contribution_rate": 0.03,
            "eligibility": {
                "minimum_tenure_years": 1,
                "require_active_at_year_end": True,
                "minimum_hours_annual": 1000,
                "allow_new_hires": False,
                "allow_terminated_new_hires": False,
                "allow_experienced_terminations": False,
            },
        }
        result = _export_core_contribution_vars(cfg)
        assert result["employer_core_enabled"] is True
        assert result["employer_core_contribution_rate"] == 0.03
        assert result["core_minimum_tenure_years"] == 1
        assert result["core_require_active_eoy"] is True
        assert result["core_minimum_hours"] == 1000
        assert result["core_allow_new_hires"] is False

    def test_core_contribution_nested_structure(self):
        cfg = _make_config()
        cfg.employer_core_contribution = {
            "enabled": True,
            "contribution_rate": 0.05,
            "eligibility": {"minimum_tenure_years": 0},
        }
        result = _export_core_contribution_vars(cfg)
        nested = result["employer_core_contribution"]
        assert nested["enabled"] is True
        assert nested["contribution_rate"] == 0.05
        # allow_new_hires should be re-derived: tenure 0 -> True
        assert nested["eligibility"]["allow_new_hires"] is True

    def test_core_contribution_allow_new_hires_default_tenure_nonzero(self):
        """When tenure > 0 and allow_new_hires not set, defaults to False."""
        cfg = _make_config()
        cfg.employer_core_contribution = {
            "enabled": True,
            "contribution_rate": 0.02,
            "eligibility": {"minimum_tenure_years": 2},
        }
        result = _export_core_contribution_vars(cfg)
        nested = result["employer_core_contribution"]
        assert nested["eligibility"]["allow_new_hires"] is False

    def test_core_contribution_status_and_graded_schedule(self):
        cfg = _make_config()
        cfg.employer_core_contribution = {
            "enabled": True,
            "contribution_rate": 0.03,
            "status": "graded_by_service",
            "graded_schedule": [
                {"service_years_min": 0, "service_years_max": 5, "contribution_rate": 0.02},
                {"service_years_min": 5, "service_years_max": None, "contribution_rate": 0.04},
            ],
            "eligibility": {},
        }
        result = _export_core_contribution_vars(cfg)
        assert result["employer_core_status"] == "graded_by_service"
        schedule = result["employer_core_graded_schedule"]
        assert len(schedule) == 2
        assert schedule[0]["min_years"] == 0
        assert schedule[0]["rate"] == pytest.approx(2.0)
        assert schedule[1]["rate"] == pytest.approx(4.0)

    def test_core_contribution_points_schedule(self):
        cfg = _make_config()
        cfg.employer_core_contribution = {
            "enabled": True,
            "contribution_rate": 0.03,
            "points_schedule": [
                {"min_points": 0, "max_points": 40, "contribution_rate": 0.02},
                {"min_points": 40, "max_points": None, "contribution_rate": 0.05},
            ],
            "eligibility": {},
        }
        result = _export_core_contribution_vars(cfg)
        pts = result["employer_core_points_schedule"]
        assert len(pts) == 2
        assert pts[0]["rate"] == pytest.approx(2.0)
        assert pts[1]["rate"] == pytest.approx(5.0)

    def test_core_contribution_missing(self):
        """When employer_core_contribution is not set, no core vars are exported."""
        cfg = _make_config()
        # Remove any core contribution the production config may have loaded
        if hasattr(cfg, "employer_core_contribution"):
            delattr(cfg, "employer_core_contribution")
        if hasattr(cfg, "dc_plan"):
            delattr(cfg, "dc_plan")
        result = _export_core_contribution_vars(cfg)
        assert "employer_core_enabled" not in result

    def test_dc_plan_core_enabled_and_rate(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "core_enabled": True,
            "core_contribution_rate_percent": 2.0,
        }
        result = _export_core_contribution_vars(cfg)
        assert result["employer_core_enabled"] is True
        assert result["employer_core_contribution_rate"] == pytest.approx(0.02)
        nested = result["employer_core_contribution"]
        assert nested["enabled"] is True
        assert nested["contribution_rate"] == pytest.approx(0.02)

    def test_dc_plan_core_status_and_graded_schedule(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "core_status": "graded_by_service",
            "core_graded_schedule": [
                {"service_years_min": 0, "service_years_max": 3, "contribution_rate": 0.01},
                {"service_years_min": 3, "service_years_max": None, "contribution_rate": 0.03},
            ],
        }
        result = _export_core_contribution_vars(cfg)
        assert result["employer_core_status"] == "graded_by_service"
        schedule = result["employer_core_graded_schedule"]
        assert schedule[0]["rate"] == pytest.approx(1.0)
        assert schedule[1]["rate"] == pytest.approx(3.0)

    def test_dc_plan_core_points_schedule(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "core_points_schedule": [
                {"min_points": 0, "max_points": 30, "contribution_rate": 0.015},
                {"min_points": 30, "max_points": None, "contribution_rate": 0.04},
            ],
        }
        result = _export_core_contribution_vars(cfg)
        pts = result["employer_core_points_schedule"]
        assert pts[0]["rate"] == pytest.approx(1.5)
        assert pts[1]["rate"] == pytest.approx(4.0)

    def test_dc_plan_core_eligibility_overrides(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "core_min_tenure_years": 1,
            "core_require_year_end_active": False,
            "core_min_hours_annual": 500,
            "core_allow_terminated_new_hires": True,
            "core_allow_experienced_terminations": True,
            "core_allow_new_hires": False,
        }
        result = _export_core_contribution_vars(cfg)
        nested = result["employer_core_contribution"]
        elig = nested["eligibility"]
        assert elig["minimum_tenure_years"] == 1
        assert elig["require_active_at_year_end"] is False
        assert elig["minimum_hours_annual"] == 500
        assert elig["allow_new_hires"] is False

    def test_dc_plan_core_tenure_rederives_allow_new_hires(self):
        cfg = _make_config()
        cfg.dc_plan = {
            "core_min_tenure_years": 3,
            # allow_new_hires NOT set -> should be re-derived as False
        }
        result = _export_core_contribution_vars(cfg)
        elig = result["employer_core_contribution"]["eligibility"]
        assert elig["allow_new_hires"] is False

    def test_dc_plan_core_tenure_zero_rederives_allow_new_hires_true(self):
        cfg = _make_config()
        cfg.dc_plan = {"core_min_tenure_years": 0}
        result = _export_core_contribution_vars(cfg)
        elig = result["employer_core_contribution"]["eligibility"]
        assert elig["allow_new_hires"] is True


# ===========================================================================
# _export_deferral_match_response_vars
# ===========================================================================

class TestExportDeferralMatchResponseVars:

    def test_defaults_when_disabled(self):
        cfg = _make_config()
        cfg.deferral_match_response.enabled = False
        result = _export_deferral_match_response_vars(cfg)
        assert result["deferral_match_response_enabled"] is False

    def test_enabled_exports_all_fields(self):
        cfg = _make_config()
        cfg.deferral_match_response.enabled = True
        result = _export_deferral_match_response_vars(cfg)
        assert result["deferral_match_response_enabled"] is True
        assert "deferral_match_response_upward_participation_rate" in result
        assert "deferral_match_response_upward_maximize_rate" in result
        assert "deferral_match_response_upward_partial_factor" in result
        assert "deferral_match_response_downward_enabled" in result
        assert "deferral_match_response_downward_participation_rate" in result
        assert "deferral_match_response_downward_reduce_to_max_rate" in result
        assert "deferral_match_response_downward_partial_factor" in result
        assert "deferral_match_response_match_max_rate" in result

    def test_match_max_rate_default(self):
        cfg = _make_config()
        cfg.deferral_match_response.enabled = True
        result = _export_deferral_match_response_vars(cfg)
        # Default should be 0.06 when no formula is configured
        assert result["deferral_match_response_match_max_rate"] == pytest.approx(0.06)


# ===========================================================================
# to_dbt_vars - composer function
# ===========================================================================

class TestToDbtVars:

    def test_remove_key_sentinel_cleanup(self):
        """Keys marked with _REMOVE_KEY sentinel are removed from final output."""
        cfg = _make_config()
        # Set legacy cutoff, then dc_plan clears it
        cfg.deferral_auto_escalation = {
            "hire_date_cutoff": "2023-01-01",
        }
        cfg.dc_plan = {
            "escalation_hire_date_cutoff": "",  # User cleared it
        }
        result = to_dbt_vars(cfg)
        assert "deferral_escalation_hire_date_cutoff" not in result

    def test_dc_plan_overrides_legacy(self):
        """dc_plan (UI) settings override legacy YAML settings."""
        cfg = _make_config()
        cfg.deferral_auto_escalation = {
            "enabled": False,
            "increment_amount": 0.01,
        }
        cfg.dc_plan = {
            "auto_escalation": True,
            "escalation_rate_percent": 2.0,
        }
        result = to_dbt_vars(cfg)
        # dc_plan should win
        assert result["deferral_escalation_enabled"] is True
        assert result["deferral_escalation_increment"] == pytest.approx(0.02)

    def test_all_sections_present(self):
        """Smoke test that all major sections contribute to the output."""
        cfg = _make_config()
        result = to_dbt_vars(cfg)
        # Simulation
        assert "scenario_id" in result
        assert "random_seed" in result
        # Enrollment
        assert "auto_enrollment_enabled" in result
        assert "opt_out_rate_young" in result
        # Threading
        assert "dbt_threads" in result
        assert "event_generation_mode" in result
        # Compensation
        assert "promotion_base_increase_pct" in result
        # Legacy
        assert "deferral_baseline_mode" in result
        # Match response
        assert "deferral_match_response_enabled" in result

    def test_no_remove_key_in_final_output(self):
        """No _REMOVE_KEY sentinel values should leak into the final output."""
        cfg = _make_config()
        cfg.dc_plan = {"escalation_hire_date_cutoff": None}
        result = to_dbt_vars(cfg)
        for key, value in result.items():
            assert value is not _REMOVE_KEY, f"Sentinel leaked for key: {key}"

    def test_return_type_is_dict(self):
        cfg = _make_config()
        result = to_dbt_vars(cfg)
        assert isinstance(result, dict)
