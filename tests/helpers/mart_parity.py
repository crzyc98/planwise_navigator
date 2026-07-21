"""All-mart correctness parity helper (Feature 121).

Bidirectional, order-insensitive, duplicate-preserving comparison of every
``fct_*`` / ``dim_*`` mart between a baseline run DB and a candidate run DB, used
to prove a consolidation tier is output-neutral.

Method (see specs/121-reduce-dbt-invocations/contracts/correctness-parity.md):
for each mart, both directions of ``EXCEPT ALL`` must return 0 rows, comparing
only the columns present in *both* DBs and excluding audit-timestamp fields.

This module has no heavy dependencies and does not itself build simulations; it
compares two already-built isolated DuckDB files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import duckdb

DEFAULT_EXCLUDED: Tuple[str, ...] = ("created_at", "snapshot_created_at")
AUDIT_TABLES = frozenset({"run_metadata", "run_execution_metadata"})


def discover_marts(dbt_dir: str | Path) -> List[str]:
    """Enumerate mart model names via ``dbt ls`` so the compare set is never hardcoded.

    Returns only ``fct_*`` / ``dim_*`` models, excluding audit tables.
    """
    out = subprocess.run(
        [
            "dbt",
            "ls",
            "--select",
            "marts",
            "--resource-type",
            "model",
            "--output",
            "name",
        ],
        cwd=str(dbt_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    names = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    return [
        n
        for n in names
        if (n.startswith("fct_") or n.startswith("dim_")) and n not in AUDIT_TABLES
    ]


def _columns(con: duckdb.DuckDBPyConnection, catalog: str, table: str) -> List[str]:
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_name = ? ORDER BY ordinal_position",
        [catalog, table],
    ).fetchall()
    return [r[0] for r in rows]


def compare_marts(
    baseline_db: str | Path,
    candidate_db: str | Path,
    marts: Iterable[str],
    excluded: Sequence[str] = DEFAULT_EXCLUDED,
) -> Dict[str, Tuple[object, object]]:
    """Return {mart: (baseline_minus_candidate, candidate_minus_baseline)} row counts.

    A mart with no shared comparable columns yields the sentinel
    ``("no-shared-columns", ...)`` so callers can flag it rather than silently pass.
    """
    excluded_set = set(excluded)
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(f"ATTACH '{baseline_db}' AS base (READ_ONLY)")
        con.execute(f"ATTACH '{candidate_db}' AS cand (READ_ONLY)")
        results: Dict[str, Tuple[object, object]] = {}
        for m in marts:
            base_cols = _columns(con, "base", m)
            cand_cols = set(_columns(con, "cand", m))
            shared = [c for c in base_cols if c in cand_cols and c not in excluded_set]
            if not shared:
                results[m] = ("no-shared-columns", "no-shared-columns")
                continue
            collist = ", ".join(f'"{c}"' for c in shared)
            fwd = con.execute(
                f'SELECT count(*) FROM (SELECT {collist} FROM base."{m}" '
                f'EXCEPT ALL SELECT {collist} FROM cand."{m}")'
            ).fetchone()[0]
            rev = con.execute(
                f'SELECT count(*) FROM (SELECT {collist} FROM cand."{m}" '
                f'EXCEPT ALL SELECT {collist} FROM base."{m}")'
            ).fetchone()[0]
            results[m] = (fwd, rev)
        return results
    finally:
        con.close()


def assert_all_marts_identical(
    baseline_db: str | Path,
    candidate_db: str | Path,
    marts: Iterable[str],
    excluded: Sequence[str] = DEFAULT_EXCLUDED,
) -> Dict[str, Tuple[object, object]]:
    """Assert every mart is byte-identical (0/0 both directions). Raises on any diff."""
    results = compare_marts(baseline_db, candidate_db, marts, excluded)
    diffs = {m: v for m, v in results.items() if v != (0, 0)}
    assert not diffs, (
        "All-mart parity FAILED. mart -> (baseline−candidate, candidate−baseline): "
        f"{diffs}"
    )
    return results
