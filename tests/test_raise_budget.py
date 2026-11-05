"""One raise budget, with the share of employees receiving a raise (#1074)."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from planalign_api.routers.calibration import (
    _merge_calibration_candidate,
    _merge_raise_budget,
)
from planalign_api.services.template_service import TemplateService
from planalign_api.services.workspace_service import with_raise_budget
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


def test_new_workspaces_start_on_one_budget_at_the_same_level() -> None:
    config = with_raise_budget(
        {"compensation": {"merit_budget": 0.035, "cola_rate": 0.02}}
    )
    assert config["compensation"]["raise_budget"] == 0.055


def test_a_chosen_budget_is_not_replaced() -> None:
    config = with_raise_budget({"compensation": {"raise_budget": 0.04}})
    assert config["compensation"]["raise_budget"] == 0.04


def test_defaults_are_not_mutated() -> None:
    source = {"compensation": {"merit_budget": 0.035, "cola_rate": 0.02}}
    with_raise_budget(source)
    assert "raise_budget" not in source["compensation"]


def test_shared_config_stays_on_merit_and_cola() -> None:
    """Scenario files override merit on this base, so a budget here would mute them."""
    config = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    assert "raise_budget" not in config["compensation"]


def test_every_template_budget_matches_its_merit_and_cola() -> None:
    templates = TemplateService().list_templates()
    assert templates
    for template in templates:
        compensation = template.config["compensation"]
        total = compensation["merit_budget_percent"] + compensation["cola_rate_percent"]
        assert compensation["raise_budget"] == pytest.approx(total / 100)


def test_a_budget_keeps_the_merit_and_cola_shape() -> None:
    settings = CompensationSettings(
        merit_budget=0.035, cola_rate=0.02, raise_budget=0.045
    )
    assert settings.raise_flat_share == pytest.approx(0.02 / 0.055)


def test_the_shape_survives_a_config_round_trip() -> None:
    settings = CompensationSettings(
        merit_budget=0.035, cola_rate=0.02, raise_budget=0.045
    )
    reloaded = CompensationSettings.model_validate(settings.model_dump())
    assert reloaded.raise_flat_share == pytest.approx(0.02 / 0.055)


def test_shape_reaches_dbt_only_with_a_budget() -> None:
    assert "raise_flat_share" not in _exported()
    assert _exported(raise_budget=0.04)["raise_flat_share"] == pytest.approx(
        0.02 / 0.055
    )


def test_apply_keeps_merit_and_cola_as_the_budget_shape() -> None:
    request = SimpleNamespace(
        best_params=CalibrationParameterSet(merit_budget=0.045, cola_rate=0.0),
        context=SimpleNamespace(start_year=2026, end_year=2030),
        target_comp_growth_pct=3.0,
    )
    saved = {
        "compensation": {
            "merit_budget": 0.035,
            "cola_rate": 0.02,
            "raise_budget": 0.055,
        }
    }
    merged = _merge_calibration_candidate(saved, request)["compensation"]
    assert (merged["merit_budget"], merged["cola_rate"]) == (0.035, 0.02)
    assert merged["raise_budget"] == pytest.approx(0.045)
