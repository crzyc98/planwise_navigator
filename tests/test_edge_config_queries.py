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


def _eligibility_database(
    path: Path,
    end_status: str,
    suppressed_hire_status: str | None = "pending",
) -> None:
    """Build the case's outputs; `suppressed_hire_status=None` omits the new hire."""
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE fct_workforce_snapshot (
              employee_id VARCHAR,
              simulation_year INTEGER,
              current_eligibility_status VARCHAR
            )
            """
        )
        connection.execute(
            "INSERT INTO fct_workforce_snapshot VALUES "
            "('EDGE_SUPPRESSED', 2025, 'pending'), "
            "('EDGE_SUPPRESSED', 2026, ?), "
            "('EDGE_CONTROL', 2025, 'eligible'), "
            "('EDGE_CONTROL', 2026, 'eligible')",
            [end_status],
        )
        connection.execute(
            """
            CREATE TABLE int_plan_eligibility_override (
              employee_id VARCHAR,
              simulation_year INTEGER,
              is_plan_ineligible_override BOOLEAN,
              override_source VARCHAR
            )
            """
        )
        if suppressed_hire_status is None:
            return
        # Feature 103 (#499): a dial-suppressed hire, carried across both years.
        connection.execute(
            "INSERT INTO int_plan_eligibility_override VALUES "
            "('NH_2025_000001', 2025, TRUE, 'new_hire_dial'), "
            "('NH_2025_000001', 2026, TRUE, 'new_hire_dial')"
        )
        connection.execute(
            "INSERT INTO fct_workforce_snapshot VALUES "
            "('NH_2025_000001', 2025, ?), ('NH_2025_000001', 2026, ?)",
            [suppressed_hire_status, suppressed_hire_status],
        )


def test_eligibility_assertion_rejects_missing_event_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "eligibility-mutation.duckdb"
    _eligibility_database(database, end_status="pending")
    monkeypatch.setattr(
        "tests.edge_config.queries._grouped_employee_ids",
        lambda _: {
            "EDGE_SUPPRESSED": "suppressed_new_hire",
            "EDGE_CONTROL": "eligible_control",
        },
    )

    result = targeted_query(_case("new_hire_eligibility_suppression"), database)

    assert not result.passed
    assert any(
        "did not transition" in violation.observed for violation in result.violations
    )


def test_eligibility_assertion_accepts_prior_year_event_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "eligibility-transition.duckdb"
    _eligibility_database(database, end_status="eligible")
    monkeypatch.setattr(
        "tests.edge_config.queries._grouped_employee_ids",
        lambda _: {
            "EDGE_SUPPRESSED": "suppressed_new_hire",
            "EDGE_CONTROL": "eligible_control",
        },
    )

    assert targeted_query(_case("new_hire_eligibility_suppression"), database).passed


def test_eligibility_assertion_rejects_eligible_suppressed_new_hire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#499: a Feature 103 hire has no eligibility event, so it cannot read eligible."""
    database = tmp_path / "eligibility-suppressed-hire.duckdb"
    _eligibility_database(
        database, end_status="eligible", suppressed_hire_status="eligible"
    )
    monkeypatch.setattr(
        "tests.edge_config.queries._grouped_employee_ids",
        lambda _: {
            "EDGE_SUPPRESSED": "suppressed_new_hire",
            "EDGE_CONTROL": "eligible_control",
        },
    )

    result = targeted_query(_case("new_hire_eligibility_suppression"), database)

    assert not result.passed
    assert any(
        "suppressed new hire reported eligible" in violation.observed
        for violation in result.violations
    )


def test_eligibility_assertion_rejects_case_with_no_suppressed_hire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#498/#499: the case must fail rather than pass vacuously if the dial hires nobody."""
    database = tmp_path / "eligibility-no-hire.duckdb"
    _eligibility_database(database, end_status="eligible", suppressed_hire_status=None)
    monkeypatch.setattr(
        "tests.edge_config.queries._grouped_employee_ids",
        lambda _: {
            "EDGE_SUPPRESSED": "suppressed_new_hire",
            "EDGE_CONTROL": "eligible_control",
        },
    )

    result = targeted_query(_case("new_hire_eligibility_suppression"), database)

    assert not result.passed
    assert any(
        "suppressed no hire" in violation.observed for violation in result.violations
    )
