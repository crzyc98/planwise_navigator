"""Tests for private scratch directories, export cleanup, and import mode normalization (#1193)."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import py7zr
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.models.export import ExportStatus
from planalign_api.routers import calibration as calibration_router
from planalign_api.services.calibration_jobs import JobRunner, JobStore
from planalign_api.services.calibration_process import ProcessRegistry
from planalign_api.services.calibration_temp import (
    calibration_database_prefix,
    find_orphaned_calibration_databases,
)
from planalign_api.services.export_service import (
    BULK_EXPORT_DIR_PREFIX,
    ExportService,
    MANIFEST_VERSION,
    SINGLE_EXPORT_DIR_PREFIX,
    normalize_extracted_permissions,
)
from planalign_api.services.provenance.capture import config_fingerprint, sha256_file
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_cli.commands.gc import Reclaimable, delete_artifacts
from planalign_orchestrator import calibration_worker
from planalign_orchestrator.calibration_runner import PerYearCompensationResult

pytestmark = pytest.mark.fast


def _create_workspace(client: TestClient, name: str) -> str:
    resp = client.post("/api/workspaces", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ==================== Workspace Single & Bulk Exports ====================


def test_single_export_uses_private_dir_and_cleans_up_after_response(
    client_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Single export writes into a private mkdtemp dir and removes it via BackgroundTask."""
    temp_root = tmp_path / "tmp_exports"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

    client = client_factory(None)
    workspace_id = _create_workspace(client, "Private Single Export")

    observed_dirs: list[Path] = []
    observed_modes: list[int] = []
    original_export = ExportService.export_workspace

    def _spy_export(self, ws_id: str, output_dir: Path | None = None):
        archive_path, result = original_export(self, ws_id, output_dir=output_dir)
        observed_dirs.append(archive_path.parent)
        if os.name == "posix":
            observed_modes.append(stat.S_IMODE(archive_path.parent.stat().st_mode))
        return archive_path, result

    monkeypatch.setattr(ExportService, "export_workspace", _spy_export)

    response = client.post(f"/api/workspaces/{workspace_id}/export")

    assert response.status_code == 200
    assert len(response.content) > 0
    assert len(observed_dirs) == 1
    export_dir = observed_dirs[0]
    assert export_dir.parent == temp_root
    assert export_dir.name.startswith(SINGLE_EXPORT_DIR_PREFIX)
    if os.name == "posix":
        assert observed_modes == [0o700]
    # BackgroundTask must have removed the entire private directory.
    assert not export_dir.exists()
    assert not (temp_root / "planalign_exports").exists()


