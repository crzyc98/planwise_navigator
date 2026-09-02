"""Acceptance coverage for design-keyed same-family plan parameters."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from tests.fixtures.invariant_simulation import (
    _database_environment,
    _simulation_config,
)
from tests.fixtures.plan_design_parameters.config import (
    apply_equivalent_single_design_parameters,
    apply_two_design_parameters,
)

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]


@pytest.fixture(scope="module")
def plan_design_parameter_database(
    tmp_path_factory: pytest.TempPathFactory,
    invariant_census_parquet: Path,
) -> Path:
    database = tmp_path_factory.mktemp("plan-design-parameters") / "parameters.duckdb"
    config = apply_two_design_parameters(_simulation_config(invariant_census_parquet))
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


@pytest.fixture(scope="module")
def single_design_parity_databases(
    tmp_path_factory: pytest.TempPathFactory,
    invariant_census_parquet: Path,
) -> dict[int, tuple[Path, Path]]:
    root = tmp_path_factory.mktemp("plan-design-parameter-parity")
    databases: dict[int, tuple[Path, Path]] = {}
    for census_size in (40, 149):
        census = root / f"census_{census_size}.parquet"
        with duckdb.connect() as conn:
            (
                conn.read_parquet(str(invariant_census_parquet))
                .order("employee_id")
                .limit(census_size)
                .write_parquet(str(census))
            )
        scalar_database = root / f"scalar_{census_size}.duckdb"
        keyed_database = root / f"keyed_{census_size}.duckdb"
        configs = (
            _simulation_config(census),
            apply_equivalent_single_design_parameters(_simulation_config(census)),
        )
        for database, config in zip(
            (scalar_database, keyed_database), configs, strict=True
        ):
            with _database_environment(database):
                build_orchestrator(
                    ConstructionSpec(
                        config=config,
                        database=database,
                        threads=1,
                        entry_point="invariant_test",
                        validation_mode=True,
                    )
                ).orchestrator.execute_multi_year_simulation(
                    start_year=2025, end_year=2027
                )
        databases[census_size] = (scalar_database, keyed_database)
    return databases


@pytest.mark.parametrize(
    ("employee_id", "design_id", "ceiling", "rate"),
    [
        ("INV_EMP_0052", "legacy_design", Decimal("0.03"), Decimal("1.0")),
        ("INV_EMP_0002", "current_design", Decimal("0.06"), Decimal("0.5")),
    ],
)
def test_match_amount_ties_to_assigned_design(
    plan_design_parameter_database: Path,
    employee_id: str,
    design_id: str,
    ceiling: Decimal,
    rate: Decimal,
) -> None:
    with duckdb.connect(str(plan_design_parameter_database), read_only=True) as conn:
        row = conn.execute(
            "SELECT plan_design_id, eligible_compensation, deferral_rate, "
            "employer_match_amount FROM int_employee_match_calculations "
            "WHERE employee_id = ?",
            [employee_id],
        ).fetchone()
    assert row is not None
    actual_design, compensation, deferral_rate, actual_amount = row
    expected = (
        Decimal(str(compensation)) * min(Decimal(str(deferral_rate)), ceiling) * rate
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert actual_design == design_id
    assert Decimal(str(actual_amount)) == expected


def test_every_employee_year_resolves_one_design(
    plan_design_parameter_database: Path,
) -> None:
    with duckdb.connect(str(plan_design_parameter_database), read_only=True) as conn:
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM ("
            " SELECT scenario_id, plan_design_id, employee_id, simulation_year"
            " FROM int_employee_match_calculations GROUP BY ALL HAVING COUNT(*) <> 1)"
        ).fetchone()[0]
        design_set = conn.execute(
            "SELECT LIST(DISTINCT plan_design_id ORDER BY plan_design_id) "
            "FROM int_employee_match_calculations"
        ).fetchone()[0]
    assert duplicates == 0
    assert design_set == ["current_design", "legacy_design"]


def test_core_and_eligibility_parameters_resolve_by_design(
    plan_design_parameter_database: Path,
) -> None:
    with duckdb.connect(str(plan_design_parameter_database), read_only=True) as conn:
        core_rows = conn.execute(
            "SELECT plan_design_id, LIST(DISTINCT core_contribution_rate "
            "ORDER BY core_contribution_rate) FROM int_employer_core_contributions "
            "WHERE eligible_for_core GROUP BY plan_design_id ORDER BY plan_design_id"
        ).fetchall()
        eligibility_rows = conn.execute(
            "SELECT plan_design_id, MIN(waiting_period_days), "
            "MAX(waiting_period_days) FROM int_plan_eligibility_determination "
            "GROUP BY plan_design_id ORDER BY plan_design_id"
        ).fetchall()
        snapshot_mismatches = conn.execute(
            "SELECT COUNT(*) FROM fct_workforce_snapshot snapshot "
            "JOIN int_plan_eligibility_determination eligibility USING "
            "(plan_design_id, employee_id, simulation_year) "
            "WHERE snapshot.waiting_period_days <> eligibility.waiting_period_days "
            "OR snapshot.employee_eligibility_date <> eligibility.plan_eligibility_date"
        ).fetchone()[0]

    assert core_rows == [
        ("current_design", [Decimal("0.030000")]),
        ("legacy_design", [Decimal("0.020000")]),
    ]
    assert eligibility_rows == [
        ("current_design", 90, 90),
        ("legacy_design", 0, 0),
    ]
    assert snapshot_mismatches == 0


def test_enrollment_and_escalation_events_use_design_terms(
    plan_design_parameter_database: Path,
) -> None:
    with duckdb.connect(str(plan_design_parameter_database), read_only=True) as conn:
        auto_enrollment_rates = conn.execute(
            "SELECT plan_design_id, LIST(DISTINCT employee_deferral_rate "
            "ORDER BY employee_deferral_rate) FROM fct_yearly_events "
            "WHERE event_category = 'auto_enrollment' "
            "GROUP BY plan_design_id ORDER BY plan_design_id"
        ).fetchall()
        auto_date_mismatches = conn.execute(
            "SELECT COUNT(*) FROM fct_yearly_events event "
            "JOIN int_plan_eligibility_determination eligibility USING "
            "(plan_design_id, employee_id, simulation_year) "
            "WHERE event.event_category = 'auto_enrollment' "
            "AND event.effective_date <> eligibility.plan_eligibility_date "
            "+ INTERVAL '30 days'"
        ).fetchone()[0]
        escalation_rows = conn.execute(
            "SELECT plan_design_id, LIST(DISTINCT event_probability "
            "ORDER BY event_probability), MAX(employee_deferral_rate) "
            "FROM fct_yearly_events WHERE event_type = 'deferral_escalation' "
            "GROUP BY plan_design_id ORDER BY plan_design_id"
        ).fetchall()
        missing_designs = conn.execute(
            "SELECT COUNT(*) FROM int_deferral_rate_state_accumulator "
            "WHERE plan_design_id IS NULL"
        ).fetchone()[0]

    assert auto_enrollment_rates == [("current_design", [0.06])]
    assert auto_date_mismatches == 0
    normalized_escalations = [
        (design, [round(rate, 4) for rate in rates], round(cap, 4))
        for design, rates, cap in escalation_rows
    ]
    assert normalized_escalations == [
        ("current_design", [0.02], 0.08),
        ("legacy_design", [0.01], 0.10),
    ]
    assert missing_designs == 0


@pytest.mark.parametrize(
    ("table_name", "excluded_columns"),
    [
        ("fct_yearly_events", ["created_at"]),
        ("fct_workforce_snapshot", ["snapshot_created_at"]),
        ("int_employee_match_calculations", ["created_at"]),
        ("int_employer_core_contributions", ["created_at"]),
    ],
)
@pytest.mark.parametrize("census_size", [40, 149])
def test_equivalent_single_design_business_rows_are_identical(
    single_design_parity_databases: dict[int, tuple[Path, Path]],
    table_name: str,
    excluded_columns: list[str],
    census_size: int,
) -> None:
    scalar_database, keyed_database = single_design_parity_databases[census_size]
    excluded = ", ".join(excluded_columns)
    projection = f"* EXCLUDE ({excluded})" if excluded else "*"
    with duckdb.connect(str(scalar_database), read_only=True) as conn:
        conn.execute(f"ATTACH '{keyed_database}' AS keyed (READ_ONLY)")
        columns = [
            row[0]
            for row in conn.execute(f"DESCRIBE main.{table_name}").fetchall()
            if row[0] not in excluded_columns
        ]
        row_hash = "hash(" + ", ".join(f'"{column}"' for column in columns) + ")"
        scalar_only = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT {projection} FROM main.{table_name} "
            f"EXCEPT ALL SELECT {projection} FROM keyed.{table_name})"
        ).fetchone()[0]
        keyed_only = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT {projection} FROM keyed.{table_name} "
            f"EXCEPT ALL SELECT {projection} FROM main.{table_name})"
        ).fetchone()[0]
        scalar_hashes = conn.execute(
            f"SELECT {row_hash} FROM ("
            f"SELECT {projection} FROM main.{table_name} UNION ALL "
            f"SELECT {projection} FROM keyed.{table_name} WHERE FALSE"
            ") normalized ORDER BY 1"
        ).fetchall()
        keyed_hashes = conn.execute(
            f"SELECT {row_hash} FROM ("
            f"SELECT {projection} FROM keyed.{table_name} UNION ALL "
            f"SELECT {projection} FROM main.{table_name} WHERE FALSE"
            ") normalized ORDER BY 1"
        ).fetchall()
    assert (scalar_only, keyed_only) == (0, 0)
    assert scalar_hashes == keyed_hashes
