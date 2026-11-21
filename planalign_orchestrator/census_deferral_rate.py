"""Stop a run whose census has deferral rates outside 0-1 (#1263).

The engine reads ``employee_deferral_rate`` as a fraction of pay (0.06 for 6%).
A file that holds percentages instead (6, 15) used to run with models
disagreeing about the rate, or crash on a decimal cast once a rate reached 10.
The check reads the census file itself, before staging, because staging's own
cast fails on a rate of 100 or more. The message carries a row count only,
never row contents (PII).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb

from .exceptions import DataQualityError

RATE_COLUMN = "employee_deferral_rate"


def count_out_of_range_deferral_rates(census_path: Path) -> int:
    """Rows whose deferral rate is below 0 or above 1; 0 if the column is absent."""
    path = str(census_path.resolve()).replace("'", "''")
    source = f"read_parquet('{path}')"
    with duckdb.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()
        }
        if RATE_COLUMN not in columns:
            return 0
        row = conn.execute(f"""
            SELECT COUNT(*) FROM {source}
            WHERE TRY_CAST({RATE_COLUMN} AS DOUBLE) < 0
               OR TRY_CAST({RATE_COLUMN} AS DOUBLE) > 1
            """).fetchone()
    return int(row[0]) if row else 0


def out_of_range_message(count: int) -> Optional[str]:
    """Explain the rejection, or None when every rate is in range."""
    if not count:
        return None
    return (
        f"The census has {count} row(s) with {RATE_COLUMN} outside 0-1. "
        "Deferral rates must be a fraction of pay (0.06 for 6%, not 6). "
        "Fix the census file and run again; Census Analysis lists the rows."
    )


def require_census_deferral_rates(census_path: Optional[Path]) -> None:
    """Reject the census before staging when any deferral rate is out of range."""
    if census_path is None or not census_path.exists():
        return  # staging reports a missing census itself
    message = out_of_range_message(count_out_of_range_deferral_rates(census_path))
    if message:
        raise DataQualityError(message)
