"""Tier A all-mart parity (Feature 121) — deferred-execution integration test.

This does NOT build simulations itself (they take minutes on the 60k census).
It compares two already-built isolated DuckDB files:

    F121_BASELINE_DB   — a full 5-year run on HEAD *before* Tier A
    F121_CANDIDATE_DB  — a full 5-year run *with* Tier A (batched hazard cache)

Build them per specs/121-reduce-dbt-invocations/quickstart.md, then:

    F121_BASELINE_DB=/tmp/f121/baseline.duckdb \
    F121_CANDIDATE_DB=/tmp/f121/afterA.duckdb \
    pytest tests/integration/test_tier_a_parity.py -v

Expect every fct_*/dim_* mart to be byte-identical (0/0). Skipped when the env
vars are absent so CI stays green without the heavy build.
"""

import os
from pathlib import Path

import pytest

from tests.helpers.mart_parity import assert_all_marts_identical, discover_marts

BASELINE_DB = os.environ.get("F121_BASELINE_DB")
CANDIDATE_DB = os.environ.get("F121_CANDIDATE_DB")
DBT_DIR = Path(__file__).resolve().parents[2] / "dbt"

pytestmark = pytest.mark.skipif(
    not (BASELINE_DB and CANDIDATE_DB),
    reason="Set F121_BASELINE_DB and F121_CANDIDATE_DB to two built isolated run DBs.",
)


def test_all_marts_identical_baseline_vs_tier_a():
    marts = discover_marts(DBT_DIR)
    assert marts, "dbt ls returned no fct_*/dim_* marts — check the dbt project."
    # Raises with the offending marts + diff counts if any mart differs.
    results = assert_all_marts_identical(BASELINE_DB, CANDIDATE_DB, marts)
    # Belt-and-suspenders: no mart returned the 'no shared columns' sentinel.
    sentinels = {
        m: v
        for m, v in results.items()
        if v == ("no-shared-columns", "no-shared-columns")
    }
    assert not sentinels, f"Marts with no comparable columns (investigate): {sentinels}"
