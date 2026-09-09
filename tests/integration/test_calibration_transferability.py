"""Optimize -> exact apply -> isolated full-simulation transferability gate.

This reuses the checked-in synthetic invariant census and its session-scoped
isolated baseline. It never reads or writes ``dbt/simulation.duckdb``.

Run locally with:
    pytest tests/integration/test_calibration_transferability.py -v
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest
import yaml

from planalign_api.routers.calibration import (
    CalibrationApplyRequest,
    CalibrationContext,
    _merge_calibration_candidate,
)
from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.calibration_optimizer import (
    AutoCalibrationSettings,
    AutoCalibrator,
)
from planalign_orchestrator.calibration_runner import CalibrationRun
from planalign_orchestrator.config import SimulationConfig

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration]

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "tests/fixtures/invariant_config.yaml"
BASE_RANGES = [
    {"level": 1, "name": "Staff", "min_compensation": 56000, "max_compensation": 80000},
    {
        "level": 2,
        "name": "Manager",
        "min_compensation": 81000,
        "max_compensation": 120000,
    },
    {
        "level": 3,
        "name": "SrMgr",
        "min_compensation": 121000,
        "max_compensation": 160000,
    },
    {
        "level": 4,
        "name": "Director",
        "min_compensation": 161000,
        "max_compensation": 300000,
    },
    {"level": 5, "name": "VP", "min_compensation": 275000, "max_compensation": 500000},
]


def _config(census: Path) -> dict:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["setup"]["census_parquet_path"] = str(census)
    config["simulation"]["end_year"] = 2026
    return config


def _full_metrics(database: Path) -> dict[int, tuple[int, float, float, float | None]]:
    with duckdb.connect(str(database), read_only=True) as connection:
        rows = connection.execute(
            """
            WITH annual AS (
              SELECT
                simulation_year,
                COUNT(*) AS headcount,
                AVG(prorated_annual_compensation) AS avg_compensation,
                SUM(prorated_annual_compensation) AS total_compensation
              FROM fct_workforce_snapshot
              WHERE detailed_status_code IN ('continuous_active', 'new_hire_active')
                AND simulation_year BETWEEN 2025 AND 2026
              GROUP BY simulation_year
            )
            SELECT
              simulation_year,
              headcount,
              avg_compensation,
              total_compensation,
              100 * (avg_compensation / LAG(avg_compensation) OVER (
                ORDER BY simulation_year
              ) - 1) AS yoy_growth_pct
            FROM annual
            ORDER BY simulation_year
            """
        ).fetchall()
    return {
        int(year): (int(headcount), float(avg_comp), float(total_comp), yoy)
        for year, headcount, avg_comp, total_comp, yoy in rows
    }


def _run_full(config: dict, database: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(database))
    orchestrator = build_orchestrator(
        ConstructionSpec(
            config=SimulationConfig.model_validate(config),
            database=database,
            threads=1,
            entry_point="invariant_test",
            validation_mode=True,
        )
    ).orchestrator
    orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2026)


def test_applied_candidate_reproduces_calibration_in_full_simulation(
    tmp_path: Path,
    invariant_run_db: Path,
    invariant_census_parquet: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(invariant_census_parquet)
    config_path = tmp_path / "target.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    calibration_db = tmp_path / "calibration.duckdb"
    shutil.copy2(invariant_run_db, calibration_db)

    baseline = _full_metrics(invariant_run_db)
    target_pct = baseline[2026][3]
    assert target_pct is not None
    tolerance = 0.01
    outcome = AutoCalibrator(
        CalibrationRun(
            start_year=2025,
            end_year=2026,
            config_path=config_path,
            database_path=calibration_db,
        ),
        AutoCalibrationSettings(
            target_workforce_growth=config["simulation"]["target_growth_rate"],
            target_comp_growth=target_pct / 100,
            tolerance_pct=tolerance,
            max_iterations=4,
            search_mode="new_hire_scale",
            base_job_level_compensation=BASE_RANGES,
            initial_scale=1.0,
            lever_fallback=False,
        ),
        threads=1,
    ).optimize()

    context = CalibrationContext(
        workspace_id="synthetic-workspace",
        scenario_id="synthetic-scenario",
        source_scenario_id="synthetic-scenario",
        source_run_id="synthetic-run",
        config_fingerprint="a" * 64,
        census_fingerprint="b" * 64,
        random_seed=config["simulation"]["random_seed"],
        start_year=2025,
        end_year=2026,
    )
    applied = _merge_calibration_candidate(
        config,
        CalibrationApplyRequest(
            context=context,
            best_params=outcome.best_params,
            target_comp_growth_pct=outcome.target_comp_growth_pct,
        ),
    )
    assert applied["new_hire"]["job_level_compensation"] == (
        outcome.best_params.job_level_compensation
    )

    full_database = tmp_path / "applied_full.duckdb"
    _run_full(applied, full_database, monkeypatch)
    full = _full_metrics(full_database)

    assert outcome.converged
    assert outcome.max_abs_error_pct <= tolerance
    for result in outcome.results:
        headcount, avg_comp, total_comp, growth = full[result.simulation_year]
        assert result.headcount == headcount
        assert result.avg_compensation == pytest.approx(avg_comp, abs=1e-6)
        assert result.total_compensation == pytest.approx(total_comp, abs=1e-6)
        assert result.yoy_growth_pct == pytest.approx(growth, abs=1e-9)
        if result.growth_delta_pct is not None:
            assert abs(result.growth_delta_pct) <= tolerance
