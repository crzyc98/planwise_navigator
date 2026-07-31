"""Load-time validation for employer core schedules and integration."""

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


def _integrated_config(
    *,
    base_rate: float = 0.03,
    disparity_rate: float = 0.027,
    level_mode: str = "ss_wage_base",
    level_value: float | None = None,
    start_year: int = 2025,
    end_year: int = 2025,
    studio: bool = False,
) -> dict:
    config = {
        "simulation": {
            "start_year": start_year,
            "end_year": end_year,
            "random_seed": 42,
        },
        "compensation": {},
    }
    integration = {
        "enabled": True,
        "level_mode": level_mode,
        "level_value": level_value,
        "disparity_rate": disparity_rate,
    }
    if studio:
        config["dc_plan"] = {
            "core_status": "flat",
            "core_contribution_rate_percent": base_rate * 100,
            "core_integration_enabled": True,
            "core_integration_level_mode": level_mode,
            "core_integration_level_value": level_value,
            "core_integration_disparity_rate": disparity_rate,
        }
    else:
        config["employer_core_contribution"] = {
            "enabled": True,
            "status": "flat",
            "contribution_rate": base_rate,
            "integration": integration,
        }
    return config


@pytest.mark.parametrize(
    ("base_rate", "disparity_rate", "level_mode", "level_value", "limit", "bound"),
    [
        (0.03, 0.08, "ss_wage_base", None, "3.00%", "base rate"),
        (0.08, 0.06, "ss_wage_base", None, "5.70%", "disparity factor"),
        (0.08, 0.05, "percent_of_ss_wage_base", 50, "4.30%", "disparity factor"),
    ],
)
def test_rejects_disparity_above_the_applicable_permitted_limit(
    base_rate: float,
    disparity_rate: float,
    level_mode: str,
    level_value: float | None,
    limit: str,
    bound: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        SimulationConfig.model_validate(
            _integrated_config(
                base_rate=base_rate,
                disparity_rate=disparity_rate,
                level_mode=level_mode,
                level_value=level_value,
            )
        )

    message = str(exc_info.value)
    assert limit in message
    assert f"Bound by: {bound}" in message


def test_legal_core_integration_passes_silently() -> None:
    SimulationConfig.model_validate(_integrated_config())


def test_integration_requires_level_value_for_non_wage_base_modes() -> None:
    with pytest.raises(ValidationError, match="level_value.*percent_of_ss_wage_base"):
        SimulationConfig.model_validate(
            _integrated_config(level_mode="percent_of_ss_wage_base")
        )


def test_negative_disparity_rate_is_rejected() -> None:
    with pytest.raises(ValidationError, match="disparity_rate"):
        SimulationConfig.model_validate(_integrated_config(disparity_rate=-0.01))


def test_enabled_integration_allows_a_zero_disparity_rate() -> None:
    SimulationConfig.model_validate(_integrated_config(disparity_rate=0.0))


def test_nonzero_disparity_requires_a_nonzero_base_rate() -> None:
    with pytest.raises(ValidationError, match="base contribution rate"):
        SimulationConfig.model_validate(_integrated_config(base_rate=0.0))


def test_fixed_dollar_validation_names_the_first_illegal_later_year() -> None:
    with pytest.raises(ValidationError, match="simulation year 2027"):
        SimulationConfig.model_validate(
            _integrated_config(
                base_rate=0.08,
                disparity_rate=0.05,
                level_mode="fixed_dollar",
                level_value=150000,
                end_year=2027,
            )
        )


@pytest.mark.parametrize("studio", [False, True])
def test_illegal_integration_is_rejected_for_direct_and_studio_shapes(
    studio: bool,
) -> None:
    with pytest.raises(ValidationError, match="disparity_rate 8.00%"):
        SimulationConfig.model_validate(
            _integrated_config(base_rate=0.03, disparity_rate=0.08, studio=studio)
        )


def test_studio_percent_disparity_key_is_not_a_validation_bypass() -> None:
    """A percent-shaped Studio rate must validate as a rate, not read as zero.

    Validation and dbt-var export share one normalizer precisely so an illegal
    rate cannot arrive under a key validation ignores. If the percent key were
    read as a missing decimal, this 8% rate would fall through as 0.0 and an
    illegal allocation would run.
    """
    config = _integrated_config(base_rate=0.03, disparity_rate=0.0, studio=True)
    config["dc_plan"].pop("core_integration_disparity_rate")
    config["dc_plan"]["core_integration_disparity_rate_percent"] = 8.0

    with pytest.raises(ValidationError, match="disparity_rate 8.00%"):
        SimulationConfig.model_validate(config)
