"""Studio runs simulations one at a time and recovers runs after a restart."""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from planalign_api.config import APISettings
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.simulation import SimulationRun
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import batch as batch_router
from planalign_api.routers import simulations
from planalign_api.services.simulation import run_slots
from planalign_api.services.simulation.recovery import fail_interrupted_simulations
from planalign_api.services.simulation.service import SimulationService
from planalign_api.services.telemetry_service import get_telemetry_service
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = pytest.mark.fast


class ConcurrencyProbe:
    """Records the most runs that were inside the simulation body at once."""

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.started: list[str] = []

    async def run(self, run_id: str) -> None:
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.started.append(run_id)
        await asyncio.sleep(0.01)
        self.active -= 1


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    monkeypatch.setattr(simulations, "_active_runs", {})


@pytest.fixture
def storage(tmp_path) -> WorkspaceStorage:
    return WorkspaceStorage(tmp_path / "workspaces")


def _workspace_with(storage: WorkspaceStorage, count: int) -> tuple[str, list[str]]:
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    ids = [
        storage.create_scenario(workspace.id, ScenarioCreate(name=f"S{i}")).id
        for i in range(count)
    ]
    return workspace.id, ids


def _queued_run(scenario_id: str) -> SimulationRun:
    return SimulationRun(
        id=str(uuid.uuid4()),
        scenario_id=scenario_id,
        status="queued",
        started_at=datetime.now(timezone.utc),
    )


def _slotted_service(monkeypatch, limit: int):
    monkeypatch.setattr(
        run_slots,
        "get_settings",
        lambda: APISettings(max_concurrent_simulations=limit),
    )
    probe = ConcurrencyProbe()

    class SlottedService:
        """Stands in for SimulationService, with the same decorator."""

        @run_slots.runs_in_simulation_slot
        async def execute_simulation(self, workspace_id, scenario_id, run_id, config):
            await probe.run(run_id)

    return SlottedService(), probe


def _run_together(service, workspace_id: str, runs: list[SimulationRun]) -> None:
    async def main() -> None:
        await asyncio.gather(
            *(
                service.execute_simulation(workspace_id, run.scenario_id, run.id, {})
                for run in runs
            )
        )

    asyncio.run(main())


def _reserve_all(storage, workspace_id, scenario_ids) -> list[SimulationRun]:
    runs = [_queued_run(scenario_id) for scenario_id in scenario_ids]
    assert all(simulations.reserve_run(storage, workspace_id, run) for run in runs)
    return runs


def test_default_limit_is_one() -> None:
    assert APISettings().max_concurrent_simulations == 1


def test_simulation_service_waits_for_a_slot() -> None:
    assert hasattr(SimulationService.execute_simulation, "__wrapped__")


def test_runs_started_together_take_turns(monkeypatch, storage) -> None:
    workspace_id, scenario_ids = _workspace_with(storage, 4)
    runs = _reserve_all(storage, workspace_id, scenario_ids)
    service, probe = _slotted_service(monkeypatch, limit=1)

    assert simulations.get_queued_run_count() == 4
    _run_together(service, workspace_id, runs)

    assert probe.peak == 1
    assert len(probe.started) == 4


def test_a_higher_limit_allows_that_many_at_once(monkeypatch, storage) -> None:
    workspace_id, scenario_ids = _workspace_with(storage, 4)
    runs = _reserve_all(storage, workspace_id, scenario_ids)
    service, probe = _slotted_service(monkeypatch, limit=2)

    _run_together(service, workspace_id, runs)

    assert probe.peak == 2


def test_reserving_marks_the_scenario_queued_and_blocks_a_duplicate(storage) -> None:
    workspace_id, (scenario_id,) = _workspace_with(storage, 1)
    first = _queued_run(scenario_id)

    assert simulations.reserve_run(storage, workspace_id, first)
    assert not simulations.reserve_run(storage, workspace_id, _queued_run(scenario_id))
    scenario = storage.get_scenario(workspace_id, scenario_id)
    assert (scenario.status, scenario.last_run_id) == ("queued", first.id)


def test_reserving_clears_the_previous_runs_telemetry(storage) -> None:
    workspace_id, (scenario_id,) = _workspace_with(storage, 1)
    telemetry = get_telemetry_service()
    telemetry.start_run(
        "old-run", scenario_id=scenario_id, start_year=2025, total_years=1
    )
    telemetry.set_terminal("old-run", "completed")

    simulations.reserve_run(storage, workspace_id, _queued_run(scenario_id))

    assert telemetry.get_snapshot_for_scenario(scenario_id) is None


