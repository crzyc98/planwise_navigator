"""Config and executed SQL contracts for normalized opt-out probabilities."""

from pathlib import Path

import duckdb
from jinja2 import Environment
from pydantic import ValidationError
import pytest

from planalign_orchestrator.config.workforce import OptOutRatesSettings
from planalign_api.models.studio_config import StudioDCPlanConfig

pytestmark = pytest.mark.fast
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "bands",
    [
        [],
        [{"min": 1, "multiplier": 1}],
        [{"min": 0, "multiplier": -1}],
        [{"min": 0, "multiplier": 1}, {"min": 0, "multiplier": 2}],
    ],
)
def test_invalid_bands(bands: list[dict[str, float]]) -> None:
    with pytest.raises(ValidationError):
        OptOutRatesSettings(multipliers={"age": bands})
    with pytest.raises(ValidationError):
        StudioDCPlanConfig(opt_out_multipliers_age=bands)


def probabilities(
    target: float, bands: dict[str, list[dict[str, float]]]
) -> list[float]:
    source = (ROOT / "dbt/models/intermediate/int_enrollment_events.sql").read_text()
    sql = (
        source[
            source.index("opt_out_candidates_weighted AS (") : source.index(
                "-- Generate opt-out events using simplified logic"
            )
        ]
        .rstrip()
        .rstrip(",")
    )
    macro_source = (ROOT / "dbt/macros/deferral_change.sql").read_text()
    env = Environment()
    variables = {
        "opt_out_rate_target": target,
        **{f"opt_out_multipliers_{k}": v for k, v in bands.items()},
    }
    context = {"var": lambda key, default=None: variables.get(key, default)}
    module = env.from_string(macro_source).make_module(context)
    sql = env.from_string(sql).render(
        **context, deferral_change_multiplier=module.deferral_change_multiplier
    )
    with duckdb.connect() as con:
        rows = con.execute(
            "WITH opt_out_candidates_raw AS (SELECT age AS current_age, income AS current_compensation, 2025 AS simulation_year, false AS is_hire_year_new_hire FROM (VALUES (25, 40000), (35, 75000), (50, 150000), (65, 250000)) t(age,income)), "
            + sql
            + " SELECT optout_probability FROM opt_out_candidates"
        ).fetchall()
    return [float(row[0]) for row in rows]


def test_default_normalization_and_relative_propensity() -> None:
    bands = OptOutRatesSettings().multipliers.model_dump()
    values = probabilities(0.09, bands)
    assert sum(values) / len(values) == pytest.approx(0.09)
    assert values[0] > values[-1]


@pytest.mark.parametrize("weight", [0.0, 1.0])
def test_flat_and_zero_denominator(weight: float) -> None:
    assert probabilities(
        0.09, {dim: [{"min": 0, "multiplier": weight}] for dim in ("age", "income")}
    ) == pytest.approx([0.09] * 4)


def test_saturation_lowers_expected_rate() -> None:
    values = probabilities(0.9, OptOutRatesSettings().multipliers.model_dump())
    assert max(values) == 1
    assert min(values) >= 0
    assert sum(values) / len(values) < 0.9


def test_studio_override_export_and_validation() -> None:
    from planalign_orchestrator.config import load_simulation_config
    from planalign_orchestrator.config.export import to_dbt_vars
    from planalign_orchestrator.config.dbt_var_validation import validate_dbt_vars

    config = load_simulation_config(
        ROOT / "config/simulation_config.yaml", env_overrides=False
    )
    bands = [{"min": 0, "multiplier": 1}, {"min": 40, "multiplier": 2}]
    config.dc_plan = {
        "opt_out_rate_target": 0.15,
        "opt_out_multipliers_age": bands,
        "opt_out_rate_young": 0.99,
    }
    variables = to_dbt_vars(config)
    assert variables["opt_out_rate_target"] == 0.15
    assert variables["opt_out_multipliers_age"] == bands
    assert "opt_out_rate_young" not in variables
    assert not validate_dbt_vars(variables)
    assert validate_dbt_vars(
        {**variables, "opt_out_multipliers_age": [{"min": 10, "multiplier": 1}]}
    )
    assert validate_dbt_vars({**variables, "opt_out_rate_target": 1.1})


def test_recorded_rate_uses_candidates_and_handles_legacy_database() -> None:
    from planalign_api.services.analytics_service import AnalyticsService

    with duckdb.connect() as conn:
        assert AnalyticsService._get_opt_out_by_year(conn) == []
        conn.execute(
            "CREATE TABLE int_enrollment_events(simulation_year INTEGER, optout_candidate_count INTEGER, optout_realized_count INTEGER, optout_target_rate DOUBLE)"
        )
        conn.execute(
            "INSERT INTO int_enrollment_events VALUES (2025, 100, 8, 0.09), (2025, 100, 8, 0.09), (2026, 0, 0, 0.15)"
        )
        conn.execute(
            "INSERT INTO int_enrollment_events VALUES (2024, NULL, NULL, NULL)"
        )
        rows = AnalyticsService._get_opt_out_by_year(conn)
        assert len(rows) == 2
        assert rows[0].realized_rate == 0.08
        assert rows[0].target_rate == 0.09
        assert rows[0].candidate_count == 100
        assert rows[1].realized_rate is None
