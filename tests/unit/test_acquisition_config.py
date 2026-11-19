"""Config and export tests for acquired groups (#1226)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb

import pytest
from jinja2 import Environment
from pydantic import ValidationError

from planalign_orchestrator.config import (
    AcquisitionSettings,
    SimulationConfig,
    load_simulation_config,
    to_dbt_vars,
)
from planalign_orchestrator.pipeline_orchestrator import warn_unreached_acquisitions
from planalign_orchestrator.run_metadata import compute_config_fingerprint

pytestmark = [pytest.mark.fast, pytest.mark.config]

ACME = {
    "id": "acme",
    "name": "Acme Co",
    "headcount": 120,
    "effective_date": "2026-07-01",
}


def _config(acquisitions: list[dict[str, Any]] | None = None) -> SimulationConfig:
    payload = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    ).model_dump()
    if acquisitions is not None:
        payload["workforce"]["acquisitions"] = acquisitions
    return SimulationConfig.model_validate(payload)


def test_no_acquisitions_exports_nothing_and_keeps_fingerprint() -> None:
    base = _config()
    explicit_empty = _config([])
    assert base.workforce.acquisitions == []
    assert "acquisitions" not in to_dbt_vars(base)
    assert compute_config_fingerprint(base) == compute_config_fingerprint(
        explicit_empty
    )


def test_acquisitions_export_as_list_var_without_display_name() -> None:
    config = _config([ACME])
    assert to_dbt_vars(config)["acquisitions"] == [
        {
            "id": "acme",
            "headcount": 120,
            "effective_date": "2026-07-01",
            "service_credit": "prior_service",
            "plan_entry": "acquisition_date",
        }
    ]


def test_acquisitions_change_the_fingerprint_but_names_do_not() -> None:
    base = _config()
    acquired = _config([ACME])
    renamed = _config([{**ACME, "name": "Renamed"}])
    assert compute_config_fingerprint(acquired) != compute_config_fingerprint(base)
    assert compute_config_fingerprint(acquired) == compute_config_fingerprint(renamed)


@pytest.mark.parametrize(
    "override",
    [
        {"id": "acme_co"},
        {"id": "acme's"},
        {"id": "-acme"},
        {"id": ""},
        {"id": "a" * 33},
        {"headcount": 0},
        {"headcount": -5},
        {"headcount": "10"},
        {"effective_date": None},
    ],
)
def test_acquisition_rejects_unsafe_or_missing_values(override: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AcquisitionSettings.model_validate({**ACME, **override})


def test_effective_date_is_required() -> None:
    payload = {key: value for key, value in ACME.items() if key != "effective_date"}
    with pytest.raises(ValidationError):
        AcquisitionSettings.model_validate(payload)


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate acquisition ids: acme"):
        _config([ACME, {**ACME, "effective_date": "2027-01-01"}])


@pytest.mark.parametrize("effective_date", ["2024-12-31", "2030-01-01"])
def test_effective_date_outside_simulated_years_still_loads(
    effective_date: str,
) -> None:
    """Calibration and validate-change reload a scenario over a shorter range."""
    config = _config([{**ACME, "effective_date": effective_date}])
    assert config.workforce.acquisitions[0].effective_date.isoformat() == effective_date


def test_run_range_that_misses_an_acquisition_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _config([ACME, {**ACME, "id": "later", "effective_date": "2028-03-01"}])
    with caplog.at_level(logging.WARNING):
        skipped = warn_unreached_acquisitions(config, 2025, 2027)
    assert skipped == ["later (2028-03-01)"]
    assert "ACQUISITIONS NOT APPLIED" in caplog.text
    assert warn_unreached_acquisitions(config, 2025, 2029) == []


def test_top_level_acquisitions_key_is_rejected() -> None:
    payload = _config().model_dump()
    payload["acquisitions"] = [ACME]
    with pytest.raises(ValidationError, match="workforce.acquisitions"):
        SimulationConfig.model_validate(payload)


def test_headcount_stays_inside_one_member_ssn_block() -> None:
    assert _config([{**ACME, "headcount": 99_999}]).workforce.acquisitions
    with pytest.raises(ValidationError):
        _config([{**ACME, "headcount": 100_000}])


@pytest.mark.parametrize(
    ("hired", "year", "year_end_tenure", "left", "expected"),
    [
        # 5 years carried in; year-end tenure advances by one per year
        ("2026-07-01", 2027, 6, "2027-03-01", 5),
        ("2026-07-01", 2027, 6, "2027-09-01", 6),
        ("2026-01-01", 2027, 6, "2027-01-01", 5),
        ("2026-12-31", 2027, 6, "2027-04-01", 5),
        ("2026-07-01", 2029, 8, "2029-02-01", 7),
    ],
)
def test_carried_tenure_keeps_prior_service_at_termination(
    hired: str, year: int, year_end_tenure: int, left: str, expected: int
) -> None:
    macros = Path(__file__).resolve().parents[2] / "dbt" / "macros"
    env = Environment(extensions=["jinja2.ext.do"])
    env.globals["calculate_tenure"] = env.from_string(
        (macros / "calculate_tenure.sql").read_text()
    ).module.calculate_tenure
    carried = env.from_string(
        (macros / "events" / "acquisitions.sql").read_text()
    ).module.carried_tenure_at
    sql = carried(f"DATE '{hired}'", str(year_end_tenure), year, f"DATE '{left}'")
    assert duckdb.sql(f"SELECT {sql}").fetchall() == [(expected,)]


def test_calibration_warns_when_its_range_misses_an_acquisition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from planalign_orchestrator import calibration_runner

    seen: list[tuple[int, int]] = []
    monkeypatch.setattr(
        calibration_runner, "verify_dc_prerequisites", lambda path: None
    )
    monkeypatch.setattr(
        calibration_runner,
        "warn_unreached_acquisitions",
        lambda config, start, end: seen.append((start, end)) or [],
    )
    runner = object.__new__(calibration_runner.CalibrationRunner)
    runner.database_path = Path("unused.duckdb")
    runner._config = _config([{**ACME, "effective_date": "2028-03-01"}])
    runner.run = type("Run", (), {"start_year": 2025, "end_year": 2026})()
    for step in ("_ensure_projection_tables", "_record_run_provenance"):
        monkeypatch.setattr(runner, step, lambda: None, raising=False)
    monkeypatch.setattr(runner, "_read_baseline_costs", lambda: {}, raising=False)
    monkeypatch.setattr(runner, "_build_all_years", lambda: [], raising=False)
    assert runner.run_calibration() == []
    assert seen == [(2025, 2026)]


def test_bridge_census_roll_forward_never_applies_acquisitions(
    tmp_path: Path,
) -> None:
    from planalign_orchestrator.census_rollforward import _bridge_config

    config = _config([{**ACME, "effective_date": "2024-06-01"}])
    bridge = _bridge_config(config, tmp_path / "census.parquet", 2024, 2025)
    assert bridge.workforce.acquisitions == []
    assert config.workforce.acquisitions[0].id == "acme"


# --- #1227: plan settings --------------------------------------------------

PLAN_SETTINGS = {
    "service_credit": "acquisition_date",
    "plan_entry": "waiting_period",
    "starting_participation_rate": 0.7,
    "starting_deferral_rate": 0.05,
}


def test_plan_settings_default_to_prior_service_entry_on_date_and_ae() -> None:
    acquisition = AcquisitionSettings.model_validate(ACME)
    assert acquisition.service_credit == "prior_service"
    assert acquisition.plan_entry == "acquisition_date"
    assert acquisition.starting_participation_rate is None
    assert acquisition.starting_deferral_rate is None


def test_plan_settings_export_and_round_trip() -> None:
    config = _config([{**ACME, **PLAN_SETTINGS}])
    exported = to_dbt_vars(config)["acquisitions"][0]
    assert {key: exported[key] for key in PLAN_SETTINGS} == PLAN_SETTINGS
    dumped = config.model_dump(mode="json")["workforce"]["acquisitions"][0]
    assert (
        SimulationConfig.model_validate(
            {**config.model_dump(mode="json"), "workforce": {"acquisitions": [dumped]}}
        ).workforce.acquisitions[0]
        == config.workforce.acquisitions[0]
    )


def test_plan_settings_change_the_fingerprint() -> None:
    assert compute_config_fingerprint(_config([ACME])) != compute_config_fingerprint(
        _config([{**ACME, **PLAN_SETTINGS}])
    )


@pytest.mark.parametrize(
    "override",
    [
        {"service_credit": "hire_date"},
        {"plan_entry": "next_quarter"},
        {"starting_participation_rate": 0.5},
        {"starting_deferral_rate": 0.05},
        {"starting_participation_rate": 1.5, "starting_deferral_rate": 0.05},
        {"starting_participation_rate": 0.5, "starting_deferral_rate": 0},
    ],
)
def test_plan_settings_reject_invalid_values(override: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AcquisitionSettings.model_validate({**ACME, **override})


def _acquisition_macros(acquisitions: list[dict[str, Any]]) -> Any:
    macros = Path(__file__).resolve().parents[2] / "dbt" / "macros"
    env = Environment(extensions=["jinja2.ext.do"])
    env.globals["var"] = lambda name, default=None: (
        acquisitions if name == "acquisitions" else default
    )
    return env.from_string((macros / "events" / "acquisitions.sql").read_text()).module


@pytest.mark.parametrize(
    ("employee_id", "expected"),
    [
        ("ACQ_acme_000001", "acme"),
        ("ACQ_acme-2_000042", "acme-2"),
        ("ACQ_acme_00001", None),
        ("ACQ_other_000001", None),
        ("NH_2026_000001", None),
        ("EMP_000001", None),
    ],
)
def test_acquisition_id_of_matches_only_built_member_ids(
    employee_id: str, expected: str | None
) -> None:
    module = _acquisition_macros([{"id": "acme"}, {"id": "acme-2"}])
    built = duckdb.sql(
        "SELECT " + module.acquisition_member_id("'acme'", "1")
    ).fetchall()
    assert built == [("ACQ_acme_000001",)]
    sql = module.acquisition_id_of(f"'{employee_id}'")
    assert duckdb.sql(f"SELECT {sql}").fetchall() == [(expected,)]


def test_acquisition_macros_render_nothing_without_acquisitions() -> None:
    module = _acquisition_macros([])
    assert module.acquisition_cohort("employee_id").strip() == ""
    sql = module.acquisition_id_of("'ACQ_acme_000001'")
    assert duckdb.sql(f"SELECT {sql}").fetchall() == [(None,)]


# --- #1228: who the group is -----------------------------------------------

OVERRIDES = {"relative_pay": 0.9, "average_age": 45, "average_service": 8.5}


def test_unset_overrides_mirror_staff_and_keep_the_fingerprint() -> None:
    acquisition = AcquisitionSettings.model_validate(ACME)
    assert acquisition.average_pay is None and acquisition.relative_pay is None
    assert acquisition.average_age is None and acquisition.average_service is None
    exported = to_dbt_vars(_config([ACME]))["acquisitions"][0]
    assert not set(exported) & {
        "average_pay",
        "relative_pay",
        "average_age",
        "average_service",
    }


def test_overrides_export_and_change_the_fingerprint() -> None:
    config = _config([{**ACME, **OVERRIDES}])
    exported = to_dbt_vars(config)["acquisitions"][0]
    assert {key: exported[key] for key in OVERRIDES} == OVERRIDES
    assert compute_config_fingerprint(config) != compute_config_fingerprint(
        _config([ACME])
    )
    amount = to_dbt_vars(_config([{**ACME, "average_pay": 82_000}]))
    assert amount["acquisitions"][0]["average_pay"] == 82_000


def test_overrides_reach_the_joining_macro() -> None:
    macros = Path(__file__).resolve().parents[2] / "dbt" / "macros"
    env = Environment(extensions=["jinja2.ext.do"])
    returned: list[Any] = []
    env.globals["var"] = lambda name, default=None: (
        [{**ACME, **OVERRIDES}] if name == "acquisitions" else default
    )
    env.globals["return"] = lambda value: returned.append(value) or ""
    module = env.from_string((macros / "events" / "acquisitions.sql").read_text())
    module.module.acquisitions_joining(2026)
    [joining] = returned
    assert {key: joining[0][key] for key in OVERRIDES} == OVERRIDES
    assert joining[0]["average_pay"] is None


@pytest.mark.parametrize(
    "override",
    [
        {"average_pay": 80_000, "relative_pay": 0.9},
        {"average_pay": 0},
        {"relative_pay": 0},
        {"relative_pay": 90},
        {"average_age": 17},
        {"average_age": 81},
        {"average_service": -1},
        {"average_age": 30, "average_service": 13},
    ],
)
def test_overrides_reject_invalid_values(override: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AcquisitionSettings.model_validate({**ACME, **override})
