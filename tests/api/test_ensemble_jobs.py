"""Studio seed-ensemble jobs: estimate, lifecycle, queueing, cancel, recovery.

Jobs run tests/fixtures/ensemble_stub.py in place of ``planalign simulate``.
The stub speaks the real progress protocol and exit codes, so every outcome is
exercised through the real runner, slot, registry and API.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import psutil
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.config import APISettings
from planalign_api.models.ensemble_job import (
    EnsembleEstimate,
    EnsembleJob,
    EnsembleProgress,
    EnsembleRequest,
)
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import ensembles
from planalign_api.services.ensemble_jobs import (
    EnsembleJobService,
    fail_interrupted_ensembles,
)
from planalign_api.services.ensemble_jobs.runner import EnsembleRegistry, JobPaths
from planalign_api.services.ensemble_jobs.store import EnsembleJobStore
from planalign_api.services.simulation import run_slots
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_ensemble.progress import (
    ENV_FLAG,
    emit_pool_event,
    parse_progress_line,
)
from planalign_orchestrator.run_pool import EventKind, PoolEvent

pytestmark = [pytest.mark.fast]

STUB = Path(__file__).parents[1] / "fixtures" / "ensemble_stub.py"
TERMINAL = {"completed", "partial", "failed", "cancelled"}


@dataclass
class StubCommands:
    behaviour: str = "success"
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, job: EnsembleJob, paths: JobPaths) -> list[str]:
        command = [
            sys.executable,
            str(STUB),
            self.behaviour,
            str(paths.output_root),
            ",".join(str(seed) for seed in job.seeds),
            job.job_id,
        ]
        self.calls.append(command)
        return command


@dataclass
class Harness:
    storage: WorkspaceStorage
    workspace_id: str
    scenario_id: str
    commands: StubCommands
    registry: EnsembleRegistry

    def service(self) -> EnsembleJobService:
        return EnsembleJobService(
            self.storage, registry=self.registry, command_factory=self.commands
        )

    def scenario_url(self, suffix: str = "") -> str:
        return (
            f"/api/workspaces/{self.workspace_id}/scenarios/{self.scenario_id}"
            f"/ensembles{suffix}"
        )

    def jobs_url(self, suffix: str = "") -> str:
        return f"/api/workspaces/{self.workspace_id}/ensembles{suffix}"


@pytest.fixture(autouse=True)
def default_slot_limit(monkeypatch) -> None:
    """Studio's default: one simulation at a time (#1086)."""
    monkeypatch.setattr(run_slots, "get_settings", lambda: APISettings())


@pytest.fixture
def harness(tmp_path) -> Harness:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    census = tmp_path / "census.parquet"
    census.write_bytes(b"stub census")
    base = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    base["setup"]["census_parquet_path"] = str(census)
    base["simulation"].update(start_year=2026, end_year=2027, random_seed=7)
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), base)
    scenario = storage.create_scenario(workspace.id, ScenarioCreate(name="Baseline"))
    assert scenario is not None
    return Harness(
        storage, workspace.id, scenario.id, StubCommands(), EnsembleRegistry()
    )


@pytest.fixture
def client(harness) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(ensembles.router, prefix="/api")
    app.dependency_overrides[ensembles.get_ensemble_job_service] = harness.service
    with TestClient(app) as test_client:
        yield test_client


