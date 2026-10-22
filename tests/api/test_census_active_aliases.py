"""Regression coverage for #959: suggestions accept text ``active`` values."""

import csv
from datetime import date

import pytest

from planalign_api.services.band_service import BandService
from planalign_api.services.file_service import FileService
from planalign_api.services.turnover_service import TurnoverAnalysisService

pytestmark = pytest.mark.fast

WORKSPACE = "test-workspace"


def _rows(active: str, inactive: str) -> list[dict[str, object]]:
    rows = []
    for index in range(40):
        terminated = index % 5 == 0
        rows.append(
            {
                "employee_id": f"E{index}",
                "employee_hire_date": f"{2018 + index % 8}-03-01",
                "employee_birth_date": f"{1965 + index % 30}-06-15",
                "employee_termination_date": "2025-08-15" if terminated else "",
                "employee_gross_compensation": 50_000 + index * 1_000,
                "level_id": 1 + index % 3,
                "scheduled_hours_per_week": 20 if index % 4 == 0 else 40,
                "active": inactive if terminated else active,
            }
        )
    return rows


def _write(path, rows) -> None:
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _suggestions(root, filename: str) -> dict[str, object]:
    files, bands = FileService(root), BandService(root)
    results: dict[str, object] = {
        "turnover": TurnoverAnalysisService(root).analyze_turnover_rates(
            WORKSPACE, filename
        ),
        "age_bands": bands.analyze_age_distribution_for_bands(WORKSPACE, filename),
        "tenure_bands": bands.analyze_tenure_distribution_for_bands(
            WORKSPACE, filename
        ),
        "new_hire_ages": files.analyze_age_distribution(WORKSPACE, filename),
        "part_time": files.analyze_part_time_pct(WORKSPACE, filename),
        "compensation": files.analyze_compensation_by_level(WORKSPACE, filename),
    }
    return {
        name: {
            key: value
            for key, value in (
                result if isinstance(result, dict) else result.model_dump()
            ).items()
            if key not in {"source_file", "file_path"}
        }
        for name, result in results.items()
    }


@pytest.mark.parametrize(
    ("active", "inactive"), [("Active", "Terminated"), ("employed", "separated")]
)
def test_text_active_census_matches_boolean_census(tmp_path, active, inactive):
    """A census set by path keeps its text flags; every suggestion must still work."""
    root = tmp_path / "workspaces"
    (root / WORKSPACE).mkdir(parents=True)
    _write(root / WORKSPACE / "bool.csv", _rows("true", "false"))
    _write(root / WORKSPACE / "text.csv", _rows(active, inactive))

    assert _suggestions(root, "text.csv") == _suggestions(root, "bool.csv")


@pytest.mark.parametrize("term_date_column", [True, False])
@pytest.mark.parametrize("inactive", ["false", "Terminated", "separated"])
def test_turnover_counts_undated_inactive_flags(tmp_path, inactive, term_date_column):
    """Without a termination date, the active flag decides; NULL stays active."""
    root = tmp_path / "workspaces"
    (root / WORKSPACE).mkdir(parents=True)
    flags = [inactive] * 4 + ["Active"] * 10 + [""] * 2
    rows = [
        {
            "employee_id": f"E{index}",
            "employee_hire_date": "2020-03-01",
            **({"employee_termination_date": ""} if term_date_column else {}),
            "active": flag,
        }
        for index, flag in enumerate(flags)
    ]
    _write(root / WORKSPACE / "census.csv", rows)

    result = TurnoverAnalysisService(root).analyze_turnover_rates(
        WORKSPACE, "census.csv", as_of_date=date(2025, 12, 31)
    )

    assert (result.total_employees, result.total_terminated) == (16, 4)
