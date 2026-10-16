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


def test_unknown_workspace_is_not_found(workspace):
    storage, _ = workspace
    with pytest.raises(HTTPException) as failure:
        preview_configuration("missing", ConfigPreviewRequest(config={}), storage)
    assert failure.value.status_code == 404
