"""One pay scale for existing staff and hires: opt-in config and level assignment."""

from pathlib import Path

import duckdb
from jinja2 import Environment
import pytest
import yaml
from pydantic import ValidationError

from planalign_orchestrator.config import SimulationConfig, to_dbt_vars

pytestmark = pytest.mark.fast
ROOT = Path(__file__).resolve().parents[1]
RANGES = [
    {"level": 1, "min_compensation": 40000, "max_compensation": 60000},
    {"level": 2, "min_compensation": 60000, "max_compensation": 90000},
    {"level": 3, "min_compensation": 90000, "max_compensation": 150000},
]


def config(new_hire: dict[str, object]) -> SimulationConfig:
    raw = yaml.safe_load((ROOT / "config/simulation_config.yaml").read_text())
    raw["new_hire"] = new_hire
    return SimulationConfig.model_validate(raw)


def level_for(pay: float) -> int:
    source = (ROOT / "dbt/macros/pay_scale_level.sql").read_text()
    env = Environment(extensions=["jinja2.ext.do"])
    module = env.from_string(source, globals={"var": lambda _: RANGES}).module
    sql = module.pay_scale_level(str(pay))
    return duckdb.sql(f"SELECT {sql}").fetchall()[0][0]


def test_off_by_default_keeps_dbt_vars_unchanged() -> None:
    assert "shared_pay_scale" not in to_dbt_vars(config({}))


def test_on_exports_the_flag_with_ranges() -> None:
    dbt_vars = to_dbt_vars(
        config({"shared_pay_scale": True, "job_level_compensation": RANGES})
    )
    assert dbt_vars["shared_pay_scale"] is True
    assert dbt_vars["job_level_compensation"] == RANGES


def test_requires_ranges() -> None:
    with pytest.raises(ValidationError, match="requires job_level_compensation"):
        config({"shared_pay_scale": True})


@pytest.mark.parametrize(
    ("pay", "level"),
    [(1000, 1), (59999, 1), (60000, 2), (89999, 2), (90000, 3), (2_000_000, 3)],
)
def test_every_pay_gets_a_level(pay: float, level: int) -> None:
    assert level_for(pay) == level


def test_ratio_is_off_by_default() -> None:
    assert "hire_pay_ratio" not in to_dbt_vars(config({}))


def test_ratio_exports_with_shared_scale() -> None:
    dbt_vars = to_dbt_vars(
        config(
            {
                "shared_pay_scale": True,
                "job_level_compensation": RANGES,
                "hire_pay_ratio": 0.95,
            }
        )
    )
    assert dbt_vars["hire_pay_ratio"] == 0.95


def test_ratio_requires_shared_scale() -> None:
    with pytest.raises(ValidationError, match="requires shared_pay_scale"):
        config({"hire_pay_ratio": 1.0})


def test_apply_carries_the_solved_ratio_and_growth() -> None:
    from planalign_api.routers.calibration import (
        CalibrationApplyRequest,
        CalibrationContext,
        _merge_calibration_candidate,
    )
    from planalign_orchestrator.calibration_runner import CalibrationParameterSet

    context = CalibrationContext(
        workspace_id="workspace",
        source_scenario_id="scenario",
        source_run_id="run",
        config_fingerprint="config",
        census_fingerprint="census",
        random_seed=42,
        start_year=2026,
        end_year=2030,
    )
    request = CalibrationApplyRequest(
        context=context,
        best_params=CalibrationParameterSet(
            cola_rate=0.02,
            merit_budget=0.07,
            new_hire_salary_growth_rate=0.055,
            hire_pay_ratio=0.92,
        ),
        target_comp_growth_pct=5.5,
    )
    original = config({"shared_pay_scale": True, "job_level_compensation": RANGES})
    new_hire = _merge_calibration_candidate(original.model_dump(mode="json"), request)[
        "new_hire"
    ]
    assert new_hire["hire_pay_ratio"] == 0.92
    assert new_hire["salary_growth_rate"] == 0.055
    assert new_hire["shared_pay_scale"] is True