def _wait(predicate: Callable[[], Any], timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


def _wait_terminal(client: TestClient, harness: Harness, job_id: str) -> dict:
    def _poll() -> dict | None:
        body = client.get(harness.jobs_url(f"/{job_id}")).json()
        return body if body["status"] in TERMINAL else None

    return _wait(_poll)


def _start(client: TestClient, harness: Harness, seed_count: int = 3) -> dict:
    response = client.post(harness.scenario_url(), json={"seed_count": seed_count})
    assert response.status_code == 202, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Estimate
# ---------------------------------------------------------------------------


def test_estimate_is_returned_before_anything_starts(client, harness) -> None:
    response = client.post(harness.scenario_url("/estimate"), json={"seed_count": 3})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["seeds"] == [7, 1008, 2009]  # base seed + 1001*i, as the CLI does
    assert (body["start_year"], body["end_year"]) == (2026, 2027)
    assert body["run_count"] == 3
    assert body["workers"] == 1
    assert body["time_basis"] == "default"
    assert body["seconds_per_run"] == 60.0  # 30s per run-year x 2 years
    assert body["estimated_seconds"] == 180.0
    assert body["estimated_disk_mib"] == pytest.approx(3 * (11.6 * 2 + 18) + 4)
    assert harness.commands.calls == []
    assert not (
        harness.storage.workspaces_root / harness.workspace_id / "ensembles"
    ).exists()


def test_estimate_scales_the_scenarios_last_completed_run(client, harness) -> None:
    runs = (
        harness.storage._scenario_path(harness.workspace_id, harness.scenario_id)
        / "runs"
    )
    for name, completed_at, duration, status in (
        ("old", "2026-01-01T00:00:00", 400.0, "completed"),
        ("new", "2026-02-01T00:00:00", 100.0, "completed"),
        ("bad", "2026-03-01T00:00:00", 10.0, "failed"),
    ):
        (runs / name).mkdir(parents=True)
        (runs / name / "run_metadata.json").write_text(
            json.dumps(
                {
                    "status": status,
                    "completed_at": completed_at,
                    "duration_seconds": duration,
                    "start_year": 2025,
                    "end_year": 2026,
                }
            )
        )

    body = client.post(harness.scenario_url("/estimate"), json={"seed_count": 4}).json()

    assert body["time_basis"] == "measured"
    assert body["seconds_per_run"] == 100.0  # 50s/year from "new" x 2 years
    assert body["estimated_seconds"] == 400.0


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_ensemble_completes_with_per_seed_progress_and_reader_ids(
    client, harness
) -> None:
    job = _start(client, harness)
    assert job["status"] == "queued"
    assert job["seeds"] == [7, 1008, 2009]
    assert job["estimate"]["run_count"] == 3

    done = _wait_terminal(client, harness, job["job_id"])

    assert done["status"] == "completed", done
    assert done["progress"] == {
        "seeds_total": 3,
        "seeds_completed": 3,
        "seeds_failed": 0,
        "current_seed": None,
        "updated_at": done["progress"]["updated_at"],
    }
    assert done["started_at"] and done["completed_at"]
    output = done["output"]
    assert output["ensemble_id"] == "ens-stub"
    assert output["ensemble_scenario_id"] == "scenario-in-db"
    job_dir = harness.storage.workspaces_root / harness.workspace_id / "ensembles"
    job_dir = job_dir / job["job_id"]
    assert Path(output["database_path"]) == (job_dir / "ensemble.duckdb").resolve()
    assert not (job_dir / "work").exists()
    # The existing reader finds it through the path on the record.
    found = client.get("/api/ensembles/discover", params={"root": str(job_dir)}).json()
    assert [item["ensemble_ids"] for item in found] == [["ens-stub"]]


def test_list_filters_by_scenario(client, harness) -> None:
    job = _start(client, harness, seed_count=2)
    _wait_terminal(client, harness, job["job_id"])

    everything = client.get(harness.jobs_url()).json()
    mine = client.get(harness.jobs_url(), params={"scenario_id": harness.scenario_id})
    other = client.get(harness.jobs_url(), params={"scenario_id": str(uuid.uuid4())})

    assert [item["job_id"] for item in everything] == [job["job_id"]]
    assert [item["job_id"] for item in mine.json()] == [job["job_id"]]
    assert other.json() == []


def test_some_failed_seeds_is_a_partial_outcome(client, harness) -> None:
    harness.commands.behaviour = "partial"
    done = _wait_terminal(client, harness, _start(client, harness)["job_id"])

    assert done["status"] == "partial"
    assert done["failed_seeds"] == [2009]
    assert done["progress"]["seeds_completed"] == 2
    assert done["progress"]["seeds_failed"] == 1
    assert done["error"]["kind"] == "seeds_failed"
    assert done["output"]["ensemble_id"] == "ens-stub"


def test_no_successful_seed_fails_the_job(client, harness) -> None:
    harness.commands.behaviour = "none"
    done = _wait_terminal(client, harness, _start(client, harness)["job_id"])

    assert done["status"] == "failed"
    assert done["error"]["kind"] == "no_seeds"
    assert done["output"] is None


def test_a_cli_error_fails_without_leaking_server_paths(client, harness) -> None:
    harness.commands.behaviour = "crash"
    done = _wait_terminal(client, harness, _start(client, harness)["job_id"])

    assert done["status"] == "failed"
    assert done["error"]["kind"] == "unexpected"
    assert "exit code 1" in done["error"]["message"]
    assert str(harness.storage.workspaces_root) not in done["error"]["message"]


def test_missing_census_is_refused_before_queueing(client, harness, tmp_path) -> None:
    (tmp_path / "census.parquet").unlink()

    response = client.post(harness.scenario_url(), json={"seed_count": 2})

    assert response.status_code == 422
    assert client.get(harness.jobs_url()).json() == []


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_running_stops_the_whole_process_tree(client, harness) -> None:
    harness.commands.behaviour = "sleep"
    job = _start(client, harness)
    store = EnsembleJobStore(harness.storage.workspaces_root)
    child_pid_file = store.work_dir(harness.workspace_id, job["job_id"]) / "output"

    _wait(
        lambda: (
            client.get(harness.jobs_url(f"/{job['job_id']}")).json()["progress"][
                "current_seed"
            ]
            == 7
            and (child_pid_file / "child.pid").exists()
        )
    )
    cli_pid = store.recorded_process(harness.workspace_id, job["job_id"])
    child_pid = int((child_pid_file / "child.pid").read_text())

    response = client.post(harness.jobs_url(f"/{job['job_id']}/cancel"))

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert cli_pid is not None
    for pid in (cli_pid, child_pid):
        _wait(lambda pid=pid: not _alive(pid), timeout=15)
    again = client.post(harness.jobs_url(f"/{job['job_id']}/cancel"))
    assert again.status_code == 409


def _alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def test_cancel_while_queued_never_starts(harness) -> None:
    service = harness.service()

    async def main() -> str:
        release = asyncio.Event()
        holder = asyncio.create_task(_hold_slot(release))
        await asyncio.sleep(0)
        job = service.start(
            harness.workspace_id, harness.scenario_id, EnsembleRequest(seed_count=2)
        )
        await asyncio.sleep(0.2)
        assert service.get(harness.workspace_id, job.job_id).status == "queued"
        cancelled = service.cancel(harness.workspace_id, job.job_id)
        assert cancelled.status == "cancelled"
        assert not service.store.work_dir(harness.workspace_id, job.job_id).exists()
        release.set()
        await holder
        await _drain()
        return job.job_id

    job_id = asyncio.run(main())

    assert harness.commands.calls == []
    assert harness.service().get(harness.workspace_id, job_id).status == "cancelled"
    assert not harness.registry.owns(job_id)


# ---------------------------------------------------------------------------
# Queueing with simulations (#1086)
# ---------------------------------------------------------------------------


async def _hold_slot(release: asyncio.Event) -> None:
    async with run_slots.simulation_slot():
        await release.wait()


async def _drain() -> None:
    """Let every queued ensemble task finish."""
    current = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task is not current]
    await asyncio.wait_for(asyncio.gather(*pending), timeout=30)


