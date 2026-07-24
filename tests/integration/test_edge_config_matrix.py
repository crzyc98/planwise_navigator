"""Contract and targeted tests for the four-case edge matrix."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.edge_config.assertions import assert_bounded_samples
from tests.edge_config.catalog import EdgeConfigScenario, validate_catalog
from tests.edge_config.queries import execute_violation_query, targeted_query
from tests.fixtures.edge_config_matrix import require_completed

pytestmark = [pytest.mark.integration, pytest.mark.edge_config_matrix]
pytest_plugins = ("tests.fixtures.edge_config_matrix",)


def test_catalog_shape(edge_catalog: tuple[EdgeConfigScenario, ...]) -> None:
    validate_catalog(edge_catalog)
    assert {case.assertion_kind for case in edge_catalog} == {
        "cutoff_enrollment",
        "eligibility_suppression",
        "tenure_match",
        "escalation_cap",
    }


def test_fixture_groups_are_non_empty(
    edge_catalog: tuple[EdgeConfigScenario, ...]
) -> None:
    from tests.fixtures.edge_config_matrix import load_case_frame

    for case in edge_catalog:
        frame = load_case_frame(case)
        assert set(case.expected_groups) <= set(frame["boundary_group"])


def test_matrix_case_has_completed_outputs(edge_run) -> None:
    database = require_completed(edge_run)
    result = targeted_query(edge_run.scenario, database)
    assert_bounded_samples(result.violations, edge_run.scenario.sample_limit)
    assert result.passed, result


def test_violation_query_is_bounded(tmp_path: Path) -> None:
    import duckdb

    database = tmp_path / "query.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute("CREATE TABLE violations (employee_id VARCHAR)")
        connection.execute("INSERT INTO violations VALUES ('a'), ('b'), ('c')")
    rows = execute_violation_query(database, "SELECT employee_id FROM violations", 2)
    assert len(rows) == 2


def test_shared_database_is_not_a_valid_matrix_target() -> None:
    from tests.edge_config.catalog import CATALOG

    assert all(case.config_path.parent != Path("dbt") for case in CATALOG)
