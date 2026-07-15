"""Same-seed, same-config simulation determinism checks."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.fixtures.invariant_simulation import SimulationRun
from tests.invariants.comparison import COMPARED_TABLES, compare_tables
from tests.invariants.queries import SNAPSHOT_NO_FOREIGN_ROWS

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]


def test_rerun_simulation_completed(invariant_run_b_result: SimulationRun) -> None:
    assert invariant_run_b_result.error is None, (
        "reference rerun failed before determinism comparison: "
        f"{invariant_run_b_result.error!r}"
    )


def test_rerun_snapshot_has_no_foreign_rows(invariant_run_db_b: Path) -> None:
    with duckdb.connect(str(invariant_run_db_b), read_only=True) as connection:
        violations = connection.execute(
            f"SELECT * FROM ({SNAPSHOT_NO_FOREIGN_ROWS}) violations LIMIT 20"
        ).fetchall()
    assert not violations, (
        "Invariant: snapshot-no-foreign-rows\n"
        "Description: stale prior-run rows must be purged before a rerun.\n"
        f"Sample rows ({len(violations)}): {violations!r}"
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
