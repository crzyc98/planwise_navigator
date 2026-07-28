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


def _growth_database(
    path: Path, years: list[tuple[int, int, float, int, int, int]]
) -> None:
    """Build snapshot/event/needs rows from (year, starting, rate, ending, hires, terms)."""
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE fct_workforce_snapshot (
              employee_id VARCHAR, simulation_year INTEGER, employment_status VARCHAR
            );
            CREATE TABLE fct_yearly_events (
              employee_id VARCHAR, simulation_year INTEGER, event_type VARCHAR
            );
            CREATE TABLE int_workforce_needs (
              simulation_year INTEGER,
              starting_workforce_count BIGINT,
              target_growth_rate DECIMAL(9, 4)
            )
            """
        )
        for year, starting, rate, ending, hires, terminations in years:
            connection.execute(
                "INSERT INTO int_workforce_needs VALUES (?, ?, ?)",
                [year, starting, rate],
            )
            for index in range(ending):
                connection.execute(
                    "INSERT INTO fct_workforce_snapshot VALUES (?, ?, 'active')",
                    [f"EMP_{year}_{index:04d}", year],
                )
            for index in range(hires):
                connection.execute(
                    "INSERT INTO fct_yearly_events VALUES (?, ?, 'hire')",
                    [f"NH_{year}_{index:04d}", year],
                )
            for index in range(terminations):
                connection.execute(
                    "INSERT INTO fct_yearly_events VALUES (?, ?, 'termination')",
                    [f"TERM_{year}_{index:04d}", year],
                )


def test_zero_growth_assertion_accepts_conserved_headcount(tmp_path: Path) -> None:
    """#498: zero *net* growth still replaces attrition; hires are expected, not banned."""
    database = tmp_path / "zero-growth.duckdb"
    _growth_database(
        database, [(2025, 100, 0.0, 100, 10, 10), (2026, 100, 0.0, 100, 9, 9)]
    )

    assert targeted_query(_case("zero_target_growth_rate"), database).passed


def test_zero_growth_assertion_rejects_static_workforce(tmp_path: Path) -> None:
    """The pre-#498 fixture: headcount holds only because nothing ever moves."""
    database = tmp_path / "static-workforce.duckdb"
    _growth_database(
        database, [(2025, 100, 0.0, 100, 0, 0), (2026, 100, 0.0, 100, 0, 0)]
    )

    result = targeted_query(_case("zero_target_growth_rate"), database)

    assert not result.passed
    assert any(
        "without hires and terminations" in violation.observed
        for violation in result.violations
    )


def test_zero_growth_assertion_rejects_changed_growth_rate(tmp_path: Path) -> None:
    """#490: moving target_growth_rate must fail the case, not move the expectation."""
    database = tmp_path / "mutated-growth.duckdb"
    _growth_database(
        database, [(2025, 100, 0.03, 103, 13, 10), (2026, 103, 0.03, 106, 13, 10)]
    )

    result = targeted_query(_case("zero_target_growth_rate"), database)

    assert not result.passed
    assert any(
        "not the case boundary" in violation.observed for violation in result.violations
    )


def test_zero_growth_assertion_rejects_headcount_drift(tmp_path: Path) -> None:
    database = tmp_path / "drifting-headcount.duckdb"
    _growth_database(
        database, [(2025, 100, 0.0, 100, 10, 10), (2026, 100, 0.0, 97, 7, 10)]
    )

    result = targeted_query(_case("zero_target_growth_rate"), database)

    assert not result.passed
    assert any(
        "did not track the target" in violation.observed
        for violation in result.violations
    )


def test_negative_growth_assertion_accepts_configured_decline(tmp_path: Path) -> None:
    """The solver declines by under-replacing attrition: 100 -> 95 -> 90."""
    database = tmp_path / "negative-growth.duckdb"
    _growth_database(
        database, [(2025, 100, -0.05, 95, 5, 10), (2026, 95, -0.05, 90, 4, 9)]
    )

    assert targeted_query(_case("negative_target_growth_rate"), database).passed


def test_negative_growth_assertion_rejects_over_termination(tmp_path: Path) -> None:
    """Hitting the target by terminating faster instead of hiring less is not the same."""
    database = tmp_path / "over-terminated.duckdb"
    _growth_database(
        database, [(2025, 100, -0.05, 90, 5, 15), (2026, 95, -0.05, 90, 4, 9)]
    )

    result = targeted_query(_case("negative_target_growth_rate"), database)

    assert not result.passed
    assert any(
        "did not track the target" in violation.observed
        for violation in result.violations
    )
