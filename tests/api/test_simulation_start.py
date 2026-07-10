"""Tests for simulation start concurrency guards."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from planalign_api.models.simulation import RunRequest, SimulationRun
from planalign_api.routers import simulations


@pytest.fixture
def simulation_start(monkeypatch):
    """Set up a startable scenario and synchronous endpoint dependencies."""
    scenario = SimpleNamespace(id="scenario-123", status="not_run")
    workspace = SimpleNamespace(id="workspace-123")
    storage = MagicMock()
    storage.get_merged_config.return_value = {
        "simulation": {"start_year": 2025, "end_year": 2027}
    }
    monkeypatch.setattr(simulations, "_active_runs", {})
    monkeypatch.setattr(
        simulations,
        "_find_scenario_and_workspace",
        lambda storage, scenario_id: (workspace, scenario),
    )
    return scenario, storage, MagicMock()


def _start(storage, service):
    return simulations.start_simulation(
        "scenario-123", RunRequest(), BackgroundTasks(), storage, service
    )


def test_start_rejects_scenario_with_queued_run(simulation_start):
    """Queued runs reserve a scenario before the background task starts."""
    scenario, storage, service = simulation_start
    scenario.status = "queued"

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_start(storage, service))

    assert exc_info.value.status_code == 409
    storage.update_scenario_status.assert_not_called()


def test_overlapping_starts_accept_at_most_one_run(simulation_start):
    """The check-and-reserve section admits only one run per scenario."""
    _, storage, service = simulation_start

    async def start_twice():
        return await asyncio.gather(
            _start(storage, service),
            _start(storage, service),
            return_exceptions=True,
        )

    results = asyncio.run(start_twice())

    assert sum(isinstance(result, SimulationRun) for result in results) == 1
    conflicts = [result for result in results if isinstance(result, HTTPException)]
    assert len(conflicts) == 1
    assert conflicts[0].status_code == 409
    assert storage.update_scenario_status.call_count == 1


@pytest.mark.parametrize("previous_status", ["completed", "failed", "cancelled"])
def test_start_allows_terminal_previous_runs(simulation_start, previous_status):
    """Terminal run records do not block a new simulation."""
    scenario, storage, service = simulation_start
    scenario.status = previous_status
    simulations._active_runs["previous-run"] = SimulationRun(
        id="previous-run",
        scenario_id="scenario-123",
        status=previous_status,
        started_at=datetime.now(timezone.utc),
    )

    run = asyncio.run(_start(storage, service))

    assert run.status == "pending"
    storage.update_scenario_status.assert_called_once_with(
        "workspace-123", "scenario-123", "queued", run.id
    )
