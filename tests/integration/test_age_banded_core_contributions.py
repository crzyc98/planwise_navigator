"""Isolated-DB integration coverage for age-banded employer core contributions.

Every assertion runs against a disposable per-session database built by the
canonical construction path; the shared dev database is never written to.

`int_employer_core_contributions` is a table materialization, so it only ever
retains the final simulation year of a run. The audited rate lives nowhere else
(`fct_workforce_snapshot` carries the amount but no rate), so the boundary year
and the migration year are built as two separate runs of the same fixture.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import duckdb
import pytest

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import load_simulation_config
from tests.fixtures.edge_config_matrix import SHARED_DEV_DB, file_signature

pytestmark = [pytest.mark.integration, pytest.mark.very_slow]

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures/age_banded_core"
CENSUS = FIXTURE_ROOT / "age_banded_core.csv"
SCHEDULE_CONFIG = FIXTURE_ROOT / "age_banded_core.yaml"
EMPTY_SCHEDULE_CONFIG = FIXTURE_ROOT / "age_banded_core_empty_schedule.yaml"

# Mirrors age_banded_core.yaml; [min_age, max_age) with an unbounded final tier.
SCHEDULE = ((0, 30, 0.03), (30, 40, 0.04), (40, 50, 0.05), (50, None, 0.06))
FLAT_FALLBACK_RATE = 0.02
CENSUS_HEADCOUNT = 8


def expected_rate(age: int) -> float:
    """Resolve the configured rate for an age, independent of the SQL macro."""
    for min_age, max_age, rate in SCHEDULE:
        if age >= min_age and (max_age is None or age < max_age):
            return rate
    raise AssertionError(f"age {age} is not covered by the schedule")


def _tier_case_sql(column: str, schedule: tuple = SCHEDULE) -> str:
    """Build the expected-rate CASE from a schedule, so SQL cannot drift from it."""
    branches = [
        f"WHEN {column} >= {low}"
        + ("" if high is None else f" AND {column} < {high}")
        + f" THEN {rate}"
        for low, high, rate in reversed(schedule)
    ]
    return "CASE " + " ".join(branches) + " END"


@dataclass(frozen=True)
class CoreMode:
    """One non-age core mode, with the tier input its rate is driven by."""

    name: str
    config: Path
    #: Expected-rate expression over CORE_WITH_AGE, derived from the fixture YAML.
    expected_rate_sql: str
    #: Distinct paid rates the census must produce, guarding against vacuity.
    distinct_rates: int


POINTS_COLUMN = "(current_age + applied_years_of_service)"

CORE_MODES = (
    CoreMode("flat", FIXTURE_ROOT / "core_mode_flat.yaml", "0.025", 1),
    CoreMode(
        "graded_by_service",
        FIXTURE_ROOT / "core_mode_graded_by_service.yaml",
        _tier_case_sql(
            "applied_years_of_service",
            ((0, 5, 0.03), (5, 10, 0.04), (10, 15, 0.05), (15, None, 0.06)),
        ),
        3,
    ),
    CoreMode(
        "points_based",
        FIXTURE_ROOT / "core_mode_points_based.yaml",
        _tier_case_sql(
            POINTS_COLUMN,
            ((0, 40, 0.02), (40, 60, 0.03), (60, 80, 0.04), (80, None, 0.05)),
        ),
        3,
    ),
)


@contextmanager
def _database_environment(database: Path) -> Iterator[None]:
    previous = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(database)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = previous


def _run(config_path: Path, database: Path, end_year: int) -> Path:
    config = load_simulation_config(config_path, env_overrides=False)
    config.simulation.end_year = end_year
    census_parquet = database.with_suffix(".census.parquet")
    with duckdb.connect() as connection:
        connection.read_csv(str(CENSUS)).write_parquet(str(census_parquet))
    config.setup["census_parquet_path"] = str(census_parquet)
    with _database_environment(database):
        orchestrator = build_orchestrator(
            ConstructionSpec(
                config=config,
                database=database,
                threads=1,
                entry_point="invariant_test",
                validation_mode=True,
            )
        ).orchestrator
        orchestrator.execute_multi_year_simulation(
            start_year=config.simulation.start_year, end_year=end_year
        )
    return database


def _query(database: Path, sql: str) -> list[tuple]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(sql).fetchall()


# Core rows joined to the annual age that drove the tier decision.
CORE_WITH_AGE = """
SELECT
    ec.employee_id,
    ec.simulation_year,
    ws.current_age,
    -- DECIMAL(3,2) in the model; widen so Python compares against plain floats.
    CAST(ec.core_contribution_rate AS DOUBLE) AS core_contribution_rate,
    ec.employer_core_amount,
    ec.eligible_compensation,
    ec.irs_401a17_limit,
    ec.applied_years_of_service,
    ws.full_year_equivalent_compensation,
    EXTRACT(YEAR FROM ws.employee_hire_date) AS hire_year
FROM int_employer_core_contributions ec
JOIN int_workforce_state_accumulator ws
  ON ws.employee_id = ec.employee_id
 AND ws.simulation_year = ec.simulation_year
 AND ws.scenario_id = ec.scenario_id
