"""Three-year simulation invariants for Feature 113."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import duckdb

from tests.fixtures.invariant_simulation import (
    SimulationRun,
    assert_census_coverage,
)
from tests.invariants.catalog import CATALOG, Invariant

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]


def test_reference_census_coverage(invariant_census_frame: pd.DataFrame) -> None:
    assert_census_coverage(invariant_census_frame)


def test_invariant_simulation_completed(invariant_run_a_result: SimulationRun) -> None:
    assert invariant_run_a_result.error is None, (
        "reference simulation failed before invariant evaluation: "
        f"{invariant_run_a_result.error!r}"
    )


def _format_violations(
    invariant: Invariant,
    violation_count: int,
    columns: list[str],
    rows: list[tuple[object, ...]],
) -> str:
    issue = invariant.guarded_issue or "none"
    samples = [dict(zip(columns, row)) for row in rows]
    return (
        f"Invariant: {invariant.name}\n"
        f"Description: {invariant.description}\n"
        f"Guarded issue: {issue}\n"
        f"Violation count: {violation_count}\n"
        f"Sample rows ({len(samples)}): {samples!r}"
    )


@pytest.mark.parametrize("invariant", CATALOG, ids=lambda item: item.name)
def test_multi_year_invariant(invariant_run_db: Path, invariant: Invariant) -> None:
    with duckdb.connect(str(invariant_run_db), read_only=True) as connection:
        count = connection.execute(
            f"SELECT COUNT(*) FROM ({invariant.violation_sql}) violations"
        ).fetchone()[0]
        if count == 0:
            return
        result = connection.execute(
            f"SELECT * FROM ({invariant.violation_sql}) violations "
            f"LIMIT {invariant.sample_limit}"
        )
        columns = [description[0] for description in result.description]
        samples = result.fetchall()
    pytest.fail(_format_violations(invariant, count, columns, samples))
