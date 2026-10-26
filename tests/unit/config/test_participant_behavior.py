"""Config-only contract for epic #986; no simulation behavior is enabled."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from planalign_api.models.studio_config import StudioConfig
from planalign_orchestrator.config import SimulationConfig, load_simulation_config
from planalign_orchestrator.config.dbt_var_validation import validate_dbt_vars
from planalign_orchestrator.config.export import to_dbt_vars
from planalign_orchestrator.config.participant_behavior import (
    BelowDefaultSettings,
    DeferralAutoEscalationSettings,
    DeferralRateChangesSettings,
    EasyEnrollSettings,
)

pytestmark = [pytest.mark.fast, pytest.mark.config]
ROOT = Path(__file__).resolve().parents[3]

# Explicit expected values also keep the export/mapping tests independent of implementation.
DEFAULTS: dict[str, Any] = {
    "deferral_escalation_mode": "automatic",
    "deferral_escalation_participant_elected_signup_probability": 0.0,
    "easy_enroll_enabled": False,
    "easy_enroll_channel_share": 0.35,
    "easy_enroll_packages": [
        {"rate": 0.06, "share": 0.30},
        {"rate": 0.08, "share": 0.50},
        {"rate": 0.10, "share": 0.20},
    ],
    "easy_enroll_escalation_cap": 0.10,
    "enrollment_match_magnet_downward_enabled": False,
    "below_default_share_tiers": [{"max_auto_enroll_default_rate": None, "share": 0.0}],
    "below_default_steps": [
        {"pp": 1, "weight": 0.50},
        {"pp": 2, "weight": 0.30},
        {"pp": 3, "weight": 0.20},
    ],
    "deferral_rate_changes_enabled": False,
    "deferral_rate_changes_with_escalation_increase_probability": 0.03,
    "deferral_rate_changes_with_escalation_decrease_probability": 0.15,
    "deferral_rate_changes_without_escalation_increase_probability": 0.25,
    "deferral_rate_changes_without_escalation_decrease_probability": 0.075,
    "deferral_rate_changes_increase_steps": [
        {"pp": pp, "weight": weight}
        for pp, weight in [
            (1, 0.15),
            (2, 0.20),
            (3, 0.15),
            (5, 0.20),
            (7, 0.15),
            (10, 0.15),
        ]
    ],
    "deferral_rate_changes_decrease_steps": [
        {"pp": pp, "weight": weight}
        for pp, weight in [(1, 0.15), (2, 0.25), (3, 0.20), (5, 0.20), (8, 0.20)]
    ],
    "deferral_rate_changes_post_escalation_decrease_window_days": 90,
    "deferral_rate_changes_post_escalation_decrease_leaves_escalation": False,
    "deferral_rate_changes_stop_probability": 0.015,
    "deferral_rate_changes_restart_probability": 0.0,
}
OVERRIDES: dict[str, Any] = {
    "escalation_mode": "participant_elected",
    "escalation_participant_elected_signup_probability": 0.01,
    "easy_enroll_enabled": True,
    "easy_enroll_channel_share": 0.42,
    "easy_enroll_packages": [
        {"rate": 0.07, "share": 0.25},
        {"rate": 0.04, "share": 0.75},
    ],
    "easy_enroll_escalation_cap": 0.12,
    "match_magnet_downward_enabled": True,
    "below_default_share_tiers": [
        {"max_auto_enroll_default_rate": 0.03, "share": 0.10},
        {"max_auto_enroll_default_rate": None, "share": 0.15},
    ],
    "below_default_steps": [
        {"pp": 1, "weight": 0.20},
        {"pp": 2, "weight": 0.30},
        {"pp": 3, "weight": 0.50},
    ],
    "deferral_rate_changes_enabled": True,
    "deferral_rate_changes_with_escalation_increase_probability": 0.04,
    "deferral_rate_changes_with_escalation_decrease_probability": 0.16,
    "deferral_rate_changes_without_escalation_increase_probability": 0.26,
    "deferral_rate_changes_without_escalation_decrease_probability": 0.08,
    "deferral_rate_changes_increase_steps": [{"pp": 2, "weight": 1.0}],
    "deferral_rate_changes_decrease_steps": [{"pp": 4, "weight": 1.0}],
    "deferral_rate_changes_post_escalation_decrease_window_days": 0,
    "deferral_rate_changes_post_escalation_decrease_leaves_escalation": True,
    "deferral_rate_changes_stop_probability": 0.0,
    "deferral_rate_changes_restart_probability": 0.05,
}


def test_off_defaults_and_preexisting_vars_unchanged() -> None:
    exported = to_dbt_vars(load_simulation_config("config/simulation_config.yaml"))
    baseline = json.loads(
        (ROOT / "tests/fixtures/participant_behavior_legacy_vars.json").read_text()
    )
    baseline["census_parquet_path"] = str(ROOT / "data/census_preprocessed.parquet")
    assert {key: exported[key] for key in baseline} == baseline
    assert exported.keys() - baseline.keys() == DEFAULTS.keys()
    assert {key: exported[key] for key in DEFAULTS} == DEFAULTS
    assert not validate_dbt_vars(exported)


@pytest.mark.parametrize("key,value", OVERRIDES.items())
def test_each_dc_plan_override(key: str, value: Any) -> None:
    cfg = load_simulation_config("config/simulation_config.yaml")
    # Exercise the partial API model too, including its dictionary round trip.
    cfg.dc_plan = StudioConfig.model_validate({"dc_plan": {key: value}}).model_dump(
        exclude_unset=True
    )["dc_plan"]
    target = {
        "escalation_mode": "deferral_escalation_mode",
        "escalation_participant_elected_signup_probability": "deferral_escalation_participant_elected_signup_probability",
        "match_magnet_downward_enabled": "enrollment_match_magnet_downward_enabled",
    }.get(key, key)
    result = to_dbt_vars(cfg)
    assert result[target] == value
    assert not validate_dbt_vars(result)


@pytest.mark.parametrize("mode", ["automatic", "participant_elected"])
def test_escalation_mode_does_not_export_enabled(mode: str) -> None:
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.deferral_auto_escalation = DeferralAutoEscalationSettings.model_validate(
        {"mode": mode}
    )
    result = to_dbt_vars(cfg)
    assert result["deferral_escalation_mode"] == mode
    assert "deferral_escalation_enabled" not in result


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("mode", ["automatic", "participant_elected"])
def test_escalation_enabled_dump_edit_validate_round_trip(
    enabled: bool, mode: str
) -> None:
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.deferral_auto_escalation.mode = mode
    cfg.deferral_auto_escalation.enabled = not enabled
    payload = cfg.model_dump(mode="python")
    payload["deferral_auto_escalation"]["enabled"] = enabled
    restored = SimulationConfig.model_validate(payload)
    exported = to_dbt_vars(restored)
    assert restored.deferral_auto_escalation.enabled is enabled
    assert restored.deferral_auto_escalation.mode == mode
    assert exported["deferral_escalation_enabled"] is enabled
    assert exported["deferral_escalation_mode"] == mode


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("mode", ["automatic", "participant_elected"])
@pytest.mark.parametrize("override_toggle", [False, True])
def test_studio_escalation_mode_preserves_independent_toggle(
    enabled: bool, mode: str, override_toggle: bool
) -> None:
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.deferral_auto_escalation.enabled = not enabled if override_toggle else enabled
    overrides: dict[str, Any] = {"escalation_mode": mode}
    if override_toggle:
        overrides["auto_escalation"] = enabled
    cfg.dc_plan = StudioConfig.model_validate({"dc_plan": overrides}).model_dump(
        exclude_unset=True
    )["dc_plan"]
    exported = to_dbt_vars(cfg)
    assert exported["deferral_escalation_enabled"] is enabled
    assert exported["deferral_escalation_mode"] == mode


@pytest.mark.parametrize(
    "model,data",
    [
        (EasyEnrollSettings, {"channel_share": -0.1}),
        (EasyEnrollSettings, {"escalation_cap": 1.1}),
        (EasyEnrollSettings, {"packages": []}),
        (EasyEnrollSettings, {"packages": [{"rate": 0, "share": 1}]}),
        (EasyEnrollSettings, {"packages": [{"rate": 1.1, "share": 1}]}),
        (EasyEnrollSettings, {"packages": [{"rate": 0.06, "share": 0.5}]}),
        (BelowDefaultSettings, {"share_tiers": []}),
        (
            BelowDefaultSettings,
            {"share_tiers": [{"max_auto_enroll_default_rate": 0.03, "share": 0.1}]},
        ),
        (
            BelowDefaultSettings,
            {
                "share_tiers": [
                    {"max_auto_enroll_default_rate": None, "share": 0.1},
                    {"max_auto_enroll_default_rate": None, "share": 0.1},
                ]
            },
        ),
        (
            BelowDefaultSettings,
            {
                "share_tiers": [
                    {"max_auto_enroll_default_rate": None, "share": 0.1},
                    {"max_auto_enroll_default_rate": 0.03, "share": 0.1},
                ]
            },
        ),
        (
            BelowDefaultSettings,
            {
                "share_tiers": [
                    {"max_auto_enroll_default_rate": 0.06, "share": 0.1},
                    {"max_auto_enroll_default_rate": 0.03, "share": 0.1},
                    {"max_auto_enroll_default_rate": None, "share": 0.1},
                ]
            },
        ),
        (
            BelowDefaultSettings,
            {"share_tiers": [{"max_auto_enroll_default_rate": None, "share": 1.1}]},
        ),
        (
            BelowDefaultSettings,
            {"steps": [{"pp": 1, "weight": 0.2}, {"pp": 2, "weight": 0.2}]},
        ),
        (
            BelowDefaultSettings,
            {"steps": [{"pp": 1, "weight": -0.2}, {"pp": 2, "weight": 1.2}]},
        ),
        (
            DeferralAutoEscalationSettings,
            {"participant_elected_signup_probability": 1.1},
        ),
        (DeferralAutoEscalationSettings, {"mode": "invalid"}),
        (DeferralAutoEscalationSettings, {"mode": "none"}),
        (DeferralRateChangesSettings, {"post_escalation_decrease_window_days": -1}),
        (DeferralRateChangesSettings, {"post_escalation_decrease_window_days": 1.5}),
        (DeferralRateChangesSettings, {"stop_probability": -1}),
        (DeferralRateChangesSettings, {"restart_probability": 1.1}),
        (
            DeferralRateChangesSettings,
            {
                "with_escalation": {
                    "increase_probability": 1.1,
                    "decrease_probability": 0.1,
                }
            },
        ),
        (
            DeferralRateChangesSettings,
            {
                "without_escalation": {
                    "increase_probability": 0.1,
                    "decrease_probability": -0.1,
                }
            },
        ),
        *[
            (BelowDefaultSettings, {"steps": value})
            for value in (
                [],
                [0.5, 0.5],
                [{"pp": 0, "weight": 1}],
                [{"pp": 1.5, "weight": 1}],
                [{"pp": True, "weight": 1}],
                [{"pp": 1, "weight": 0.5}],
                [{"pp": 1, "weight": 1.1}],
            )
        ],
        *[
            (DeferralRateChangesSettings, {key: value})
            for key in ("increase_steps", "decrease_steps")
            for value in (
                [],
                [{"pp": 0, "weight": 1}],
                [{"pp": 1.5, "weight": 1}],
                [{"pp": True, "weight": 1}],
                [{"pp": 1, "weight": 0.5}],
                [{"pp": 1, "weight": 1.1}],
            )
        ],
    ],
)
def test_reject_invalid_settings(model: type[BaseModel], data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("easy_enroll_packages", "[]"),
        ("easy_enroll_packages", [{"rate": 0.06, "share": 0.5}]),
        (
            "below_default_share_tiers",
            [{"max_auto_enroll_default_rate": 0.03, "share": 0}],
        ),
        ("below_default_steps", [{"pp": 1, "weight": 0.2}, {"pp": 2, "weight": 0.2}]),
        ("deferral_rate_changes_increase_steps", [{"pp": 0, "weight": 1}]),
        ("deferral_rate_changes_decrease_steps", [{"pp": 1, "weight": 0.5}]),
        ("deferral_escalation_mode", "invalid"),
        ("deferral_escalation_mode", "none"),
        ("easy_enroll_enabled", "false"),
        ("deferral_rate_changes_post_escalation_decrease_window_days", -1),
        ("deferral_rate_changes_restart_probability", float("nan")),
    ],
)
def test_export_type_checks(field: str, value: Any) -> None:
    problems = validate_dbt_vars({field: value})
    assert problems and problems[0]["field"] == field


def test_distribution_tolerance() -> None:
    EasyEnrollSettings(packages=[{"rate": 0.06, "share": 0.9999999}])
    BelowDefaultSettings(
        steps=[{"pp": 1, "weight": 0.5}, {"pp": 3, "weight": 0.5000001}]
    )
    DeferralRateChangesSettings(increase_steps=[{"pp": 1, "weight": 0.9999999}])


def test_legacy_enabled_can_be_updated_on_loaded_config() -> None:
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.deferral_auto_escalation.enabled = False
    exported = to_dbt_vars(cfg)
    assert exported["deferral_escalation_mode"] == "automatic"
    assert exported["deferral_escalation_enabled"] is False


def test_all_yaml_settings_export_nondefault_values() -> None:
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.deferral_auto_escalation = DeferralAutoEscalationSettings(
        mode="participant_elected", participant_elected_signup_probability=0.01
    )
    cfg.easy_enroll = EasyEnrollSettings(
        enabled=True,
        channel_share=0.42,
        packages=OVERRIDES["easy_enroll_packages"],
        escalation_cap=0.12,
    )
    cfg.enrollment.match_magnet.downward_enabled = True
    cfg.enrollment.below_default = BelowDefaultSettings(
        share_tiers=OVERRIDES["below_default_share_tiers"],
        steps=OVERRIDES["below_default_steps"],
    )
    cfg.deferral_rate_changes = DeferralRateChangesSettings(
        enabled=True,
        with_escalation={"increase_probability": 0.04, "decrease_probability": 0.16},
        without_escalation={"increase_probability": 0.26, "decrease_probability": 0.08},
        increase_steps=[{"pp": 2, "weight": 1.0}],
        decrease_steps=[{"pp": 4, "weight": 1.0}],
        post_escalation_decrease_window_days=0,
        post_escalation_decrease_leaves_escalation=True,
        stop_probability=0.0,
        restart_probability=0.05,
    )
    yaml_result = to_dbt_vars(cfg)
    cfg.dc_plan = OVERRIDES
    studio_result = to_dbt_vars(cfg)
    assert {key: yaml_result[key] for key in DEFAULTS} == {
        key: studio_result[key] for key in DEFAULTS
    }


@pytest.mark.parametrize(
    "yaml_value,expected",
    [
        ("2020-01-01", "2020-01-01"),
        ("2020-01-01T12:34:56", "2020-01-01T12:34:56"),
    ],
)
@pytest.mark.parametrize(
    "field,target",
    [
        ("hire_date_cutoff", "deferral_escalation_hire_date_cutoff"),
        ("effective_day", "deferral_escalation_effective_mmdd"),
    ],
)
def test_unquoted_yaml_dates_load_and_export_as_iso_strings(
    tmp_path: Path, yaml_value: str, expected: str, field: str, target: str
) -> None:
    raw = yaml.safe_load((ROOT / "config/simulation_config.yaml").read_text())
    raw.pop("deferral_auto_escalation")
    path = tmp_path / "dates.yaml"
    path.write_text(
        yaml.safe_dump(raw) + f"deferral_auto_escalation:\n  {field}: {yaml_value}\n"
    )
    cfg = load_simulation_config(path)
    assert getattr(cfg.deferral_auto_escalation, field) == expected
    assert to_dbt_vars(cfg)[target] == expected


@pytest.mark.parametrize(
    "overrides,expected_escalation_vars",
    [
        ({}, {}),
        ({"auto_escalation": False}, {"deferral_escalation_enabled": False}),
        (
            {
                "auto_escalation": True,
                "escalation_rate_percent": 2,
                "escalation_cap_percent": 12,
                "escalation_effective_day": "07-01",
                "escalation_delay_years": 0,
                "escalation_hire_date_cutoff": "2021-01-01",
            },
            {
                "deferral_escalation_enabled": True,
                "deferral_escalation_increment": 0.02,
                "deferral_escalation_cap": 0.12,
                "deferral_escalation_effective_mmdd": "07-01",
                "deferral_escalation_first_delay_years": 0,
                "deferral_escalation_hire_date_cutoff": "2021-01-01",
            },
        ),
    ],
)
def test_null_escalation_preserves_main_exports(
    tmp_path: Path, overrides: dict[str, Any], expected_escalation_vars: dict[str, Any]
) -> None:
    raw = yaml.safe_load((ROOT / "config/simulation_config.yaml").read_text())
    raw["deferral_auto_escalation"] = None
    raw["dc_plan"] = StudioConfig.model_validate({"dc_plan": overrides}).model_dump(
        exclude_unset=True
    )["dc_plan"]
    path = tmp_path / "null_escalation.yaml"
    path.write_text(yaml.safe_dump(raw))
    cfg = load_simulation_config(path)
    assert cfg.deferral_auto_escalation.model_dump(exclude_unset=True) == {}
    # The fixture records main's full export. A null legacy section skips all
    # legacy escalation vars; explicit Studio settings are then applied.
    baseline = json.loads(
        (ROOT / "tests/fixtures/participant_behavior_legacy_vars.json").read_text()
    )
    expected = {
        key: value
        for key, value in baseline.items()
        if not key.startswith("deferral_escalation_")
    }
    expected["census_parquet_path"] = str(ROOT / "data/census_preprocessed.parquet")
    expected.update(expected_escalation_vars)
    exported = to_dbt_vars(cfg)
    assert {
        key: value for key, value in exported.items() if key not in DEFAULTS
    } == expected
    assert {key: exported[key] for key in DEFAULTS} == DEFAULTS


@pytest.mark.parametrize(
    "field_path",
    [
        ("easy_enroll",),
        ("deferral_rate_changes",),
        ("enrollment", "below_default"),
        ("enrollment", "match_magnet", "downward_enabled"),
    ],
)
def test_null_new_behavior_settings_load_as_defaults(
    tmp_path: Path, field_path: tuple[str, ...]
) -> None:
    raw = yaml.safe_load((ROOT / "config/simulation_config.yaml").read_text())
    section = raw
    for part in field_path[:-1]:
        section = section[part]
    section[field_path[-1]] = None
    path = tmp_path / "null_behavior.yaml"
    path.write_text(yaml.safe_dump(raw))
    cfg = load_simulation_config(path)
    assert to_dbt_vars(cfg) == to_dbt_vars(
        load_simulation_config("config/simulation_config.yaml")
    )