"""


def _build(
    tmp_path_factory: pytest.TempPathFactory,
    name: str,
    config: Path,
    end_year: int,
    signature: tuple[int, str] | None,
) -> Iterator[Path]:
    database = tmp_path_factory.mktemp(name) / f"{name}.duckdb"
    yield _run(config, database, end_year)
    assert (
        file_signature(SHARED_DEV_DB) == signature
    ), f"{name}: the simulation modified the shared dev database {SHARED_DEV_DB}"


@pytest.fixture(scope="session")
def shared_db_signature() -> tuple[int, str] | None:
    return file_signature(SHARED_DEV_DB)


@pytest.fixture(scope="session")
def boundary_year_db(
    tmp_path_factory: pytest.TempPathFactory,
    shared_db_signature: tuple[int, str] | None,
) -> Iterator[Path]:
    """2025 only: the year whose census ages sit exactly on the tier boundaries."""
    yield from _build(
        tmp_path_factory, "age_banded_2025", SCHEDULE_CONFIG, 2025, shared_db_signature
    )


@pytest.fixture(scope="session")
def migration_year_db(
    tmp_path_factory: pytest.TempPathFactory,
    shared_db_signature: tuple[int, str] | None,
) -> Iterator[Path]:
    """2025-2026: every boundary cohort has aged one year into the next tier."""
    yield from _build(
        tmp_path_factory, "age_banded_2026", SCHEDULE_CONFIG, 2026, shared_db_signature
    )


@pytest.fixture(scope="session")
def empty_schedule_db(
    tmp_path_factory: pytest.TempPathFactory,
    shared_db_signature: tuple[int, str] | None,
) -> Iterator[Path]:
    yield from _build(
        tmp_path_factory,
        "age_banded_empty",
        EMPTY_SCHEDULE_CONFIG,
        2025,
        shared_db_signature,
    )


def test_boundary_ages_are_exercised(boundary_year_db: Path) -> None:
    """The fixture must actually place employees on the tier boundaries."""
    ages = {
        row[0]
        for row in _query(
            boundary_year_db, f"SELECT DISTINCT current_age FROM ({CORE_WITH_AGE})"
        )
    }
    assert {
        29,
        30,
        39,
        40,
        49,
        50,
    } <= ages, f"missing boundary ages, saw {sorted(ages)}"


@pytest.mark.parametrize("database", ["boundary_year_db", "migration_year_db"])
def test_every_paid_contribution_uses_its_annual_age_tier(
    database: str, request: pytest.FixtureRequest
) -> None:
    """SC-002: 100% of paid rows carry the rate for their annual age tier."""
    violations = _query(
        request.getfixturevalue(database),
        f"""
        SELECT employee_id, simulation_year, current_age, core_contribution_rate
        FROM ({CORE_WITH_AGE})
        WHERE employer_core_amount > 0
          AND core_contribution_rate <> {_tier_case_sql('current_age')}
        ORDER BY employee_id
        LIMIT 20
        """,
    )
    assert violations == [], f"rate did not match the age tier: {violations}"


@pytest.mark.parametrize("database", ["boundary_year_db", "migration_year_db"])
def test_amount_agrees_with_audited_rate(
    database: str, request: pytest.FixtureRequest
) -> None:
    """SC-003/FR-006: the reported rate reproduces the reported amount."""
    violations = _query(
        request.getfixturevalue(database),
        f"""
        SELECT employee_id, simulation_year, employer_core_amount,
               eligible_compensation, core_contribution_rate
        FROM ({CORE_WITH_AGE})
        WHERE ABS(
            employer_core_amount
            - ROUND(LEAST(eligible_compensation, irs_401a17_limit)
                    * core_contribution_rate, 2)
        ) > 0.01
        ORDER BY employee_id
        LIMIT 20
        """,
    )
    assert violations == [], f"amount and audited rate disagree: {violations}"


@pytest.mark.parametrize("database", ["boundary_year_db", "migration_year_db"])
def test_flat_fallback_rate_never_leaks_into_a_scheduled_run(
    database: str, request: pytest.FixtureRequest
) -> None:
    """A schedule covering [0, infinity) must never fall through to the flat rate."""
    leaked = _query(
        request.getfixturevalue(database),
        f"""
        SELECT employee_id, current_age
        FROM ({CORE_WITH_AGE})
        WHERE employer_core_amount > 0
          AND core_contribution_rate = {FLAT_FALLBACK_RATE}
        LIMIT 20
        """,
    )
    assert leaked == [], f"flat fallback applied under an age-banded schedule: {leaked}"


@pytest.mark.parametrize("database", ["boundary_year_db", "migration_year_db"])
def test_whole_census_receives_a_contribution(
    database: str, request: pytest.FixtureRequest
) -> None:
    """Guard the tier assertions above from passing vacuously on empty output."""
    paid = _query(
        request.getfixturevalue(database),
        f"""
        SELECT COUNT(*) FROM ({CORE_WITH_AGE})
        WHERE employer_core_amount > 0 AND employee_id LIKE 'AGE_BAND_%'
        """,
    )
    assert paid == [(CENSUS_HEADCOUNT,)]


@pytest.mark.parametrize(
    ("employee_id", "age_2025", "rate_2025", "rate_2026"),
    [
        ("AGE_BAND_29", 29, 0.03, 0.04),
        ("AGE_BAND_39", 39, 0.04, 0.05),
        ("AGE_BAND_49", 49, 0.05, 0.06),
        ("AGE_BAND_30", 30, 0.04, 0.04),
        ("AGE_BAND_60", 60, 0.06, 0.06),
    ],
)
def test_annual_tier_migration(
    boundary_year_db: Path,
    migration_year_db: Path,
    employee_id: str,
    age_2025: int,
    rate_2025: float,
    rate_2026: float,
) -> None:
    """FR-003: the tier is re-resolved each year from that year's age."""
    select = f"""
        SELECT simulation_year, current_age, core_contribution_rate
        FROM ({CORE_WITH_AGE})
        WHERE employee_id = '{employee_id}'
    """
    assert _query(boundary_year_db, select) == [(2025, age_2025, rate_2025)]
    assert _query(migration_year_db, select) == [(2026, age_2025 + 1, rate_2026)]


