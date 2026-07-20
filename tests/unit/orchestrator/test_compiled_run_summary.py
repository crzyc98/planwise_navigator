"""Compiled invocation aggregation tests."""

import pytest

from planalign_orchestrator.engine.records import InvocationExecutionRecord
from planalign_orchestrator.run_summary import aggregate_execution_records

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def _record(mode: str, reason: str | None, rollback: bool = False):
    return InvocationExecutionRecord(
        run_id="run",
        sequence=0,
        year=2025,
        stage="FOUNDATION",
        mode=mode,
        reason_code=reason,
        context_digest=None,
        bundle_digest=None,
        planned_nodes=("model.a",),
        attempted_nodes=("model.a",),
        completed_nodes=("model.a",),
        target_database_digest="d",
        started_at="start",
        finished_at="finish",
        elapsed_seconds=1.0,
        rollback_attempted=rollback,
        rollback_succeeded=rollback,
        outcome="success",
    )


def test_summary_distinguishes_expected_and_unexpected_delegation() -> None:
    summary = aggregate_execution_records(
        [
            _record("direct", None),
            _record("dbt_delegation", "command"),
            _record("dbt_delegation", "hook", rollback=True),
        ]
    )
    assert summary["direct_invocations"] == 1
    assert summary["delegated_invocations"] == 2
    assert summary["unexpected_fallbacks"] == 1
    assert summary["reason_counts"] == {"command": 1, "hook": 1}
