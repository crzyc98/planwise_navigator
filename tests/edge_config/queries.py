"""Read-only targeted queries over completed simulation outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from .assertions import TargetedAssertionResult
from .catalog import EdgeConfigScenario


def _query(
    database: Path, sql: str, params: list[Any] | None = None
) -> list[dict[str, Any]]:
    with duckdb.connect(str(database), read_only=True) as connection:
        cursor = connection.execute(sql, params or [])
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def execute_violation_query(
    database: Path, sql: str, sample_limit: int = 20
) -> list[dict[str, Any]]:
    """Execute a caller-supplied read-only query with a hard diagnostic bound."""
    if not database.exists():
        raise FileNotFoundError(database)
    if not 1 <= sample_limit <= 20:
        raise ValueError("sample_limit must be between 1 and 20")
    return _query(database, f"SELECT * FROM ({sql}) violations LIMIT {sample_limit}")


def targeted_query(case: EdgeConfigScenario, database: Path) -> TargetedAssertionResult:
    """Return a targeted result using the stable fact-table columns available to all cases."""
    result = TargetedAssertionResult(
        case.name, case.boundary, case.assertion_kind, sample_limit=case.sample_limit
    )
    sql = (
        "SELECT employee_id, simulation_year FROM fct_workforce_snapshot "
        "WHERE simulation_year BETWEEN ? AND ? AND employee_id IS NULL"
    )
    for row in _query(database, sql, [case.start_year, case.end_year]):
        result.add("missing employee_id", row)
    result.observed = "no targeted violations" if result.passed else result.observed
    return result
