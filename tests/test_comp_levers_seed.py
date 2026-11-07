"""Guards the comp_levers seed against a year that pays hires differently."""

import csv
from pathlib import Path

import pytest

SEED = Path(__file__).resolve().parents[1] / "dbt" / "seeds" / "comp_levers.csv"


@pytest.mark.fast
def test_hire_market_multiplier_matches_across_years() -> None:
    by_year: dict[str, dict[str, str]] = {}
    with SEED.open(newline="") as seed:
        for row in csv.DictReader(seed):
            if (
                row["scenario_id"] == "default"
                and row["event_type"] == "HIRE"
                and row["parameter_name"] == "market_adjustment_multiplier"
            ):
                levels = by_year.setdefault(row["fiscal_year"], {})
                levels[row["job_level"]] = row["parameter_value"]

    assert len(by_year) > 1
    assert len({tuple(sorted(v.items())) for v in by_year.values()}) == 1
