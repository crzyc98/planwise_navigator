"""Fast mutation pins for employer service-credit invariants."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.invariants import queries

pytestmark = pytest.mark.fast
SCOPE = ("service_credit_synthetic", "service_credit_plan")


def _build(
    path: Path,
    workforce_rows: list[tuple],
    eligibility_rows: list[tuple],
) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE int_workforce_state_accumulator (
              scenario_id VARCHAR,
              plan_design_id VARCHAR,
              employee_id VARCHAR,
              simulation_year INTEGER,
              current_tenure INTEGER,
              employee_hire_date DATE
            )
            """
        )
        connection.executemany(
            "INSERT INTO int_workforce_state_accumulator VALUES (?, ?, ?, ?, ?, ?)",
            workforce_rows,
        )
        connection.execute(
            """
            CREATE TABLE int_employer_eligibility (
              scenario_id VARCHAR,
              employee_id VARCHAR,
              simulation_year INTEGER,
              current_tenure INTEGER,
              eligible_for_core BOOLEAN,
              core_tenure_requirement INTEGER,
              core_allow_new_hires BOOLEAN,
              match_apply_eligibility BOOLEAN,
              eligible_for_match BOOLEAN,
              match_tenure_requirement INTEGER,
              match_allow_new_hires BOOLEAN
            )
            """
        )
        connection.executemany(
            "INSERT INTO int_employer_eligibility VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            eligibility_rows,
        )


def _workforce(employee: str, tenure: int, hire_date: str = "2020-01-01") -> tuple:
    return (*SCOPE, employee, 2026, tenure, hire_date)


def _eligibility(
    employee: str,
    tenure: int,
    *,
    core_eligible: bool = False,
    core_wait: int = 2,
    core_new_hire: bool = False,
    match_eligible: bool = False,
    match_wait: int = 2,
    match_new_hire: bool = False,
) -> tuple:
    return (
        SCOPE[0],
        employee,
        2026,
        tenure,
        core_eligible,
        core_wait,
        core_new_hire,
        True,
        match_eligible,
        match_wait,
        match_new_hire,
    )


def _violations(path: Path, sql: str) -> list[tuple]:
    with duckdb.connect(str(path), read_only=True) as connection:
        return connection.execute(sql).fetchall()


def test_exact_active_and_termination_service_values_pass(tmp_path: Path) -> None:
    database = tmp_path / "exact.duckdb"
    _build(
        database,
        [_workforce("ACTIVE", 4), _workforce("TERMINATED", 1)],
        [_eligibility("ACTIVE", 4), _eligibility("TERMINATED", 1)],
    )
    assert (
        _violations(database, queries.EMPLOYER_ELIGIBILITY_SERVICE_MATCHES_WORKFORCE)
        == []
    )


def test_one_year_and_reset_offsets_are_reported(tmp_path: Path) -> None:
    database = tmp_path / "offsets.duckdb"
    _build(
        database,
        [_workforce("ACTIVE_OFFSET", 2), _workforce("RESET_OFFSET", 0)],
        [_eligibility("ACTIVE_OFFSET", 3), _eligibility("RESET_OFFSET", 5)],
    )
    violations = _violations(
        database, queries.EMPLOYER_ELIGIBILITY_SERVICE_MATCHES_WORKFORCE
    )
    assert [(row[0], row[2], row[3]) for row in violations] == [
        ("ACTIVE_OFFSET", 3, 2),
        ("RESET_OFFSET", 5, 0),
    ]


def test_exact_threshold_and_explicit_hire_year_exception_pass(
    tmp_path: Path,
) -> None:
    database = tmp_path / "allowed.duckdb"
    _build(
        database,
        [_workforce("BOUNDARY", 2), _workforce("NEW_HIRE", 0, "2026-06-01")],
        [
            _eligibility("BOUNDARY", 2, core_eligible=True, match_eligible=True),
            _eligibility(
                "NEW_HIRE",
                0,
                core_eligible=True,
                core_new_hire=True,
                match_eligible=True,
                match_new_hire=True,
            ),
        ],
    )
    assert _violations(database, queries.EMPLOYER_TENURE_REQUIREMENTS_ENFORCED) == []


def test_unsupported_below_threshold_core_and_match_are_reported(
    tmp_path: Path,
) -> None:
    database = tmp_path / "below-threshold.duckdb"
    _build(
        database,
        [_workforce("BELOW", 1)],
        [_eligibility("BELOW", 1, core_eligible=True, match_eligible=True)],
    )
    violations = _violations(database, queries.EMPLOYER_TENURE_REQUIREMENTS_ENFORCED)
    assert [(row[0], row[1]) for row in violations] == [
        ("core", "BELOW"),
        ("match", "BELOW"),
    ]
