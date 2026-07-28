"""Fast mutation checks for edge-matrix boundary query dispatch."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.edge_config.assertions import assert_no_violations
from tests.edge_config.catalog import CATALOG, EdgeConfigScenario
from tests.edge_config.queries import targeted_query


def _case(name: str) -> EdgeConfigScenario:
    """Look up by name; the catalog's order is not a contract."""
    return next(case for case in CATALOG if case.name == name)


def _cutoff_database(path: Path, after_enrolled: bool) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE fct_workforce_snapshot (
              employee_id VARCHAR,
              simulation_year INTEGER,
              is_enrolled_flag BOOLEAN,
              employee_enrollment_date DATE
            )
            """
        )
        connection.execute(
            "INSERT INTO fct_workforce_snapshot VALUES "
            "('EDGE_CUTOFF_BEFORE', 2025, FALSE, NULL), "
            "('EDGE_CUTOFF_AFTER', 2025, ?, ?)",
            [after_enrolled, "2025-01-15" if after_enrolled else None],
        )


def test_cutoff_assertion_rejects_default_like_enrollment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A default-like all-unenrolled output must fail the cutoff case."""
    database = tmp_path / "mutation.duckdb"
    _cutoff_database(database, after_enrolled=False)
    monkeypatch.setattr(
        "tests.edge_config.queries._grouped_employee_ids",
        lambda _: {
            "EDGE_CUTOFF_BEFORE": "before_cutoff",
            "EDGE_CUTOFF_AFTER": "after_cutoff",
        },
    )

    result = targeted_query(_case("broad_auto_enrollment_cutoff"), database)

    assert not result.passed
    with pytest.raises(AssertionError, match="Case: broad_auto_enrollment_cutoff"):
        assert_no_violations(result)


def test_cutoff_assertion_accepts_configured_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "boundary.duckdb"
    _cutoff_database(database, after_enrolled=True)
    monkeypatch.setattr(
        "tests.edge_config.queries._grouped_employee_ids",
        lambda _: {
            "EDGE_CUTOFF_BEFORE": "before_cutoff",
            "EDGE_CUTOFF_AFTER": "after_cutoff",
        },
    )

    assert targeted_query(_case("broad_auto_enrollment_cutoff"), database).passed
