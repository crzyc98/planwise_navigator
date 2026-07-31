"""Isolated-DB coverage for Social Security integrated core contributions."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb
import pytest

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import load_simulation_config
from tests.fixtures.edge_config_matrix import SHARED_DEV_DB, file_signature


pytestmark = [pytest.mark.integration, pytest.mark.very_slow]

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures/integrated_core"
CENSUS = FIXTURE_ROOT / "integrated_core.csv"
INTEGRATED_CONFIG = FIXTURE_ROOT / "integrated_core.yaml"
BASELINE_CONFIG = FIXTURE_ROOT / "flat_core_baseline.yaml"
TUFTS_CONFIG = FIXTURE_ROOT / "tufts_cross_tested.yaml"
TUFTS_CENSUS = FIXTURE_ROOT / "tufts_cross_tested.csv"
MODE_CONFIGS = tuple(
    FIXTURE_ROOT / f"core_mode_{mode}_integrated.yaml"
    for mode in ("flat", "graded_by_service", "points_based", "age_banded")
)
PARITY_COLUMNS = """
employee_id, simulation_year, eligible_compensation, employment_status,
eligible_for_core, annual_hours_worked, employer_core_amount,
core_contribution_rate, contribution_method, standard_core_rate,
applied_years_of_service, irs_401a17_limit, irs_401a17_limit_applied
"""


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


def _run(
    config_path: Path,
    database: Path,
    mode: str = "configured",
    census: Path = CENSUS,
) -> Path:
    config = load_simulation_config(config_path, env_overrides=False)
    core = config.employer_core_contribution
    if mode == "disabled":
        core["integration"]["enabled"] = False
    if mode == "omitted":
        core.pop("integration", None)
    census_parquet = database.with_suffix(".census.parquet")
    with duckdb.connect() as connection:
        connection.read_csv(str(census)).write_parquet(str(census_parquet))
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
            start_year=config.simulation.start_year,
            end_year=config.simulation.end_year,
        )
    return database


def _query(database: Path, sql: str) -> list[tuple]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(sql).fetchall()


def _build(
    tmp_path_factory: pytest.TempPathFactory,
    name: str,
    config: Path,
    shared_signature: tuple[int, str] | None,
    mode: str = "configured",
) -> Iterator[Path]:
    database = tmp_path_factory.mktemp(name) / f"{name}.duckdb"
    yield _run(config, database, mode)
    assert (
        file_signature(SHARED_DEV_DB) == shared_signature
    ), f"{name}: the simulation modified the shared dev database {SHARED_DEV_DB}"


@pytest.fixture(scope="session")
def shared_db_signature() -> tuple[int, str] | None:
    return file_signature(SHARED_DEV_DB)


@pytest.fixture(scope="session")
def integrated_db(
    tmp_path_factory: pytest.TempPathFactory,
    shared_db_signature: tuple[int, str] | None,
) -> Iterator[Path]:
    yield from _build(
        tmp_path_factory, "integrated", INTEGRATED_CONFIG, shared_db_signature
    )


@pytest.fixture(scope="session")
def baseline_db(
    tmp_path_factory: pytest.TempPathFactory,
    shared_db_signature: tuple[int, str] | None,
) -> Iterator[Path]:
    yield from _build(
        tmp_path_factory, "baseline", BASELINE_CONFIG, shared_db_signature
    )


@pytest.fixture(scope="session")
def mode_databases(
    tmp_path_factory: pytest.TempPathFactory,
    shared_db_signature: tuple[int, str] | None,
) -> dict[str, Path]:
    databases = {}
    for config_path in MODE_CONFIGS:
        name = config_path.stem
        database = tmp_path_factory.mktemp(name) / f"{name}.duckdb"
        databases[name] = _run(config_path, database)
    assert file_signature(SHARED_DEV_DB) == shared_db_signature
    return databases


def test_integrated_amounts_reconcile_to_the_audited_components(
    integrated_db: Path,
) -> None:
    """FR-008/FR-017/FR-018: the formula is visible and exact per employee."""
    violations = _query(
        integrated_db,
        """
        SELECT employee_id
        FROM int_employer_core_contributions
        WHERE ROUND(base_core_amount + disparity_core_amount, 2)
                  <> ROUND(employer_core_amount, 2)
           OR ABS(base_core_amount - ROUND(
                core_contribution_rate * LEAST(eligible_compensation, irs_401a17_limit), 2
              )) > 0.001
           OR ABS(disparity_core_amount - ROUND(0.027 * excess_compensation, 2)) > 0.001
        """,
    )
    assert violations == []


def test_employee_at_integration_level_receives_no_disparity(
    integrated_db: Path,
) -> None:
    row = _query(
        integrated_db,
        """
        SELECT excess_compensation, disparity_core_amount
        FROM int_employer_core_contributions
        WHERE employee_id = 'CORE_AT_BASE'
        """,
    )
    assert row == [(0, 0)]


def test_cap_applies_before_split(integrated_db: Path) -> None:
    row = _query(
        integrated_db,
        """
        SELECT eligible_compensation, irs_401a17_limit, ss_wage_base, excess_compensation
        FROM int_employer_core_contributions
        WHERE employee_id = 'CORE_ABOVE_CAP'
        """,
    )
    assert len(row) == 1
    eligible_compensation, cap, wage_base, excess = row[0]
    assert eligible_compensation > cap
    assert excess == max(0, cap - wage_base)


def test_integration_level_not_prorated_for_mid_year_hire(integrated_db: Path) -> None:
    row = _query(
        integrated_db,
        """
        SELECT eligible_compensation, integration_level_applied,
               excess_compensation, disparity_core_amount
        FROM int_employer_core_contributions
        WHERE employee_id = 'CORE_MID_YEAR_HIRE'
        """,
    )
    assert len(row) == 1
    compensation, level, excess, disparity = row[0]
    assert compensation < level
    assert excess == 0
    assert disparity == 0


def test_integrated_core_sql_invariants(integrated_db: Path) -> None:
    violations = _query(
        integrated_db,
        """
        SELECT employee_id FROM int_employer_core_contributions
        WHERE excess_compensation = 0 AND disparity_core_amount <> 0
        UNION ALL
        SELECT employee_id FROM int_employer_core_contributions
        WHERE eligible_for_core = FALSE
          AND (employer_core_amount <> 0 OR base_core_amount <> 0 OR disparity_core_amount <> 0)
        UNION ALL
        SELECT employee_id FROM int_employer_core_contributions
        WHERE excess_compensation < 0
           OR excess_compensation > LEAST(eligible_compensation, irs_401a17_limit)
        """,
    )
    assert violations == []
    assert _query(
        integrated_db,
        "SELECT COUNT(*) FROM int_employer_core_contributions WHERE eligible_for_core = FALSE",
    ) == [(1,)]


def test_flat_vs_integrated_cost_delta_equals_disparity_total(
    baseline_db: Path, integrated_db: Path
) -> None:
    flat_total = _query(
        baseline_db,
        "SELECT CAST(SUM(employer_core_amount) AS DECIMAL(18, 2)) "
        "FROM int_employer_core_contributions",
    )[0][0]
    integrated_total, disparity_total = _query(
        integrated_db,
        "SELECT CAST(SUM(employer_core_amount) AS DECIMAL(18, 2)), "
        "CAST(SUM(disparity_core_amount) AS DECIMAL(18, 2)) "
        "FROM int_employer_core_contributions",
    )[0]
    assert integrated_total - flat_total == disparity_total


def test_disparity_composes_with_every_core_status(
    mode_databases: dict[str, Path]
) -> None:
    for name, database in mode_databases.items():
        violations = _query(
            database,
            """
            SELECT employee_id
            FROM int_employer_core_contributions
            WHERE ABS(disparity_core_amount - ROUND(0.01 * excess_compensation, 2)) > 0.001
            """,
        )
        assert violations == [], name
        assert (
            _query(
                database,
                "SELECT COUNT(*) FROM int_employer_core_contributions WHERE disparity_core_amount > 0",
            )[0][0]
            > 0
        ), name


def test_graded_schedule_keeps_its_base_rate_below_and_above_the_level(
    mode_databases: dict[str, Path]
) -> None:
    rows = _query(
        mode_databases["core_mode_graded_by_service_integrated"],
        """
        SELECT core_contribution_rate, disparity_core_amount, excess_compensation
        FROM int_employer_core_contributions
        WHERE excess_compensation > 0
        """,
    )
    assert len({row[0] for row in rows}) >= 2
    assert all(disparity == round(0.01 * excess, 2) for _, disparity, excess in rows)


def test_disabled_integration_matches_an_omitted_integration_block(
    tmp_path_factory: pytest.TempPathFactory,
    shared_db_signature: tuple[int, str] | None,
) -> None:
    for config_path in MODE_CONFIGS:
        disabled = (
            tmp_path_factory.mktemp(f"{config_path.stem}_disabled") / "disabled.duckdb"
        )
        omitted = (
            tmp_path_factory.mktemp(f"{config_path.stem}_omitted") / "omitted.duckdb"
        )
        _run(config_path, disabled, "disabled")
        _run(config_path, omitted, "omitted")
        with duckdb.connect() as connection:
            connection.execute(f"ATTACH '{disabled}' AS disabled (READ_ONLY)")
            connection.execute(f"ATTACH '{omitted}' AS omitted (READ_ONLY)")
            differences = connection.execute(
                f"""
                SELECT {PARITY_COLUMNS} FROM disabled.int_employer_core_contributions
                EXCEPT
                SELECT {PARITY_COLUMNS} FROM omitted.int_employer_core_contributions
                """
            ).fetchall()
        assert differences == [], config_path.stem
    assert file_signature(SHARED_DEV_DB) == shared_db_signature


@pytest.fixture(scope="session")
def tufts_db(
    tmp_path_factory: pytest.TempPathFactory,
    shared_db_signature: tuple[int, str] | None,
) -> Iterator[Path]:
    database = tmp_path_factory.mktemp("tufts") / "tufts.duckdb"
    yield _run(TUFTS_CONFIG, database, census=TUFTS_CENSUS)
    assert file_signature(SHARED_DEV_DB) == shared_db_signature


def test_age_banded_integration_reproduces_a_real_two_band_design(
    tufts_db: Path,
) -> None:
    """An age-banded base rate composes with integration into a step-rate design.

    Modeled on a published university plan: employees under 40 receive 5% of pay
    up to the Social Security wage base and 10% above it; employees 40 and older
    receive 10% below and 15% above. Both bands share a single 5-point disparity,
    which is what makes one `disparity_rate` sufficient for the whole design.

    The existing mode tests only check that disparity equals rate x excess. This
    asserts the dollars an administrator would reconcile against, per band, so a
    regression in how the base rate and the disparity compose cannot pass.
    """
    rows = _query(
        tufts_db,
        """
        SELECT employee_id, core_contribution_rate, ss_wage_base,
               eligible_compensation, excess_compensation,
               base_core_amount, disparity_core_amount, employer_core_amount
        FROM int_employer_core_contributions
        ORDER BY employee_id
        """,
    )
    assert rows, "the Tufts fixture produced no core contribution rows"

    for row in rows:
        employee_id = row[0]
        # DuckDB returns the rate and amounts as Decimal; compare in float.
        base_rate, wage_base, compensation, excess = (
            float(value) for value in row[1:5]
        )
        base_amount, disparity_amount, total = (float(value) for value in row[5:8])

        assert base_rate in (0.05, 0.10), employee_id
        # The design as stated in the plan document, computed independently of
        # the model's base/excess split.
        below = min(compensation, wage_base)
        above = max(0.0, compensation - wage_base)
        expected = round(base_rate * below + (base_rate + 0.05) * above, 2)
        assert round(total, 2) == expected, employee_id
        assert round(base_amount + disparity_amount, 2) == expected, employee_id
        assert round(excess, 2) == round(above, 2), employee_id


def test_age_banded_integration_doubles_the_base_rate_across_the_band(
    tufts_db: Path,
) -> None:
    """The older band receives exactly double the younger band below the level."""
    below_level = _query(
        tufts_db,
        """
        SELECT core_contribution_rate, MIN(base_core_amount / eligible_compensation)
        FROM int_employer_core_contributions
        WHERE excess_compensation = 0 AND eligible_compensation > 0
        GROUP BY core_contribution_rate
        ORDER BY core_contribution_rate
        """,
    )
    assert [float(rate) for rate, _ in below_level] == [0.05, 0.10]
    younger, older = (float(effective) for _, effective in below_level)
    assert older == pytest.approx(2 * younger)
