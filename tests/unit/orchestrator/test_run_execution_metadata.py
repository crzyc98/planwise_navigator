"""Append-only terminal execution metadata tests."""

import json

import duckdb
import pytest

from planalign_orchestrator.engine.records import InvocationExecutionRecord
from planalign_orchestrator.run_execution_metadata import (
    append_run_execution_metadata,
)
from planalign_orchestrator.utils import DatabaseConnectionManager

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def _record(sequence: int, mode: str, reason: str | None = None):
    return InvocationExecutionRecord(
        run_id="run-1",
        sequence=sequence,
        year=2025,
        stage="FOUNDATION",
        mode=mode,
        reason_code=reason,
        context_digest="c" * 64 if mode == "direct" else None,
        bundle_digest="b" * 64 if mode == "direct" else None,
        planned_nodes=("model.pkg.a",),
        attempted_nodes=("model.pkg.a",),
        completed_nodes=("model.pkg.a",),
        target_database_digest="d" * 64,
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        elapsed_seconds=1.0,
        rollback_attempted=False,
        rollback_succeeded=False,
        outcome="success",
    )


def test_terminal_metadata_is_append_only(tmp_path) -> None:
    database = tmp_path / "metadata.duckdb"
    manager = DatabaseConnectionManager(database)
    records = (_record(0, "direct"), _record(1, "dbt_delegation", "command"))

    append_run_execution_metadata(
        manager,
        run_id="run-1",
        status="success",
        execution_engine="compiled",
        records=records,
    )
    append_run_execution_metadata(
        manager,
        run_id="run-2",
        status="failed",
        execution_engine="compiled",
    )

    manager.close_all()
    with duckdb.connect(str(database), read_only=True) as connection:
        rows = connection.execute(
            "SELECT run_id, status, direct_invocation_count, "
            "delegated_invocation_count, reason_counts_json "
            "FROM run_execution_metadata ORDER BY recorded_at"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0][:4] == ("run-1", "success", 1, 1)
    assert json.loads(rows[0][4]) == {"command": 1}
