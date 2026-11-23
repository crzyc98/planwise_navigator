"""Process-wide concurrency and queue-depth limits for heavy API jobs."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import duckdb
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.config import APISettings
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import calibration as calibration_router
from planalign_api.routers import census_rollforward as rollforward_router
from planalign_api.routers import ensembles as ensembles_router
from planalign_api.routers import optimizer as optimizer_router
from planalign_api.services import census_rollforward_jobs
from planalign_api.services.calibration_jobs import JobRunner as CalibrationRunner
from planalign_api.services.calibration_jobs import JobStore as CalibrationStore
from planalign_api.services.calibration_process import (
    ProcessRegistry as CalibrationRegistry,
)
from planalign_api.services.ensemble_jobs import EnsembleJobService
from planalign_api.services.ensemble_jobs.runner import EnsembleRegistry
from planalign_api.services.simulation import run_slots
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_optimizer.models import (
    Candidate,
    DesignSpaceSpec,
    LeverSpec,
    ObjectiveConstraintSpec,
    ObjectiveTerm,
    OptimizerRun,
)
from planalign_orchestrator.calibration_runner import PerYearCompensationResult
from planalign_api.services.param_fit.runner import ProcessRegistry as ParamFitRegistry
from tests.fixtures.param_fit import (
    StubCommands as ParamFitStubCommands,
    build_fixture_pack,
    history_files,
    make_harness as make_param_fit_harness,
)

pytestmark = [pytest.mark.fast]

_CAL_ROW = PerYearCompensationResult(
    simulation_year=2025, avg_compensation=100_000.0, headcount=10
)


def _wait(predicate: Callable[[], Any], timeout: float = 10.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("condition not met within timeout")


def _set_limits(
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_concurrent: int = 1,
    max_queued: int = 10,
) -> None:
    settings = APISettings(
        max_concurrent_simulations=max_concurrent,
        max_queued_jobs_per_type=max_queued,
    )
    monkeypatch.setattr(run_slots, "get_settings", lambda: settings)


# ---------------------------------------------------------------------------
# Unified process-wide run_slots (async <-> thread sharing)
# ---------------------------------------------------------------------------


def test_default_queue_limit_setting() -> None:
    assert APISettings().max_queued_jobs_per_type == 10


def test_async_and_thread_waiters_share_one_process_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_limits(monkeypatch, max_concurrent=1)
    thread_entered = threading.Event()
    thread_release = threading.Event()
    async_entered = threading.Event()

    def _thread_job() -> None:
        with run_slots.simulation_slot_sync() as acquired:
            assert acquired
            thread_entered.set()
            assert thread_release.wait(timeout=5.0)

    worker = threading.Thread(target=_thread_job, daemon=True)

    async def _main() -> None:
        # 1. Async holder blocks thread waiter.
        async with run_slots.simulation_slot():
            worker.start()
            await asyncio.sleep(0.08)
            assert not thread_entered.is_set()
        # Slot released by async -> thread acquires it.
        assert await asyncio.to_thread(thread_entered.wait, 5.0)

        # 2. Thread holder blocks async waiter.
        async def _async_waiter() -> None:
            async with run_slots.simulation_slot():
                async_entered.set()

        task = asyncio.create_task(_async_waiter())
        await asyncio.sleep(0.08)
        assert not async_entered.is_set()
        thread_release.set()
        await asyncio.wait_for(task, timeout=5.0)
        assert async_entered.is_set()

    asyncio.run(_main())
    worker.join(timeout=5.0)
    assert run_slots.available_slots() == 1


def test_cancelled_thread_waiter_does_not_leak_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_limits(monkeypatch, max_concurrent=1)
    cancelled = threading.Event()
    outcomes: list[bool] = []

    def _waiter() -> None:
        with run_slots.simulation_slot_sync(is_cancelled=cancelled.is_set) as acquired:
            outcomes.append(acquired)

    with run_slots.simulation_slot_sync() as held:
        assert held
        thread = threading.Thread(target=_waiter, daemon=True)
        thread.start()
        time.sleep(0.05)
        cancelled.set()
        thread.join(timeout=5.0)
        assert not thread.is_alive()

    assert outcomes == [False]
    assert run_slots.available_slots() == 1


def test_failed_slot_body_releases_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_limits(monkeypatch, max_concurrent=1)
    with pytest.raises(RuntimeError, match="boom"):
        with run_slots.simulation_slot_sync() as acquired:
            assert acquired
            raise RuntimeError("boom")
    assert run_slots.available_slots() == 1


# ---------------------------------------------------------------------------
# Calibration jobs
# ---------------------------------------------------------------------------


def _gated_calibration_command(
    gate_dir: Path,
    *,
    fail: bool = False,
    iterations: int = 1,
) -> Callable[[Path], list[str]]:
    payload = json.dumps([_CAL_ROW.model_dump(mode="json")])
    script = (
        "import json, sys, time\n"
        "from pathlib import Path\n"
        "job_dir = Path(sys.argv[1])\n"
        "gate_dir = Path(sys.argv[2])\n"
        "fail = sys.argv[3] == '1'\n"
        "iters = int(sys.argv[4])\n"
        "active_file = gate_dir / f'{job_dir.name}.active'\n"
        "active_file.write_text('1')\n"
        "try:\n"
        "    for i in range(iters):\n"
        "        (gate_dir / f'{job_dir.name}.iter_{i}').write_text('ok')\n"
        "    release = gate_dir / f'{job_dir.name}.release'\n"
        "    release_all = gate_dir / 'release_all'\n"
        "    deadline = time.monotonic() + 15.0\n"
        "    while not release.exists() and not release_all.exists():\n"
        "        if time.monotonic() > deadline:\n"
        "            raise SystemExit(99)\n"
        "        time.sleep(0.02)\n"
        "    if fail:\n"
        "        (job_dir / 'error.json').write_text("
        "json.dumps({'error': 'boom', 'error_status': 409}))\n"
        "        raise SystemExit(1)\n"
        f"    (job_dir / 'result.json').write_text({payload!r})\n"
        "finally:\n"
        "    active_file.unlink(missing_ok=True)\n"
    )
    script_path = gate_dir / "cal_worker.py"
    script_path.write_text(script, encoding="utf-8")

    def _factory(job_dir: Path) -> list[str]:
        return [
            sys.executable,
            str(script_path),
            str(job_dir),
            str(gate_dir),
            "1" if fail else "0",
            str(iterations),
        ]

    return _factory


def _make_calibration_workspace(root: Path, workspace_id: str = "ws1") -> object:
    from types import SimpleNamespace
    from uuid import uuid4

    from planalign_api.services.provenance.capture import (
        config_fingerprint,
        sha256_file,
    )

    ws_dir = root / workspace_id
    ws_dir.mkdir(parents=True, exist_ok=True)
    census = ws_dir / "census.parquet"
    census.write_bytes(b"pii-safe-test-census")
    run_id = str(uuid4())
    source_db = ws_dir / "source.duckdb"
    source_db.write_bytes(b"source-db")
    base_config = {
        "setup": {"census_parquet_path": "census.parquet"},
        "simulation": {"start_year": 2025, "end_year": 2026, "random_seed": 42},
    }
    effective = {**base_config, "setup": {"census_parquet_path": str(census.resolve())}}
    (ws_dir / "provenance.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "capture_state": "completed",
                "run_identity": {
                    "workspace_id": workspace_id,
                    "intended_start_year": 2025,
                    "intended_end_year": 2026,
                },
                "configuration": {"fingerprint": config_fingerprint(effective)},
                "random_seed": 42,
                "census_input": {"sha256": sha256_file(census)[0]},
            }
        ),
        encoding="utf-8",
    )

    class _Storage:
        workspaces_root = root

        def get_workspace(self, wid: str) -> Any:
            return (
                SimpleNamespace(base_config=base_config)
                if wid == workspace_id
                else None
            )

        def _workspace_path(self, wid: str) -> Path:
            return root / wid

        def list_scenarios(self, wid: str) -> list[Any]:
            return [SimpleNamespace(id="scenario-1")] if wid == workspace_id else []

        def get_scenario_read_context(self, wid: str, sid: str) -> Any:
            return SimpleNamespace(database_path=source_db, result_run_id=run_id)

    return _Storage()


def _make_calibration_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: Callable[[Path], list[str]],
) -> tuple[TestClient, CalibrationRunner]:
    store = CalibrationStore(tmp_path / "workspaces")
    storage = _make_calibration_workspace(tmp_path / "workspaces")
    runner = CalibrationRunner(store, CalibrationRegistry(), command)
    monkeypatch.setattr(calibration_router, "get_job_store", lambda: store)
    monkeypatch.setattr(calibration_router, "get_job_runner", lambda: runner)
    app = FastAPI()
    app.include_router(calibration_router.router, prefix="/api")
    app.dependency_overrides[calibration_router.get_storage] = lambda: storage
    return TestClient(app), runner


@pytest.mark.parametrize("limit,total", [(1, 3), (2, 4)])
def test_calibration_respects_concurrency_limit_and_queues_excess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
    total: int,
) -> None:
    _set_limits(monkeypatch, max_concurrent=limit, max_queued=10)
    gate_dir = tmp_path / "gates"
    gate_dir.mkdir()
    client, runner = _make_calibration_client(
        tmp_path, monkeypatch, _gated_calibration_command(gate_dir)
    )
    run_ids: list[str] = []
    for _ in range(total):
        resp = client.post(
            "/api/calibration/run",
            json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
        )
        assert resp.status_code == 202
        run_ids.append(resp.json()["run_id"])

    _wait(lambda: len(list(gate_dir.glob("*.active"))) == limit)
    time.sleep(0.1)
    assert len(list(gate_dir.glob("*.active"))) == limit
    statuses = [
        client.get(f"/api/calibration/runs/{rid}").json()["status"] for rid in run_ids
    ]
    assert statuses.count("running") == limit
    assert statuses.count("queued") == total - limit

    (gate_dir / "release_all").write_text("go")
    _wait(lambda: all(not runner.registry.owns(rid) for rid in run_ids))
    assert all(
        client.get(f"/api/calibration/runs/{rid}").json()["status"] == "completed"
        for rid in run_ids
    )


def test_calibration_cancel_queued_never_runs_and_releases_after_failure_and_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=10)
    gate_dir = tmp_path / "gates"
    gate_dir.mkdir()
    fail_first = [True]
    fail_cmd = _gated_calibration_command(gate_dir, fail=True)
    ok_cmd = _gated_calibration_command(gate_dir, fail=False)
    started_dirs: list[str] = []

    def _command(job_dir: Path) -> list[str]:
        started_dirs.append(job_dir.name)
        if fail_first[0]:
            fail_first[0] = False
            return fail_cmd(job_dir)
        return ok_cmd(job_dir)

    client, runner = _make_calibration_client(tmp_path, monkeypatch, _command)

    first = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    ).json()["run_id"]
    _wait(lambda: (gate_dir / f"{first}.active").exists())

    queued_cancelled = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    ).json()["run_id"]
    queued_next = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    ).json()["run_id"]
    assert (
        client.get(f"/api/calibration/runs/{queued_cancelled}").json()["status"]
        == "queued"
    )

    cancel_resp = client.post(f"/api/calibration/runs/{queued_cancelled}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"
    assert queued_cancelled not in started_dirs

    # Fail the first job -> slot releases -> queued_next runs.
    (gate_dir / f"{first}.release").write_text("go")
    _wait(lambda: (gate_dir / f"{queued_next}.active").exists())
    assert client.get(f"/api/calibration/runs/{first}").json()["status"] == "failed"

    # Cancel the now-running job -> slot releases -> a fresh job completes.
    assert (
        client.post(f"/api/calibration/runs/{queued_next}/cancel").json()["status"]
        == "cancelled"
    )
    after = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    ).json()["run_id"]
    (gate_dir / "release_all").write_text("go")
    _wait(lambda: not runner.registry.owns(after))
    assert client.get(f"/api/calibration/runs/{after}").json()["status"] == "completed"
    assert queued_cancelled not in started_dirs


def test_calibration_inner_iterations_complete_with_single_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_limits(monkeypatch, max_concurrent=1)
    gate_dir = tmp_path / "gates"
    gate_dir.mkdir()
    (gate_dir / "release_all").write_text("go")
    client, runner = _make_calibration_client(
        tmp_path, monkeypatch, _gated_calibration_command(gate_dir, iterations=4)
    )
    run_id = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    ).json()["run_id"]
    _wait(lambda: not runner.registry.owns(run_id))
    assert client.get(f"/api/calibration/runs/{run_id}").json()["status"] == "completed"
    assert len(list(gate_dir.glob(f"{run_id}.iter_*"))) == 4


def test_calibration_queue_cap_returns_429_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=1)
    gate_dir = tmp_path / "gates"
    gate_dir.mkdir()
    client, runner = _make_calibration_client(
        tmp_path, monkeypatch, _gated_calibration_command(gate_dir)
    )

    first = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    )
    assert first.status_code == 202
    _wait(lambda: (gate_dir / f"{first.json()['run_id']}.active").exists())

    second = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    )
    assert second.status_code == 202

    rejected = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    )
    assert rejected.status_code == 429
    assert len(runner.store.list_jobs()) == 2

    (gate_dir / "release_all").write_text("go")
    _wait(lambda: not runner.registry.owned())


# ---------------------------------------------------------------------------
# Parameter fit & backtest jobs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def param_fit_history(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    return history_files(tmp_path_factory.mktemp("pf_history") / "census", years=3)


@pytest.fixture(scope="module")
def param_fit_pack(
    tmp_path_factory: pytest.TempPathFactory, param_fit_history: list[Path]
) -> Path:
    return build_fixture_pack(
        param_fit_history[0].parent, tmp_path_factory.mktemp("pf_pack") / "pack"
    )


def _gated_param_fit_command(
    gate_dir: Path, fixture_pack: Path
) -> tuple[Callable[..., list[str]], dict[str, str], list[str]]:
    behaviours: dict[str, str] = {}
    started: list[str] = []
    script = (
        "import shutil, sys, time\n"
        "from pathlib import Path\n"
        "job_id, pack_dir, fixture_dir, gate_dir, mode = sys.argv[1:6]\n"
        "gate = Path(gate_dir)\n"
        "active = gate / f'{job_id}.active'\n"
        "active.write_text('1')\n"
        "try:\n"
        '    print(\'PLANALIGN_FIT_PROGRESS|\' + \'{"event":"stage","stage":"fitting"}\', flush=True)\n'
        "    if mode == 'backtest':\n"
        "        for idx, seed in enumerate((42, 43), start=1):\n"
        '            print(f\'PLANALIGN_FIT_PROGRESS|{{"event":"seed_started","seed":{seed},"index":{idx},"total":2}}\', flush=True)\n'
        '            print(f\'PLANALIGN_FIT_PROGRESS|{{"event":"seed_completed","seed":{seed},"index":{idx},"total":2}}\', flush=True)\n'
        "    release = gate / f'{job_id}.release'\n"
        "    release_all = gate / 'release_all'\n"
        "    deadline = time.monotonic() + 15.0\n"
        "    while not release.exists() and not release_all.exists():\n"
        "        if time.monotonic() > deadline:\n"
        "            raise SystemExit(99)\n"
        "        time.sleep(0.02)\n"
        "    if mode == 'fail':\n"
        "        raise SystemExit(3)\n"
        "    shutil.copytree(fixture_dir, pack_dir, dirs_exist_ok=True)\n"
        "finally:\n"
        "    active.unlink(missing_ok=True)\n"
    )
    script_path = gate_dir / "pf_worker.py"
    script_path.write_text(script, encoding="utf-8")

    def _factory(job: Any, paths: Any) -> list[str]:
        started.append(job.job_id)
        mode = behaviours.get(job.job_id, behaviours.get("default", job.mode))
        return [
            sys.executable,
            str(script_path),
            job.job_id,
            str(paths.pack_dir),
            str(fixture_pack),
            str(gate_dir),
            mode,
        ]

    return _factory, behaviours, started


def _backtest_harnesses(
    tmp_path: Path,
    command: Callable[..., list[str]],
    history: list[Path],
    count: int,
) -> list[tuple[Any, str]]:
    """One workspace per backtest (one active backtest per workspace), one registry."""
    registry = ParamFitRegistry()
    harnesses = []
    for index in range(count):
        harness = make_param_fit_harness(
            tmp_path / f"ws{index}", command, registry=registry
        )
        harnesses.append((harness, harness.upload(history).json()["history_id"]))
    return harnesses


def _start_backtest(harness: Any, history_id: str) -> str:
    response = harness.start(history_id, mode="backtest", seeds=[42, 43])
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


def _status(harness: Any, job_id: str) -> str:
    return harness.client.get(harness.url(f"/param-fits/{job_id}")).json()["status"]


@pytest.mark.parametrize("limit,total", [(1, 3), (2, 4)])
def test_backtest_respects_concurrency_limit_and_queues_excess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    param_fit_history: list[Path],
    param_fit_pack: Path,
    limit: int,
    total: int,
) -> None:
    _set_limits(monkeypatch, max_concurrent=limit, max_queued=10)
    gate_dir = tmp_path / "gates"
    gate_dir.mkdir()
    command, _, _ = _gated_param_fit_command(gate_dir, param_fit_pack)
    harnesses = _backtest_harnesses(tmp_path, command, param_fit_history, total)

    jobs = [(h, _start_backtest(h, history_id)) for h, history_id in harnesses]
    _wait(lambda: len(list(gate_dir.glob("*.active"))) == limit)
    time.sleep(0.1)
    assert len(list(gate_dir.glob("*.active"))) == limit

    statuses = [_status(h, jid) for h, jid in jobs]
    assert statuses.count("running") == limit
    assert statuses.count("queued") == total - limit

    (gate_dir / "release_all").write_text("go")
    for h, jid in jobs:
        assert h.wait(jid)["status"] == "completed"


def test_backtest_cancel_queued_and_release_after_failure_and_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    param_fit_history: list[Path],
    param_fit_pack: Path,
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=10)
    gate_dir = tmp_path / "gates"
    gate_dir.mkdir()
    command, behaviours, started = _gated_param_fit_command(gate_dir, param_fit_pack)
    (first_h, first_hist), (cancel_h, cancel_hist), (next_h, next_hist) = (
        _backtest_harnesses(tmp_path, command, param_fit_history, 3)
    )

    behaviours["default"] = "fail"
    first = _start_backtest(first_h, first_hist)
    _wait(lambda: (gate_dir / f"{first}.active").exists())

    behaviours["default"] = "backtest"
    queued_cancelled = _start_backtest(cancel_h, cancel_hist)
    queued_next = _start_backtest(next_h, next_hist)
    assert _status(cancel_h, queued_cancelled) == "queued"

    cancelled = cancel_h.client.post(
        cancel_h.url(f"/param-fits/{queued_cancelled}/cancel")
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert queued_cancelled not in started

    # Release failing job -> slot frees -> queued_next starts.
    (gate_dir / f"{first}.release").write_text("go")
    _wait(lambda: (gate_dir / f"{queued_next}.active").exists())
    assert first_h.wait(first)["status"] == "failed"

    # Cancel running job -> slot frees -> new backtest completes with 1 slot.
    assert (
        next_h.client.post(next_h.url(f"/param-fits/{queued_next}/cancel")).json()[
            "status"
        ]
        == "cancelled"
    )
    backtest = _start_backtest(first_h, first_hist)
    (gate_dir / "release_all").write_text("go")
    assert first_h.wait(backtest)["status"] == "completed"
    assert queued_cancelled not in started


def test_backtest_queue_cap_returns_429_but_fits_still_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    param_fit_history: list[Path],
    param_fit_pack: Path,
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=1)
    gate_dir = tmp_path / "gates"
    gate_dir.mkdir()
    command, _, _ = _gated_param_fit_command(gate_dir, param_fit_pack)
    (run_h, run_hist), (queue_h, queue_hist), (reject_h, reject_hist) = (
        _backtest_harnesses(tmp_path, command, param_fit_history, 3)
    )

    running = _start_backtest(run_h, run_hist)
    _wait(lambda: (gate_dir / f"{running}.active").exists())
    queued = _start_backtest(queue_h, queue_hist)
    assert _status(queue_h, queued) == "queued"

    rejected = reject_h.start(reject_hist, mode="backtest", seeds=[42, 43])
    assert rejected.status_code == 429
    assert reject_h.client.get(reject_h.url("/param-fits")).json() == []

    # Fits never wait for a slot, so the backtest queue cap does not apply.
    fits = [reject_h.start(reject_hist).json()["job_id"] for _ in range(2)]
    _wait(lambda: all((gate_dir / f"{fit}.active").exists() for fit in fits))
    assert [_status(reject_h, fit) for fit in fits] == ["running", "running"]

    (gate_dir / "release_all").write_text("go")
    for harness, job_id in [(run_h, running), (queue_h, queued)] + [
        (reject_h, fit) for fit in fits
    ]:
        assert harness.wait(job_id)["status"] == "completed"
    assert run_slots.available_slots() == 1


def test_fit_starts_and_completes_while_the_only_slot_is_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    param_fit_history: list[Path],
    param_fit_pack: Path,
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=0)
    commands = ParamFitStubCommands(fixture_pack=param_fit_pack, behaviour="success")
    harness = make_param_fit_harness(tmp_path, commands)
    history_id = harness.upload(param_fit_history).json()["history_id"]

    with run_slots.simulation_slot_sync() as held:
        assert held
        response = harness.start(history_id)
        assert response.status_code == 202
        assert harness.wait(response.json()["job_id"])["status"] == "completed"
        assert run_slots.available_slots() == 0
    assert run_slots.available_slots() == 1


# ---------------------------------------------------------------------------
# Optimizer jobs
# ---------------------------------------------------------------------------


def _optimizer_spec() -> dict[str, Any]:
    return {
        "design_space": {
            "levers": [
                {
                    "name": "auto_enrollment.default_deferral_rate",
                    "kind": "continuous",
                    "bounds": [0.03, 0.08],
                }
            ]
        },
        "objective": {
            "objectives": [{"metric": "participation_rate", "direction": "maximize"}]
        },
        "baseline": {"config_path": "config/simulation_config.yaml"},
    }


def _sample_optimizer_run() -> OptimizerRun:
    return OptimizerRun(
        run_id="run-0000",
        design_space=DesignSpaceSpec(
            levers=(
                LeverSpec(
                    name="auto_enrollment.default_deferral_rate",
                    kind="continuous",
                    bounds=(0.03, 0.08),
                ),
            )
        ),
        objective_constraint_spec=ObjectiveConstraintSpec(
            objectives=(
                ObjectiveTerm(metric="participation_rate", direction="maximize"),
            )
        ),
        max_runs=3,
        search_seed=0,
        baseline_config_fingerprint="fp-abc",
        candidates=(
            Candidate(
                candidate_id="candidate-0000",
                lever_values={"auto_enrollment.default_deferral_rate": 0.05},
                status="feasible",
                objective_values={"participation_rate": 0.87},
            ),
        ),
        ranked_feasible=("candidate-0000",),
    )


@pytest.fixture
def optimizer_client(tmp_path: Path) -> Iterator[TestClient]:
    optimizer_router._reserved_dirs.clear()
    optimizer_router._jobs.clear()
    settings = APISettings(optimizer_runs_root=tmp_path / "opt_runs")
    app = FastAPI()
    app.include_router(optimizer_router.router, prefix="/api")
    app.dependency_overrides[optimizer_router.get_settings] = lambda: settings
    yield TestClient(app)
    optimizer_router._reserved_dirs.clear()
    optimizer_router._jobs.clear()


def _wait_optimizer_status(client: TestClient, run_id: str, expected: str) -> None:
    _wait(
        lambda: client.get(f"/api/optimizer/runs/{run_id}").json()["status"] == expected
    )


@pytest.mark.parametrize("limit,total", [(1, 3), (2, 4)])
def test_optimizer_respects_concurrency_limit_and_caps_inner_parallel(
    optimizer_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
    total: int,
) -> None:
    _set_limits(monkeypatch, max_concurrent=limit, max_queued=10)
    gate = threading.Event()
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}
    seen_parallel: list[int | None] = []

    def _fake_optimizer(*_args: Any, **kwargs: Any) -> tuple[OptimizerRun, None]:
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            seen_parallel.append(kwargs.get("parallel"))
        try:
            gate.wait(timeout=10.0)
            return _sample_optimizer_run(), None
        finally:
            with lock:
                state["active"] -= 1

    monkeypatch.setattr(optimizer_router, "run_optimizer", _fake_optimizer)

    run_ids: list[str] = []
    for idx in range(total):
        resp = optimizer_client.post(
            "/api/optimizer/run",
            json={
                "spec": _optimizer_spec(),
                "max_runs": 3,
                "parallel": 8,
                "database_dir": f"run_{idx}",
            },
        )
        assert resp.status_code == 202
        run_ids.append(resp.json()["run_id"])

    _wait(lambda: state["active"] == limit)
    time.sleep(0.08)
    assert state["peak"] == limit
    statuses = [
        optimizer_client.get(f"/api/optimizer/runs/{rid}").json()["status"]
        for rid in run_ids
    ]
    assert statuses.count("running") == limit
    assert statuses.count("queued") == total - limit

    gate.set()
    for rid in run_ids:
        _wait_optimizer_status(optimizer_client, rid, "completed")
    assert state["peak"] == limit
    assert seen_parallel == [1] * total


def test_optimizer_releases_slot_on_failure_and_completes_inner_candidates(
    optimizer_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=10)
    calls = {"count": 0}

    def _fake_optimizer(*_args: Any, **kwargs: Any) -> tuple[OptimizerRun, None]:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("candidate evaluation failed")
        # Simulate multi-candidate evaluation inside the single slot (no deadlock).
        assert kwargs.get("parallel") == 1
        return _sample_optimizer_run(), None

    monkeypatch.setattr(optimizer_router, "run_optimizer", _fake_optimizer)

    first = optimizer_client.post(
        "/api/optimizer/run",
        json={"spec": _optimizer_spec(), "max_runs": 3, "database_dir": "fail_run"},
    ).json()["run_id"]
    second = optimizer_client.post(
        "/api/optimizer/run",
        json={"spec": _optimizer_spec(), "max_runs": 3, "database_dir": "ok_run"},
    ).json()["run_id"]

    _wait(
        lambda: optimizer_client.get(f"/api/optimizer/runs/{first}").json()["status"]
        == "failed"
    )
    _wait(
        lambda: optimizer_client.get(f"/api/optimizer/runs/{second}").json()["status"]
        == "completed"
    )
    assert run_slots.available_slots() == 1


def test_optimizer_queue_cap_returns_429_and_releases_directory_reservation(
    optimizer_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=1)
    started = threading.Event()
    release = threading.Event()

    def _slow_optimizer(*_args: Any, **_kwargs: Any) -> tuple[OptimizerRun, None]:
        started.set()
        release.wait(timeout=10.0)
        return _sample_optimizer_run(), None

    monkeypatch.setattr(optimizer_router, "run_optimizer", _slow_optimizer)

    first = optimizer_client.post(
        "/api/optimizer/run",
        json={"spec": _optimizer_spec(), "max_runs": 2, "database_dir": "dir_1"},
    )
    assert first.status_code == 202
    assert started.wait(timeout=5.0)

    second = optimizer_client.post(
        "/api/optimizer/run",
        json={"spec": _optimizer_spec(), "max_runs": 2, "database_dir": "dir_2"},
    )
    assert second.status_code == 202

    rejected = optimizer_client.post(
        "/api/optimizer/run",
        json={"spec": _optimizer_spec(), "max_runs": 2, "database_dir": "dir_3"},
    )
    assert rejected.status_code == 429

    release.set()
    for rid in (first.json()["run_id"], second.json()["run_id"]):
        _wait_optimizer_status(optimizer_client, rid, "completed")

    # Rejected directory was released, so it can now be started cleanly.
    retry = optimizer_client.post(
        "/api/optimizer/run",
        json={"spec": _optimizer_spec(), "max_runs": 2, "database_dir": "dir_3"},
    )
    assert retry.status_code == 202
    _wait(
        lambda: optimizer_client.get(
            f"/api/optimizer/runs/{retry.json()['run_id']}"
        ).json()["status"]
        == "completed"
    )


# ---------------------------------------------------------------------------
# Queue caps for Ensembles and Census Roll-Forward
# ---------------------------------------------------------------------------


def test_ensemble_queue_cap_returns_429_without_creating_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=1)
    storage = WorkspaceStorage(tmp_path / "workspaces")
    census = storage.workspaces_root / "census.parquet"
    census.parent.mkdir(parents=True, exist_ok=True)
    census.write_bytes(b"stub census")
    base = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    base["setup"]["census_parquet_path"] = str(census)
    base["simulation"].update(start_year=2026, end_year=2027, random_seed=7)
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), base)
    scenario = storage.create_scenario(workspace.id, ScenarioCreate(name="Baseline"))
    assert scenario is not None

    registry = EnsembleRegistry()
    service = EnsembleJobService(
        storage,
        registry=registry,
        command_factory=lambda _job, _paths: [sys.executable, "-c", "pass"],
    )
    app = FastAPI()
    app.include_router(ensembles_router.router, prefix="/api")
    app.dependency_overrides[ensembles_router.get_ensemble_job_service] = (
        lambda: service
    )
    url = f"/api/workspaces/{workspace.id}/scenarios/{scenario.id}/ensembles"

    # Hold the single process slot so ensembles stay queued.
    with run_slots.simulation_slot_sync() as held:
        assert held
        with TestClient(app) as client:
            first = client.post(url, json={"seed_count": 5})
            assert first.status_code == 202
            second = client.post(url, json={"seed_count": 5})
            assert second.status_code == 429
            assert len(service.list_jobs(workspace.id)) == 1
            client.post(
                f"/api/workspaces/{workspace.id}/ensembles/{first.json()['job_id']}/cancel"
            )


def test_census_rollforward_queue_cap_returns_429(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=1)
    monkeypatch.setattr(census_rollforward_jobs, "_jobs", {})
    storage = WorkspaceStorage(tmp_path / "workspaces")
    census = tmp_path / "workspaces" / "census.parquet"
    census.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as conn:
        conn.execute(
            f"COPY (SELECT 'E' || i AS employee_id, "
            f"MAKE_DATE(2024 - (i % 3), 3, 1) AS employee_hire_date "
            f"FROM range(10) t(i)) TO '{census}' (FORMAT parquet)"
        )
    workspaces = [
        storage.create_workspace(
            WorkspaceCreate(name=f"W{i}"),
            {
                "simulation": {"start_year": 2026, "end_year": 2028},
                "setup": {"census_parquet_path": str(census)},
            },
        )
        for i in range(2)
    ]

    async def _noop_run(storage_arg: WorkspaceStorage, job_id: str) -> None:
        return None

    monkeypatch.setattr(census_rollforward_jobs, "run_job", _noop_run)
    app = FastAPI()
    app.include_router(rollforward_router.router, prefix="/api/workspaces")
    app.dependency_overrides[rollforward_router.get_storage] = lambda: storage

    with run_slots.simulation_slot_sync() as held:
        assert held
        with TestClient(app) as client:
            first = client.post(
                f"/api/workspaces/{workspaces[0].id}/census/roll-forward"
            )
            assert first.status_code == 202
            second = client.post(
                f"/api/workspaces/{workspaces[1].id}/census/roll-forward"
            )
            assert second.status_code == 429


def test_simulation_slot_blocks_calibration_and_optimizer_until_released(
    tmp_path: Path,
    optimizer_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_limits(monkeypatch, max_concurrent=1, max_queued=10)
    gate_dir = tmp_path / "cross_gates"
    gate_dir.mkdir()
    (gate_dir / "release_all").write_text("go")
    cal_client, cal_runner = _make_calibration_client(
        tmp_path / "cal_ws", monkeypatch, _gated_calibration_command(gate_dir)
    )
    opt_started = threading.Event()

    def _fake_opt(*_args: Any, **_kwargs: Any) -> tuple[OptimizerRun, None]:
        opt_started.set()
        return _sample_optimizer_run(), None

    monkeypatch.setattr(optimizer_router, "run_optimizer", _fake_opt)

    with run_slots.simulation_slot_sync() as held:
        assert held
        cal_id = cal_client.post(
            "/api/calibration/run",
            json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
        ).json()["run_id"]
        opt_id = optimizer_client.post(
            "/api/optimizer/run",
            json={"spec": _optimizer_spec(), "max_runs": 2, "database_dir": "cross"},
        ).json()["run_id"]
        time.sleep(0.1)
        assert (
            cal_client.get(f"/api/calibration/runs/{cal_id}").json()["status"]
            == "queued"
        )
        assert (
            optimizer_client.get(f"/api/optimizer/runs/{opt_id}").json()["status"]
            == "queued"
        )
        assert not opt_started.is_set()

    _wait(lambda: not cal_runner.registry.owns(cal_id))
    _wait(
        lambda: optimizer_client.get(f"/api/optimizer/runs/{opt_id}").json()["status"]
        == "completed"
    )
    assert (
        cal_client.get(f"/api/calibration/runs/{cal_id}").json()["status"]
        == "completed"
    )
