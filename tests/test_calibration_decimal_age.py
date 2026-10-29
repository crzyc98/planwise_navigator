"""Regression for calibration age coercion reaching full-run date SQL."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
import yaml
from jinja2 import Template
from pydantic import ValidationError

from planalign_orchestrator.calibration_runner import CalibrationParameterSet
from planalign_api.routers.calibration import _merge_calibration_candidate

pytestmark = pytest.mark.fast


@pytest.mark.parametrize("age", [22, 25, 22.0, 25.0])
def test_calibration_age_survives_apply_and_sql(age: int | float) -> None:
    params = CalibrationParameterSet.model_validate_json(
        CalibrationParameterSet(
            new_hire_age_distribution=[{"age": age, "weight": 1.0}]
        ).model_dump_json()
    )
    request = SimpleNamespace(
        best_params=params,
        context=SimpleNamespace(start_year=2026, end_year=2030),
        target_comp_growth_pct=1.0,
    )
    merged = _merge_calibration_candidate({}, request)
    distribution = yaml.safe_load(yaml.safe_dump(merged))["new_hire"][
        "age_distribution"
    ]
    # Render the production hiring CTE, including its uncast age literal.
    sql = Path("dbt/models/intermediate/events/int_hiring_events.sql").read_text()
    cte = sql[
        sql.index("age_distribution AS (") : sql.index(
            "age_distribution_normalized AS ("
        )
    ]
    rendered = (
        Template(cte)
        .render(age_dist_var=distribution, ref=lambda name: name)
        .rsplit("),", 1)[0]
        + ")"
    )
    with duckdb.connect(":memory:") as conn:
        result = conn.execute(
            "WITH " + rendered + " SELECT MAKE_DATE(2026 - hire_age + 21, 1, 1) "
            "FROM age_distribution"
        ).fetchone()
    assert result == (date(2026 - int(age) + 21, 1, 1),)
    assert type(distribution[0]["age"]) is int
    assert distribution[0]["weight"] == 1.0


def test_calibration_rejects_fractional_age_without_rounding() -> None:
    with pytest.raises(ValidationError):
        CalibrationParameterSet(
            new_hire_age_distribution=[{"age": 22.5, "weight": 1.0}]
        )