def test_cancelled_queued_run_never_starts_even_after_a_rerun(
    monkeypatch, storage
) -> None:
    workspace_id, (scenario_id,) = _workspace_with(storage, 1)
    (cancelled,) = _reserve_all(storage, workspace_id, [scenario_id])
    monkeypatch.setattr(
        simulations,
        "_find_scenario_and_workspace",
        lambda _storage, sid: (
            storage.get_workspace(workspace_id),
            storage.get_scenario(workspace_id, sid),
        ),
    )
    service = MagicMock()

    response = asyncio.run(simulations.cancel_simulation(scenario_id, storage, service))
    (rerun,) = _reserve_all(storage, workspace_id, [scenario_id])
    slotted, probe = _slotted_service(monkeypatch, limit=1)
    _run_together(slotted, workspace_id, [cancelled, rerun])

    assert response == {"success": True}
    service.cancel_simulation.assert_not_called()
    assert probe.started == [rerun.id]


def test_restart_fails_only_interrupted_scenarios(storage) -> None:
    workspace_id, _ = _workspace_with(storage, 0)
    statuses = ["running", "queued", "completed", "failed", "cancelled", "not_run"]
    ids = {}
    for scenario_status in statuses:
        scenario = storage.create_scenario(
            workspace_id, ScenarioCreate(name=scenario_status)
        )
        if scenario_status != "not_run":
            storage.update_scenario_status(workspace_id, scenario.id, scenario_status)
        ids[scenario_status] = scenario.id

    assert fail_interrupted_simulations(storage) == 2

    after = {
        name: storage.get_scenario(workspace_id, scenario_id).status
        for name, scenario_id in ids.items()
    }
    assert after == {
        "running": "failed",
        "queued": "failed",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
        "not_run": "not_run",
    }


def test_restart_skips_an_unreadable_workspace(monkeypatch, storage) -> None:
    broken_id, _ = _workspace_with(storage, 0)
    workspace_id, (scenario_id,) = _workspace_with(storage, 1)
    storage.update_scenario_status(workspace_id, scenario_id, "running")
    real_list = storage.list_scenarios

    def list_scenarios(wid):
        if wid == broken_id:
            raise ValueError("corrupt scenario file")
        return real_list(wid)

    monkeypatch.setattr(storage, "list_scenarios", list_scenarios)

    assert fail_interrupted_simulations(storage) == 1


class ProbeBatchService:
    probe = ConcurrencyProbe()

    def __init__(self, storage):
        self.storage = storage

    async def execute_simulation(self, *, workspace_id, scenario_id, run_id, **_):
        await self.probe.run(run_id)
        self.storage.update_scenario_status(
            workspace_id, scenario_id, "completed", run_id
        )


def _run_batch(monkeypatch, client_factory, workspace_id, scenario_ids):
    ProbeBatchService.probe = ConcurrencyProbe()
    monkeypatch.setattr(batch_router, "SimulationService", ProbeBatchService)
    client = client_factory("secret")
    headers = {"Authorization": "Bearer secret"}
    created = client.post(
        f"/api/workspaces/{workspace_id}/run-all",
        json={"scenario_ids": scenario_ids, "parallel": True},
        headers=headers,
    )
    return client.get(
        f"/api/batches/{created.json()['id']}/status", headers=headers
    ).json()


def test_batch_runs_in_sequence_and_releases_its_runs(
    monkeypatch, client_factory, tmp_path
) -> None:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace_id, scenario_ids = _workspace_with(storage, 3)

    body = _run_batch(monkeypatch, client_factory, workspace_id, scenario_ids)

    assert "parallel" not in body
    assert body["status"] == "completed"
    assert ProbeBatchService.probe.peak == 1
    assert len(ProbeBatchService.probe.started) == 3
    assert simulations._active_runs == {}


def test_batch_skips_a_scenario_that_is_already_running(
    monkeypatch, client_factory, tmp_path
) -> None:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace_id, (busy, free) = _workspace_with(storage, 2)
    (busy_run,) = _reserve_all(storage, workspace_id, [busy])

    body = _run_batch(monkeypatch, client_factory, workspace_id, [busy, free])

    outcomes = {item["scenario_id"]: item for item in body["scenarios"]}
    assert outcomes[busy]["status"] == "failed"
    assert outcomes[busy]["error_message"] == "Scenario already has an active run"
    assert outcomes[free]["status"] == "completed"
    assert list(simulations._active_runs) == [busy_run.id]
