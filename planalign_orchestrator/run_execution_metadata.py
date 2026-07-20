"""Append-only terminal execution evidence for Feature 119 runs."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, Optional

from planalign_orchestrator.engine.records import InvocationExecutionRecord

RUN_EXECUTION_METADATA_TABLE = "run_execution_metadata"

_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {RUN_EXECUTION_METADATA_TABLE} (
    run_id VARCHAR NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    status VARCHAR NOT NULL,
    execution_engine VARCHAR NOT NULL,
    direct_invocation_count INTEGER NOT NULL,
    delegated_invocation_count INTEGER NOT NULL,
    unexpected_fallback_count INTEGER NOT NULL,
    reason_counts_json VARCHAR NOT NULL,
    render_context_digests_json VARCHAR NOT NULL,
    parity_status VARCHAR NOT NULL,
    peak_rss_mb DOUBLE
)
"""


def append_run_execution_metadata(
    db_manager,
    *,
    run_id: str,
    status: str,
    execution_engine: str,
    records: Iterable[InvocationExecutionRecord] = (),
    parity_status: str = "not_run",
    peak_rss_mb: Optional[float] = None,
) -> None:
    """Append exactly one terminal row; no update/delete path exists."""
    frozen = tuple(records)
    direct = sum(record.mode == "direct" for record in frozen)
    delegated = sum(record.mode == "dbt_delegation" for record in frozen)
    unexpected = sum(
        record.mode == "dbt_delegation" and record.rollback_attempted
        for record in frozen
    )
    reasons = Counter(
        record.reason_code for record in frozen if record.reason_code is not None
    )
    context_digests = sorted(
        {record.context_digest for record in frozen if record.context_digest}
    )
    with db_manager.get_connection() as connection:
        connection.execute(_CREATE_TABLE_SQL)
        connection.execute(
            f"INSERT INTO {RUN_EXECUTION_METADATA_TABLE} VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                datetime.now(timezone.utc),
                status,
                execution_engine,
                direct,
                delegated,
                unexpected,
                json.dumps(dict(sorted(reasons.items())), sort_keys=True),
                json.dumps(context_digests),
                parity_status,
                peak_rss_mb,
            ],
        )
