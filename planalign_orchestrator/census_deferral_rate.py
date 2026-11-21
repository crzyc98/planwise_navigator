"""Stop a run whose census has unusable deferral rates (#1263).

The engine reads ``employee_deferral_rate`` as a fraction of pay (0.06 for 6%).
A file that holds percentages instead (6, 15) used to run with models
disagreeing about the rate, or crash on a decimal cast once a rate reached 10.
The check reads the census file itself, before anything is built or cleared,
because staging's own cast fails on a rate of 100 or more and on text such as
``6%``. The message carries a row count only, never row contents (PII).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import duckdb

from .exceptions import DataQualityError

logger = logging.getLogger(__name__)

RATE_COLUMN = "employee_deferral_rate"
# dbt_project.yml's default for the census_parquet_path var.
DEFAULT_CENSUS_FILE = "census_preprocessed.parquet"


def resolve_census_path(configured: object, dbt_dir: Path) -> Path:
    """The census dbt will read: the configured path, else dbt's default."""
    if configured:
        return Path(str(configured))
    data_dir = Path(os.environ.get("DATA_PATH", "../data"))
    if not data_dir.is_absolute():
        data_dir = dbt_dir / data_dir
    return data_dir / DEFAULT_CENSUS_FILE


def count_bad_deferral_rates(census_path: Path) -> int:
    """File rows whose rate is not a number or rounds outside 0-1.

    Counts every row in the file, including duplicates staging would drop.
    Rounds as staging does (5 places), so float noise around 0 and 1 passes.
    """
    path = str(census_path.resolve()).replace("'", "''")
    source = f"read_parquet('{path}')"
    rate = f"TRY_CAST({RATE_COLUMN} AS DOUBLE)"
    with duckdb.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()
        }
        if RATE_COLUMN not in columns:
            return 0
        row = conn.execute(f"""
            SELECT COUNT(*) FROM {source}
            WHERE {RATE_COLUMN} IS NOT NULL
              AND ({rate} IS NULL OR ROUND({rate}, 5) NOT BETWEEN 0 AND 1)
            """).fetchone()
    return int(row[0]) if row else 0


def bad_rate_message(count: int) -> Optional[str]:
    """Explain the rejection, or None when every rate is usable."""
    if not count:
        return None
    return (
        f"The census file has {count} row(s) where {RATE_COLUMN} is not a "
        "number from 0 to 1. Deferral rates must be a fraction of pay "
        "(0.06 for 6%, not 6 or 6%). Fix the census file and run again."
    )


def require_census_deferral_rates(census_path: Path) -> None:
    """Reject the census when any deferral rate is unusable."""
    if not census_path.is_file():
        return  # staging reports a missing census itself
    try:
        count = count_bad_deferral_rates(census_path)
    except duckdb.Error as exc:
        # An unreadable file is staging's failure to report, as before.
        logger.debug("Census deferral rate check skipped: %r", exc)
        return
    message = bad_rate_message(count)
    if message:
        raise DataQualityError(message)
