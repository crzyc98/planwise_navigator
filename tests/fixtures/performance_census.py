"""Deterministically scale a Parquet census to an exact employee count.

Generated census files are disposable, PII-bearing runtime artifacts. Callers
must write them outside the repository (normally under ``/tmp``) and must not
commit them.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Sequence

import duckdb

from scripts.perf_profile.make_large_census import build_query


def generate_performance_census(
    source: Path,
    destination: Path,
    employee_count: int = 100_000,
) -> Path:
    """Create an exact-size census by deterministic duplication and truncation."""
    if employee_count < 1:
        raise ValueError("employee_count must be at least 1")
    if not source.is_file():
        raise FileNotFoundError(f"source census does not exist: {source}")
    if "'" in str(source) or "'" in str(destination):
        raise ValueError("census paths must not contain single quotes")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as connection:
        source_count = connection.execute(
            "SELECT COUNT(*) FROM read_parquet(?)", [str(source)]
        ).fetchone()[0]
        factor = math.ceil(employee_count / source_count)
        scaled_query = build_query(source, factor)
        exact_query = f"""
            SELECT
              'PERF_' || lpad(row_number() OVER ()::VARCHAR, 6, '0') AS employee_id,
              'PERF-SSN-' || lpad(row_number() OVER ()::VARCHAR, 9, '0') AS employee_ssn,
              employee_birth_date,
              employee_hire_date,
              employee_termination_date,
              employee_gross_compensation,
              employee_capped_compensation,
              employee_contribution,
              pre_tax_contribution,
              roth_contribution,
              after_tax_contribution,
              employer_core_contribution,
              employer_match_contribution,
              employee_deferral_rate,
              eligibility_entry_date,
              active
            FROM ({scaled_query})
            LIMIT {employee_count}
        """
        connection.execute(
            f"COPY ({exact_query}) TO '{destination}' (FORMAT PARQUET)",
        )
        row = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT employee_id) FROM read_parquet(?)",
            [str(destination)],
        ).fetchone()

    if row != (employee_count, employee_count):
        raise RuntimeError(
            "generated census failed row/identity validation: "
            f"expected {(employee_count, employee_count)}, got {row}"
        )
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    """Generate a performance census from command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--employees", type=int, default=100_000)
    args = parser.parse_args(argv)
    path = generate_performance_census(args.source, args.out, args.employees)
    print(f"generated {args.employees:,} employees at {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
