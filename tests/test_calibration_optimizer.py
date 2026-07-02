"""Fast unit tests for the auto-calibration secant search (Feature 105).

The CalibrationRunner is replaced with a synthetic linear growth response so
no dbt build runs; the tests assert the search converges on the target
avg-comp growth and that workforce growth is set (not searched).
"""

from __future__ import annotations

import pytest

from planalign_orchestrator.calibration_optimizer import (
    AutoCalibrationSettings,
    AutoCalibrator,
)
from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
    PerYearCompensationResult,
)

pytestmark = [pytest.mark.fast]


def _make_optimizer(tmp_path, settings: AutoCalibrationSettings) -> AutoCalibrator:
    run = CalibrationRun(
        start_year=2025, end_year=2027, database_path=tmp_path / "cal.duckdb"
    )
    return AutoCalibrator(run, settings, threads=1)


def _wire_synthetic_response(optimizer: AutoCalibrator, slope: float = 90.0) -> list:
    """Replace dbt evaluation with growth ≈ slope*(cola+merit) + 0.4pp drag."""
    calls: list = []

    def response(params: CalibrationParameterSet):
        growth = slope * (params.cola_rate + params.merit_budget) + 0.4
        calls.append((params.cola_rate, params.merit_budget))
        return [
            PerYearCompensationResult(
                simulation_year=2025, avg_compensation=90000.0, headcount=100
            ),
            PerYearCompensationResult(
                simulation_year=2026,
                avg_compensation=93000.0,
                yoy_growth_pct=growth,
                headcount=103,
            ),
            PerYearCompensationResult(
                simulation_year=2027,
                avg_compensation=96000.0,
                yoy_growth_pct=growth,
                headcount=106,
            ),
        ]

    optimizer._runner.run_calibration = lambda: response(  # type: ignore[assignment]
        optimizer._runner.run.params
    )

    def rerun(params: CalibrationParameterSet):
        optimizer._runner.run = optimizer._runner.run.model_copy(
            update={"params": params}
        )
        return response(params)

    optimizer._runner.rerun_with_params = rerun  # type: ignore[assignment]
    return calls


def test_optimizer_converges_on_target(tmp_path) -> None:
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.035,
        tolerance_pct=0.05,
        max_iterations=10,
    )
    optimizer = _make_optimizer(tmp_path, settings)
    calls = _wire_synthetic_response(optimizer)

    outcome = optimizer.optimize()

    assert outcome.converged
    assert outcome.achieved_comp_growth_pct == pytest.approx(3.5, abs=0.05)
    # A linear response should converge in very few evaluations.
    assert len(calls) <= 4
    # Workforce growth was SET, not searched.
    assert outcome.best_params.workforce_growth_rate == 0.03
    # The delta-column target follows the comp target.
    assert outcome.best_params.target_growth_pct == 0.035


def test_optimizer_reports_best_when_not_converged(tmp_path) -> None:
    # Impossibly tight tolerance with 1 iteration -> not converged, but the
    # best attempt is still reported with a clear message.
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.035,
        tolerance_pct=0.001,
        max_iterations=1,
    )
    optimizer = _make_optimizer(tmp_path, settings)
    _wire_synthetic_response(optimizer)

    outcome = optimizer.optimize()

    assert not outcome.converged
    assert "Stopped after 1 run(s)" in outcome.message
    assert len(outcome.iterations) == 1
    assert outcome.results  # best run's per-year results still returned


def test_optimizer_adjust_cola_only_keeps_merit_fixed(tmp_path) -> None:
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.05,
        tolerance_pct=0.05,
        max_iterations=10,
        adjust="cola",
    )
    optimizer = _make_optimizer(tmp_path, settings)
    calls = _wire_synthetic_response(optimizer)

    outcome = optimizer.optimize()

    assert outcome.converged
    merits = {round(m, 6) for _, m in calls}
    assert len(merits) == 1  # merit never moved


_BASE_RANGES = [
    {"level": 1, "name": "Staff", "min_compensation": 50000, "max_compensation": 80000},
    {
        "level": 2,
        "name": "Manager",
        "min_compensation": 80000,
        "max_compensation": 120000,
    },
]


