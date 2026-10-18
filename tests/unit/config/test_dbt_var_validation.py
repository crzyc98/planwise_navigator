"""Exported vars are checked against the types their SQL consumers require."""

from pathlib import Path

import pytest
import yaml

from planalign_orchestrator.config.dbt_var_validation import validate_dbt_vars
from planalign_orchestrator.config.export import to_dbt_vars
from planalign_orchestrator.config.loader import SimulationConfig
from planalign_orchestrator.exceptions import ConfigurationError
from planalign_orchestrator.construction import ConstructionSpec, build_orchestrator

pytestmark = pytest.mark.fast


@pytest.mark.parametrize("value", ["", " "])
def test_blank_date_is_rejected(value):
    assert validate_dbt_vars({"auto_enrollment_hire_date_cutoff": value}) == [
        {
            "section": "engine_variables",
            "field": "auto_enrollment_hire_date_cutoff",
            "message": "must be an ISO date (YYYY-MM-DD); omit it to use the default",
        }
    ]


@pytest.mark.parametrize("value", ["2025-02-30", "yesterday", "2025-1-1"])
def test_invalid_date_is_rejected(value):
    problems = validate_dbt_vars({"plan_year_start_date": value})
    assert [problem["field"] for problem in problems] == ["plan_year_start_date"]


def test_boolean_rate_and_enum_are_checked():
    problems = validate_dbt_vars(
        {
            "auto_enrollment_enabled": "false",
            "auto_enrollment_default_deferral_rate": 1.2,
            "auto_enrollment_scope": ["other"],
            "employer_match": {"eligibility": {"allow_new_hires": "false"}},
        }
    )
    assert {problem["field"] for problem in problems} == {
        "auto_enrollment_enabled",
        "auto_enrollment_default_deferral_rate",
        "auto_enrollment_scope",
        "employer_match.eligibility.allow_new_hires",
    }


def test_simulation_rejects_invalid_export_before_dbt(tmp_path):
    payload = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    payload.setdefault("setup", {})["plan_year_start_date"] = "2025-02-30"
    config = SimulationConfig.model_validate(payload)
    with pytest.raises(ConfigurationError, match="plan_year_start_date"):
        build_orchestrator(
            ConstructionSpec(
                config=config,
                database=tmp_path / "run.duckdb",
                reports_dir=tmp_path / "reports",
            )
        )


def test_checked_in_configs_export_without_var_problems():
    base = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    paths = [Path("config/simulation_config.yaml")]
    paths.extend(sorted(Path("scenarios").rglob("*.yaml")))
    paths.extend(sorted(Path("tests/fixtures").rglob("*.yaml")))
    checked = []
    for path in paths:
        payload = yaml.safe_load(path.read_text())
        if not isinstance(payload, dict) or "simulation" not in payload:
            continue  # Non-configuration fixture.
        if path.parent == Path("scenarios"):
            payload = _merge(base, payload)
        config = SimulationConfig.model_validate(payload)
        assert not validate_dbt_vars(to_dbt_vars(config)), str(path)
        checked.append(path)
    assert len(checked) >= 30


def _merge(base: dict, overrides: dict) -> dict:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged
