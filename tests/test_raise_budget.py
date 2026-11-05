"""One raise budget, with the share of employees receiving a raise (#1074)."""

import pytest

from planalign_api.routers.calibration import _merge_raise_budget
from planalign_orchestrator.calibration_runner import CalibrationParameterSet
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


def test_full_coverage_adds_no_dbt_var() -> None:
    assert "raise_coverage" not in _exported()


def test_partial_coverage_reaches_dbt() -> None:
    assert _exported(raise_coverage=0.9)["raise_coverage"] == 0.9


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
