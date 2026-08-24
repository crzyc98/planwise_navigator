"""Retention tests for in-memory API operation registries."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from planalign_api.models.batch import BatchJob
from planalign_api.models.export import BulkOperationStatus
from planalign_api.routers import batch as batch_router
from planalign_api.services.export_service import ExportService


def _batch_job(job_id: str, status: str, completed_at: datetime) -> BatchJob:
    return BatchJob(
        id=job_id,
        name=job_id,
        workspace_id="workspace",
        status=status,
        submitted_at=completed_at - timedelta(minutes=1),
        completed_at=completed_at,
    )


def test_batch_retention_keeps_active_and_bounds_terminal_jobs(monkeypatch):
    now = datetime.now(timezone.utc)
    settings = SimpleNamespace(
        batch_operation_ttl_seconds=60,
        batch_operation_max_entries=1,
    )
    monkeypatch.setattr(batch_router, "get_settings", lambda: settings)
    registry = {
        "active": _batch_job("active", "running", now - timedelta(hours=2)),
        "old": _batch_job("old", "completed", now - timedelta(hours=2)),
        "new": _batch_job("new", "failed", now - timedelta(seconds=1)),
    }
    monkeypatch.setattr(batch_router, "_batch_jobs", registry)

    batch_router._prune_batch_jobs(now)

    assert set(registry) == {"active", "new"}


def test_bulk_import_retention_keeps_active_and_expires_terminal():
    settings = SimpleNamespace(
        bulk_import_operation_ttl_seconds=60,
        bulk_import_operation_max_entries=1,
    )
    service = ExportService(MagicMock(), settings)
    old = service.start_bulk_import(1)
    active = service.start_bulk_import(1)
    old.status = BulkOperationStatus.COMPLETED
    service._bulk_import_terminal_at[old.operation_id] = datetime.now(
        timezone.utc
    ) - timedelta(minutes=2)

    service._prune_bulk_import_operations()

    assert service.get_bulk_import_status(old.operation_id) is None
    assert service.get_bulk_import_status(active.operation_id) is not None


def test_bulk_import_retention_enforces_terminal_maximum():
    settings = SimpleNamespace(
        bulk_import_operation_ttl_seconds=3600,
        bulk_import_operation_max_entries=2,
    )
    service = ExportService(MagicMock(), settings)
    operations = [service.start_bulk_import(1) for _ in range(3)]
    for index, operation in enumerate(operations):
        operation.status = BulkOperationStatus.COMPLETED
        service._bulk_import_terminal_at[operation.operation_id] = datetime.now(
            timezone.utc
        ) - timedelta(minutes=3 - index)

    service._prune_bulk_import_operations()

    assert service.get_bulk_import_status(operations[0].operation_id) is None
    assert len(service._bulk_import_operations) == 2
