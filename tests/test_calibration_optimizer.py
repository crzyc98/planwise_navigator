"""Fast unit tests for the auto-calibration secant search (Feature 105).

The CalibrationRunner is replaced with a synthetic linear growth response so
no dbt build runs; the tests assert the search converges on the target
avg-comp growth and that workforce growth is set (not searched).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

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


def test_mean_on_target_does_not_converge_when_annual_years_miss(tmp_path) -> None:
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.035,
        tolerance_pct=0.1,
        max_iterations=1,
    )
    optimizer = _make_optimizer(tmp_path, settings)

    def annual_mismatch(_params: CalibrationParameterSet):
        return [
            PerYearCompensationResult(
                simulation_year=2025, avg_compensation=90000.0, headcount=100
            ),
            PerYearCompensationResult(
                simulation_year=2026,
                avg_compensation=93000.0,
                yoy_growth_pct=2.5,
                headcount=103,
            ),
            PerYearCompensationResult(
                simulation_year=2027,
                avg_compensation=96000.0,
                yoy_growth_pct=4.5,
                headcount=106,
            ),
        ]

    optimizer._runner.run_calibration = lambda: annual_mismatch(  # type: ignore[assignment]
        optimizer._runner.run.params
    )

    outcome = optimizer.optimize()

    assert outcome.achieved_comp_growth_pct == pytest.approx(3.5)
    assert outcome.max_abs_error_pct == pytest.approx(1.0)
    assert not outcome.converged
    assert outcome.objective == "max_annual_error"


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
        lever_fallback=True,
    )
    optimizer = _make_optimizer(tmp_path, settings)
    _wire_scaled_response(optimizer)

    outcome = optimizer.optimize()

    assert outcome.converged
    assert outcome.best_scale == pytest.approx(1.2)
    # Levers moved above their anchors only in the fallback stage.
    assert (outcome.best_params.cola_rate + outcome.best_params.merit_budget) > 0.055
    assert "COLA/merit were adjusted" in outcome.reason
    assert outcome.status == "converged"


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


@pytest.mark.parametrize(
    ("response", "budget", "expected", "reason"),
    [
        (lambda s: (2 * s, 2 * s), 12, "converged", None),
        (lambda s: (2 * s - 1, 2 * s + 1), 12, "infeasible", "spread"),
        (lambda s: (s - 5, s - 4), 12, "infeasible", "maximum scale bound"),
        (lambda s: (s + 5, s + 6), 12, "infeasible", "minimum scale bound"),
        (lambda s: (2 - s, 3 - s), 12, "not_converged", "monotonicity"),
        (lambda s: (2 * s, 10 - s), 12, "not_converged", "monotonicity"),
        (lambda s: (2 * s, 2 * s), 1, "not_converged", "budget exhausted"),
    ],
)
def test_minimax_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: Callable[[float], tuple[float, float]],
    budget: int,
    expected: str,
    reason: str | None,
) -> None:
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.035,
        search_mode="new_hire_scale",
        base_job_level_compensation=_BASE_RANGES,
        max_iterations=budget,
        tolerance_pct=0.01,
    )
    assert settings.lever_fallback is False
    optimizer = _make_optimizer(tmp_path, settings)

    def evaluate(params: CalibrationParameterSet) -> list[PerYearCompensationResult]:
        optimizer._evals += 1
        assert params.job_level_compensation is not None
        scale = params.job_level_compensation[0]["min_compensation"] / 50000
        return [
            PerYearCompensationResult(
                simulation_year=year,
                avg_compensation=100,
                headcount=10,
                yoy_growth_pct=growth,
            )
            for year, growth in zip((2025, 2026, 2027), (999, *response(scale)))
        ]

    monkeypatch.setattr(optimizer, "_evaluate", evaluate)
    outcome = optimizer.optimize()
    assert outcome.status == expected
    assert outcome.converged == (expected == "converged")
    assert len(outcome.iterations) <= budget
    assert outcome.max_abs_error_pct == min(
        i.max_abs_error_pct for i in outcome.iterations
    )
    assert {(i.cola_rate, i.merit_budget) for i in outcome.iterations} == {
        (0.02, 0.035)
    }
    if reason:
        assert reason in outcome.reason
    if expected == "infeasible":
        assert "2026:" in outcome.reason and "2027:" in outcome.reason
        assert "worst-year error" in outcome.reason
    if reason == "spread":
        assert outcome.best_scale == pytest.approx(1.75)
        assert outcome.max_abs_error_pct == pytest.approx(1)


@pytest.mark.parametrize(
    "budget,upper,converged",
    [(8, 0.08, True), (12, 0.02, False), (1, 0.08, False), (2, 0.08, False)],
)
def test_two_dial_linear_search(
    tmp_path, monkeypatch, budget, upper, converged
) -> None:
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.04,
        search_mode="new_hire_scale",
        base_job_level_compensation=_BASE_RANGES,
        solve_salary_growth=True,
        salary_growth_max=upper,
        tolerance_pct=0.001,
        max_iterations=budget,
    )
    optimizer = _make_optimizer(tmp_path, settings)

    def evaluate(params: CalibrationParameterSet) -> list[PerYearCompensationResult]:
        optimizer._evals += 1
        scale = params.job_level_compensation[0]["min_compensation"] / 50000
        rate = params.new_hire_salary_growth_rate
        assert settings.scale_min <= scale <= settings.scale_max
        assert 0 <= rate <= upper
        return [
            PerYearCompensationResult(
                simulation_year=2025 + year,
                avg_compensation=100,
                headcount=10,
                yoy_growth_pct=4 + 2 * (scale - 1.2) + year * 100 * (rate - 0.04),
            )
            for year in range(3)
        ]

    monkeypatch.setattr(optimizer, "_evaluate", evaluate)
    outcome = optimizer.optimize()
    assert outcome.converged is converged
    assert len(outcome.iterations) <= budget
    assert outcome.max_abs_error_pct == min(
        i.max_abs_error_pct for i in outcome.iterations
    )
    assert (
        outcome.best_params.new_hire_salary_growth_rate
        == outcome.best_salary_growth_rate
    )
    if converged:
        assert outcome.best_salary_growth_rate == pytest.approx(0.04)
        assert outcome.best_scale == pytest.approx(1.2)
    else:
        assert outcome.status == ("not_converged" if budget <= 2 else "best_achievable")
        if budget <= 2:
            assert "budget exhausted" in outcome.reason
        assert "2026:" in outcome.reason


@pytest.mark.parametrize(
    "updates",
    [
        {"search_mode": "levers"},
        {"salary_growth_min": 0.08},
        {"salary_growth_min": -0.01},
        {"salary_growth_max": 0.26},
    ],
)
def test_two_dial_settings_validation(updates) -> None:
    values = dict(
        target_workforce_growth=0.03,
        target_comp_growth=0.04,
        search_mode="new_hire_scale",
        base_job_level_compensation=_BASE_RANGES,
        solve_salary_growth=True,
    )
    with pytest.raises(ValueError):
        AutoCalibrationSettings(**(values | updates))


@pytest.mark.parametrize(
    "param_rate,config_rate,expected",
    [
        (None, 0.03, 0.03),
        (0.05, 0.03, 0.05),
        (0.2, 0.03, 0.08),
        (0.0, 0.03, 0.0),
    ],
)
def test_initial_salary_growth(tmp_path, param_rate, config_rate, expected) -> None:
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.04,
        search_mode="new_hire_scale",
        base_job_level_compensation=_BASE_RANGES,
        solve_salary_growth=True,
    )
    optimizer = _make_optimizer(tmp_path, settings)
    optimizer.run.params.new_hire_salary_growth_rate = param_rate
    optimizer._runner._config.new_hire["salary_growth_rate"] = config_rate
    assert optimizer._initial_dials()[1] == expected


@pytest.mark.parametrize("collapse_after_rejections", [False, True])
@pytest.mark.parametrize("growths", [(2.0, 2.0), (4.3, 3.7)])
def test_two_dial_flat_response_status(
    tmp_path, monkeypatch, collapse_after_rejections, growths
) -> None:
    """A stalled search is best achievable only when the mean is on target."""
    settings = AutoCalibrationSettings(
        target_workforce_growth=0.03,
        target_comp_growth=0.04,
        search_mode="new_hire_scale",
        base_job_level_compensation=_BASE_RANGES,
        solve_salary_growth=True,
        initial_scale=3,
        max_iterations=25,
        salary_growth_min=0.079,
        salary_growth_max=0.08,
    )
    optimizer = _make_optimizer(tmp_path, settings)
    optimizer.run.params.new_hire_salary_growth_rate = 0.08

    def evaluate(params: CalibrationParameterSet) -> list[PerYearCompensationResult]:
        optimizer._evals += 1
        assert 0.079 <= params.new_hire_salary_growth_rate <= 0.08
        return [
            PerYearCompensationResult(
                simulation_year=year,
                avg_compensation=100,
                headcount=10,
                yoy_growth_pct=growth,
            )
            for year, growth in zip((2026, 2027), growths)
        ]

    monkeypatch.setattr(optimizer, "_evaluate", evaluate)
    if collapse_after_rejections:
        # Reuse a synthetic Jacobian so rejected steps fit within the budget.
        monkeypatch.setattr(
            optimizer, "_dial_jacobian", lambda x, errors, target: x.reshape(1, 2)
        )
        monkeypatch.setattr(
            optimizer, "_dial_step", lambda x, errors, jacobian, trust: trust.copy()
        )
    outcome = optimizer.optimize()
    assert not outcome.converged
    if growths == (2.0, 2.0):
        # A systematic 2pp shortfall is not noise: keep not_converged.
        assert outcome.status == "not_converged"
        assert "Trust region collapsed" in outcome.reason
    else:
        assert outcome.status == "best_achievable"
        assert outcome.message == (
            f"Best achievable fit after {len(outcome.iterations)} run(s): worst "
            "annual error 0.30pp (tolerance 0.05pp; horizon mean 4.00% vs target "
            "4.00%)."
        )
        assert outcome.reason == (
            "Further changes to new-hire pay level and growth did not reduce the "
            "worst-year error; the remaining miss is year-to-year simulation "
            "variation. Annual growth: 2026: 4.30%, 2027: 3.70%."
        )
    assert outcome.best_scale == 3
    assert outcome.best_salary_growth_rate == 0.08


@pytest.mark.parametrize("rate", [-0.01, 0.251])
def test_salary_growth_parameter_validation(rate) -> None:
    with pytest.raises(ValueError):
        CalibrationParameterSet(new_hire_salary_growth_rate=rate)
