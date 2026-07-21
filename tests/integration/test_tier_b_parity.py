"""Tier B all-mart parity + determinism (Feature 121) — deferred-execution integration test.

Compares two already-built isolated DuckDB files (does NOT build sims itself):

    F121_BASELINE_DB     — a full 5-year run BEFORE Tier B (or a pre-121 baseline)
    F121_TIER_B_DB       — a full 5-year run WITH Tier B (cumulative A+B)
    F121_TIER_B_DB2      — (optional) a second identical-seed Tier B run, for determinism

Build per specs/121-reduce-dbt-invocations/quickstart.md, then:

    F121_BASELINE_DB=/tmp/f121/baseline.duckdb \
    F121_TIER_B_DB=/tmp/f121/afterB.duckdb \
    pytest tests/integration/test_tier_b_parity.py -v

Expect every fct_*/dim_* mart byte-identical (0/0). Skipped without the env vars.
"""

import os
from pathlib import Path

import pytest

from tests.helpers.mart_parity import assert_all_marts_identical, discover_marts

BASELINE_DB = os.environ.get("F121_BASELINE_DB")
TIER_B_DB = os.environ.get("F121_TIER_B_DB")
TIER_B_DB2 = os.environ.get("F121_TIER_B_DB2")
DBT_DIR = Path(__file__).resolve().parents[2] / "dbt"


@pytest.mark.skipif(
    not (BASELINE_DB and TIER_B_DB),
    reason="Set F121_BASELINE_DB and F121_TIER_B_DB to two built isolated run DBs.",
)
def test_all_marts_identical_baseline_vs_tier_b():
    marts = discover_marts(DBT_DIR)
    assert marts, "dbt ls returned no fct_*/dim_* marts."
    assert_all_marts_identical(BASELINE_DB, TIER_B_DB, marts)


@pytest.mark.skipif(
    not (TIER_B_DB and TIER_B_DB2),
    reason="Set F121_TIER_B_DB and F121_TIER_B_DB2 to two identical-seed Tier B runs.",
)
def test_tier_b_is_deterministic():
    """Two identical-seed Tier B runs must be byte-identical (FR-010)."""
    marts = discover_marts(DBT_DIR)
    assert_all_marts_identical(TIER_B_DB, TIER_B_DB2, marts)
