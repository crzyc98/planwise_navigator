"""A grandfathered design authored in Studio runs in the shipped engine (#646).

Runs the exact payload Studio's editor emits (see
``tests/fixtures/studio_grandfathered_design``) for 2025-2027 in an isolated
database, and checks each hire-date cohort gets its own match and core.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from tests.fixtures.invariant_simulation import (
    _database_environment,
    _simulation_config,
)
from tests.fixtures.studio_grandfathered_design import (
    CUTOFF,
    EXISTING_DESIGN,
    NEW_HIRE_DESIGN,
    apply_studio_payload,
)

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]

# (employee_min, employee_max, match_rate) and the cap, as Studio emitted them.
MATCH_TERMS: dict[str, tuple[list[tuple[str, str, str]], str]] = {
    EXISTING_DESIGN: ([("0", "0.03", "1"), ("0.03", "0.05", "0.5")], "0.04"),
    NEW_HIRE_DESIGN: ([("0", "0.06", "0.5")], "0.03"),
}


@pytest.fixture(scope="module")
def studio_design_database(
    tmp_path_factory: pytest.TempPathFactory,
    invariant_census_parquet: Path,
) -> Path:
    database = tmp_path_factory.mktemp("studio-grandfathered") / "studio.duckdb"
    config = apply_studio_payload(_simulation_config(invariant_census_parquet))
    with _database_environment(database):
        build_orchestrator(
            ConstructionSpec(
                config=config,
                database=database,
                threads=1,
                entry_point="invariant_test",
                validation_mode=True,
            )
        ).orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2027)
    return database


def _expected_match(design: str, compensation: Decimal, deferral: Decimal) -> Decimal:
    tiers, cap = MATCH_TERMS[design]
    amount = Decimal(0)
    for low, high, rate in tiers:
        covered = min(deferral, Decimal(high)) - Decimal(low)
        amount += compensation * max(covered, Decimal(0)) * Decimal(rate)
    return min(amount, compensation * Decimal(cap))


def test_each_cohort_gets_the_design_for_its_hire_date(
    studio_design_database: Path,
) -> None:
    with duckdb.connect(str(studio_design_database), read_only=True) as conn:
        counts = conn.execute(
            "SELECT plan_design_id, employee_hire_date >= ?::DATE, COUNT(*) "
            "FROM fct_workforce_snapshot GROUP BY ALL ORDER BY ALL",
            [CUTOFF],
        ).fetchall()
    assert [(design, after) for design, after, _ in counts] == [
        (EXISTING_DESIGN, False),
        (NEW_HIRE_DESIGN, True),
    ]


def test_core_rate_follows_each_design(studio_design_database: Path) -> None:
    with duckdb.connect(str(studio_design_database), read_only=True) as conn:
        rates = conn.execute(
            "SELECT plan_design_id, LIST(DISTINCT core_contribution_rate "
            "ORDER BY core_contribution_rate) FROM int_employer_core_contributions "
            "WHERE eligible_for_core GROUP BY plan_design_id ORDER BY plan_design_id"
        ).fetchall()
    assert rates == [
        (EXISTING_DESIGN, [Decimal("0.010000")]),
        (NEW_HIRE_DESIGN, [Decimal("0.030000")]),
    ]


@pytest.mark.parametrize("design", [EXISTING_DESIGN, NEW_HIRE_DESIGN])
def test_match_follows_each_design(studio_design_database: Path, design: str) -> None:
    with duckdb.connect(str(studio_design_database), read_only=True) as conn:
        rows = conn.execute(
            # The match applies to pay up to the IRS 401(a)(17) limit.
            "SELECT LEAST(eligible_compensation, irs_401a17_limit), deferral_rate, "
            "employer_match_amount FROM int_employee_match_calculations "
            "WHERE plan_design_id = ? AND is_eligible_for_match AND deferral_rate > 0 "
            "ORDER BY simulation_year, employee_id",
            [design],
        ).fetchall()
    assert rows
    # The table rounds deferral_rate to 4 decimals; the match uses the exact rate.
    half_step, cent = Decimal("0.00005"), Decimal("0.01")
    for compensation, deferral, actual in rows:
        pay, rate = Decimal(str(compensation)), Decimal(str(deferral))
        low = _expected_match(design, pay, rate - half_step) - cent
        high = _expected_match(design, pay, rate + half_step) + cent
        assert low <= Decimal(str(actual)) <= high, (compensation, deferral, actual)
