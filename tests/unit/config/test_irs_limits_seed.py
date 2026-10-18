"""Integrity checks for the statutory limits seed."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest


SEED_PATH = Path(__file__).resolve().parents[3] / "dbt/seeds/config_irs_limits.csv"
CHARACTERIZATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests/fixtures/employer_eligibility_tenure/baseline_characterization.json"
)


@pytest.mark.fast
def test_characterization_irs_seed_hash() -> None:
    baseline = json.loads(CHARACTERIZATION_PATH.read_text())
    assert (
        hashlib.sha256(SEED_PATH.read_bytes()).hexdigest()
        == baseline["provenance"]["irs_seed_sha256"]
    ), "IRS seed changed; reconcile characterization using its documented provenance"


@pytest.mark.parametrize(
    "column",
    (
        "base_limit",
        "catch_up_limit",
        "super_catch_up_limit",
        "compensation_limit",
        "annual_additions_limit",
    ),
)
def test_statutory_limits_never_decrease(column: str) -> None:
    with SEED_PATH.open(newline="") as source:
        rows = sorted(csv.DictReader(source), key=lambda row: int(row["limit_year"]))

    for previous, current in zip(rows, rows[1:]):
        assert int(current[column]) >= int(previous[column]), (
            f"{column} decreased from {previous['limit_year']} "
            f"({previous[column]}) to {current['limit_year']} ({current[column]})"
        )


@pytest.mark.parametrize("column", ("catch_up_limit", "super_catch_up_limit"))
def test_projected_catch_up_allowances_preserve_published_anchor(column: str) -> None:
    with SEED_PATH.open(newline="") as source:
        rows = sorted(csv.DictReader(source), key=lambda row: int(row["limit_year"]))

    anchor = next(row for row in rows if row["limit_year"] == "2026")
    previous_allowance = int(anchor[column]) - int(anchor["base_limit"])
    previous_year = 2026
    for row in rows:
        year = int(row["limit_year"])
        if year <= previous_year:
            continue
        allowance = int(row[column]) - int(row["base_limit"])
        assert allowance >= previous_allowance, (
            f"{column} allowance decreased from {previous_year} "
            f"({previous_allowance}) to {year} ({allowance})"
        )
        previous_allowance = allowance
        previous_year = year


def test_social_security_wage_base_seed_is_complete_and_anchored() -> None:
    """Published wage-base anchors and projected values must stay usable by year."""
    with SEED_PATH.open(newline="") as seed_file:
        rows = list(csv.DictReader(seed_file))

    wage_bases = [
        (int(row["limit_year"]), int(row["social_security_wage_base"])) for row in rows
    ]

    assert all(wage_base > 0 for _, wage_base in wage_bases)
    assert wage_bases == sorted(wage_bases)
    assert [wage_base for _, wage_base in wage_bases] == sorted(
        wage_base for _, wage_base in wage_bases
    )
    assert (
        dict(wage_bases).items() >= {2024: 168600, 2025: 176100, 2026: 184500}.items()
    )


def test_projected_wage_base_rows_remain_estimated() -> None:
    """The new column must follow the seed's established projected-year convention."""
    with SEED_PATH.open(newline="") as seed_file:
        rows = list(csv.DictReader(seed_file))

    assert all(
        row["is_estimated"].lower() == "true"
        for row in rows
        if int(row["limit_year"]) >= 2027
    )


def test_published_2026_limits() -> None:
    with SEED_PATH.open(newline="") as source:
        row = next(r for r in csv.DictReader(source) if r["limit_year"] == "2026")
    assert {
        key: int(row[key])
        for key in (
            "base_limit",
            "catch_up_limit",
            "super_catch_up_limit",
            "annual_additions_limit",
            "compensation_limit",
        )
    } == {
        "base_limit": 24500,
        "catch_up_limit": 32500,
        "super_catch_up_limit": 35750,
        "annual_additions_limit": 72000,
        "compensation_limit": 360000,
    }
    assert row["is_estimated"] == "false"
