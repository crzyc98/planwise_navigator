"""Census more than a year behind the simulation start (#1078)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.census_year import census_gap_message, infer_census_year

pytestmark = [pytest.mark.fast, pytest.mark.config]


def _census(tmp_path: Path, hire_dates: list[str]) -> Path:
    path = tmp_path / "census.parquet"
    values = ", ".join(f"('{d}')" for d in hire_dates)
    with duckdb.connect() as conn:
        conn.execute(
            f"COPY (SELECT * FROM (VALUES {values}) t(employee_hire_date)) "
            f"TO '{path}' (FORMAT parquet)"
        )
    return path


def test_census_year_ignores_stray_future_hires(tmp_path: Path) -> None:
    dates = ["2020-03-01"] * 150 + ["2024-06-01"] * 49 + ["2025-02-22"]
    assert infer_census_year(_census(tmp_path, dates)) == 2024


def test_census_year_is_none_without_hire_dates(tmp_path: Path) -> None:
    assert infer_census_year(_census(tmp_path, ["not a date"])) is None


@pytest.mark.parametrize("start", [2024, 2025])
def test_no_warning_when_the_census_is_current(start: int) -> None:
    assert census_gap_message(2024, start) is None


def test_warning_points_to_the_roll_forward() -> None:
    message = census_gap_message(2024, 2026)
    assert message is not None
    assert "2025 has no simulated hires" in message
    assert "Roll the census forward to 2025" in message


def test_warning_spans_a_multi_year_gap() -> None:
    message = census_gap_message(2022, 2026)
    assert message is not None
    assert "2023-2025 has no simulated hires" in message
