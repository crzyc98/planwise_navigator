"""A census with deferral rates outside 0-1 is rejected before staging (#1263)."""

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import duckdb
import pytest

from planalign_orchestrator.census_deferral_rate import (
    count_out_of_range_deferral_rates,
    require_census_deferral_rates,
)
from planalign_orchestrator.exceptions import DataQualityError
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator

pytestmark = pytest.mark.fast


def _census(
    tmp_path: Path, rates: list[Optional[str]], sql_type: str = "DOUBLE"
) -> Path:
    path = tmp_path / "census.parquet"
    with duckdb.connect() as conn:
        conn.execute(
            f"CREATE TABLE census (employee_id VARCHAR, employee_deferral_rate {sql_type})"
        )
        for i, rate in enumerate(rates):
            conn.execute("INSERT INTO census VALUES (?, ?)", [f"E{i}", rate])
        conn.execute(f"COPY census TO '{path}' (FORMAT PARQUET)")
    return path


def test_fractions_and_blank_rates_pass(tmp_path: Path) -> None:
    path = _census(tmp_path, ["0", "0.06", "0.75", "1", None])

    require_census_deferral_rates(path)


@pytest.mark.parametrize("sql_type", ["DOUBLE", "VARCHAR"])
def test_percent_style_rates_are_rejected_with_a_count(
    tmp_path: Path, sql_type: str
) -> None:
    path = _census(tmp_path, ["0.06", "6", "15", "95", "150", "-0.02"], sql_type)

    with pytest.raises(DataQualityError) as excinfo:
        require_census_deferral_rates(path)

    message = str(excinfo.value)
    assert "5 row(s)" in message
    assert "employee_deferral_rate" in message
    assert "0.06 for 6%" in message
    assert "E1" not in message


def test_unreadable_text_rates_are_left_to_staging(tmp_path: Path) -> None:
    path = _census(tmp_path, ["0.06", "six"], "VARCHAR")

    assert count_out_of_range_deferral_rates(path) == 0


def test_census_without_the_column_passes(tmp_path: Path) -> None:
    path = tmp_path / "census.parquet"
    with duckdb.connect() as conn:
        conn.execute(f"COPY (SELECT 'E1' AS employee_id) TO '{path}' (FORMAT PARQUET)")

    require_census_deferral_rates(path)


def test_missing_census_is_left_to_staging(tmp_path: Path) -> None:
    require_census_deferral_rates(tmp_path / "missing.parquet")
    require_census_deferral_rates(None)


def test_bad_rates_stop_the_run_before_staging(tmp_path: Path) -> None:
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._dbt_vars = {"census_parquet_path": str(_census(tmp_path, ["15"]))}
    orchestrator.dbt_runner = MagicMock()

    with pytest.raises(DataQualityError):
        orchestrator._run_start_year_setup(2025)

    orchestrator.dbt_runner.execute_command.assert_not_called()
