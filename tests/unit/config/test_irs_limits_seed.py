"""Integrity checks for the statutory limits seed."""

from __future__ import annotations

import csv
from pathlib import Path


SEED_PATH = Path(__file__).resolve().parents[3] / "dbt/seeds/config_irs_limits.csv"


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
