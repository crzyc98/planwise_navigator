"""Integration coverage for batch execution events on the WebSocket channel."""

import asyncio
from datetime import datetime, timezone

import pytest

from planalign_api.models.batch import BatchJob, BatchScenario
from planalign_api.models.scenario import Scenario
from planalign_api.routers import batch as batch_router
from planalign_api.websocket.handlers import batch_websocket
from planalign_api.websocket.manager import ConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.closed = asyncio.Event()

    async def accept(self) -> None:
        pass

    async def send_json(self, data: dict) -> None:
        self.messages.append(data)

    async def send_text(self, _data: str) -> None:
        pass

    async def receive_text(self) -> str:
        await self.closed.wait()
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect()


class FakeTelemetry:
    def __init__(self) -> None:
        self.progress = 50

    def get_snapshot(self, _run_id: str):
        return type("Snapshot", (), {"progress": self.progress})()


class FakeSimulationService:
    def __init__(self, _storage) -> None:
        pass

    async def execute_simulation(self, **_kwargs) -> None:
        await asyncio.sleep(0.3)


class FakeStorage:
    def get_merged_config(self, _workspace_id: str, _scenario_id: str) -> dict:
        return {}

    def get_scenario(self, _workspace_id: str, _scenario_id: str) -> Scenario:
        return Scenario(
            id="scenario-1",
            workspace_id="workspace-1",
            name="Baseline",
            created_at=datetime.now(timezone.utc),
            status="completed",
        )


@pytest.mark.integration
def test_batch_websocket_replays_snapshot_and_execution_terminal_state(monkeypatch):
    async def run_test() -> None:
        manager = ConnectionManager()
        socket = FakeWebSocket()
        job = BatchJob(
            id="batch-1",
            name="Nightly",
            workspace_id="workspace-1",
            status="pending",
            submitted_at=datetime.now(timezone.utc),
            scenarios=[
                BatchScenario(
                    scenario_id="scenario-1", name="Baseline", status="pending"
                )
            ],
        )
        batch_router._batch_jobs[job.id] = job
        handler = asyncio.create_task(batch_websocket(socket, job.id, manager=manager))
        await asyncio.sleep(0)
        assert socket.messages[0]["event"] == "snapshot"
        assert socket.messages[0]["overall_progress"] == 0

        await batch_router._execute_batch(
            FakeStorage(),
            "workspace-1",
            job.id,
            [
                Scenario(
                    id="scenario-1",
                    workspace_id="workspace-1",
                    name="Baseline",
                    created_at=datetime.now(timezone.utc),
                )
            ],
            False,
            None,
            manager,
        )

        events = [message["event"] for message in socket.messages]
        assert "running" in events
        assert "progress" in events
        assert events[-1] == "completed"
        assert socket.messages[-1]["overall_progress"] == 100

        socket.closed.set()
        await handler

    monkeypatch.setattr(batch_router, "SimulationService", FakeSimulationService)
    monkeypatch.setattr(batch_router, "get_telemetry_service", FakeTelemetry)
    asyncio.run(run_test())
