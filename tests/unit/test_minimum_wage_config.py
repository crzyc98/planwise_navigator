"""Config, export and run-check tests for the minimum wage floor (#1229)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
import pytest
from jinja2 import Environment
from pydantic import ValidationError

from planalign_api.models.studio_config import StudioCompensationConfig
from planalign_orchestrator.config import (
    MinimumWageStep,
    SimulationConfig,
    load_simulation_config,
    to_dbt_vars,
)
from planalign_orchestrator.exceptions import ConfigurationError
from planalign_orchestrator.minimum_wage import (
    require_census_hourly_rates,
    warn_unreached_minimum_wage_steps,
)
from planalign_orchestrator.run_metadata import compute_config_fingerprint

pytestmark = [pytest.mark.fast, pytest.mark.config]

STEP_2026 = {"hourly_rate": 20.0, "effective_date": "2026-07-01"}
STEP_2027 = {"hourly_rate": 21.0, "effective_date": "2027-01-01"}
MACROS = Path(__file__).resolve().parents[2] / "dbt" / "macros" / "events"


def _config(steps: list[dict[str, Any]] | None = None) -> SimulationConfig:
    payload = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    ).model_dump()
    if steps is not None:
        payload["compensation"]["minimum_wage"] = steps
    return SimulationConfig.model_validate(payload)


def test_no_minimum_wage_exports_nothing_and_keeps_fingerprint() -> None:
    base = _config()
    assert base.compensation.minimum_wage == []
    assert "minimum_wage_steps" not in to_dbt_vars(base)
    assert compute_config_fingerprint(base) == compute_config_fingerprint(_config([]))


def test_steps_export_sorted_by_date_and_change_the_fingerprint() -> None:
    config = _config([STEP_2027, STEP_2026])
    assert to_dbt_vars(config)["minimum_wage_steps"] == [STEP_2026, STEP_2027]
    assert compute_config_fingerprint(config) != compute_config_fingerprint(_config())


def test_two_steps_in_one_year_are_rejected() -> None:
    with pytest.raises(ValidationError, match="one minimum wage step per calendar"):
        _config([STEP_2026, {**STEP_2026, "effective_date": "2026-12-01"}])


@pytest.mark.parametrize(
    "override",
    [
        {"hourly_rate": 0},
        {"hourly_rate": -1},
        {"hourly_rate": 501},
        {"effective_date": None},
    ],
)
def test_step_rejects_bad_values(override: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        MinimumWageStep.model_validate({**STEP_2026, **override})


def test_step_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        MinimumWageStep.model_validate({**STEP_2026, "rate": 20})


def test_studio_config_round_trips_steps() -> None:
    payload = {"merit_budget_percent": 3.5, "minimum_wage": [STEP_2026, STEP_2027]}
    parsed = StudioCompensationConfig.model_validate(payload)
    assert parsed.model_dump(mode="json", exclude_none=True) == payload


def test_steps_outside_the_run_warn(caplog: pytest.LogCaptureFixture) -> None:
    config = _config([STEP_2026, {**STEP_2027, "effective_date": "2029-01-01"}])
    with caplog.at_level(logging.WARNING):
        skipped = warn_unreached_minimum_wage_steps(config, 2025, 2027)
    assert skipped == ["$21.00 (2029-01-01)"]
    assert "MINIMUM WAGE STEPS NOT APPLIED" in caplog.text
    assert warn_unreached_minimum_wage_steps(config, 2025, 2029) == []


def test_census_without_any_rate_is_rejected_naming_the_columns() -> None:
    conn = duckdb.connect()
    conn.execute(
        "CREATE TABLE stg_census_data AS SELECT CAST(NULL AS DOUBLE) AS census_hourly_rate"
    )
    with pytest.raises(ConfigurationError) as error:
        require_census_hourly_rates(conn)
    for column in ("hourly_rate", "hours_worked", "scheduled_hours_per_week"):
        assert column in str(error.value)
    conn.execute("INSERT INTO stg_census_data VALUES (18.5)")
    require_census_hourly_rates(conn)


def _macros() -> Any:
    env = Environment(extensions=["jinja2.ext.do"])
    return env.from_string((MACROS / "minimum_wage.sql").read_text()).module


@pytest.mark.parametrize(
    ("promotion_date", "merit_date", "through", "merit_on_through", "expected"),
    [
        # nothing after the floor: pay stays at the floor
        ("2026-02-01", "2026-03-01", "2026-12-31", "TRUE", 20_000.00),
        # promotion (+10%) and merit (+5%) after the floor compound on it
        ("2026-08-01", "2026-09-01", "2026-12-31", "TRUE", 23_100.00),
        # the raise event itself, dated before the promotion: merit only
        ("2026-10-01", "2026-09-01", "2026-09-01", "TRUE", 21_000.00),
        # the promotion event, merit on the same date applies after it
        ("2026-09-01", "2026-09-01", "2026-09-01", "FALSE", 22_000.00),
    ],
)
def test_pay_after_floor_compounds_later_events(
    promotion_date: str,
    merit_date: str,
    through: str,
    merit_on_through: str,
    expected: float,
) -> None:
    sql = _macros().pay_after_minimum_wage("t", f"DATE '{through}'", merit_on_through)
    rows = duckdb.sql(f"""
        WITH t AS (
          SELECT 20000.0 AS minimum_wage_salary, DATE '2026-07-01' AS minimum_wage_date,
            DATE '{promotion_date}' AS promotion_date, 1.10 AS promotion_ratio,
            DATE '{merit_date}' AS merit_date, 0.05 AS merit_raise_rate
        )
        SELECT {sql} FROM t
        """).fetchall()
    assert float(rows[0][0]) == pytest.approx(expected)