def test_mid_year_hire_prorates_compensation_but_not_the_rate(
    migration_year_db: Path,
) -> None:
    """FR-005: proration lands on the basis; the selected rate stays whole."""
    rows = _query(
        migration_year_db,
        f"""
        SELECT employee_id, current_age, core_contribution_rate,
               eligible_compensation, full_year_equivalent_compensation
        FROM ({CORE_WITH_AGE})
        WHERE hire_year = simulation_year
          AND employer_core_amount > 0
          AND eligible_compensation < full_year_equivalent_compensation
        ORDER BY employee_id
        """,
    )
    assert rows, "fixture produced no mid-year hire with prorated compensation"
    for _, age, rate, _, _ in rows:
        assert rate == expected_rate(int(age))


@pytest.fixture(scope="session", params=CORE_MODES, ids=lambda mode: mode.name)
def core_mode_run(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
    shared_db_signature: tuple[int, str] | None,
) -> Iterator[tuple[CoreMode, Path]]:
    """One 2025 run per pre-existing core mode, against the same census."""
    mode: CoreMode = request.param
    for database in _build(
        tmp_path_factory,
        f"core_mode_{mode.name}",
        mode.config,
        2025,
        shared_db_signature,
    ):
        # Looping lets _build's shared-database teardown assertion run on close.
        yield mode, database


def test_existing_mode_rate_matches_its_configured_schedule(
    core_mode_run: tuple[CoreMode, Path]
) -> None:
    """FR-007: flat, service-graded, and points-based selection is unchanged."""
    mode, database = core_mode_run
    violations = _query(
        database,
        f"""
        SELECT employee_id, current_age, applied_years_of_service,
               core_contribution_rate
        FROM ({CORE_WITH_AGE})
        WHERE employer_core_amount > 0
          AND core_contribution_rate <> {mode.expected_rate_sql}
        ORDER BY employee_id
        LIMIT 20
        """,
    )
    assert (
        violations == []
    ), f"{mode.name}: rate did not match its schedule: {violations}"


def test_existing_mode_amount_agrees_with_audited_rate(
    core_mode_run: tuple[CoreMode, Path]
) -> None:
    """FR-006 holds for every core mode, not only the age-banded one."""
    mode, database = core_mode_run
    violations = _query(
        database,
        f"""
        SELECT employee_id, employer_core_amount, eligible_compensation,
               core_contribution_rate
        FROM ({CORE_WITH_AGE})
        WHERE ABS(
            employer_core_amount
            - ROUND(LEAST(eligible_compensation, irs_401a17_limit)
                    * core_contribution_rate, 2)
        ) > 0.01
        ORDER BY employee_id
        LIMIT 20
        """,
    )
    assert violations == [], f"{mode.name}: amount and rate disagree: {violations}"


def test_existing_mode_exercises_its_tiers(
    core_mode_run: tuple[CoreMode, Path]
) -> None:
    """Keep the two assertions above from passing on a single-tier population."""
    mode, database = core_mode_run
    observed = _query(
        database,
        f"""
        SELECT COUNT(DISTINCT core_contribution_rate), COUNT(*)
        FROM ({CORE_WITH_AGE})
        WHERE employer_core_amount > 0 AND employee_id LIKE 'AGE_BAND_%'
        """,
    )
    distinct_rates, paid = observed[0]
    assert paid == CENSUS_HEADCOUNT
    assert (
        distinct_rates >= mode.distinct_rates
    ), f"{mode.name}: census exercised only {distinct_rates} tier(s)"


def test_empty_schedule_falls_back_to_the_flat_rate(empty_schedule_db: Path) -> None:
    """FR-009: an age-banded design with no tiers pays the configured flat rate."""
    rates = _query(
        empty_schedule_db,
        f"""
        SELECT DISTINCT core_contribution_rate
        FROM ({CORE_WITH_AGE})
        WHERE employer_core_amount > 0
        """,
    )
    assert rates == [(FLAT_FALLBACK_RATE,)]
