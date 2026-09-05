"""Guard test for #510: dbt var() calls that no config source ever supplies.

#510 found 32 enrollment config keys documented in `simulation_config.yaml`,
referenced by `var('name', default)` in dbt models, and never exported by
`to_dbt_vars` — editing them did nothing, silently. This test makes that class
of bug fail CI instead of sitting unnoticed for a year: it collects every
`var('name', ...)` call under `dbt/models`, subtracts every name that
`dbt_project.yml` defaults or `to_dbt_vars` can export, and asserts the
remainder is exactly the documented, reasoned allow-list below.

`to_dbt_vars` exports many vars conditionally (behind `dc_plan`/Studio UI
fields, `new_hire` overrides, etc.), so a single default-config call
under-reports what the export layer actually covers. `_maximal_config` sets
every such conditional field so its export result is a superset covering all
reachable branches — a var missing from *that* union is genuinely never
wired, not just unset in the shipped default.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.config.export import (
    DBT_VAR_DEFERRED,
    DBT_VAR_PER_DESIGN,
    dbt_var_disposition,
    to_dbt_vars,
)

pytestmark = [pytest.mark.fast, pytest.mark.config]

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_MODELS_DIR = REPO_ROOT / "dbt" / "models"
DBT_PROJECT_YML = REPO_ROOT / "dbt" / "dbt_project.yml"

_VAR_CALL_RE = re.compile(r"var\(\s*['\"]([a-zA-Z0-9_]+)['\"]")

# Vars supplied outside to_dbt_vars(), via a per-invocation `--vars` merge at
# dbt-call time rather than the config export layer.
_ORCHESTRATOR_INJECTED_VARS = {
    # hazard_cache_manager.py merges {"hazard_params_hash": ...} into the dbt
    # invocation only when rebuilding hazard caches; it is never part of
    # to_dbt_vars() or a config default.
    "hazard_params_hash",
}

# var() calls with no config source anywhere (not to_dbt_vars, not
# dbt_project.yml, not an orchestrator invocation merge) and no plan to add
# one. Every entry needs a reason. This is not a place to silence a #510-style
# bug — if you're tempted to add something here because a test failed, first
# check whether it should be wired into to_dbt_vars instead (see #510).
_KNOWN_STALE_VARS = {
    "dbt_version": (
        "audit-trail placeholder in data-quality models; no config field exists "
        "to source it from"
    ),
    "irs_402g_limit": (
        "IRS elective-deferral limit constant; currently hardcoded rather than "
        "config-driven, pending a future feature"
    ),
}


def _referenced_vars() -> set[str]:
    names: set[str] = set()
    for sql_file in DBT_MODELS_DIR.rglob("*.sql"):
        names.update(_VAR_CALL_RE.findall(sql_file.read_text()))
    return names


def _dbt_project_vars() -> set[str]:
    data = yaml.safe_load(DBT_PROJECT_YML.read_text())
    return set((data.get("vars") or {}).keys())


def _base_config():
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.scenario_id = "guard_test"
    cfg.plan_design_id = "guard_test"
    return cfg


def _maximal_config():
    """A config that sets every field `to_dbt_vars` only exports conditionally.

    Mirrors a fully-populated Studio scenario: every optional `dc_plan`/
    `new_hire` field the export layer checks for is present, so its export
    result is a superset of every reachable branch.
    """
    cfg = _base_config()
    cfg.workforce.part_time_new_hire_pct = 0.05
    cfg.dc_plan = {
        "auto_enroll": True,
        "auto_enroll_hire_date_cutoff": "2025-01-01",
        "auto_enroll_window_days": 45,
        "auto_enroll_opt_out_grace_period": 30,
        "default_deferral_percent": 6.0,
        "auto_enroll_scope": "new_hires_only",
        "auto_escalation": True,
        "escalation_rate_percent": 1.0,
        "escalation_cap_percent": 10.0,
        "escalation_effective_day": "01-01",
        "escalation_delay_years": 1,
        "escalation_hire_date_cutoff": "2025-01-01",
        "voluntary_enrollment_rate": 0.5,
        "new_hire_opt_out_rate": 0.1,
        "deferral_spread_max_lift": 4,
        "match_magnet_enabled": True,
        "match_magnet_probability": 0.5,
        "max_voluntary_deferral_percent": 0.15,
        "eligibility_months": 3,
        "match_enabled": True,
        "match_template": "tiered",
        "match_tiers": [{"employee_min": 0.0, "employee_max": 0.06, "match_rate": 0.5}],
        "match_cap_percent": 0.04,
        "match_status": "graded_by_service",
        "match_graded_schedule": [
            {
                "service_years_min": 0,
                "service_years_max": 5,
                "match_rate": 0.5,
                "max_deferral_pct": 0.06,
            }
        ],
        "tenure_match_tiers": [
            {
                "min_years": 0,
                "max_years": 5,
                "match_rate": 0.5,
                "max_deferral_pct": 0.06,
            }
        ],
        "points_match_tiers": [
            {
                "min_points": 0,
                "max_points": 50,
                "match_rate": 0.5,
                "max_deferral_pct": 0.06,
            }
        ],
        "tenure_graded_bands": [
            {
                "min_years": 0,
                "max_years": 5,
                "tiers": [
                    {"employee_min": 0.0, "employee_max": 0.06, "match_rate": 1.0}
                ],
            }
        ],
        "match_min_tenure_years": 1,
        "match_require_year_end_active": True,
        "match_min_hours_annual": 1000,
        "match_allow_terminated_new_hires": False,
        "match_allow_experienced_terminations": False,
        "match_allow_new_hires": True,
        "core_min_tenure_years": 1,
        "core_require_year_end_active": True,
        "core_min_hours_annual": 1000,
        "core_allow_terminated_new_hires": False,
        "core_allow_experienced_terminations": False,
        "core_allow_new_hires": True,
        "core_enabled": True,
        "core_contribution_rate_percent": 3.0,
        "core_status": "graded_by_service",
        "core_graded_schedule": [
            {"service_years_min": 0, "service_years_max": 5, "contribution_rate": 0.03}
        ],
        "core_points_schedule": [
            {"min_points": 0, "max_points": 50, "contribution_rate": 0.03}
        ],
        "core_age_schedule": [{"min_age": 0, "max_age": 50, "contribution_rate": 0.03}],
        "core_integration_enabled": True,
    }
    cfg.new_hire = {
        "job_level_compensation": {"1": {"min": 40000, "max": 60000}},
        "age_distribution": [{"age": 25, "weight": 1.0}],
        "market_scenario": "baseline",
        "level_market_adjustments": {"1": 0},
    }
    cfg.setup = {"enforce_contracts": True}
    return cfg


def _all_exported_vars() -> set[str]:
    return set(to_dbt_vars(_base_config()).keys()) | set(
        to_dbt_vars(_maximal_config()).keys()
    )


class TestDbtVarCoverage:
    def test_formula_family_payload_owns_age_and_points_core_schedules(self):
        from tests.fixtures.plan_design_formula_families import (
            relation_contract_payload,
        )

        payload = relation_contract_payload()
        assert payload["age_design"]["employer_core"]["age_schedule"]
        assert payload["points_design"]["employer_core"]["points_schedule"]
        assert "employer_core_age_schedule" in DBT_VAR_PER_DESIGN
        assert "employer_core_points_schedule" in DBT_VAR_PER_DESIGN
        assert DBT_VAR_DEFERRED == frozenset()

    def test_every_exported_var_has_a_plan_design_disposition(self):
        dispositions = {dbt_var_disposition(name) for name in _all_exported_vars()}
        assert dispositions <= {"per_design", "global", "deferred"}
        assert DBT_VAR_PER_DESIGN <= _all_exported_vars()
        assert DBT_VAR_DEFERRED <= _all_exported_vars()

    def test_every_referenced_var_has_a_source(self):
        referenced = _referenced_vars()
        supplied = (
            _dbt_project_vars() | _all_exported_vars() | _ORCHESTRATOR_INJECTED_VARS
        )

        dead = referenced - supplied - set(_KNOWN_STALE_VARS)
        assert not dead, (
            f"dbt var() call(s) with no config source and no allow-list entry: "
            f"{sorted(dead)}. Either export them from to_dbt_vars(), add a "
            "dbt_project.yml default, or add them to _KNOWN_STALE_VARS with a "
            "reason (see #510)."
        )

    def test_known_stale_allowlist_is_still_accurate(self):
        """Allow-list entries must stay both referenced and unsupplied.

        Otherwise the list silently drifts into stale documentation instead of
        being a live guard.
        """
        referenced = _referenced_vars()
        supplied = (
            _dbt_project_vars() | _all_exported_vars() | _ORCHESTRATOR_INJECTED_VARS
        )

        for name in _KNOWN_STALE_VARS:
            assert name in referenced, (
                f"{name!r} is allow-listed as stale but no var() call references "
                "it anymore - remove it from _KNOWN_STALE_VARS."
            )
            assert name not in supplied, (
                f"{name!r} is allow-listed as stale but is now supplied by "
                "config export, dbt_project.yml, or an orchestrator injection - "
                "remove it from _KNOWN_STALE_VARS."
            )
