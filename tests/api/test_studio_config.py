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


@pytest.mark.parametrize("mode", ["none", "invalid"])
def test_invalid_escalation_mode_is_rejected(mode: str) -> None:
    with pytest.raises(ValidationError, match="escalation_mode"):
        ScenarioCreate(
            name="S", config_overrides={"dc_plan": {"escalation_mode": mode}}
        )


@pytest.mark.parametrize(
    "field",
    [
        "easy_enroll_channel_share_without_auto_enrollment",
        "easy_enroll_channel_share_with_auto_enrollment",
    ],
)
@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_invalid_easy_enroll_channel_shares_are_rejected(
    field: str, value: float
) -> None:
    with pytest.raises(ValidationError, match=field):
        ScenarioCreate(name="S", config_overrides={"dc_plan": {field: value}})


@pytest.mark.parametrize(
    "field",
    [
        "easy_enroll_channel_share_without_auto_enrollment",
        "easy_enroll_channel_share_with_auto_enrollment",
    ],
)
@pytest.mark.parametrize("value", [None, 0.0, 0.42, 1.0])
def test_easy_enroll_channel_share_partial_round_trip(
    field: str, value: float | None
) -> None:
    config = {"dc_plan": {field: value}}
    model = ScenarioCreate(name="S", config_overrides=config)
    assert model.model_dump(mode="json")["config_overrides"] == config
    assert (
        ScenarioCreate.model_validate_json(model.model_dump_json()).config_overrides
        == config
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


@pytest.mark.parametrize(
    "field,value",
    [
        ("reenrollment_sweep_interval_years", 0),
        ("reenrollment_sweep_interval_years", 1.5),
        ("reenrollment_sweep_first_year", 2027.5),
    ],
)
def test_sweep_api_rejects_invalid_schedule(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ScenarioCreate(name="S", config_overrides={"dc_plan": {field: value}})


def test_acquisition_plan_settings_round_trip_through_scenario_storage(tmp_path):
    """#1227: Studio can save an acquisition's plan settings before #1228 adds UI."""
    from planalign_orchestrator.config import AcquisitionSettings

    acquisition = {
        "id": "acme",
        "name": "Acme Co",
        "headcount": 120,
        "effective_date": "2026-07-01",
        "service_credit": "acquisition_date",
        "plan_entry": "waiting_period",
        "starting_participation_rate": 0.7,
        "starting_deferral_rate": 0.05,
    }
    overrides = {"workforce": {"acquisitions": [acquisition]}}
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    service = ScenarioService(storage)
    created = service.create_scenario(
        workspace.id, ScenarioCreate(name="S", config_overrides=overrides)
    )
    stored = storage.get_scenario(workspace.id, created.id).config_overrides
    assert stored == overrides
    merged = service.get_merged_config(workspace.id, created.id)
    loaded = AcquisitionSettings.model_validate(merged["workforce"]["acquisitions"][0])
    assert loaded.model_dump(mode="json", exclude_none=True) == acquisition


@pytest.mark.parametrize("field", ["scenario_id", "plan_design_id", "SCENARIO_ID"])
@pytest.mark.parametrize("bad_value", ["o'brien", "plan;drop", "   ", " lead", 123])
def test_api_rejects_invalid_identifiers_in_overrides_and_base_config(
    client_factory, field: str, bad_value: object
) -> None:
    headers = {"Authorization": "Bearer secret"}
    client = client_factory("secret")

    ws_create = client.post(
        "/api/workspaces",
        json={"name": "Bad WS", "base_config": {field: bad_value}},
        headers=headers,
    )
    assert ws_create.status_code == 422

    ws_ok = client.post("/api/workspaces", json={"name": "Good WS"}, headers=headers)
    assert ws_ok.status_code == 201
    workspace_id = ws_ok.json()["id"]

    ws_update = client.put(
        f"/api/workspaces/{workspace_id}",
        json={"base_config": {field: bad_value}},
        headers=headers,
    )
    assert ws_update.status_code == 422

    sc_create = client.post(
        f"/api/workspaces/{workspace_id}/scenarios",
        json={"name": "Bad Scenario", "config_overrides": {field: bad_value}},
        headers=headers,
    )
    assert sc_create.status_code == 422

    sc_ok = client.post(
        f"/api/workspaces/{workspace_id}/scenarios",
        json={"name": "Good Scenario", "config_overrides": {}},
        headers=headers,
    )
    assert sc_ok.status_code == 201
    scenario_id = sc_ok.json()["id"]

    sc_update = client.put(
        f"/api/workspaces/{workspace_id}/scenarios/{scenario_id}",
        json={"config_overrides": {field: bad_value}},
        headers=headers,
    )
    assert sc_update.status_code == 422


def test_api_accepts_valid_identifiers_and_rejects_invalid_scopes(
    client_factory,
) -> None:
    headers = {"Authorization": "Bearer secret"}
    client = client_factory("secret")

    ws_resp = client.post(
        "/api/workspaces",
        json={
            "name": "Valid WS",
            "base_config": {
                "scenario_id": "baseline_v1.0",
                "plan_design_id": "standard-401k",
                "simulation": {"start_year": 2026, "end_year": 2028},
            },
        },
        headers=headers,
    )
    assert ws_resp.status_code == 201
    workspace_id = ws_resp.json()["id"]

    sc_resp = client.post(
        f"/api/workspaces/{workspace_id}/scenarios",
        json={
            "name": "Valid Scenario",
            "config_overrides": {
                "scenario_id": "alt-design.1",
                "plan_design_id": "enhanced_401k",
                "dc_plan": {"auto_enroll_scope": "all_eligible"},
            },
        },
        headers=headers,
    )
    assert sc_resp.status_code == 201

    bad_scope = client.post(
        f"/api/workspaces/{workspace_id}/scenarios",
        json={
            "name": "Bad Scope",
            "config_overrides": {"dc_plan": {"auto_enroll_scope": "bad'scope"}},
        },
        headers=headers,
    )
    assert bad_scope.status_code == 422

    bad_nested_scope = client.put(
        f"/api/workspaces/{workspace_id}",
        json={
            "base_config": {"enrollment": {"auto_enrollment": {"scope": "bad'scope"}}}
        },
        headers=headers,
    )
    assert bad_nested_scope.status_code == 422


def test_api_rejects_invalid_nested_plan_design_ids(client_factory) -> None:
    headers = {"Authorization": "Bearer secret"}
    client = client_factory("secret")
    ws_id = client.post("/api/workspaces", json={"name": "WS"}, headers=headers).json()[
        "id"
    ]

    bad_assignment = client.post(
        f"/api/workspaces/{ws_id}/scenarios",
        json={
            "name": "Bad Assignment",
            "config_overrides": {
                "plan_design_assignment": {
                    "default_plan_design_id": "legacy",
                    "rules": [
                        {
                            "type": "hire_date_cutoff",
                            "cutoff": "2026-01-01",
                            "plan_design_id": "bad'design",
                        }
                    ],
                }
            },
        },
        headers=headers,
    )
    assert bad_assignment.status_code == 422

    bad_params = client.post(
        f"/api/workspaces/{ws_id}/scenarios",
        json={
            "name": "Bad Params",
            "config_overrides": {
                "plan_design_parameters": {"bad;design": {"eligibility": {}}}
            },
        },
        headers=headers,
    )
    assert bad_params.status_code == 422


def test_simulation_start_rejects_tampered_stored_identifier_with_422(
    client_factory, tmp_path
) -> None:
    import yaml

    headers = {"Authorization": "Bearer secret"}
    client = client_factory("secret")
    ws_id = client.post("/api/workspaces", json={"name": "WS"}, headers=headers).json()[
        "id"
    ]
    sc_id = client.post(
        f"/api/workspaces/{ws_id}/scenarios",
        json={"name": "Scenario", "config_overrides": {}},
        headers=headers,
    ).json()["id"]

    # Simulate an existing on-disk config containing an invalid identifier.
    base_cfg_path = tmp_path / "workspaces" / ws_id / "base_config.yaml"
    raw = yaml.safe_load(base_cfg_path.read_text(encoding="utf-8"))
    raw["scenario_id"] = "bad'id"
    base_cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    resp = client.post(f"/api/scenarios/{sc_id}/run", headers=headers)
    assert resp.status_code == 422
    assert "invalid identifier" in resp.json()["detail"]
