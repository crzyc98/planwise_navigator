"""The report's plain-words plan design states what the engine does."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from planalign_api.services.report_design import (
    ENGINE_AUTO_ENROLL_CUTOFF,
    ENGINE_AUTO_ENROLL_SCOPE,
    NOT_RECORDED,
    _band_percents,
    describe_plan_design,
)

pytestmark = [pytest.mark.fast]

ROOT = Path(__file__).resolve().parents[2]
ON = {"auto_enroll": True, "default_deferral_percent": 6.0}


def _design(dc: dict[str, Any], **config: Any):
    return describe_plan_design({"dc_plan": dc, **config})


# --------------------------------------------------------------------------
# Auto-enrollment scope and hire-date cutoff
# --------------------------------------------------------------------------
def test_engine_defaults_match_the_dbt_macro():
    macro = (ROOT / "dbt/macros/enrollment_eligibility.sql").read_text()
    assert f"var('auto_enrollment_scope', '{ENGINE_AUTO_ENROLL_SCOPE}')" in macro
    assert (
        f"var('auto_enrollment_hire_date_cutoff', '{ENGINE_AUTO_ENROLL_CUTOFF}')"
        in macro
    )


def test_all_eligible_scope_applies_the_hire_date_cutoff():
    text = _design(
        {
            **ON,
            "auto_enroll_scope": "all_eligible",
            "auto_enroll_hire_date_cutoff": "2024-01-01",
        }
    ).auto_enrollment
    assert text == (
        "Eligible employees hired on or after 2024-01-01 who are not yet enrolled "
        "are auto-enrolled at 6% of pay and may opt out."
    )


@pytest.mark.parametrize("blank", ["", "  ", None])
def test_blank_cutoff_states_the_engine_default(blank):
    text = _design(
        {
            **ON,
            "auto_enroll_scope": "all_eligible",
            "auto_enroll_hire_date_cutoff": blank,
        },
        enrollment={"auto_enrollment": {"hire_date_cutoff": "2010-01-01"}},
    ).auto_enrollment
    # export removes the var for a blank dc_plan value, so dbt's default wins.
    assert "hired on or after 2020-01-01 (the engine default)" in text


def test_new_hires_only_cutoff_applies_to_the_first_year_only():
    text = _design(
        {
            **ON,
            "auto_enroll_scope": "new_hires_only",
            "auto_enroll_hire_date_cutoff": "2025-01-01",
        }
    ).auto_enrollment
    assert text == (
        "In the first plan year, eligible employees hired on or after 2025-01-01 "
        "who are not yet enrolled are auto-enrolled at 6% of pay; after that, only "
        "each year's new hires are. Employees may opt out."
    )


def test_scope_and_cutoff_fall_back_like_the_export():
    inherited = _design(
        {"auto_enroll": True},
        enrollment={
            "auto_enrollment": {
                "scope": "new_hires_only",
                "hire_date_cutoff": "2023-06-01",
                "default_deferral_rate": 0.04,
            }
        },
    ).auto_enrollment
    assert inherited.startswith("In the first plan year")
    assert "on or after 2023-06-01 who" in inherited and "at 4% of pay" in inherited

    default = _design({"auto_enroll": True}).auto_enrollment
    assert default == (
        "Eligible employees hired on or after 2020-01-01 (the engine default) who "
        "are not yet enrolled are auto-enrolled and may opt out."
    )
    assert _design({**ON, "auto_enroll_scope": "odd"}).auto_enrollment == NOT_RECORDED


# --------------------------------------------------------------------------
# Units of every printed rate
# --------------------------------------------------------------------------
PERCENT_TIER = {
    "service_years_min": 0,
    "service_years_max": None,
    "match_rate": 70,
    "max_deferral_pct": 8,
}
FRACTION_TIER = {
    "service_years_min": 0,
    "service_years_max": None,
    "match_rate": 0.7,
    "max_deferral_pct": 0.08,
}
LEGACY_TIER = {"min_years": 0, "max_years": None, "rate": 70.0, "max_deferral_pct": 8.0}


@pytest.mark.parametrize("tier", [PERCENT_TIER, FRACTION_TIER, LEGACY_TIER])
def test_graded_match_reads_whole_percent_and_fraction_tiers(tier):
    match = _design(
        {"match_status": "graded_by_service", "match_graded_schedule": [tier]}
    ).match
    assert match == "By years of service. 0+ years: 70% of up to 8% deferred."


@pytest.mark.parametrize("tier", [PERCENT_TIER, FRACTION_TIER, LEGACY_TIER])
def test_band_units_match_the_engine_export(tier):
    from planalign_orchestrator.config import load_simulation_config
    from planalign_orchestrator.config.export import _export_employer_match_vars

    cfg = load_simulation_config(str(ROOT / "config/simulation_config.yaml"))
    cfg.dc_plan = {"match_status": "graded_by_service", "match_graded_schedule": [tier]}
    exported = _export_employer_match_vars(cfg)["employer_match_graded_schedule"][0]
    assert _band_percents(tier) == pytest.approx(
        (exported["rate"], exported["max_deferral_pct"])
    )


def test_legacy_employer_match_schedule_is_not_stated():
    """The engine only exports dc_plan.match_graded_schedule."""
    match = _design(
        {"match_status": "graded_by_service"},
        employer_match={"graded_schedule": [PERCENT_TIER]},
    ).match
    assert match == NOT_RECORDED


def test_core_bands_read_fraction_and_percent_rates():
    core = _design(
        {
            "core_status": "graded_by_service",
            "core_graded_schedule": [
                {
                    "service_years_min": 0,
                    "service_years_max": 5,
                    "contribution_rate": 0.02,
                },
                {"min_years": 5, "max_years": None, "rate": 4.0},
            ],
        }
    ).core
    assert core == (
        "By years of service: 2% (0–5 years), 4% (5+ years), whether or not the "
        "employee defers."
    )


def test_integration_reads_the_studio_percent_key():
    core = _design(
        {
            "core_status": "flat",
            "core_contribution_rate_percent": 3.0,
            "core_integration_enabled": True,
            "core_integration_level_mode": "ss_wage_base",
            "core_integration_disparity_rate_percent": 5.7,
        }
    ).core
    assert core.startswith(
        "3% of pay, plus 5.7% of pay above the Social Security wage base"
    )


def test_deferral_match_states_the_engine_cap():
    tiers = [{"employee_min": 0.0, "employee_max": 0.06, "match_rate": 1.0}]
    capped = _design({"match_tiers": tiers, "match_cap_percent": 0.04}).match
    assert capped == "100% of the first 6% deferred (up to 4% of pay)."
    uncapped = _design({"match_tiers": tiers}).match
    assert (
        uncapped
        == "100% of the first 6% deferred; the cap on the match is not recorded."
    )


# --------------------------------------------------------------------------
# Absent numbers are never printed as zero
# --------------------------------------------------------------------------
def test_absent_numbers_read_not_recorded_not_zero():
    design = _design(
        {
            "auto_escalation": True,
            "match_tiers": [{"employee_min": 0.0, "employee_max": 0.03}],
            "core_status": "flat",
            "core_integration_enabled": True,
            "core_integration_level_mode": "fixed_dollar",
        }
    )
    assert design.escalation == (
        "Deferrals rise each year (cap not recorded); the yearly increase is not "
        "recorded."
    )
    assert design.match == NOT_RECORDED
    assert design.core == NOT_RECORDED
    graded = _design(
        {
            "match_status": "graded_by_service",
            "match_graded_schedule": [{"service_years_min": 0, "match_rate": 0.5}],
            "core_status": "graded_by_service",
            "core_graded_schedule": [{"service_years_min": 0}],
        }
    )
    assert graded.match == NOT_RECORDED and graded.core == NOT_RECORDED
    for text in (*design.model_dump().values(), *graded.model_dump().values()):
        assert not re.search(r"(?<![\d.])0%", text), text


def test_integration_without_level_or_rate_says_so():
    core = _design(
        {
            "core_contribution_rate_percent": 2.0,
            "core_integration_enabled": True,
            "core_integration_level_mode": "fixed_dollar",
        }
    ).core
    assert core == (
        "2% of pay, plus an extra contribution on pay above an integration level "
        "that is not recorded (rate not recorded), whether or not the employee "
        "defers."
    )
