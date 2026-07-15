"""Same-seed, same-config simulation determinism checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.invariant_simulation import (
    SHARED_DEV_DB,
    SimulationRun,
    file_signature,
)
from tests.invariants.comparison import COMPARED_TABLES, compare_tables

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]


def test_rerun_simulation_completed(invariant_run_b_result: SimulationRun) -> None:
    assert invariant_run_b_result.error is None, (
        "reference rerun failed before determinism comparison: "
        f"{invariant_run_b_result.error!r}"
    )


@pytest.mark.parametrize("table", COMPARED_TABLES)
def test_deterministic_table(
    invariant_run_db: Path,
    invariant_run_db_b: Path,
    table: str,
) -> None:
    count_a, count_b, diff_count, samples = compare_tables(
        invariant_run_db, invariant_run_db_b, table
    )
    assert count_a == count_b and diff_count == 0, (
        f"Determinism violation in {table}: count_a={count_a}, "
        f"count_b={count_b}, diff_count={diff_count}, sample_rows={samples!r}"
    )


def test_shared_dev_database_untouched(
    invariant_run_db: Path,
    invariant_run_db_b: Path,
    shared_dev_db_signature: tuple[int, str] | None,
) -> None:
    del invariant_run_db, invariant_run_db_b
    assert file_signature(SHARED_DEV_DB) == shared_dev_db_signature
