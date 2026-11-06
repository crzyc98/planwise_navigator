"""Reject simulation years that the year-keyed seed files do not cover."""

from __future__ import annotations

import csv
from pathlib import Path

_SEED_DIR = Path(__file__).resolve().parents[2] / "dbt/seeds"
# Past its last year, comp_levers and the COLA seed drop raises and promotions,
# and the IRS seed leaves contribution limits empty. dbt reports none of these.
_YEAR_COLUMNS = {
    "comp_levers.csv": "fiscal_year",
    "config_cola_by_year.csv": "year",
    "config_irs_limits.csv": "limit_year",
}


def _last_seed_year(file_name: str, column: str) -> int:
    with (_SEED_DIR / file_name).open(newline="") as seed_file:
        return max(int(row[column]) for row in csv.DictReader(seed_file))


def validate_seed_coverage(end_year: int) -> None:
    """Raise ``ValueError`` if a required seed file stops before ``end_year``."""
    last_years = {
        file_name: _last_seed_year(file_name, column)
        for file_name, column in _YEAR_COLUMNS.items()
    }
    last_covered = min(last_years.values())
    if end_year > last_covered:
        short_seeds = ", ".join(
            name for name, year in last_years.items() if year < end_year
        )
        raise ValueError(
            f"Simulations can only run through {last_covered}, but the end year is "
            f"{end_year}. Compensation and IRS limit data stops before {end_year} "
            f"in dbt/seeds: {short_seeds}. Choose an earlier end year, or add the "
            "missing years to those files."
        )
