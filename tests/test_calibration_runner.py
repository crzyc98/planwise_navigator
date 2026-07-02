"""Fast unit tests for the CalibrationRunner plumbing (Feature 105).

Covers year-range validation, parameter validation, first-year null growth,
isolated-DB default resolution, and the fail-fast prerequisite guard. These
tests do NOT run dbt -- they exercise the pure-Python logic in isolation.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.calibration_runner import (
    DC_PREREQUISITE_TABLES,
    CalibrationParameterSet,
    CalibrationRun,
    CalibrationRunner,
    PerYearCompensationResult,
    resolve_calibration_database,
    verify_dc_prerequisites,
)
from planalign_orchestrator.exceptions import ConfigurationError

pytestmark = [pytest.mark.fast]


# -- year range / param validation ---------------------------------------
def test_year_range_must_be_ordered() -> None:
    with pytest.raises(ValueError):
        CalibrationRun(start_year=2029, end_year=2025)


def test_valid_single_year_range() -> None:
    run = CalibrationRun(start_year=2025, end_year=2025)
    assert run.start_year == run.end_year == 2025


def test_negative_cola_rejected() -> None:
    with pytest.raises(ValueError):
        CalibrationParameterSet(cola_rate=-0.01)


def test_age_distribution_must_sum_positive() -> None:
    with pytest.raises(ValueError):
        CalibrationParameterSet(
            new_hire_age_distribution=[
                {"age": 25, "weight": 0.0},
                {"age": 35, "weight": 0.0},
            ]
        )


def test_age_distribution_rejects_negative_weight() -> None:
    with pytest.raises(ValueError):
        CalibrationParameterSet(
            new_hire_age_distribution=[
                {"age": 25, "weight": -0.5},
                {"age": 35, "weight": 1.0},
            ]
        )


def test_age_distribution_rejects_missing_keys() -> None:
    with pytest.raises(ValueError):
        CalibrationParameterSet(new_hire_age_distribution=[{"age": 25}])


def test_age_distribution_rejects_implausible_age() -> None:
    with pytest.raises(ValueError):
        CalibrationParameterSet(new_hire_age_distribution=[{"age": 5, "weight": 1.0}])


def test_valid_age_distribution_accepted() -> None:
    params = CalibrationParameterSet(
        new_hire_age_distribution=[
            {"age": 25, "weight": 0.4},
            {"age": 35, "weight": 0.6},
        ]
    )
    assert len(params.new_hire_age_distribution) == 2


def test_workforce_growth_rate_bounds() -> None:
    assert (
        CalibrationParameterSet(workforce_growth_rate=0.03).workforce_growth_rate
        == 0.03
    )
    with pytest.raises(ValueError):
        CalibrationParameterSet(workforce_growth_rate=1.5)


# -- first-year null growth ----------------------------------------------
def test_first_year_growth_and_delta_are_null() -> None:
    row = CalibrationRunner._assemble_row(
        2025,
        {"avg_compensation": 92000.0, "yoy_growth_pct": None},
        {"headcount": 100, "new_hire_avg": 80000.0, "existing_avg": 95000.0},
        target=0.035,
    )
    assert row.yoy_growth_pct is None
    assert row.growth_delta_pct is None
    assert row.new_hire_gap == pytest.approx(-15000.0)


def test_delta_computed_on_percentage_scale() -> None:
    # target 0.035 (decimal) -> 3.5%; yoy 3.6% -> delta +0.1
    row = CalibrationRunner._assemble_row(
        2026,
        {"avg_compensation": 95000.0, "yoy_growth_pct": 3.6},
        {"headcount": 105, "new_hire_avg": 82000.0, "existing_avg": 96000.0},
        target=0.035,
    )
    assert row.target_growth_pct == pytest.approx(3.5)
    assert row.growth_delta_pct == pytest.approx(0.1, abs=1e-6)
    assert isinstance(row, PerYearCompensationResult)


# -- isolated DB default --------------------------------------------------
def test_isolated_db_default_seeds_from_shared(tmp_path, monkeypatch) -> None:
    # With a built shared dev DB present, the default copies it to an isolated
    # calibration DB (never returns the shared path, never mutates it).
    monkeypatch.chdir(tmp_path)
    shared = Path("dbt") / "simulation.duckdb"
    shared.parent.mkdir(parents=True, exist_ok=True)
    shared.write_bytes(b"seed-db-contents")

    resolved = resolve_calibration_database(None)

    assert resolved != shared
    assert "calibration" in str(resolved)
    assert resolved.exists() and resolved.read_bytes() == b"seed-db-contents"
    assert shared.read_bytes() == b"seed-db-contents"  # source untouched


def test_isolated_db_default_raises_without_source(tmp_path, monkeypatch) -> None:
    # No shared dev DB to seed from -> fail fast with actionable guidance.
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigurationError):
        resolve_calibration_database(None)


def test_explicit_db_is_respected() -> None:
    explicit = Path("/tmp/cal/iso.duckdb")
    assert resolve_calibration_database(explicit) == explicit


# -- prerequisite guard ---------------------------------------------------
def test_guard_raises_when_db_missing(tmp_path) -> None:
    with pytest.raises(ConfigurationError):
        verify_dc_prerequisites(tmp_path / "nope.duckdb")


def test_guard_raises_when_dc_tables_missing(tmp_path) -> None:
    db = tmp_path / "empty.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE TABLE some_other_table (x INTEGER)")
    conn.close()
    with pytest.raises(ConfigurationError) as exc:
        verify_dc_prerequisites(db)
    # message should name at least one missing prerequisite
    assert any(t in str(exc.value) for t in DC_PREREQUISITE_TABLES)


def test_guard_passes_when_all_dc_tables_present(tmp_path) -> None:
    db = tmp_path / "ok.duckdb"
    conn = duckdb.connect(str(db))
    for table in DC_PREREQUISITE_TABLES:
        conn.execute(f"CREATE TABLE {table} (x INTEGER)")
    conn.close()
    verify_dc_prerequisites(db)  # must not raise


# -- interactive re-tune param logic (US2) --------------------------------
def _runner_with_default_config(tmp_path) -> CalibrationRunner:
    # Explicit tmp DB path (no isolated-dir creation) + the repo's default
    # config. __init__ builds a DbtRunner but runs no dbt, so this stays fast.
    run = CalibrationRun(
        start_year=2025, end_year=2026, database_path=tmp_path / "cal.duckdb"
    )
    return CalibrationRunner(run, threads=1)


def test_retune_overrides_cola_and_merit_only(tmp_path) -> None:
    runner = _runner_with_default_config(tmp_path)
    baseline_growth = runner._config.simulation.target_growth_rate

    runner._apply_param_overrides(
        CalibrationParameterSet(
            cola_rate=0.05, merit_budget=0.06, target_growth_pct=0.04
        )
    )

    assert runner._config.compensation.cola_rate == 0.05
    assert runner._config.compensation.merit_budget == 0.06
    # CRITICAL: the compensation-growth target must NOT alter the workforce
    # growth target that sizes E077 hiring (this was the exactness bug).
    assert runner._config.simulation.target_growth_rate == baseline_growth


def test_retune_leaves_unset_params_at_config_default(tmp_path) -> None:
    runner = _runner_with_default_config(tmp_path)
    default_cola = runner._config.compensation.cola_rate

    # Only merit provided -> cola stays at the config default.
    runner._apply_param_overrides(CalibrationParameterSet(merit_budget=0.07))

    assert runner._config.compensation.merit_budget == 0.07
    assert runner._config.compensation.cola_rate == default_cola


# -- Match Census job-level ranges flow into the dbt var (Feature 105) -----
def test_job_level_compensation_injected_into_dbt_vars(tmp_path) -> None:
    from types import SimpleNamespace

    runner = _runner_with_default_config(tmp_path)
    ranges = [
        {"level": 1, "min_compensation": 60000, "max_compensation": 90000},
        {"level": 5, "min_compensation": 400000, "max_compensation": 800000},
    ]
    runner.run = runner.run.model_copy(
        update={"params": CalibrationParameterSet(job_level_compensation=ranges)}
    )

    captured = {}

    def _fake_exec(command, **kwargs):
        captured.update(kwargs.get("dbt_vars") or {})
        return SimpleNamespace(success=True, return_code=0)

    runner._runner.execute_command = _fake_exec  # type: ignore[assignment]
    runner._build_year(2025)

    assert captured.get("job_level_compensation") == ranges


# -- new-hire age distribution flows into the dbt var ----------------------
def test_age_distribution_injected_into_dbt_vars(tmp_path) -> None:
    from types import SimpleNamespace

    runner = _runner_with_default_config(tmp_path)
    dist = [{"age": 25, "weight": 0.4}, {"age": 40, "weight": 0.6}]
    runner.run = runner.run.model_copy(
        update={"params": CalibrationParameterSet(new_hire_age_distribution=dist)}
    )

    captured = {}

    def _fake_exec(command, **kwargs):
        captured.update(kwargs.get("dbt_vars") or {})
        return SimpleNamespace(success=True, return_code=0)

    runner._runner.execute_command = _fake_exec  # type: ignore[assignment]
    runner._build_year(2025)

    assert captured.get("new_hire_age_distribution") == dist


# -- workforce growth is a deliberate, explicit headcount lever ------------
def test_workforce_growth_rate_applies_to_simulation_config(tmp_path) -> None:
    runner = _runner_with_default_config(tmp_path)
    baseline_growth = runner._config.simulation.target_growth_rate

    # target_growth_pct alone must NOT touch it...
    runner._apply_param_overrides(CalibrationParameterSet(target_growth_pct=0.04))
    assert runner._config.simulation.target_growth_rate == baseline_growth

    # ...but the explicit workforce_growth_rate lever must.
    runner._apply_param_overrides(CalibrationParameterSet(workforce_growth_rate=0.05))
    assert runner._config.simulation.target_growth_rate == 0.05