def _wire_scaled_response(optimizer: AutoCalibrator, scale_slope: float = 6.0) -> list:
    """Growth ≈ 60*(cola+merit) + scale_slope*(scale-1) + 0.4pp.

    The scale is inferred from the level-1 min so the fake reacts to the
    ranges the optimizer actually injects.
    """
    calls: list = []

    def response(params: CalibrationParameterSet):
        scale = 1.0
        if params.job_level_compensation:
            scale = params.job_level_compensation[0]["min_compensation"] / 50000
        growth = (
            60 * (params.cola_rate + params.merit_budget)
            + scale_slope * (scale - 1)
            + 0.4
        )
        calls.append((params.cola_rate, params.merit_budget, scale))
        return [
            PerYearCompensationResult(
                simulation_year=2025, avg_compensation=90000.0, headcount=100
            ),
            PerYearCompensationResult(
                simulation_year=2026,
                avg_compensation=93000.0,
                yoy_growth_pct=growth,
                headcount=103,
            ),
        ]

    optimizer._runner.run_calibration = lambda: response(  # type: ignore[assignment]
        optimizer._runner.run.params
    )

    def rerun(params: CalibrationParameterSet):
        optimizer._runner.run = optimizer._runner.run.model_copy(
            update={"params": params}
        )
        return response(params)

    optimizer._runner.rerun_with_params = rerun  # type: ignore[assignment]
    return calls


def test_scale_mode_solves_ranges_and_keeps_levers_fixed(tmp_path) -> None:
    # Anchor levers (config defaults 2% COLA / 3.5% merit) give 60*0.055+0.4
    # = 3.7%; target 4.3% needs 6*(scale-1) = 0.6 -> scale ≈ 1.10.
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.043,
        tolerance_pct=0.05,
        max_iterations=10,
        search_mode="new_hire_scale",
        base_job_level_compensation=_BASE_RANGES,
        initial_scale=1.0,
    )
    optimizer = _make_optimizer(tmp_path, settings)
    calls = _wire_scaled_response(optimizer)

    outcome = optimizer.optimize()

    assert outcome.converged
    assert outcome.best_scale == pytest.approx(1.10, abs=0.03)
    # COLA/merit never moved off the anchors -- the whole point of the mode.
    levers = {(round(c, 6), round(m, 6)) for c, m, _ in calls}
    assert len(levers) == 1
    assert outcome.best_params.cola_rate == pytest.approx(0.02)
    assert outcome.best_params.merit_budget == pytest.approx(0.035)
    # The winning ranges are on the params so Apply-to-Workspace persists them.
    assert outcome.best_params.job_level_compensation[0]["min_compensation"] == round(
        50000 * outcome.best_scale
    )
    assert "new-hire range scale" in outcome.message


def test_scale_mode_falls_back_to_levers_at_bound(tmp_path) -> None:
    # Scale capped at 1.2 contributes at most 6*0.2 = 1.2pp -> growth 4.9%;
    # target 6.0% forces the fallback to raise COLA/merit for the rest.
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.06,
        tolerance_pct=0.05,
        max_iterations=15,
        search_mode="new_hire_scale",
        base_job_level_compensation=_BASE_RANGES,
        initial_scale=1.0,
        scale_max=1.2,
    )
    optimizer = _make_optimizer(tmp_path, settings)
    _wire_scaled_response(optimizer)

    outcome = optimizer.optimize()

    assert outcome.converged
    assert outcome.best_scale == pytest.approx(1.2)
    # Levers moved above their anchors only in the fallback stage.
    assert (outcome.best_params.cola_rate + outcome.best_params.merit_budget) > 0.055
    assert "hit its bound" in outcome.message


def test_scale_mode_requires_base_ranges() -> None:
    with pytest.raises(ValueError, match="base_job_level_compensation"):
        AutoCalibrationSettings(
            target_workforce_growth=0.03,
            target_comp_growth=0.04,
            search_mode="new_hire_scale",
        )


def test_single_year_range_raises_clear_error(tmp_path) -> None:
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03, target_comp_growth=0.035
    )
    run = CalibrationRun(
        start_year=2025, end_year=2025, database_path=tmp_path / "cal.duckdb"
    )
    optimizer = AutoCalibrator(run, settings, threads=1)
    optimizer._runner.run_calibration = lambda: [  # type: ignore[assignment]
        PerYearCompensationResult(
            simulation_year=2025, avg_compensation=90000.0, headcount=100
        )
    ]

    with pytest.raises(ValueError, match="two-year range"):
        optimizer.optimize()
