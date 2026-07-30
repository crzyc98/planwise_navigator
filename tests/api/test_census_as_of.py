"""Regression coverage for fixed-date census analyzers."""

import csv
from datetime import date

from planalign_api.services.band_service import BandService
from planalign_api.services.file_service import FileService
from planalign_api.services.turnover_service import TurnoverAnalysisService


def _write_census(path, rows):
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixed_2025_census():
    rows = []
    for index in range(8):
        rows.append(
            {
                "employee_id": f"new-active-{index}",
                "employee_hire_date": "2025-03-01",
                "employee_birth_date": "2000-06-15",
                "employee_termination_date": "",
                "active": "true",
            }
        )
    for index in range(2):
        rows.append(
            {
                "employee_id": f"new-terminated-{index}",
                "employee_hire_date": "2025-03-01",
                "employee_birth_date": "2000-06-15",
                "employee_termination_date": "2025-08-15",
                "active": "false",
            }
        )
    rows.append(
        {
            "employee_id": "experienced",
            "employee_hire_date": "2020-01-01",
            "employee_birth_date": "1980-01-01",
            "employee_termination_date": "",
            "active": "true",
        }
    )
    return rows


def test_fixed_census_uses_its_own_as_of_date_for_all_analyzers(tmp_path):
    """A 2025 census must not change results when the test runs in later years."""
    workspaces_root = tmp_path / "workspaces"
    workspace = workspaces_root / "test-workspace"
    workspace.mkdir(parents=True)
    _write_census(workspace / "census.csv", _fixed_2025_census())

    turnover = TurnoverAnalysisService(workspaces_root).analyze_turnover_rates(
        "test-workspace", "census.csv"
    )
    age_bands = BandService(workspaces_root).analyze_age_distribution_for_bands(
        "test-workspace", "census.csv"
    )
    tenure_bands = BandService(workspaces_root).analyze_tenure_distribution_for_bands(
        "test-workspace", "census.csv"
    )
    new_hire_ages = FileService(workspaces_root).analyze_age_distribution(
        "test-workspace", "census.csv"
    )

    assert turnover.as_of_date.isoformat() == "2025-12-31"
    assert turnover.new_hire_rate is not None
    assert turnover.new_hire_rate.rate == 0.2
    assert "No employees with tenure" not in (turnover.message or "")
    assert tenure_bands.as_of_date.isoformat() == "2025-12-31"
    assert tenure_bands.distribution_stats.max_value == 5
    assert age_bands.as_of_date.isoformat() == "2025-12-31"
    assert age_bands.fallback_notice is not None
    assert new_hire_ages["as_of_date"] == "2025-12-31"
    assert new_hire_ages["fallback_notice"] is not None


def test_explicit_as_of_date_overrides_inference(tmp_path):
    workspaces_root = tmp_path / "workspaces"
    workspace = workspaces_root / "test-workspace"
    workspace.mkdir(parents=True)
    _write_census(workspace / "census.csv", _fixed_2025_census())

    result = TurnoverAnalysisService(workspaces_root).analyze_turnover_rates(
        "test-workspace", "census.csv", as_of_date=date(2026, 12, 31)
    )

    assert result.as_of_date.isoformat() == "2026-12-31"
    assert result.as_of_date_source == "provided"
