"""Resolve a census analysis date without relying on the wall clock."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import duckdb


@dataclass(frozen=True)
class ResolvedAsOf:
    """The date used for census-derived calculations and its provenance."""

    date: date
    source: str


def resolve_as_of_date(
    conn: duckdb.DuckDBPyConnection,
    hire_column: Optional[str],
    termination_column: Optional[str] = None,
    override: Optional[date] = None,
) -> ResolvedAsOf:
    """Resolve an explicit or inferred census as-of date.

    Inference uses the latest parseable termination date or hire date and anchors
    the census to December 31 of that year. Callers supply only allowlisted,
    validated column names.
    """
    if override is not None:
        return ResolvedAsOf(date=override, source="provided")

    date_expressions = []
    if termination_column:
        date_expressions.append(f"TRY_CAST({termination_column} AS DATE)")
    if hire_column:
        date_expressions.append(f"TRY_CAST({hire_column} AS DATE)")
    if not date_expressions:
        raise ValueError(
            "Cannot infer a census as-of date without a hire or termination date. "
            "Provide an as-of date."
        )

    event_date = (
        f"COALESCE({', '.join(date_expressions)})"
        if len(date_expressions) > 1
        else date_expressions[0]
    )
    row = conn.execute(f"SELECT MAX({event_date}) FROM census").fetchone()
    latest_date = row[0] if row else None
    if latest_date is None:
        raise ValueError(
            "Cannot infer a census as-of date from unparseable hire or termination dates. "
            "Provide an as-of date."
        )
    return ResolvedAsOf(date=date(latest_date.year, 12, 31), source="inferred")
