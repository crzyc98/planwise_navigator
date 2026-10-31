"""Starting-pay indexation contracts, using isolated SQL expression execution."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import duckdb
from jinja2 import Environment
import pytest
import yaml
from pydantic import ValidationError

from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
    CalibrationRunner,
)
from planalign_orchestrator.config import SimulationConfig, to_dbt_vars
from planalign_orchestrator.run_metadata import compute_config_fingerprint

pytestmark = pytest.mark.fast
ROOT = Path(__file__).resolve().parents[1]


def config(new_hire: dict[str, object] | None = None) -> SimulationConfig:
    raw = {"simulation": {"start_year": 2030, "end_year": 2032}, "compensation": {}}
    if new_hire is not None:
        raw["new_hire"] = new_hire
    return SimulationConfig.model_validate(raw)


@pytest.mark.parametrize("inputs", [None, {}, {"salary_growth_rate": 0}])
def test_default_and_export(inputs: dict[str, object] | None) -> None:
    cfg = config(inputs)
    assert cfg.new_hire["salary_growth_rate"] == 0
    assert "new_hire_salary_growth_rate" not in to_dbt_vars(cfg)


@pytest.mark.parametrize("rate", [0.0, 0.03, 0.25])
def test_decimal_rate_and_fingerprint(rate: float) -> None:
    cfg = config({"salary_growth_rate": rate, "market_scenario": "competitive"})
    assert to_dbt_vars(cfg).get("new_hire_salary_growth_rate", 0.0) == rate
    assert cfg.new_hire["market_scenario"] == "competitive"
    assert (
        compute_config_fingerprint(cfg)
        == compute_config_fingerprint(config({"market_scenario": "competitive"}))
    ) == (rate == 0)


@pytest.mark.parametrize("rate", [-0.01, 0.25001, 3, float("nan"), float("inf")])
def test_invalid_rate(rate: float) -> None:
    with pytest.raises(ValidationError, match="salary_growth_rate"):
        config({"salary_growth_rate": rate})


def salary_expression(model: str, alias: str) -> str:
    source = (ROOT / "dbt/models/intermediate" / f"{model}.sql").read_text()
    end = source.index(f" AS {alias}")
    return source[source.rindex("CAST(", 0, end) : end]


@pytest.mark.parametrize("rate", [0, 0.03, 0.25])
@pytest.mark.parametrize("year", [2030, 2032])
@pytest.mark.parametrize(
    "model,alias,base",
    [
        ("int_workforce_needs_by_level", "new_hire_avg_compensation", 81580.0),
        ("int_new_hire_compensation_staging", "avg_level_compensation", 70000.0),
    ],
)
def test_model_salary_expressions(
    tmp_path: Path,
    rate: float,
    year: int,
    model: str,
    alias: str,
    base: float,
) -> None:
    variables = {
        "new_hire_salary_growth_rate": rate,
        "start_year": 2030,
        "simulation_year": year,
        "market_scenario_adjustment": 5,
    }
    env = Environment()
    env.globals.update(
        var=lambda name, default=None: variables.get(name, default),
        simulation_year=year,
        resolve_parameter=lambda *args: (
            0.6 if args[2] == "compensation_percentile" else 1.1
        ),
    )
    macro = (ROOT / "dbt/macros/new_hire_salary_index.sql").read_text()
    expression = salary_expression(model, alias)
    rendered = env.from_string(macro + expression).render()
    legacy = env.from_string(
        expression.replace("{{ new_hire_salary_index() }}", "")
    ).render()
    query = "SELECT {} FROM (VALUES (1, 40000.0, 100000.0)) jlm(level_id, min_compensation, max_compensation)"
    with duckdb.connect(str(tmp_path / "salary.duckdb")) as conn:
        actual = conn.execute(query.format(rendered)).fetchone()[0]
        if rate == 0:
            assert actual == conn.execute(query.format(legacy)).fetchone()[0]
            assert "POWER" not in rendered
        else:
            expected = base * (1 + rate) ** (year - 2030)
            assert float(actual) == pytest.approx(expected, abs=0.005)


def test_calibration_fast_path_preserves_fixed_input(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(config({"salary_growth_rate": 0.03}).model_dump(mode="json"))
    )
    run = CalibrationRun(
        start_year=2030,
        end_year=2032,
        config_path=path,
        database_path=tmp_path / "calibration.duckdb",
    )
    runner = CalibrationRunner(run)
    runner._runner = Mock()
    runner._runner.execute_command.return_value = SimpleNamespace(success=True)
    runner._apply_param_overrides(
        CalibrationParameterSet(cola_rate=0.04, merit_budget=0.05)
    )
    runner._build_year(2032)
    assert runner._config.new_hire["salary_growth_rate"] == 0.03
    assert runner._runner.execute_command.call_count > 0
    for call in runner._runner.execute_command.call_args_list:
        assert call.kwargs["dbt_vars"]["new_hire_salary_growth_rate"] == 0.03
        assert call.kwargs["dbt_vars"]["start_year"] == 2030
    assert "salary_growth_rate" not in CalibrationParameterSet.model_fields


def test_calibration_apply_preserves_analyst_rate() -> None:
    from planalign_api.routers.calibration import (
        CalibrationApplyRequest,
        CalibrationContext,
        _merge_calibration_candidate,
    )

    original = config({"salary_growth_rate": 0.03}).model_dump(mode="json")
    context = CalibrationContext(
        workspace_id="workspace",
        source_scenario_id="scenario",
        source_run_id="run",
        config_fingerprint="config",
        census_fingerprint="census",
        random_seed=42,
        start_year=2030,
        end_year=2032,
    )
    request = CalibrationApplyRequest(
        context=context,
        best_params=CalibrationParameterSet(
            cola_rate=0.04,
            job_level_compensation=[
                {"level": 1, "min_compensation": 50000, "max_compensation": 90000},
            ],
        ),
        target_comp_growth_pct=5,
    )
    merged = _merge_calibration_candidate(original, request)
    assert merged["new_hire"]["salary_growth_rate"] == 0.03
    assert original["new_hire"] == {"salary_growth_rate": 0.03}
