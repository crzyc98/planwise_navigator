"""Studio's grandfathered-design payload is accepted end to end (#646)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from planalign_api.models.studio_config import StudioConfig
from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.config.dbt_var_validation import validate_dbt_vars
from planalign_orchestrator.config.export import to_dbt_vars
from tests.fixtures.studio_grandfathered_design import (
    CUTOFF,
    EXISTING_DESIGN,
    NEW_HIRE_DESIGN,
    load_studio_payload,
)

pytestmark = [pytest.mark.fast, pytest.mark.config]
ROOT = Path(__file__).resolve().parents[3]


def _config_with(overrides: dict[str, Any]) -> SimulationConfig:
    raw = yaml.safe_load((ROOT / "config/simulation_config.yaml").read_text())
    raw.pop("plan_design_id", None)
    return SimulationConfig.model_validate({**raw, **overrides})


def test_api_accepts_the_studio_payload() -> None:
    payload = load_studio_payload()
    validated = StudioConfig.model_validate(payload).model_dump(exclude_unset=True)
    assert validated == payload


def test_engine_exports_both_designs_from_the_studio_payload() -> None:
    dbt_vars = to_dbt_vars(_config_with(load_studio_payload()))

    assert not validate_dbt_vars(dbt_vars)
    assert dbt_vars["plan_design_assignment"] == {
        "default_plan_design_id": EXISTING_DESIGN,
        "rules": [
            {
                "type": "hire_date_cutoff",
                "cutoff": CUTOFF,
                "plan_design_id": NEW_HIRE_DESIGN,
            }
        ],
    }
    designs = dbt_vars["plan_design_parameters"]
    assert sorted(designs) == [EXISTING_DESIGN, NEW_HIRE_DESIGN]
    assert designs[EXISTING_DESIGN]["employer_core"]["contribution_rate"] == 0.01
    assert designs[NEW_HIRE_DESIGN]["employer_core"]["contribution_rate"] == 0.03
    assert designs[NEW_HIRE_DESIGN]["match"]["tiers"] == [
        {"employee_min": 0.0, "employee_max": 0.06, "match_rate": 0.5}
    ]


def test_turned_off_payload_runs_a_single_design() -> None:
    dbt_vars = to_dbt_vars(
        _config_with({"plan_design_assignment": None, "plan_design_parameters": None})
    )

    assert "plan_design_assignment" not in dbt_vars
    assert "plan_design_parameters" not in dbt_vars
    assert dbt_vars["plan_design_id"] == "default"
