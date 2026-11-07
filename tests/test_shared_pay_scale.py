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