def test_ensemble_waits_for_a_running_simulation(harness) -> None:
    service = harness.service()

    async def main() -> tuple[str, str]:
        release = asyncio.Event()
        holder = asyncio.create_task(_hold_slot(release))
        await asyncio.sleep(0)
        job = service.start(
            harness.workspace_id, harness.scenario_id, EnsembleRequest(seed_count=2)
        )
        await asyncio.sleep(0.3)
        while_held = service.get(harness.workspace_id, job.job_id).status
        assert harness.commands.calls == []
        release.set()
        await holder
        await _drain()
        return while_held, service.get(harness.workspace_id, job.job_id).status

    assert asyncio.run(main()) == ("queued", "completed")


def test_simulation_waits_for_a_running_ensemble(harness) -> None:
    harness.commands.behaviour = "sleep"
    service = harness.service()

    async def main() -> None:
        job = service.start(
            harness.workspace_id, harness.scenario_id, EnsembleRequest(seed_count=2)
        )
        while (
            service.get(harness.workspace_id, job.job_id).progress.current_seed is None
        ):
            await asyncio.sleep(0.05)
        entered = asyncio.Event()

        async def simulation() -> None:
            async with run_slots.simulation_slot():
                entered.set()

        sim = asyncio.create_task(simulation())
        await asyncio.sleep(0.3)
        assert not entered.is_set()
        cancelled = await asyncio.to_thread(
            service.cancel, harness.workspace_id, job.job_id
        )
        assert cancelled.status == "cancelled"
        await asyncio.wait_for(sim, timeout=10)
        assert entered.is_set()

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Restart recovery
# ---------------------------------------------------------------------------


