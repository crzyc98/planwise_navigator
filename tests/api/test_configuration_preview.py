"""Draft previews must match production export without persisting edits."""

from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from planalign_api.models.scenario import ConfigPreviewRequest, ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers.scenarios import preview_configuration
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_orchestrator.config.loader import SimulationConfig
from planalign_orchestrator.config.export import to_dbt_vars

pytestmark = pytest.mark.fast


@pytest.fixture
def workspace(tmp_path):
    storage = WorkspaceStorage(tmp_path / "workspaces")
    config = yaml.safe_load(Path("tests/fixtures/invariant_config.yaml").read_text())
    saved = storage.create_workspace(WorkspaceCreate(name="Preview contract"), config)
    return storage, saved


def test_preview_equals_saved_production_merge_and_export(workspace):
    storage, saved = workspace
    draft = {
        "dc_plan": {"auto_enroll": False, "new_hire_opt_out_rate": 0},
        "custom": {"retained": True},
    }
    before = {
        p: p.read_bytes()
        for p in storage._workspace_path(saved.id).rglob("*")
        if p.is_file()
    }
    preview = preview_configuration(
        saved.id, ConfigPreviewRequest(config=draft), storage
    )
    after = {
        p: p.read_bytes()
        for p in storage._workspace_path(saved.id).rglob("*")
        if p.is_file()
    }
    assert before == after
    scenario = storage.create_scenario(
        saved.id, ScenarioCreate(name="Saved", config_overrides=draft)
    )
    merged = storage.get_merged_config(saved.id, scenario.id)
    assert preview["configuration"] == merged
    assert preview["engine_variables"] == to_dbt_vars(SimulationConfig(**merged))
    assert preview["engine_variables"]["new_hire_opt_out_rate"] == 0


def test_workspace_preview_does_not_merge_old_workspace_values(workspace):
    storage, saved = workspace
    draft = dict(saved.base_config)
    draft["dc_plan"] = {"auto_enroll": False}
    preview = preview_configuration(
        saved.id, ConfigPreviewRequest(config=draft, target="workspace"), storage
    )
    assert preview["configuration"]["dc_plan"]["auto_enroll"] is False
    assert storage.get_workspace(saved.id).base_config == saved.base_config


def test_invalid_preview_fails_without_writing(workspace):
    storage, saved = workspace
    with pytest.raises(HTTPException) as failure:
        preview_configuration(
            saved.id,
            ConfigPreviewRequest(config={"simulation": {"start_year": "invalid"}}),
            storage,
        )
    assert failure.value.status_code == 422
    assert storage.get_workspace(saved.id).base_config == saved.base_config


def test_invalid_exported_date_is_a_field_level_422(workspace):
    storage, saved = workspace
    with pytest.raises(HTTPException) as failure:
        preview_configuration(
            saved.id,
            ConfigPreviewRequest(
                config={"setup": {"plan_year_start_date": "2025-02-30"}}
            ),
            storage,
        )
    assert failure.value.status_code == 422
    assert failure.value.detail["errors"][0]["field"] == "plan_year_start_date"


def test_stale_match_boolean_is_a_field_level_422(workspace):
    storage, saved = workspace
    with pytest.raises(HTTPException) as failure:
        preview_configuration(
            saved.id,
            ConfigPreviewRequest(
                config={"dc_plan": {"match_allow_new_hires": "false"}}
            ),
            storage,
        )
    assert failure.value.status_code == 422
    assert failure.value.detail["errors"][0]["field"] == (
        "employer_match.eligibility.allow_new_hires"
    )


def test_unknown_workspace_is_not_found(workspace):
    storage, _ = workspace
    with pytest.raises(HTTPException) as failure:
        preview_configuration("missing", ConfigPreviewRequest(config={}), storage)
    assert failure.value.status_code == 404


@pytest.mark.parametrize("target", ["workspace", "scenario"])
def test_displayed_match_policy_overrides_dormant_legacy_values(workspace, target):
    storage, saved = workspace
    base = dict(saved.base_config)
    base["employer_match"] = {
        "apply_eligibility": False,
        "eligibility": {
            "minimum_tenure_years": 3,
            "minimum_hours_annual": 500,
            "require_active_at_year_end": False,
            "allow_new_hires": False,
            "allow_terminated_new_hires": True,
            "allow_experienced_terminations": True,
        },
    }
    storage.update_workspace(saved.id, base_config=base)
    policy = {
        "match_min_tenure_years": 0,
        "match_min_hours_annual": 750,
        "match_require_year_end_active": True,
        "match_allow_new_hires": True,
        "match_allow_terminated_new_hires": False,
        "match_allow_experienced_terminations": False,
    }
    draft = {**(base if target == "workspace" else {}), "dc_plan": policy}
    preview = preview_configuration(
        saved.id, ConfigPreviewRequest(config=draft, target=target), storage
    )
    assert preview["configuration"]["employer_match"] == base["employer_match"]
    match = preview["engine_variables"]["employer_match"]
    assert match["apply_eligibility"] is True
    assert match["eligibility"] == {
        "minimum_tenure_years": 0,
        "minimum_hours_annual": 750,
        "require_active_at_year_end": True,
        "allow_new_hires": True,
        "allow_terminated_new_hires": False,
        "allow_experienced_terminations": False,
    }
