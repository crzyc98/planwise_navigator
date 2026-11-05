"""One raise budget, with the share of employees receiving a raise (#1074)."""

from pathlib import Path

import pytest
import yaml

from planalign_api.routers.calibration import _merge_raise_budget
from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
    CalibrationRunner,
)
from planalign_orchestrator.config import load_simulation_config, to_dbt_vars
from planalign_orchestrator.config.loader import SimulationConfig
from planalign_orchestrator.config.simulation import CompensationSettings

pytestmark = pytest.mark.fast


def test_existing_merit_and_cola_config_is_unchanged() -> None:
    settings = CompensationSettings(cola_rate=0.02, merit_budget=0.035)
    assert (settings.cola_rate, settings.merit_budget) == (0.02, 0.035)
    assert settings.raise_budget is None
    assert settings.raise_coverage == 1.0


def test_raise_budget_replaces_merit_and_cola() -> None:
    settings = CompensationSettings(
        cola_rate=0.02, merit_budget=0.035, raise_budget_percent=4.0
    )
    assert settings.merit_budget == pytest.approx(0.04)
    assert settings.cola_rate == 0.0


def test_raise_budget_can_be_zero() -> None:
    settings = CompensationSettings(raise_budget=0.0)
    assert (settings.merit_budget, settings.cola_rate) == (0.0, 0.0)


@pytest.mark.parametrize("coverage", [0.0, 1.5])
def test_coverage_must_be_a_share(coverage: float) -> None:
    with pytest.raises(ValueError):
        CompensationSettings(raise_coverage=coverage)


def _exported(**compensation: float) -> dict:
    config = load_simulation_config("config/simulation_config.yaml").model_dump()
    config["compensation"].update(compensation)
    return to_dbt_vars(SimulationConfig.model_validate(config))


def test_merit_and_cola_configs_add_no_dbt_vars() -> None:
    exported = _exported(raise_coverage=0.9)
    assert "raise_budget" not in exported
    assert "raise_coverage" not in exported


def test_full_coverage_exports_only_the_budget() -> None:
    exported = _exported(raise_budget=0.04)
    assert exported["raise_budget"] == 0.04
    assert "raise_coverage" not in exported


def test_partial_coverage_reaches_dbt() -> None:
    exported = _exported(raise_budget=0.04, raise_coverage=0.9)
    assert exported["raise_coverage"] == 0.9


def test_calibration_levers_move_a_set_budget(tmp_path) -> None:
    config = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    config["compensation"]["raise_budget"] = 0.04
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    run = CalibrationRun(
        start_year=2026,
        end_year=2027,
        config_path=path,
        database_path=tmp_path / "cal.duckdb",
    )
    runner = CalibrationRunner(run)
    runner._apply_param_overrides(
        CalibrationParameterSet(merit_budget=0.045, cola_rate=0.005)
    )
    assert runner._config.compensation.raise_budget == pytest.approx(0.05)


def test_apply_writes_the_budget_when_one_is_set() -> None:
    compensation = {"raise_budget_percent": 4.0}
    params = CalibrationParameterSet(merit_budget=0.045, cola_rate=0.0)
    _merge_raise_budget(compensation, params)
    assert compensation["raise_budget"] == pytest.approx(0.045)
    assert compensation["raise_budget_percent"] == pytest.approx(4.5)


def test_apply_leaves_merit_and_cola_configs_alone() -> None:
    compensation = {"merit_budget": 0.035}
    _merge_raise_budget(compensation, CalibrationParameterSet(merit_budget=0.04))
    assert "raise_budget" not in compensation


def test_clearing_the_budget_returns_to_merit_and_cola() -> None:
    settings = CompensationSettings(
        cola_rate=0.02,
        merit_budget=0.035,
        raise_budget=None,
        raise_budget_percent=None,
    )
    assert settings.raise_budget is None
    assert (settings.cola_rate, settings.merit_budget) == (0.02, 0.035)
