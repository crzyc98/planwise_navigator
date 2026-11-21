"""A census with deferral rates outside 0-1 is rejected before staging (#1263)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import duckdb
import pytest

from planalign_orchestrator import pipeline_orchestrator as pipeline_module
from planalign_orchestrator.census_deferral_rate import (
    require_census_deferral_rates,
    resolve_census_path,
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


def test_float_noise_around_the_bounds_passes(tmp_path: Path) -> None:
    path = _census(tmp_path, ["1.0000000000000002", "-0.000001", "0.999999"])

    require_census_deferral_rates(path)


def test_text_that_is_not_a_number_is_rejected(tmp_path: Path) -> None:
    path = _census(tmp_path, ["0.06", "6%", "six", None], "VARCHAR")

    with pytest.raises(DataQualityError, match=r"2 row\(s\)"):
        require_census_deferral_rates(path)


def test_census_without_the_column_passes(tmp_path: Path) -> None:
    path = tmp_path / "census.parquet"
    with duckdb.connect() as conn:
        conn.execute(f"COPY (SELECT 'E1' AS employee_id) TO '{path}' (FORMAT PARQUET)")

    require_census_deferral_rates(path)


def test_missing_or_unreadable_census_is_left_to_staging(tmp_path: Path) -> None:
    require_census_deferral_rates(tmp_path / "missing.parquet")
    require_census_deferral_rates(tmp_path)
    not_parquet = tmp_path / "census.parquet"
    not_parquet.write_text("employee_id,employee_deferral_rate\nE1,15\n")
    require_census_deferral_rates(not_parquet)


def test_census_path_falls_back_to_the_dbt_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dbt_dir = tmp_path / "dbt"
    monkeypatch.delenv("DATA_PATH", raising=False)
    assert resolve_census_path("/srv/c.parquet", dbt_dir) == Path("/srv/c.parquet")
    assert (
        resolve_census_path(None, dbt_dir)
        == dbt_dir / "../data" / "census_preprocessed.parquet"
    )
    monkeypatch.setenv("DATA_PATH", "/srv/data")
    assert resolve_census_path(None, dbt_dir) == Path(
        "/srv/data/census_preprocessed.parquet"
    )


def test_bad_rates_stop_the_run_before_anything_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialized: list[bool] = []
    for name in (
        "validate_seed_coverage",
        "warn_unreached_acquisitions",
        "warn_unreached_minimum_wage_steps",
    ):
        monkeypatch.setattr(pipeline_module, name, lambda *_args: None)
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator.config = SimpleNamespace(
        simulation=SimpleNamespace(start_year=2025, end_year=2026)
    )
    orchestrator._dbt_vars = {"census_parquet_path": str(_census(tmp_path, ["15"]))}
    orchestrator.dbt_runner = SimpleNamespace(working_dir=tmp_path)
    orchestrator._initialization_callback = lambda: initialized.append(True)

    with pytest.raises(DataQualityError):
        orchestrator.execute_multi_year_simulation()

    assert not initialized
