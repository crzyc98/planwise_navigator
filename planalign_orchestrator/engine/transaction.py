"""One DuckDB transaction per direct invocation (#470, research R8).

A short-lived connection is opened only after preflight, connection hooks
apply outside the transaction, every frozen operation executes inside
``BEGIN``/``COMMIT``, and any exception rolls back and closes the
connection before propagating — partial writes cannot leak into a dbt
replay or the error path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import duckdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransactionOutcome:
    committed: bool
    operations_completed: int


class TransactionExecutionError(RuntimeError):
    """A frozen operation failed; the invocation was rolled back."""

    def __init__(
        self,
        message: str,
        *,
        node: Optional[str],
        phase: str,
        statement: str,
        original: BaseException,
        rollback_attempted: bool,
        rollback_succeeded: bool,
        operations_completed: int,
    ) -> None:
        super().__init__(message)
        self.node = node
        self.phase = phase
        self.statement = statement[:500]
        self.original = original
        self.rollback_attempted = rollback_attempted
        self.rollback_succeeded = rollback_succeeded
        self.operations_completed = operations_completed


def _sql_of(operation: Any) -> str:
    if isinstance(operation, dict):
        return operation["sql"]
    return operation.sql


def _node_of(operation: Any) -> Optional[str]:
    if isinstance(operation, dict):
        return operation.get("node")
    return getattr(operation, "node", None)


def _phase_of(operation: Any) -> str:
    if isinstance(operation, dict):
        return operation.get("phase", "model")
    return getattr(operation, "phase", "model")


def execute_invocation_transaction(
    *,
    database_path: Path,
    connection_hooks: Sequence[str],
    operations: Sequence[Any],
) -> TransactionOutcome:
    """Execute one invocation's frozen operations atomically."""
    conn = duckdb.connect(str(database_path))
    completed = 0
    in_transaction = False
    try:
        for hook_sql in connection_hooks:
            if hook_sql and hook_sql.strip():
                try:
                    conn.execute(hook_sql)
                except duckdb.Error as exc:
                    logger.warning("connection hook failed (%s): %s", hook_sql, exc)
        conn.execute("BEGIN TRANSACTION")
        in_transaction = True
        for operation in operations:
            sql = _sql_of(operation)
            if not sql or not sql.strip():
                completed += 1
                continue
            try:
                conn.execute(sql)
            except Exception as exc:
                rollback_attempted = True
                rollback_succeeded = False
                try:
                    conn.execute("ROLLBACK")
                    rollback_succeeded = True
                    in_transaction = False
                except duckdb.Error as rollback_exc:
                    logger.error("rollback failed: %s", rollback_exc)
                raise TransactionExecutionError(
                    f"invocation failed at node={_node_of(operation)} "
                    f"phase={_phase_of(operation)}: {exc}",
                    node=_node_of(operation),
                    phase=_phase_of(operation),
                    statement=sql,
                    original=exc,
                    rollback_attempted=rollback_attempted,
                    rollback_succeeded=rollback_succeeded,
                    operations_completed=completed,
                ) from exc
            completed += 1
        conn.execute("COMMIT")
        in_transaction = False
        return TransactionOutcome(committed=True, operations_completed=completed)
    finally:
        if in_transaction:
            try:
                conn.execute("ROLLBACK")
            except duckdb.Error:
                pass
        conn.close()
