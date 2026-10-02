"""Studio config contracts preserve partial overrides and storage behavior."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from planalign_api.models.scenario import Scenario, ScenarioCreate, ScenarioUpdate
from planalign_api.models.simulation import RunDetails
from planalign_api.models.templates import Template
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.scenario_service import ScenarioService
from planalign_api.services.template_service import TemplateService
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = [pytest.mark.fast, pytest.mark.unit]


@pytest.fixture
def partial_config():
    return {
        "simulation": {"start_year": 2025, "target_growth_rate": 0},
        "dc_plan": {
            "auto_enroll": False,
            "match_tiers": [{"match_rate": 0, "future_tier_key": [1, 2]}],
        },
        "promotion_hazard": {
            "base_rate": 0,
            "age_multipliers": [{"age_band": "young", "multiplier": 1, "future": True}],
            "tenure_multipliers": [
                {"tenure_band": "new", "multiplier": 1, "future": True}
            ],
        },
        "age_bands": [
            {
                "band_id": 1,
                "band_label": "all",
                "min_value": 0,
                "max_value": 100,
                "display_order": 1,
                "future": True,
            }
        ],
        "future_section": {"nested": {"enabled": True}},
    }


def test_config_fields_round_trip_without_inserting_defaults(partial_config):
    models_and_fields = [
        (ScenarioCreate(name="S", config_overrides=partial_config), "config_overrides"),
        (ScenarioUpdate(config_overrides=partial_config), "config_overrides"),
        (
            Scenario(
                id="s",
                workspace_id="w",
                name="S",
                created_at=datetime.now(timezone.utc),
                config_overrides=partial_config,
            ),
            "config_overrides",
        ),
        (
            Template(
                id="t",
                name="T",
                description="D",
                category="general",
                config=partial_config,
            ),
            "config",
        ),
        (
            RunDetails(
                id="r",
                scenario_id="s",
                scenario_name="S",
                workspace_id="w",
                workspace_name="W",
                status="completed",
                config=partial_config,
            ),
            "config",
        ),
    ]
    for model, field in models_and_fields:
        assert getattr(model, field) == partial_config
        assert model.model_dump(mode="json")[field] == partial_config
        assert (
            type(model).model_validate_json(model.model_dump_json()).model_dump()[field]
            == partial_config
        )


@pytest.mark.parametrize("config", [{}, {"simulation": {}}, {"dc_plan": None}])
def test_empty_and_explicit_null_are_preserved(config):
    assert (
        ScenarioCreate(name="S", config_overrides=config).model_dump()[
            "config_overrides"
        ]
        == config
    )


def test_known_field_wrong_type_is_rejected():
    with pytest.raises(ValidationError, match="target_growth_rate"):
        ScenarioCreate(
            name="S", config_overrides={"simulation": {"target_growth_rate": "typo"}}
        )


def test_create_copy_and_template_paths_preserve_config(tmp_path, partial_config):
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(
        WorkspaceCreate(name="W"), {"simulation": {"end_year": 2027}}
    )
    service = ScenarioService(storage)
    original = service.create_scenario(
        workspace.id, ScenarioCreate(name="Original", config_overrides=partial_config)
    )
    copied = service.duplicate_scenario(workspace.id, original.id, "Copy")
    assert (
        storage.get_scenario(workspace.id, copied.id).config_overrides == partial_config
    )
    merged = service.get_merged_config(workspace.id, copied.id)
    assert merged["simulation"]["end_year"] == 2027
    assert merged["simulation"]["target_growth_rate"] == 0

    for template in TemplateService().list_templates():
        payload = template.model_dump(mode="json")["config"]
        created = service.create_scenario(
            workspace.id, ScenarioCreate(name=template.name, config_overrides=payload)
        )
        assert (
            storage.get_scenario(workspace.id, created.id).config_overrides == payload
        )
