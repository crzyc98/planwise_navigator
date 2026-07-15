"""Determinism comparison and its minimal wall-clock exemption policy.

Only ``fct_yearly_events.created_at`` and
``fct_workforce_snapshot.snapshot_created_at`` are exempt because dbt populates
them from ``CURRENT_TIMESTAMP``. ``run_metadata`` is excluded as a whole because
it records run timestamps and fingerprints rather than simulation state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb

COMPARED_TABLES = ("fct_yearly_events", "fct_workforce_snapshot")
WHOLE_TABLE_EXCLUSIONS = {
    "run_metadata": "Run timestamps and fingerprints are bookkeeping by design."
}


@dataclass(frozen=True, slots=True)
class ExemptField:
    """A wall-clock field omitted from deterministic state comparison."""

    table: str
    column: str
    justification: str


EXEMPT_FIELDS = (
    ExemptField(
        "fct_yearly_events",
        "created_at",
        "Build-time CURRENT_TIMESTAMP; not simulation state.",
    ),
    ExemptField(
        "fct_workforce_snapshot",
        "snapshot_created_at",
        "Build-time CURRENT_TIMESTAMP; not simulation state.",
    ),
)


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def _quoted(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _columns(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    exempt: Iterable[ExemptField],
) -> list[str]:
    rows = connection.execute(f"DESCRIBE run_a.{_quoted(table)}").fetchall()
    excluded = {field.column for field in exempt if field.table == table}
    return [row[0] for row in rows if row[0] not in excluded]


def _diff_sql(table: str, projection: str) -> str:
    qualified = _quoted(table)
    return f"""
WITH a_only AS (
  SELECT {projection} FROM run_a.{qualified}
  EXCEPT
  SELECT {projection} FROM run_b.{qualified}
),
b_only AS (
  SELECT {projection} FROM run_b.{qualified}
  EXCEPT
  SELECT {projection} FROM run_a.{qualified}
)
SELECT 'a_only' AS difference_source, * FROM a_only
UNION ALL
SELECT 'b_only' AS difference_source, * FROM b_only
"""


def compare_tables(
    db_a: Path,
    db_b: Path,
    table: str,
    exempt: Iterable[ExemptField] = EXEMPT_FIELDS,
) -> tuple[int, int, int, list[tuple[object, ...]]]:
    """Compare one table using counts plus symmetric EXCEPT and bounded samples."""
    if table not in COMPARED_TABLES:
        raise ValueError(f"Unsupported deterministic comparison table: {table}")
    with duckdb.connect() as connection:
        connection.execute(f"ATTACH '{_sql_path(db_a)}' AS run_a (READ_ONLY)")
        connection.execute(f"ATTACH '{_sql_path(db_b)}' AS run_b (READ_ONLY)")
        columns = _columns(connection, table, exempt)
        projection = ", ".join(_quoted(column) for column in columns)
        count_a = connection.execute(
            f"SELECT COUNT(*) FROM run_a.{_quoted(table)}"
        ).fetchone()[0]
        count_b = connection.execute(
            f"SELECT COUNT(*) FROM run_b.{_quoted(table)}"
        ).fetchone()[0]
        diff_sql = _diff_sql(table, projection)
        diff_count = connection.execute(
            f"SELECT COUNT(*) FROM ({diff_sql}) differences"
        ).fetchone()[0]
        order_columns = [
            column
            for column in (
                "simulation_year",
                "employee_id",
                "event_sequence",
                "event_type",
            )
            if column in columns
        ]
        order_by = ", ".join(_quoted(column) for column in order_columns)
        samples = connection.execute(
            f"SELECT * FROM ({diff_sql}) differences ORDER BY {order_by} LIMIT 20"
        ).fetchall()
    return count_a, count_b, diff_count, samples
