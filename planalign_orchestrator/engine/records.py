"""Immutable invocation execution records for compiled-engine evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class InvocationExecutionRecord:
    run_id: str
    sequence: int
    year: Optional[int]
    stage: Optional[str]
    mode: str
    reason_code: Optional[str]
    context_digest: Optional[str]
    bundle_digest: Optional[str]
    planned_nodes: Tuple[str, ...]
    attempted_nodes: Tuple[str, ...]
    completed_nodes: Tuple[str, ...]
    target_database_digest: str
    started_at: str
    finished_at: str
    elapsed_seconds: float
    rollback_attempted: bool
    rollback_succeeded: bool
    outcome: str
    error_context: Optional[Dict[str, Any]] = None
