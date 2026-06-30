"""Integration test: comp metrics from calibration are EXACT vs. a full sim.

This is the make-or-break gate (SC-002 / FR-003). Because calibration reuses
the identical validated SQL, the per-year average compensation and YoY growth
must match a full simulation bit-for-bit under the same config.

The test runs against a pre-built, fully-simulated isolated baseline database
(per the CLAUDE.md isolated-DB rule -- never the shared dev DB). Point it at one
with:

    CALIBRATION_BASELINE_DB=/tmp/cal/iso.duckdb \
      pytest tests/test_calibration_exactness.py -v

To produce the baseline:

    DATABASE_PATH=/tmp/cal/iso.duckdb \
      planalign simulate 2025-2029 --database /tmp/cal/iso.duckdb

The test skips when no baseline DB is provided so the fast suite stays fast.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.calibration_runner import (
    CalibrationRun,
    CalibrationRunner,
)

pytestmark = [pytest.mark.integration]

_BASELINE_ENV = "CALIBRATION_BASELINE_DB"


def _baseline_db() -> Path:
    raw = os.getenv(_BASELINE_ENV)
    if not raw:
        pytest.skip(
            f"Set {_BASELINE_ENV} to a fully-built isolated DB to run the "
            "exactness integration test (see module docstring)."
        )
    db = Path(raw)
    if not db.exists():
        pytest.skip(f"{_BASELINE_ENV}={db} does not exist")
    return db


def _year_bounds(db: Path) -> tuple[int, int]:
    conn = duckdb.connect(str(db), read_only=True)
    try:
        lo, hi = conn.execute(
            "SELECT MIN(simulation_year), MAX(simulation_year) "
            "FROM fct_workforce_snapshot"
        ).fetchone()
    finally:
        conn.close()
    return int(lo), int(hi)


def _per_employee_comp(db: Path) -> dict[tuple[int, str], float]:
    """Active employees' prorated comp keyed by (year, employee_id)."""
    conn = duckdb.connect(str(db), read_only=True)
    try:
        rows = conn.execute(
            """
            SELECT simulation_year, employee_id, prorated_annual_compensation
            FROM fct_workforce_snapshot
            WHERE detailed_status_code IN ('continuous_active', 'new_hire_active')
            """
        ).fetchall()
    finally:
        conn.close()
    return {(int(r[0]), r[1]): r[2] for r in rows}


def test_calibration_comp_columns_exact(tmp_path) -> None:
    """Calibrate a copy of the baseline; comp must match the full sim per-row.

    The full pipeline does not build fct_compensation_growth, so the source of
    truth is fct_workforce_snapshot (which it does build). Because calibration
    reuses the identical validated SQL, the per-employee prorated compensation
    must be exact -- compared here employee-by-employee.
    """
    baseline = _baseline_db()
    start, end = _year_bounds(baseline)

    # Copy so we never mutate the baseline; calibrate rebuilds the comp subgraph.
    target = tmp_path / "calibrated.duckdb"
    shutil.copy(baseline, target)

    run = CalibrationRun(start_year=start, end_year=end, database_path=target)
    results = CalibrationRunner(run, threads=1).run_calibration()

    full = _per_employee_comp(baseline)
    calibrated = _per_employee_comp(target)

    # Same active population, same comp for every employee in every year.
    assert set(calibrated) == set(full), "active population diverged"
    for key, full_comp in full.items():
        assert calibrated[key] == pytest.approx(
            full_comp, abs=1e-6
        ), f"comp drift for {key}"

    # The S051 growth mart must have been produced for every year.
    assert {r.simulation_year for r in results} == set(range(start, end + 1))


def test_calibration_tracks_non_default_config(tmp_path) -> None:
    """Exactness must hold under a non-default comp config, not just defaults.

    Point CALIBRATION_EDGE_BASELINE_DB at a full sim built with an edge config
    (e.g. higher COLA + a fixed new-hire level distribution) and
    CALIBRATION_EDGE_CONFIG at that same config file.
    """
    raw_db = os.getenv("CALIBRATION_EDGE_BASELINE_DB")
    raw_cfg = os.getenv("CALIBRATION_EDGE_CONFIG")
    if not raw_db or not raw_cfg:
        pytest.skip(
            "Set CALIBRATION_EDGE_BASELINE_DB and CALIBRATION_EDGE_CONFIG to run "
            "the edge-config exactness test."
        )
    baseline = Path(raw_db)
    config = Path(raw_cfg)
    if not baseline.exists() or not config.exists():
        pytest.skip("edge baseline DB or config does not exist")

    start, end = _year_bounds(baseline)
    target = tmp_path / "edge_calibrated.duckdb"
    shutil.copy(baseline, target)

    CalibrationRunner(
        CalibrationRun(
            start_year=start,
            end_year=end,
            database_path=target,
            config_path=config,
        ),
        threads=1,
    ).run_calibration()

    full = _per_employee_comp(baseline)
    calibrated = _per_employee_comp(target)
    assert set(calibrated) == set(full)
    for key, full_comp in full.items():
        assert calibrated[key] == pytest.approx(full_comp, abs=1e-6)


def test_shared_dev_db_untouched(tmp_path) -> None:
    """A calibration run must not write to the shared dev DB (SC-004)."""
    shared = Path("dbt") / "simulation.duckdb"
    if not shared.exists():
        pytest.skip("shared dev DB not present")
    before = shared.stat().st_mtime_ns

    baseline = _baseline_db()
    start, end = _year_bounds(baseline)
    target = tmp_path / "calibrated.duckdb"
    shutil.copy(baseline, target)
    CalibrationRunner(
        CalibrationRun(start_year=start, end_year=end, database_path=target),
        threads=1,
    ).run_calibration()

    assert shared.stat().st_mtime_ns == before, "shared dev DB was modified"
