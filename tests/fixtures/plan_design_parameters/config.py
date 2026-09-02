"""Configuration helpers for per-design parameter integration coverage."""

from __future__ import annotations

from planalign_orchestrator.config import (
    PlanDesignAssignmentSettings,
    PlanDesignParametersMap,
    SimulationConfig,
)


def apply_two_design_parameters(config: SimulationConfig) -> SimulationConfig:
    """Return a copy configured for the same-family match acceptance case."""
    configured = config.model_copy(deep=True)
    configured.plan_design_id = None
    configured.plan_design_assignment = PlanDesignAssignmentSettings.model_validate(
        {
            "default_plan_design_id": "legacy_design",
            "rules": [
                {
                    "type": "hire_date_cutoff",
                    "cutoff": "2015-01-01",
                    "plan_design_id": "current_design",
                }
            ],
        }
    )
    configured.plan_design_parameters = PlanDesignParametersMap.model_validate(
        {
            "legacy_design": _parameter_set(
                match_rate=1.0,
                match_ceiling=0.03,
                core_rate=0.02,
                default_rate=0.03,
                window_days=45,
                scope="all_eligible_employees",
                escalation_increment=0.01,
                escalation_cap=0.10,
                waiting_days=0,
            ),
            "current_design": _parameter_set(
                match_rate=0.5,
                match_ceiling=0.06,
                core_rate=0.03,
                default_rate=0.06,
                window_days=30,
                scope="new_hires_only",
                escalation_increment=0.02,
                escalation_cap=0.08,
                waiting_days=90,
            ),
        }
    )
    configured.deferral_auto_escalation = dict(
        getattr(configured, "deferral_auto_escalation", {})
    )
    configured.deferral_auto_escalation.update(
        {
            "enabled": True,
            "effective_day": "01-01",
            "hire_date_cutoff": "1900-01-01",
            "first_escalation_delay_years": 0,
        }
    )
    return configured


def apply_equivalent_single_design_parameters(
    config: SimulationConfig,
) -> SimulationConfig:
    """Express the invariant fixture's legacy scalar terms as one keyed design."""
    configured = config.model_copy(deep=True)
    design_id = configured.plan_design_id or "default"
    configured.plan_design_assignment = None
    configured.plan_design_parameters = PlanDesignParametersMap.model_validate(
        {
            design_id: {
                "match": {
                    "cap_percent": 0.04,
                    "tiers": [
                        {
                            "employee_min": 0.0,
                            "employee_max": 0.03,
                            "match_rate": 1.0,
                        },
                        {
                            "employee_min": 0.03,
                            "employee_max": 0.05,
                            "match_rate": 0.5,
                        },
                    ],
                },
                "employer_core": {"contribution_rate": 0.02},
                "auto_enrollment": {
                    "default_deferral_rate": 0.04,
                    "window_days": 45,
                    "scope": "all_eligible_employees",
                },
                "deferral_escalation": {"increment": 0.01, "cap": 0.06},
                "eligibility": {"waiting_period_days": 0},
            }
        }
    )
    return configured


def _parameter_set(
    *,
    match_rate: float,
    match_ceiling: float,
    core_rate: float,
    default_rate: float,
    window_days: int,
    scope: str,
    escalation_increment: float,
    escalation_cap: float,
    waiting_days: int,
) -> dict[str, object]:
    return {
        "match": {
            "cap_percent": 0.04,
            "tiers": [
                {
                    "employee_min": 0.0,
                    "employee_max": match_ceiling,
                    "match_rate": match_rate,
                }
            ],
        },
        "employer_core": {"contribution_rate": core_rate},
        "auto_enrollment": {
            "default_deferral_rate": default_rate,
            "window_days": window_days,
            "scope": scope,
        },
        "deferral_escalation": {
            "increment": escalation_increment,
            "cap": escalation_cap,
        },
        "eligibility": {"waiting_period_days": waiting_days},
    }
