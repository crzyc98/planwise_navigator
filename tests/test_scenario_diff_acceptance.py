"""Isolated acceptance fixture for the focused two-scenario diff."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from planalign_api.services.comparison_service import ComparisonService
from planalign_api.services.config_diff_service import ConfigDiffService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from tests.fixtures.scenario_diff import create_scenario_database


@pytest.mark.fast
def test_match_only_lever_moves_match_cost_not_workforce(tmp_path) -> None:
    rows_a = [
        {
            "employee_id": "E1",
            "year": 2025,
            "status": "Active",
            "enrolled": True,
            "deferral_rate": 0.06,
            "match": 3000,
            "compensation": 100000,
        }
    ]
    rows_b = [{**rows_a[0], "match": 4500}]
    metadata = [
        {"timestamp": datetime.now(timezone.utc), "seed": 426, "fingerprint": "a" * 64}
    ]
    paths = {
        "a": create_scenario_database(tmp_path, "a", rows_a, metadata),
        "b": create_scenario_database(tmp_path, "b", rows_b, metadata),
    }
    resolver = MagicMock()
    resolver.resolve.side_effect = lambda _, scenario_id: ResolvedDatabasePath(
        path=paths[scenario_id], source="scenario"
    )
    metric_service = ComparisonService(MagicMock(), resolver)
    metric_result = metric_service.compare_scenarios("ws", ["a", "b"], "a")

    storage = MagicMock()
    storage.get_merged_config.side_effect = lambda _, scenario_id: {
        "scenario_id": scenario_id,
        "plan_design_id": "standard",
        "employer_match": {
            "active_formula": "simple_match" if scenario_id == "a" else "stretch_match"
        },
    }
    config_result = ConfigDiffService(storage, resolver).compare(
        "ws", "a", "b", {"a": "A", "b": "B"}
    )

    workforce = metric_result.workforce_comparison[0]
    dc_plan = metric_result.dc_plan_comparison[0]
    assert [item.path for item in config_result.differences] == [
        "employer_match.active_formula"
    ]
    assert config_result.seeds_match is True
    assert workforce.deltas["b"].headcount == 0
    assert workforce.deltas["b"].avg_compensation == 0
    assert dc_plan.deltas["b"].total_employer_match == 1500
