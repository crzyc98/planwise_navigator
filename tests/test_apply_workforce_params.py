"""Tests for Apply Workforce Parameters feature (072).

Tests the extract_workforce_params() helper and the
ScenarioService.apply_workforce_params() method.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from planalign_api.models.scenario import (
    Scenario,
    ScenarioApplyOutcome,
    WorkforceParamsApplyRequest,
    WorkforceParamsApplyResult,
)
from planalign_api.services.scenario_service import (
    ScenarioService,
    extract_workforce_params,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_scenario(
    scenario_id: str,
    name: str,
    config_overrides: dict | None = None,
) -> Scenario:
    return Scenario(
        id=scenario_id,
        workspace_id="ws1",
        name=name,
        description=None,
        config_overrides=config_overrides or {},
        status="not_run",
        created_at=datetime(2025, 1, 1),
    )


FULL_CONFIG = {
    "simulation": {
        "name": "Baseline",
        "start_year": 2025,
        "end_year": 2027,
        "random_seed": 42,
        "target_growth_rate": 0.05,
    },
    "workforce": {
        "total_termination_rate": 0.12,
        "new_hire_termination_rate": 0.25,
    },
    "compensation": {
        "merit_budget_percent": 3.0,
        "cola_rate_percent": 2.5,
        "promotion_increase_percent": 8.0,
        "promotion_budget_percent": 1.5,
        "promotion_rate_multiplier": 1.0,
        "promotion_distribution_range_percent": 2.0,
        "target_compensation_growth_percent": 4.0,
    },
    "new_hire": {
        "strategy": "percentile",
        "target_percentile": 50,
        "compensation_variance_percent": 10,
        "market_scenario": "baseline",
        "age_distribution": [{"age": 30, "weight": 1.0}],
        "level_distribution_mode": "adaptive",
        "level_distribution": [{"level": 3, "percentage": 0.5}],
        "job_level_compensation": [{"level": 3, "name": "L3", "min_compensation": 80000, "max_compensation": 120000}],
        "level_market_adjustments": [{"level": 3, "adjustment_percent": 5}],
    },
    "dc_plan": {
        "eligibility_months": 3,
        "auto_enroll": True,
        "default_deferral_percent": 6,
        "match_enabled": True,
        "match_tiers": [{"employee_min": 0, "employee_max": 0.06, "match_rate": 1.0}],
        "core_enabled": False,
    },
    "promotion_hazard": {
        "base_rate": 0.05,
        "level_dampener_factor": 0.1,
        "age_multipliers": [{"age_band": "25-34", "multiplier": 1.2}],
        "tenure_multipliers": [{"tenure_band": "0-2", "multiplier": 1.5}],
    },
    "age_bands": [{"band_id": 1, "band_label": "25-34", "min_value": 25, "max_value": 35}],
    "tenure_bands": [{"band_id": 1, "band_label": "0-2", "min_value": 0, "max_value": 2}],
    "data_sources": {"census_parquet_path": "/data/census.parquet"},
    "advanced": {"engine": "sql", "log_level": "INFO"},
}


# ---------------------------------------------------------------------------
# extract_workforce_params tests
# ---------------------------------------------------------------------------

class TestExtractWorkforceParams:
    def test_extracts_workforce_sections(self):
        result = extract_workforce_params(FULL_CONFIG)
        assert "workforce" in result
        assert "compensation" in result
        assert "new_hire" in result

    def test_extracts_simulation_growth_rate_only(self):
        result = extract_workforce_params(FULL_CONFIG)
        assert result["simulation"] == {"target_growth_rate": 0.05}
        assert "name" not in result["simulation"]
        assert "start_year" not in result["simulation"]

    def test_extracts_seed_configs(self):
        result = extract_workforce_params(FULL_CONFIG)
        assert "promotion_hazard" in result
        assert "age_bands" in result
        assert "tenure_bands" in result

    def test_excludes_dc_plan(self):
        result = extract_workforce_params(FULL_CONFIG)
        assert "dc_plan" not in result

    def test_excludes_data_sources(self):
        result = extract_workforce_params(FULL_CONFIG)
        assert "data_sources" not in result

    def test_excludes_advanced(self):
        result = extract_workforce_params(FULL_CONFIG)
        assert "advanced" not in result

    def test_empty_config_returns_empty(self):
        result = extract_workforce_params({})
        assert result == {}

    def test_deep_copies_values(self):
        result = extract_workforce_params(FULL_CONFIG)
        result["workforce"]["total_termination_rate"] = 999
        assert FULL_CONFIG["workforce"]["total_termination_rate"] == 0.12


# ---------------------------------------------------------------------------
# ScenarioService.apply_workforce_params tests
# ---------------------------------------------------------------------------

class TestApplyWorkforceParams:
    def _make_service(self):
        storage = MagicMock()
        return ScenarioService(storage), storage

    def test_returns_none_when_source_not_found(self):
        service, storage = self._make_service()
        storage.get_scenario.return_value = None
        result = service.apply_workforce_params("ws1", "missing", ["t1"])
        assert result is None

    def test_applies_to_single_target(self):
        service, storage = self._make_service()

        source = _make_scenario("src", "Source", FULL_CONFIG)
        target = _make_scenario("tgt", "Target", {
            "dc_plan": {"match_enabled": True, "match_tiers": [{"match_rate": 0.5}]},
            "compensation": {"merit_budget_percent": 1.0},
        })
        updated = _make_scenario("tgt", "Target", {})

        storage.get_scenario.side_effect = lambda ws, sid: (
            source if sid == "src" else target if sid == "tgt" else None
        )
        storage.update_scenario.return_value = updated

        result = service.apply_workforce_params("ws1", "src", ["tgt"])

        assert result.total_applied == 1
        assert result.total_failed == 0
        assert result.results[0].success is True

        # Verify the merged config passed to update_scenario
        call_args = storage.update_scenario.call_args
        merged = call_args.kwargs.get("config_overrides") or call_args[1].get("config_overrides")
        assert merged["compensation"]["merit_budget_percent"] == 3.0
        assert merged["dc_plan"]["match_enabled"] is True
        assert merged["dc_plan"]["match_tiers"] == [{"match_rate": 0.5}]

    def test_preserves_dc_plan_in_target(self):
        service, storage = self._make_service()

        source = _make_scenario("src", "Source", FULL_CONFIG)
        target_dc = {
            "eligibility_months": 6,
            "auto_enroll": False,
            "core_enabled": True,
            "core_contribution_rate_percent": 5.0,
        }
        target = _make_scenario("tgt", "Target", {"dc_plan": target_dc})
        updated = _make_scenario("tgt", "Target", {})

        storage.get_scenario.side_effect = lambda ws, sid: (
            source if sid == "src" else target if sid == "tgt" else None
        )
        storage.update_scenario.return_value = updated

        service.apply_workforce_params("ws1", "src", ["tgt"])

        call_args = storage.update_scenario.call_args
        merged = call_args.kwargs.get("config_overrides") or call_args[1].get("config_overrides")
        assert merged["dc_plan"] == target_dc

    def test_partial_failure(self):
        service, storage = self._make_service()

        source = _make_scenario("src", "Source", FULL_CONFIG)
        target = _make_scenario("tgt1", "Target1", {})
        updated = _make_scenario("tgt1", "Target1", {})

        def get_scenario(ws, sid):
            if sid == "src":
                return source
            if sid == "tgt1":
                return target
            return None  # tgt2 not found

        storage.get_scenario.side_effect = get_scenario
        storage.update_scenario.return_value = updated

        result = service.apply_workforce_params("ws1", "src", ["tgt1", "tgt2"])

        assert result.total_applied == 1
        assert result.total_failed == 1
        assert result.results[0].success is True
        assert result.results[1].success is False
        assert "not found" in result.results[1].error

    def test_preserves_non_workforce_simulation_keys(self):
        service, storage = self._make_service()

        source = _make_scenario("src", "Source", FULL_CONFIG)
        target = _make_scenario("tgt", "Target", {
            "simulation": {"name": "My Scenario", "start_year": 2026, "random_seed": 99},
        })
        updated = _make_scenario("tgt", "Target", {})

        storage.get_scenario.side_effect = lambda ws, sid: (
            source if sid == "src" else target if sid == "tgt" else None
        )
        storage.update_scenario.return_value = updated

        service.apply_workforce_params("ws1", "src", ["tgt"])

        call_args = storage.update_scenario.call_args
        merged = call_args.kwargs.get("config_overrides") or call_args[1].get("config_overrides")
        assert merged["simulation"]["name"] == "My Scenario"
        assert merged["simulation"]["start_year"] == 2026
        assert merged["simulation"]["random_seed"] == 99
        assert merged["simulation"]["target_growth_rate"] == 0.05


# ---------------------------------------------------------------------------
# Pydantic model validation tests
# ---------------------------------------------------------------------------

class TestWorkforceParamsApplyRequest:
    def test_valid_request(self):
        req = WorkforceParamsApplyRequest(target_scenario_ids=["a", "b"])
        assert len(req.target_scenario_ids) == 2

    def test_empty_target_list_rejected(self):
        with pytest.raises(Exception):
            WorkforceParamsApplyRequest(target_scenario_ids=[])
