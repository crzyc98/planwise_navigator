"""IRS 402(g) limits: run the production macro against the production seed.

`int_employee_contributions` caps deferrals at `irs_402g_limit_for_age` for the
year's `config_irs_limits` row. These tests execute that macro in DuckDB for
every seeded year and every age from 18 to 80, so a seed or macro change that
breaks the age bands (base, catch-up at 50+, SECURE 2.0 super catch-up at
60-63) fails here. Real simulations also check contributions against the
applicable limit (`test_employee_contributions_validation`).
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment

DBT = Path(__file__).resolve().parents[2] / "dbt"
SEED = DBT / "seeds" / "config_irs_limits.csv"
MODEL = DBT / "models" / "intermediate" / "int_employee_contributions.sql"
MACRO = DBT / "macros" / "irs_402g_limit_for_age.sql"
AGES = range(18, 81)


def _seed_rows() -> list[dict[str, int]]:
    with SEED.open() as handle:
        return [
            {
                key: int(row[key])
                for key in (
                    "limit_year",
                    "base_limit",
                    "catch_up_limit",
                    "catch_up_age_threshold",
                    "super_catch_up_limit",
                    "super_catch_up_age_min",
                    "super_catch_up_age_max",
                )
            }
            for row in csv.DictReader(handle)
        ]


def _expected_limit(row: dict[str, int], age: int) -> int:
    if row["super_catch_up_age_min"] <= age <= row["super_catch_up_age_max"]:
        return row["super_catch_up_limit"]
    if age >= row["catch_up_age_threshold"]:
        return row["catch_up_limit"]
    return row["base_limit"]


@pytest.fixture(scope="module")
def limits_by_year_and_age() -> dict[tuple[int, int], int]:
    macro = Environment().from_string(MACRO.read_text()).module
    limit = macro.irs_402g_limit_for_age("people.age", "il")
    with duckdb.connect() as conn:
        conn.execute(
            f"CREATE TABLE config_irs_limits AS SELECT * FROM read_csv('{SEED}')"
        )
        rows = conn.execute(f"""
            SELECT il.limit_year, people.age, {limit}
            FROM config_irs_limits il
            CROSS JOIN range({AGES.start}, {AGES.stop}) people(age)
            """).fetchall()
    return {(year, age): value for year, age, value in rows}


def test_every_seeded_year_and_age_gets_its_band_limit(
    limits_by_year_and_age: dict[tuple[int, int], int],
) -> None:
    seed = _seed_rows()
    assert len(limits_by_year_and_age) == len(seed) * len(AGES)
    for row in seed:
        for age in AGES:
            assert limits_by_year_and_age[(row["limit_year"], age)] == (
                _expected_limit(row, age)
            ), (row["limit_year"], age)


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (49, 23500),
        (50, 31000),
        (59, 31000),
        (60, 34750),
        (63, 34750),
        (64, 31000),
    ],
)
def test_2025_age_boundaries(
    limits_by_year_and_age: dict[tuple[int, int], int], age: int, expected: int
) -> None:
    assert limits_by_year_and_age[(2025, age)] == expected


def test_seed_limits_are_ordered() -> None:
    for row in _seed_rows():
        assert 0 < row["base_limit"] < row["catch_up_limit"]
        assert row["catch_up_limit"] <= row["super_catch_up_limit"]
        assert (
            row["catch_up_age_threshold"]
            < row["super_catch_up_age_min"]
            <= row["super_catch_up_age_max"]
        )


def test_contributions_model_uses_the_shared_limit_macro() -> None:
    model = MODEL.read_text()
    assert "irs_402g_limit_for_age('ci.contribution_limit_age', 'il')" in model
    # An inline copy of the age bands could drift from the tested macro.
    assert "THEN il.super_catch_up_limit" not in model
