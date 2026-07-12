"""Regression: a cancelled run must not break scenario listing.

Cancelling a simulation persists status='cancelled'
(planalign_api/routers/simulations.py), but the Scenario model's status
Literal originally lacked that value, so every subsequent
GET /api/workspaces/{id}/scenarios raised ValidationError and 500'd the
whole workspace scenario list.
"""

from __future__ import annotations

import pytest

from planalign_api.models.scenario import Scenario, ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = [pytest.mark.fast, pytest.mark.unit]


def test_scenario_model_accepts_cancelled_status():
    from datetime import datetime, timezone

    scenario = Scenario(
        id="s1",
        workspace_id="w1",
        name="cancelled scenario",
        status="cancelled",
        created_at=datetime.now(timezone.utc),
    )
    assert scenario.status == "cancelled"


def test_list_scenarios_survives_cancelled_run(tmp_path):
    storage = WorkspaceStorage(workspaces_root=tmp_path)
    workspace = storage.create_workspace(
        WorkspaceCreate(name="ws"), default_config={"simulation": {}}
    )
    scenario = storage.create_scenario(
        workspace.id, ScenarioCreate(name="test scenario")
    )

    updated = storage.update_scenario_status(workspace.id, scenario.id, "cancelled")

    assert updated is not None
    assert updated.status == "cancelled"
    listed = storage.list_scenarios(workspace.id)
    assert [s.status for s in listed] == ["cancelled"]
