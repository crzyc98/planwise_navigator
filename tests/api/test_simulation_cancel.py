"""Tests for simulation cancellation endpoint behavior."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from planalign_api.models.simulation import SimulationRun
from planalign_api.routers import simulations


@pytest.fixture
def running_simulation(monkeypatch):
    """Set up one in-memory running run and its storage lookup."""
    run = SimulationRun(
        id="run-123",
        scenario_id="scenario-123",
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(simulations, "_active_runs", {run.id: run})
    workspace = SimpleNamespace(id="workspace-123")
    scenario = SimpleNamespace(id="scenario-123")
    monkeypatch.setattr(
        simulations,
        "_find_scenario_and_workspace",
        lambda storage, scenario_id: (workspace, scenario),
    )
    storage = MagicMock()
    telemetry = MagicMock()
    monkeypatch.setattr(simulations, "get_telemetry_service", lambda: telemetry)
    return run, storage, telemetry


def test_cancel_updates_status_and_telemetry_after_subprocess_signal(
    running_simulation,
):
    """Terminal state is not published until the real cancellation succeeds."""
    run, storage, telemetry = running_simulation

    class SuccessfulService:
        async def cancel_simulation(self, run_id: str) -> bool:
            assert run_id == run.id
            assert run.status == "running"
            storage.update_scenario_status.assert_not_called()
            telemetry.set_terminal.assert_not_called()
            return True

    response = asyncio.run(
        simulations.cancel_simulation("scenario-123", storage, SuccessfulService())
    )

    assert response == {"success": True}
    assert run.status == "cancelled"
    storage.update_scenario_status.assert_called_once_with(
        "workspace-123", "scenario-123", "cancelled"
    )
    telemetry.set_terminal.assert_called_once_with("run-123", "cancelled")


def test_cancel_unknown_process_leaves_status_and_telemetry_unchanged(
    running_simulation,
):
    """API restart/missing process errors must not fabricate cancellation."""
    run, storage, telemetry = running_simulation

    class UnknownProcessService:
        async def cancel_simulation(self, run_id: str) -> bool:
            assert run_id == run.id
            return False

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            simulations.cancel_simulation(
                "scenario-123", storage, UnknownProcessService()
            )
        )

    assert exc_info.value.status_code == 404
    assert "No active subprocess found for run run-123" in exc_info.value.detail
    assert run.status == "running"
    storage.update_scenario_status.assert_not_called()
    telemetry.set_terminal.assert_not_called()
