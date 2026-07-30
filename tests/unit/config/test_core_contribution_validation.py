"""Load-time validation for age-banded employer core contribution schedules."""

import pytest
from pydantic import ValidationError

from planalign_orchestrator.config.loader import SimulationConfig


def _config_with(schedule: list[dict], *, studio: bool = False) -> dict:
    config = {
        "simulation": {"start_year": 2025, "end_year": 2025, "random_seed": 42},
        "compensation": {},
    }
    if studio:
        config["dc_plan"] = {"core_status": "age_banded", "core_age_schedule": schedule}
    else:
        config["employer_core_contribution"] = {
            "status": "age_banded",
            "contribution_rate": 0.03,
            "age_schedule": schedule,
        }
    return config


@pytest.mark.parametrize("studio", [False, True])
def test_accepts_contiguous_age_schedule_and_empty_fallback(studio: bool) -> None:
    valid = [
        {"min_age": 0, "max_age": 30, "contribution_rate": 0.03},
        {"min_age": 30, "max_age": None, "contribution_rate": 0.06},
    ]
    SimulationConfig.model_validate(_config_with(valid, studio=studio))
    SimulationConfig.model_validate(_config_with([], studio=studio))


@pytest.mark.parametrize(
    "schedule",
    [
        [{"min_age": 1, "max_age": None, "contribution_rate": 0.03}],
        [
            {"min_age": 0, "max_age": 30, "contribution_rate": 0.03},
            {"min_age": 31, "max_age": None, "contribution_rate": 0.04},
        ],
        [
            {"min_age": 0, "max_age": 30, "contribution_rate": 0.03},
            {"min_age": 29, "max_age": None, "contribution_rate": 0.04},
        ],
        [{"min_age": 0, "max_age": 0, "contribution_rate": 0.03}],
        [
            {"min_age": 0, "max_age": None, "contribution_rate": 0.03},
            {"min_age": 30, "max_age": None, "contribution_rate": 0.04},
        ],
        [{"min_age": 0, "max_age": None, "contribution_rate": -0.01}],
    ],
)
def test_rejects_invalid_age_schedule(schedule: list[dict]) -> None:
    with pytest.raises(ValidationError):
        SimulationConfig.model_validate(_config_with(schedule))
