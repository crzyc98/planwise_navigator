"""Generate the large client-representative census for the run-cost profile.

Scales the dev census (7,505 employees) by an integer factor via duplication:
copy 0 is the original; copies 1..k-1 remap employee_id/ssn to stay globally
unique and deterministically jitter compensation (and its dependent
contribution columns) by ±2% so duplicate rows aren't byte-identical.
Dates are preserved, so the demographic mix matches the source exactly.

Usage:
    python -m scripts.perf_profile.make_large_census --factor 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import duckdb

from .profile_config import DEV_CENSUS_PARQUET, LARGE_CENSUS_PARQUET

COMP_COLUMNS = (
    "employee_gross_compensation",
    "employee_capped_compensation",
    "employee_contribution",
    "pre_tax_contribution",
    "roth_contribution",
    "after_tax_contribution",
    "employer_core_contribution",
    "employer_match_contribution",
)


def build_query(source: Path, factor: int) -> str:
    # Deterministic ±2% jitter from a hash of (id, copy); copy 0 keeps originals.
    jitter = "(0.98 + 0.04 * ((hash(employee_id || '-' || c.copy) % 1000) / 1000.0))"
    comp_exprs = ",\n      ".join(
        f"CASE WHEN c.copy = 0 THEN {col} ELSE round({col} * {jitter}, 2) END AS {col}"
        for col in COMP_COLUMNS
    )
    return f"""
    SELECT
      CASE WHEN c.copy = 0 THEN employee_id
           ELSE employee_id || '_C' || c.copy END AS employee_id,
      CASE WHEN c.copy = 0 THEN employee_ssn
           ELSE employee_ssn || '-C' || c.copy END AS employee_ssn,
      employee_birth_date,
      employee_hire_date,
      employee_termination_date,
      {comp_exprs},
      employee_deferral_rate,
      eligibility_entry_date,
      active
    FROM read_parquet('{source}')
    CROSS JOIN (SELECT unnest(range({factor})) AS copy) c
    ORDER BY employee_id
    """


def summarize(conn: duckdb.DuckDBPyConnection, path: Path, label: str) -> dict:
    row = conn.sql(
        f"""
        SELECT COUNT(*),
               COUNT(DISTINCT employee_id),
               round(avg(employee_gross_compensation), 2),
               round(avg(2025 - year(CAST(employee_birth_date AS DATE))), 1),
               sum(CASE WHEN active THEN 1 ELSE 0 END)
        FROM read_parquet('{path}')
        """
    ).fetchone()
    stats = {
        "rows": row[0],
        "unique_ids": row[1],
        "avg_comp": row[2],
        "avg_age_2025": row[3],
        "active": row[4],
    }
    print(f"[make_large_census] {label}: {stats}")
    return stats


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor", type=int, default=8)
    parser.add_argument("--out", type=Path, default=LARGE_CENSUS_PARQUET)
    args = parser.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as conn:
        conn.sql(
            f"COPY ({build_query(DEV_CENSUS_PARQUET, args.factor)}) "
            f"TO '{args.out}' (FORMAT parquet)"
        )
        source = summarize(conn, DEV_CENSUS_PARQUET, "source")
        scaled = summarize(conn, args.out, "scaled")

    if scaled["rows"] != source["rows"] * args.factor:
        print("[make_large_census] ERROR: row count != source * factor")
        return 1
    if scaled["unique_ids"] != scaled["rows"]:
        print("[make_large_census] ERROR: employee_id not globally unique")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
