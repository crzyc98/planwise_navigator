"""Detect a census that is more than one year behind the simulation (#1078).

The engine treats the census as the year-end before ``start_year``. A 2024
census projected from 2026 therefore skips 2025's hires, so first-year
turnover runs low. Rolling the census forward closes the gap
(``census_rollforward``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb


def infer_census_year(census_path: Path) -> Optional[int]:
    """Return the census year: the latest hire year holding at least 1% of rows.

    Mirrors ``stg_census_data``'s census calendar, which ignores a handful of
    stray future-dated hires.
    """
    path = str(census_path.resolve()).replace("'", "''")
    with duckdb.connect() as conn:
        row = conn.execute(f"""
            WITH hires AS (
              SELECT YEAR(TRY_CAST(employee_hire_date AS DATE)) AS hire_year,
                COUNT(*) AS n
              FROM read_parquet('{path}')
              GROUP BY 1
            )
            SELECT MAX(hire_year) FROM hires
            WHERE hire_year IS NOT NULL
              AND n >= GREATEST(1, (SELECT SUM(n) FROM hires) * 0.01)
            """).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def census_gap_message(census_year: int, start_year: int) -> Optional[str]:
    """Explain a gap between the census and the first simulated year, if any."""
    if start_year <= census_year + 1:
        return None
    missing = (
        str(census_year + 1)
        if start_year == census_year + 2
        else f"{census_year + 1}-{start_year - 1}"
    )
    return (
        f"The census is from {census_year} but the simulation starts in "
        f"{start_year}, so {missing} has no simulated hires and first-year "
        f"turnover runs low. Roll the census forward to {start_year - 1} "
        f"first (planalign census roll-forward)."
    )