def _record(harness: Harness, status: str) -> EnsembleJob:
    seeds = [7, 1008]
    estimate = EnsembleEstimate(
        seed_count=2,
        seeds=seeds,
        start_year=2026,
        end_year=2027,
        run_count=2,
        workers=1,
        seconds_per_run=60.0,
        estimated_seconds=120.0,
        time_basis="default",
        estimated_disk_mib=100.0,
    )
    return EnsembleJob(
        job_id=f"ens_{uuid.uuid4().hex[:12]}",
        workspace_id=harness.workspace_id,
        scenario_id=harness.scenario_id,
        scenario_name="Baseline",
        status=status,  # type: ignore[arg-type]
        seed_count=2,
        seeds=seeds,
        start_year=2026,
        end_year=2027,
        estimate=estimate,
        created_at=datetime.now(timezone.utc),
        progress=EnsembleProgress(seeds_total=2),
    )


def test_restart_marks_queued_and_running_jobs_failed(harness) -> None:
    store = EnsembleJobStore(harness.storage.workspaces_root)
    queued, running, finished = (
        _record(harness, status) for status in ("queued", "running", "completed")
    )
    for job in (queued, running, finished):
        store.save(job)
    store.work_dir(harness.workspace_id, running.job_id).mkdir()
    orphan = subprocess.Popen(
        [sys.executable, "-c", "import time, sys; time.sleep(120)", running.job_id]
    )
    store.record_process(harness.workspace_id, running.job_id, orphan.pid)
    try:
        assert fail_interrupted_ensembles(harness.storage) == 2
        assert orphan.wait(timeout=15) is not None
    finally:
        if orphan.poll() is None:
            orphan.kill()

    for job in (queued, running):
        record = store.load(harness.workspace_id, job.job_id)
        assert record is not None and record.status == "failed"
        assert record.error is not None and record.error.kind == "interrupted"
        assert f"while this ensemble was {job.status}" in record.error.message
    assert not store.work_dir(harness.workspace_id, running.job_id).exists()
    untouched = store.load(harness.workspace_id, finished.job_id)
    assert untouched is not None and untouched.status == "completed"


# ---------------------------------------------------------------------------
# Path and id safety
# ---------------------------------------------------------------------------


def test_ids_and_bounds_are_validated(client, harness) -> None:
    other = str(uuid.uuid4())
    assert client.get("/api/workspaces/not-a-uuid/ensembles").status_code == 404
    assert client.get(f"/api/workspaces/{other}/ensembles").status_code == 404
    assert client.get(harness.jobs_url("/ens_000000000000")).status_code == 404
    assert client.get(harness.jobs_url("/..%2F..%2Fworkspace.json")).status_code == 404
    assert client.get(harness.jobs_url("/fit_abc")).status_code == 404
    bad_scenario = f"/api/workspaces/{harness.workspace_id}/scenarios/x/ensembles"
    assert client.post(bad_scenario, json={"seed_count": 2}).status_code == 404
    for seed_count in (1, 51):
        response = client.post(harness.scenario_url(), json={"seed_count": seed_count})
        assert response.status_code == 422
    assert (
        EnsembleJobStore(harness.storage.workspaces_root).load(
            harness.workspace_id, "../escape"
        )
        is None
    )
    assert harness.commands.calls == []


# ---------------------------------------------------------------------------
# Progress protocol
# ---------------------------------------------------------------------------


def test_progress_records_are_emitted_only_when_enabled(monkeypatch, capsys) -> None:
    event = PoolEvent(
        EventKind.JOB_FAILED, "seed_1008", duration_seconds=1.5, error="x"
    )
    monkeypatch.delenv(ENV_FLAG, raising=False)
    emit_pool_event(event)
    assert capsys.readouterr().out == ""

    monkeypatch.setenv(ENV_FLAG, "1")
    emit_pool_event(event)
    record = parse_progress_line(capsys.readouterr().out)

    assert record == {
        "v": 1,
        "event": "seed_failed",
        "seed": 1008,
        "duration_seconds": 1.5,
        "error": "x",
    }
    assert parse_progress_line("  ✓ seed_7 completed (1.0s)") is None
    assert parse_progress_line("PLANALIGN_ENSEMBLE_PROGRESS|{not json") is None