def test_export_workspace_direct_default_and_explicit_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct ExportService.export_workspace uses mkdtemp by default and honours output_dir."""
    temp_root = tmp_path / "tmp_direct"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

    storage = WorkspaceStorage(tmp_path / "workspaces")
    ws = storage.create_workspace(
        SimpleNamespace(name="Direct Export", description="", base_config={}),  # type: ignore[arg-type]
        {},
    )
    service = ExportService(storage)

    # Default output_dir=None uses a private mkdtemp dir, never shared planalign_exports
    default_archive, default_result = service.export_workspace(ws.id)
    assert default_result.status == ExportStatus.SUCCESS
    assert default_archive.exists()
    assert default_archive.parent.parent == temp_root
    assert default_archive.parent.name.startswith(SINGLE_EXPORT_DIR_PREFIX)
    if os.name == "posix":
        assert stat.S_IMODE(default_archive.parent.stat().st_mode) == 0o700
    assert not (temp_root / "planalign_exports").exists()

    # Explicit output_dir (e.g. CLI caller) is honoured verbatim
    explicit_dir = tmp_path / "cli_destination"
    explicit_archive, explicit_result = service.export_workspace(
        ws.id, output_dir=explicit_dir
    )
    assert explicit_result.status == ExportStatus.SUCCESS
    assert explicit_archive.parent == explicit_dir
    assert explicit_archive.exists()


def test_bulk_export_download_invokes_cleanup_and_removes_private_dir(
    client_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bulk export uses one private mkdtemp dir and invokes cleanup_bulk_export after download."""
    temp_root = tmp_path / "tmp_bulk"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

    client = client_factory(None)
    ws1 = _create_workspace(client, "Bulk One")
    ws2 = _create_workspace(client, "Bulk Two")

    cleanup_calls: list[str] = []
    original_cleanup = ExportService.cleanup_bulk_export

    def _spy_cleanup(self, operation_id: str) -> None:
        cleanup_calls.append(operation_id)
        original_cleanup(self, operation_id)

    monkeypatch.setattr(ExportService, "cleanup_bulk_export", _spy_cleanup)

    start_resp = client.post(
        "/api/workspaces/bulk-export", json={"workspace_ids": [ws1, ws2]}
    )
    assert start_resp.status_code == 200, start_resp.text
    op_id = start_resp.json()["operation_id"]

    # Status route sees the operation
    status_resp = client.get(f"/api/workspaces/bulk-export/{op_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["completed"] == 2

    bulk_dirs = list(temp_root.glob(f"{BULK_EXPORT_DIR_PREFIX}*"))
    assert len(bulk_dirs) == 1
    bulk_dir = bulk_dirs[0]
    if os.name == "posix":
        assert stat.S_IMODE(bulk_dir.stat().st_mode) == 0o700
    assert not (temp_root / "planalign_exports").exists()

    # Downloading first workspace removes its file but keeps second workspace available
    dl1 = client.get(f"/api/workspaces/bulk-export/{op_id}/download/{ws1}")
    assert dl1.status_code == 200
    assert len(dl1.content) > 0
    assert cleanup_calls == []
    assert bulk_dir.exists()

    # Downloading final workspace triggers cleanup_bulk_export and deletes bulk_dir
    dl2 = client.get(f"/api/workspaces/bulk-export/{op_id}/download/{ws2}")
    assert dl2.status_code == 200
    assert len(dl2.content) > 0
    assert cleanup_calls == [op_id]
    assert not bulk_dir.exists()
    assert client.get(f"/api/workspaces/bulk-export/{op_id}").status_code == 404


def test_bulk_export_prunes_stale_undownloaded_directories_on_new_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Abandoning a bulk export without downloading still cleans up after 24 hours."""
    temp_root = tmp_path / "tmp_stale_bulk"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

    storage = WorkspaceStorage(tmp_path / "workspaces")
    ws = storage.create_workspace(
        SimpleNamespace(name="Stale Bulk", description="", base_config={}),  # type: ignore[arg-type]
        {},
    )
    service = ExportService(storage)

    # Create an abandoned in-memory operation aged > 24h
    old_op = service.start_bulk_export([ws.id])
    service.execute_bulk_export(old_op.operation_id, [ws.id])
    old_dir = service._bulk_export_dirs[old_op.operation_id]
    assert old_dir.exists()
    service._bulk_export_created_at[old_op.operation_id] = datetime.now(
        timezone.utc
    ) - timedelta(hours=25)

    # Also create an orphaned disk-only directory (e.g. from before a restart) aged > 24h
    disk_orphan = Path(tempfile.mkdtemp(prefix=BULK_EXPORT_DIR_PREFIX, dir=temp_root))
    (disk_orphan / "leftover.7z").write_bytes(b"old")
    old_mtime = time.time() - 25 * 3600
    os.utime(disk_orphan, (old_mtime, old_mtime))

    # And a recent directory that must be kept
    fresh_dir = Path(tempfile.mkdtemp(prefix=BULK_EXPORT_DIR_PREFIX, dir=temp_root))
    (fresh_dir / "fresh.7z").write_bytes(b"new")

    # Starting a new bulk export triggers pruning
    service.start_bulk_export([ws.id])

    assert not old_dir.exists()
    assert service.get_bulk_export_status(old_op.operation_id) is None
    assert not disk_orphan.exists()
    assert fresh_dir.exists()


# ==================== Archive Import Mode Normalization ====================


def _build_permissive_archive(tmp_path: Path) -> Path:
    """Build a valid 7z archive whose members carry 0o666, 0o777, and setuid modes."""
    staging = tmp_path / "staging"
    nested = staging / "nested"
    nested.mkdir(parents=True)

    workspace_data = {
        "id": "perm-ws-1",
        "name": "Permissive Archive Workspace",
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-15T12:00:00",
    }
    workspace_json = staging / "workspace.json"
    workspace_bytes = json.dumps(workspace_data).encode("utf-8")
    workspace_json.write_bytes(workspace_bytes)

    world_file = nested / "world_rw.txt"
    world_file.write_text("world readable", encoding="utf-8")

    exec_file = nested / "world_rwx.sh"
    exec_file.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")

    setuid_file = nested / "setuid_tool"
    setuid_file.write_text("binary", encoding="utf-8")

    manifest_data = {
        "version": MANIFEST_VERSION,
        "export_date": "2025-01-20T10:00:00Z",
        "app_version": "1.0.0",
        "workspace_id": "perm-ws-1",
        "workspace_name": "Permissive Archive Workspace",
        "contents": {
            "scenario_count": 0,
            "scenarios": [],
            "file_count": 4,
            "total_size_bytes": len(workspace_bytes),
            "checksum_sha256": hashlib.sha256(workspace_bytes).hexdigest(),
        },
    }
    manifest_json = staging / "manifest.json"
    manifest_json.write_text(json.dumps(manifest_data), encoding="utf-8")

    if os.name == "posix":
        os.chmod(workspace_json, 0o666)
        os.chmod(world_file, 0o666)
        os.chmod(exec_file, 0o777)
        os.chmod(setuid_file, 0o4755)
        os.chmod(nested, 0o777)

    archive_path = tmp_path / "permissive.7z"
    with py7zr.SevenZipFile(archive_path, "w") as archive:
        archive.write(manifest_json, "manifest.json")
        archive.write(workspace_json, "workspace.json")
        archive.write(nested, "nested")
        archive.write(world_file, "nested/world_rw.txt")
        archive.write(exec_file, "nested/world_rwx.sh")
        archive.write(setuid_file, "nested/setuid_tool")
    return archive_path


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits only")
def test_extract_and_import_normalize_permissive_and_setuid_modes(
    tmp_path: Path,
) -> None:
    archive_path = _build_permissive_archive(tmp_path)
    storage = WorkspaceStorage(tmp_path / "workspaces")
    service = ExportService(storage)

    # 1. Direct extraction normalizes all extracted dirs to 0o700 and files to 0o600
    extract_dir = tmp_path / "extracted"
    service.extract_archive(archive_path, extract_dir)
    assert stat.S_IMODE((extract_dir / "nested").stat().st_mode) == 0o700
    for rel in (
        "manifest.json",
        "workspace.json",
        "nested/world_rw.txt",
        "nested/world_rwx.sh",
        "nested/setuid_tool",
    ):
        mode = stat.S_IMODE((extract_dir / rel).stat().st_mode)
        assert mode == 0o600, f"Expected 0o600 for {rel}, got {oct(mode)}"

    # 2. Full import copies normalized permissions into the created workspace
    imported = service.import_workspace(archive_path)
    ws_dir = storage._workspace_path(imported.workspace_id)
    assert stat.S_IMODE(ws_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((ws_dir / "nested").stat().st_mode) == 0o700
    for rel in (
        "workspace.json",
        "nested/world_rw.txt",
        "nested/world_rwx.sh",
        "nested/setuid_tool",
    ):
        mode = stat.S_IMODE((ws_dir / rel).stat().st_mode)
        assert mode == 0o600, f"Expected 0o600 for imported {rel}, got {oct(mode)}"


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits only")
def test_normalize_extracted_permissions_strips_special_and_group_other_bits(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tree"
    sub = root / "sub"
    sub.mkdir(parents=True)
    f_world = sub / "world.txt"
    f_setuid = sub / "suid.bin"
    f_setgid = sub / "sgid.bin"
    f_world.write_text("a", encoding="utf-8")
    f_setuid.write_text("b", encoding="utf-8")
    f_setgid.write_text("c", encoding="utf-8")

    os.chmod(f_world, 0o666)
    os.chmod(f_setuid, 0o4777)
    os.chmod(f_setgid, 0o2755)
    os.chmod(sub, 0o1777)

    normalize_extracted_permissions(root)

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(sub.stat().st_mode) == 0o700
    assert stat.S_IMODE(f_world.stat().st_mode) == 0o600
    assert stat.S_IMODE(f_setuid.stat().st_mode) == 0o600
    assert stat.S_IMODE(f_setgid.stat().st_mode) == 0o600


def test_normalize_extracted_permissions_noop_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def _fail_chmod(*_args, **_kwargs) -> None:
        nonlocal called
        called = True

    import planalign_api.services.export_service as export_mod

    monkeypatch.setattr(export_mod.os, "name", "nt")
    monkeypatch.setattr(export_mod.os, "chmod", _fail_chmod)

    normalize_extracted_permissions(tmp_path)
    assert called is False


# ==================== Calibration Private Scratch & Sweeper ====================


def test_calibration_job_dir_contains_db_and_is_removed_with_wage_evidence_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calibration puts db copy + YAML in one private dir and deletes all siblings after completion."""
    temp_root = tmp_path / "cal_tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

    store = JobStore(tmp_path / "jobs")

    def command(directory: Path) -> list[str]:
        code = calibration_worker.main(directory)
        return [sys.executable, "-c", f"raise SystemExit({code})"]

    runner = JobRunner(store, ProcessRegistry(), command)
    monkeypatch.setattr(calibration_router, "get_job_store", lambda: store)
    monkeypatch.setattr(calibration_router, "get_job_runner", lambda: runner)

    census = tmp_path / "census.parquet"
    census.write_bytes(b"census")
    run_id = str(uuid4())
    source_db = tmp_path / "source.duckdb"
    source_db.write_bytes(b"duckdb-source")

    base_config = {
        "setup": {"census_parquet_path": "census.parquet"},
        "simulation": {
            "start_year": 2025,
            "end_year": 2026,
            "random_seed": 42,
            "target_growth_rate": 0.03,
        },
        "compensation": {"cola_rate": 0.02},
    }
    effective = dict(base_config)
    effective["setup"] = {"census_parquet_path": str(census.resolve())}
    (tmp_path / "provenance.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "capture_state": "completed",
                "run_identity": {
                    "workspace_id": "ws1",
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
        def get_workspace(self, workspace_id: str):
            return SimpleNamespace(base_config=base_config)

        def _workspace_path(self, workspace_id: str) -> Path:
            return tmp_path

        def list_scenarios(self, workspace_id: str):
            return [SimpleNamespace(id="sc1")]

        def get_scenario_read_context(self, workspace_id: str, scenario_id: str):
            return SimpleNamespace(database_path=source_db, result_run_id=run_id)

    captured: dict[str, Path] = {}
    dir_modes: list[int] = []

    def _fake_init(self, run, **kw) -> None:
        captured["config_path"] = run.config_path
        captured["database_path"] = run.database_path
        captured["work_dir"] = run.database_path.parent
        if os.name == "posix":
            dir_modes.append(stat.S_IMODE(run.database_path.parent.stat().st_mode))
        # Simulate DuckDB WAL, spill dir, and wage_evidence parquet written beside DB
        Path(f"{run.database_path}.wal").write_bytes(b"wal")
        spill_dir = Path(f"{run.database_path}.tmp")
        spill_dir.mkdir()
        (spill_dir / "chunk.tmp").write_bytes(b"spill")
        wage_evidence = run.database_path.with_suffix(".wage_evidence.parquet")
        wage_evidence.write_bytes(b"parquet")
        captured["wage_evidence"] = wage_evidence

    sample = [
        PerYearCompensationResult(
            simulation_year=2025, avg_compensation=100000.0, headcount=10
        )
    ]
    monkeypatch.setattr(calibration_worker.CalibrationRunner, "__init__", _fake_init)
    monkeypatch.setattr(
        calibration_worker.CalibrationRunner, "run_calibration", lambda self: sample
    )

    app = FastAPI()
    app.include_router(calibration_router.router, prefix="/api")
    app.dependency_overrides[calibration_router.get_storage] = lambda: _Storage()
    client = TestClient(app)

    resp = client.post(
        "/api/calibration/run",
        json={"start_year": 2025, "end_year": 2026, "workspace_id": "ws1"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["run_id"]

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        job = client.get(f"/api/calibration/runs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.02)
    assert job["status"] == "completed"

    work_dir = captured["work_dir"]
    assert work_dir.parent == temp_root
    assert work_dir.name.startswith("planalign_calibration_")
    assert captured["config_path"].parent == work_dir
    assert captured["database_path"].parent == work_dir
    if os.name == "posix":
        assert dir_modes == [0o700]
    # Entire scratch directory — including db copy, config, WAL, spill dir, and wage evidence — is gone
    assert not work_dir.exists()
    assert not captured["database_path"].exists()
    assert not captured["wage_evidence"].exists()
    # Original source DB is untouched
    assert source_db.exists()


def test_calibration_recovery_removes_work_dir_from_cleanup_json(
    tmp_path: Path,
) -> None:
    """Restart recovery removes the job directory holding the paths in cleanup.json."""
    store = JobStore(tmp_path / "jobs")
    job = store.create("run")
    work_dir = Path(
        tempfile.mkdtemp(prefix=calibration_database_prefix(), dir=tmp_path)
    )
    db = work_dir / "calibration.duckdb"
    db.write_bytes(b"db")
    (work_dir / "calibration.wage_evidence.parquet").write_bytes(b"ev")
    (work_dir / "calibration_config.yaml").write_text("x: 1\n", encoding="utf-8")

    calibration_worker.atomic_write_json(
        store.job_dir(job.run_id) / "cleanup.json",
        {
            "config": str(work_dir / "calibration_config.yaml"),
            "database": str(db),
        },
    )
    store.record_process(job.run_id, os.getpid())

    JobRunner(store, ProcessRegistry()).recover()

    assert store.load(job.run_id).status == "failed"  # type: ignore[union-attr]
    assert not work_dir.exists()


def test_calibration_cancel_removes_entire_work_dir(tmp_path: Path) -> None:
    """Cancelling a running calibration job removes its private work_dir and siblings."""
    store = JobStore(tmp_path / "jobs")
    runner = JobRunner(
        store,
        ProcessRegistry(),
        lambda _: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    work_dir = Path(
        tempfile.mkdtemp(prefix=calibration_database_prefix(), dir=tmp_path)
    )
    db = work_dir / "calibration.duckdb"
    cfg = work_dir / "calibration_config.yaml"
    db.write_bytes(b"db")
    cfg.write_text("x: 1\n", encoding="utf-8")
    (work_dir / "calibration.wage_evidence.parquet").write_bytes(b"ev")
    Path(f"{db}.wal").write_bytes(b"wal")

    worker_req = calibration_worker.WorkerRequest.model_validate(
        {
            "kind": "run",
            "run": {
                "start_year": 2025,
                "end_year": 2026,
                "config_path": str(cfg),
                "database_path": str(db),
            },
        }
    )
    job = store.create("run")
    runner.start(job, worker_req, str(db), cfg, db)
    deadline = time.monotonic() + 5.0
    while store.recorded_process(job.run_id) is None:
        assert time.monotonic() < deadline
        time.sleep(0.01)

    runner.cancel(job.run_id)

    assert store.load(job.run_id).status == "cancelled"  # type: ignore[union-attr]
    assert not work_dir.exists()


def test_sweeper_removes_stale_directory_and_stale_legacy_file_with_siblings(
    tmp_path: Path,
) -> None:
    """The gc sweeper removes stale directories and legacy .duckdb files + siblings."""
    old_mtime = time.time() - 30 * 86400

    # 1. Stale legacy directory (no PID marker, older than grace window)
    stale_dir = tmp_path / "planalign_calibration_stale_dir"
    stale_dir.mkdir()
    (stale_dir / "calibration.duckdb").write_bytes(b"db")
    (stale_dir / "calibration.wage_evidence.parquet").write_bytes(b"ev")
    os.utime(stale_dir, (old_mtime, old_mtime))

    # 2. Dead-PID owned directory (reaped immediately)
    dead_dir = tmp_path / "planalign_calibration_999999_0_dead"
    dead_dir.mkdir()
    (dead_dir / "calibration.duckdb").write_bytes(b"db")

    # 3. Live-PID owned directory (must survive)
    live_dir = tmp_path / f"{calibration_database_prefix()}live"
    live_dir.mkdir()
    (live_dir / "calibration.duckdb").write_bytes(b"db")

    # 4. Stale legacy flat .duckdb file + .wal + .wage_evidence.parquet siblings
    legacy_db = tmp_path / "planalign_calibration_legacy.duckdb"
    legacy_wal = tmp_path / "planalign_calibration_legacy.duckdb.wal"
    legacy_ev = tmp_path / "planalign_calibration_legacy.wage_evidence.parquet"
    for p in (legacy_db, legacy_wal, legacy_ev):
        p.write_bytes(b"legacy")
        os.utime(p, (old_mtime, old_mtime))

    # 5. Unrelated file (must survive)
    unrelated = tmp_path / "keep_me.txt"
    unrelated.write_text("keep", encoding="utf-8")

    found = set(find_orphaned_calibration_databases(tmp_path))
    assert found == {stale_dir, dead_dir, legacy_db, legacy_wal, legacy_ev}

    delete_artifacts([Reclaimable(path, 0) for path in found])
    assert not stale_dir.exists()
    assert not dead_dir.exists()
    assert not legacy_db.exists()
    assert not legacy_wal.exists()
    assert not legacy_ev.exists()
    assert live_dir.exists()
    assert unrelated.exists()
