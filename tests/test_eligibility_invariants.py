"""Behavioural pins for the #496 eligibility-transition invariants.

The two live fixtures that exercise eligibility (the reference census behind
``test_multi_year_invariants`` and the ``new_hire_eligibility_suppression``
edge case) only ever produce *start-year* eligibility events, so neither can
distinguish "transitions in the event year" from "transitions a year late".
These synthetic databases cover that gap without paying for a simulation.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.invariants import queries

pytestmark = pytest.mark.fast

START_YEAR = 2025


def _build(
    path: Path,
    snapshot_rows: list[tuple[str, int, str]],
    event_rows: list[tuple[str, int]],
) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE fct_workforce_snapshot ("
            "  employee_id VARCHAR,"
            "  simulation_year INTEGER,"
            "  current_eligibility_status VARCHAR)"
        )
        connection.executemany(
            "INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?)", snapshot_rows
        )
        connection.execute(
            "CREATE TABLE fct_yearly_events ("
            "  employee_id VARCHAR,"
            "  simulation_year INTEGER,"
            "  event_type VARCHAR)"
        )
        if event_rows:
            connection.executemany(
                "INSERT INTO fct_yearly_events VALUES (?, ?, 'eligibility')", event_rows
            )


def _violations(path: Path, sql: str) -> list[tuple]:
    with duckdb.connect(str(path), read_only=True) as connection:
        return connection.execute(sql).fetchall()


def _snapshot(statuses: dict[int, str], employee_id: str = "EMP") -> list[tuple]:
    return [(employee_id, year, status) for year, status in statuses.items()]


def test_start_year_event_transitions_in_the_following_year(tmp_path: Path) -> None:
    """A start-year event leaves the census status alone, then transitions."""
    database = tmp_path / "start-year-event.duckdb"
    _build(
        database,
        _snapshot({2025: "pending", 2026: "eligible", 2027: "eligible"}),
        [("EMP", 2025)],
    )

    assert _violations(database, queries.ELIGIBILITY_EVENT_TRANSITIONS_STATE) == []


def test_start_year_status_is_not_rewritten_by_its_own_event(tmp_path: Path) -> None:
    """Reporting the start year as eligible is *not* required (issue #496)."""
    database = tmp_path / "start-year-preserved.duckdb"
    _build(database, _snapshot({2025: "pending", 2026: "eligible"}), [("EMP", 2025)])

    assert _violations(database, queries.ELIGIBILITY_EVENT_TRANSITIONS_STATE) == []


def test_mid_horizon_event_must_transition_in_its_own_year(tmp_path: Path) -> None:
    """The case no live fixture covers: an event that fires after the start year.

    ``fct_workforce_snapshot`` is end-of-year state, so an employee whose
    eligibility event fires during 2026 is eligible at the close of 2026 --
    deferring to 2027 is the off-by-one this invariant exists to catch.
    """
    database = tmp_path / "mid-horizon-lagged.duckdb"
    _build(
        database,
        _snapshot({2025: "pending", 2026: "pending", 2027: "eligible"}),
        [("EMP", 2026)],
    )

    violations = _violations(database, queries.ELIGIBILITY_EVENT_TRANSITIONS_STATE)

    assert [(row[0], row[2]) for row in violations] == [("EMP", 2026)]


def test_mid_horizon_event_transitioning_in_its_own_year_passes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "mid-horizon-correct.duckdb"
    _build(
        database,
        _snapshot({2025: "pending", 2026: "eligible", 2027: "eligible"}),
        [("EMP", 2026)],
    )

    assert _violations(database, queries.ELIGIBILITY_EVENT_TRANSITIONS_STATE) == []


def test_null_status_is_reported_as_a_violation(tmp_path: Path) -> None:
    """NULL is not 'eligible'; the NULL-safe comparison must still flag it."""
    database = tmp_path / "null-status.duckdb"
    _build(database, _snapshot({2025: "pending", 2026: None}), [("EMP", 2025)])

    assert _violations(database, queries.ELIGIBILITY_EVENT_TRANSITIONS_STATE)


def test_transition_without_an_event_is_a_violation(tmp_path: Path) -> None:
    """The guard against re-deriving status from dates (the #490 regression)."""
    database = tmp_path / "eventless-transition.duckdb"
    _build(database, _snapshot({2025: "pending", 2026: "eligible"}), [])

    violations = _violations(database, queries.ELIGIBILITY_TRANSITION_REQUIRES_EVENT)

    assert [(row[0], row[1]) for row in violations] == [("EMP", 2026)]


def test_transition_backed_by_an_event_is_accepted(tmp_path: Path) -> None:
    database = tmp_path / "backed-transition.duckdb"
    _build(database, _snapshot({2025: "pending", 2026: "eligible"}), [("EMP", 2025)])

    assert _violations(database, queries.ELIGIBILITY_TRANSITION_REQUIRES_EVENT) == []


def test_eligible_reverting_to_pending_is_a_violation(tmp_path: Path) -> None:
    database = tmp_path / "regression.duckdb"
    _build(database, _snapshot({2025: "eligible", 2026: "pending"}), [("EMP", 2025)])

    violations = _violations(database, queries.ELIGIBILITY_STATE_NEVER_REGRESSES)

    assert [(row[0], row[2]) for row in violations] == [("EMP", 2026)]


def test_stable_eligible_status_is_accepted(tmp_path: Path) -> None:
    database = tmp_path / "stable.duckdb"
    _build(
        database,
        _snapshot({2025: "eligible", 2026: "eligible", 2027: "eligible"}),
        [("EMP", 2025)],
    )

    assert _violations(database, queries.ELIGIBILITY_STATE_NEVER_REGRESSES) == []
