"""The run matrix and configs of the #1232 validation script."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from planalign_orchestrator.config import load_simulation_config

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import validate_acquisition_minimum_wage as validation  # noqa: E402

sys.path.remove(str(SCRIPTS))

pytestmark = pytest.mark.fast


@pytest.fixture
def plan(tmp_path: Path) -> validation.Plan:
    return validation.Plan(
        census=tmp_path / "census.parquet",
        config=validation.ROOT / "config/simulation_config.yaml",
        out=tmp_path,
        start_year=2026,
        end_year=2029,
        minimum_wage=21.0,
        headcount=50,
    )


def test_matrix_covers_every_variant_seed_and_edge_config() -> None:
    runs = validation.planned_runs([1, 2, 3], edge=True)
    names = {run.name for run in runs}
    assert len(names) == len(runs) == 3 * 4 + 3 + 4 * 4
    assert {run.seed for run in runs if run.family in validation.EDGE_CONFIGS} == {1}
    assert len(validation.planned_runs([1], edge=False)) == 5


def test_baseline_configures_neither_change(plan: validation.Plan) -> None:
    raw = validation.build_config(plan, validation.Run("default", "baseline", 7))
    assert raw["workforce"]["acquisitions"] == []
    assert raw["compensation"]["minimum_wage"] == []
    assert raw["simulation"]["random_seed"] == 7


def test_groups_join_before_on_and_after_the_step(plan: validation.Plan) -> None:
    raw = validation.build_config(plan, validation.Run("default", "both", 7))
    step = raw["compensation"]["minimum_wage"][0]["effective_date"]
    joins = [item["effective_date"] for item in raw["workforce"]["acquisitions"]]
    assert joins[0] < step == joins[1] < joins[2]
    assert step == "2027-07-01"


@pytest.mark.parametrize("family", ("default", *validation.EDGE_CONFIGS))
def test_every_config_loads(plan: validation.Plan, family: str, tmp_path: Path) -> None:
    raw = validation.build_config(plan, validation.Run(family, "both", 7))
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    config = load_simulation_config(path, env_overrides=False)
    assert len(config.workforce.acquisitions) == 3
    assert config.compensation.minimum_wage[0].hourly_rate == 21.0
