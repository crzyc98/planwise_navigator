#!/usr/bin/env python3
"""Auto-calibration: solve for the comp config that hits growth targets.

The analyst sets two targets:

* **Workforce (population) growth** -- set directly on
  ``simulation.target_growth_rate``; the E077 deterministic solver hits it
  exactly, so it needs no searching.
* **Average-compensation growth** -- searched. Each candidate is evaluated
  with a fast comp-only :class:`CalibrationRunner` build (exact vs. a full
  simulation), and a bracketed minimax search adjusts the new-hire scale to minimize the
  maximum absolute annual error. Convergence requires every post-baseline year
  to be within tolerance of the target.

Two search modes:

* ``levers`` -- new-hire comp ranges stay fixed; COLA/merit are searched.
* ``new_hire_scale`` -- COLA/merit stay where the analyst set them (they are
  policy); the census scale on the per-level new-hire comp ranges is searched
  so hiring dilution doesn't have to be papered over with outsized raises.
  Only if the scale clamps at its bounds and still misses does an optional
  fallback nudge COLA/merit to close the residual -- and says so.

Scale search balances the highest and lowest annual errors within a bracket.
The optional lever search retains its secant updates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Tuple

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import linprog

from pydantic import BaseModel, ConfigDict, Field, model_validator

from planalign_orchestrator.calibration_solver import (
    Candidate,
    SolverLimits,
    SolverOutcome,
    best_limit_message,
    horizon_cagr_error,
    solve_horizon,
)
from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
    CalibrationRunner,
    GrowthMetric,
    JobLevelRange,
    PerYearCompensationResult,
)

logger = logging.getLogger(__name__)

# Raise levers are clamped to a sane band during the search.
_LEVER_MIN = 0.0
_LEVER_MAX = 0.20
# First-step sensitivity guesses (the secant self-corrects after two points).
_LEVER_SENSITIVITY_PP = 100.0  # pp of growth per 1.0 (decimal) lever shift
# Per-year growth may dip this much as scale rises (range rounding noise)
# before the search reports the monotonicity assumption as violated.
_MONOTONE_SLACK_PP = 0.01
# Worst-year pp one pp of horizon-mean overrun costs in the two-dial objective.
_COMPOUND_PENALTY = 10.0
# A proposed two-dial step smaller than this in both dials cannot change the
# result: real searches had stopped improving by the time steps got this small.
_PLATEAU_STEP = np.array([0.001, 0.0002])
# Raises run this far above the growth target: leavers and cheaper hires dilute
# them, so a budget equal to the target would leave growth short.
_RAISE_MARGIN_PP = 1.0
# Most a single year's growth moved when only the seed changed (#1081, measured
# on development censuses). A smaller miss can't be told apart from seed noise.
_SEED_VARIATION_PP = 0.26


class AutoCalibrationSettings(BaseModel):
    """Search targets and knobs for one auto-calibration."""

    # Decimal rates, e.g. 0.03 = 3%/yr.
    target_workforce_growth: float = Field(..., ge=-1.0, le=1.0)
    target_comp_growth: float = Field(..., ge=-1.0, le=1.0)
    # Per-year convergence tolerance, in percentage points.
    tolerance_pct: float = Field(default=0.05, gt=0, le=5.0)
    # Total evaluation budget across all stages.
    max_iterations: int = Field(default=8, ge=1, le=25)
    # Which raise levers absorb a lever-stage shift.
    adjust: Literal["cola", "merit", "both"] = "both"
    # What "average pay" means for the target; see GrowthMetric.
    growth_metric: GrowthMetric = "active_average"

    # -- new_hire_scale mode ------------------------------------------------
    search_mode: Literal["levers", "new_hire_scale", "horizon"] = "levers"
    # UNSCALED (1.0x) per-level ranges, e.g. straight from census analysis.
    base_job_level_compensation: Optional[List[JobLevelRange]] = None
    initial_scale: float = Field(default=1.0, gt=0, le=5.0)
    scale_min: float = Field(default=0.5, gt=0)
    scale_max: float = Field(default=3.0, le=5.0)
    # If the scale clamps at a bound and still misses, nudge COLA/merit to
    # close the residual (reported explicitly in the outcome message).
    lever_fallback: bool = False
    solve_salary_growth: bool = False
    salary_growth_min: float = Field(default=0.0, ge=0, le=0.25)
    salary_growth_max: float = Field(default=0.08, ge=0, le=0.25)
    # Two-dial search only: also hold horizon-mean growth within this many pp of
    # target, so one noisy year cannot pull the whole horizon off target.
    compound_band_pct: Optional[float] = Field(default=None, gt=0, le=5.0)
    # Two-dial search only: stop once the next step would be negligible,
    # instead of spending the remaining budget on identical candidates.
    stop_on_plateau: bool = False
    # Two-dial search only: set the raise budget from the target first, within
    # this limit of configured, then solve hiring pay. Moves merit; COLA stays.
    solve_raise_budget: bool = False
    raise_budget_limit_pct: float = Field(default=1.0, gt=0, le=5.0)

    # -- horizon mode: see specs/1114-calibration-search/spec.md -----------------
    raise_min: float = Field(default=0.01, ge=0, le=0.25)
    raise_max: float = Field(default=0.10, ge=0, le=0.25)
    hire_pay_ratio_min: float = Field(default=0.9, ge=0.5, le=1.5)
    hire_pay_ratio_max: float = Field(default=1.1, ge=0.5, le=1.5)
    cagr_tolerance_pct: float = Field(default=0.25, gt=0, le=5.0)
    annual_guardrail_pct: float = Field(default=0.5, gt=0, le=5.0)
    horizon_evaluations: int = Field(default=12, ge=4, le=25)
    seed_count: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def _validate_scale_mode(self) -> "AutoCalibrationSettings":
        if self.solve_salary_growth and self.search_mode != "new_hire_scale":
            raise ValueError("solve_salary_growth requires new_hire_scale search")
        if self.solve_raise_budget and not self.solve_salary_growth:
            raise ValueError("solve_raise_budget requires solve_salary_growth")
        if self.raise_min >= self.raise_max:
            raise ValueError("raise_min must be below raise_max")
        if self.hire_pay_ratio_min >= self.hire_pay_ratio_max:
            raise ValueError("hire_pay_ratio_min must be below hire_pay_ratio_max")
        if self.salary_growth_min >= self.salary_growth_max:
            raise ValueError("salary_growth_min must be < salary_growth_max")
        if self.scale_min >= self.scale_max:
            raise ValueError("scale_min must be < scale_max")
        if (
            self.search_mode == "new_hire_scale"
            and not self.base_job_level_compensation
        ):
            raise ValueError(
                "new_hire_scale search requires base_job_level_compensation "
                "(the unscaled per-level census ranges to scale)"
            )
        return self


class OptimizationIteration(BaseModel):
    """One evaluated candidate in the search."""

    iteration: int
    cola_rate: float
    merit_budget: float
    scale: Optional[float] = None
    salary_growth_rate: Optional[float] = None
    achieved_growth_pct: float
    error_pct: float
    max_abs_error_pct: float


class CostEstimateRow(BaseModel):
    """Pay and estimated employer cost for one year, before and after solving.

    Calibration skips the plan calculations, so employer cost is estimated: it
    stays the same share of pay as in the run calibration started from.
    """

    simulation_year: int
    current_total_pay: float
    solved_total_pay: float
    current_employer_cost: float
    estimated_employer_cost: float


class HorizonLimitTest(BaseModel):
    """A rerun with one bound relaxed, showing whether that bound caused a miss."""

    lever: str
    bound: Literal["lower", "upper"]
    relaxed_to: float
    cagr_error_before_pct: float
    cagr_error_after_pct: float


class HorizonSeedResult(BaseModel):
    """How one seed of the best candidate grew."""

    seed: int
    cagr_pct: float
    annual_growth_pct: List[float]


class HorizonReport(BaseModel):
    """What the horizon search found, scored on the mean of its seeds."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    raises: float
    hire_pay_growth: float
    hire_pay_ratio: float
    cagr_pct: float
    cagr_error_pct: float
    annual_errors_pct: List[float]
    guardrail_misses: int
    stop_reason: Literal["on_target", "no_further_improvement", "budget_exhausted"]
    active_bounds: List[str]
    limit_tests: List[HorizonLimitTest]
    seeds: List[HorizonSeedResult]


class AutoCalibrationResult(BaseModel):
    """Outcome of the search: best params + the run that produced them."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    converged: bool
    status: Literal["converged", "best_achievable", "not_converged", "infeasible"]
    reason: Optional[str] = None
    message: str
    best_params: CalibrationParameterSet
    best_scale: Optional[float] = None
    best_salary_growth_rate: Optional[float] = None
    achieved_comp_growth_pct: float
    target_comp_growth_pct: float
    max_abs_error_pct: float
    objective: Literal["max_annual_error"] = "max_annual_error"
    growth_metric: GrowthMetric = "active_average"
    start_year: int
    end_year: int
    iterations: List[OptimizationIteration]
    results: List[PerYearCompensationResult]
    cost_estimate: List[CostEstimateRow] = Field(default_factory=list)
    # What the search was given, so a saved result can be read and rerun.
    settings: AutoCalibrationSettings
    starting_params: CalibrationParameterSet
    horizon: Optional[HorizonReport] = None


def _annual_objective(
    results: List[PerYearCompensationResult], target_pct: float
) -> Tuple[float, float, float]:
    """Return mean achieved growth, signed worst error, and max absolute error."""
    growths = [r.yoy_growth_pct for r in results if r.yoy_growth_pct is not None]
    if not growths:
        raise ValueError(
            "Auto-calibration needs at least a two-year range to measure "
            "year-over-year compensation growth"
        )
    errors = [growth - target_pct for growth in growths]
    worst = max(errors, key=abs)
    return sum(growths) / len(growths), worst, abs(worst)


def _compound_rows(
    jacobian: NDArray[np.float64], errors: NDArray[np.float64], band: float
) -> Tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Linear limits on horizon-mean error; a slack column prices any overrun."""
    slope, level = jacobian.mean(axis=0), float(errors.mean())
    rows = np.array([[*slope, 0.0, -1.0], [*-slope, 0.0, -1.0]])
    return rows, np.array([band - level, band + level])


def _clamp_lever(value: float) -> float:
    return min(max(value, _LEVER_MIN), _LEVER_MAX)


class _BestCandidate(NamedTuple):
    """The best-so-far evaluated candidate (tracked across every stage)."""

    abs_error: float
    params: CalibrationParameterSet
    achieved_pct: float
    results: List[PerYearCompensationResult]
    scale: Optional[float]
    objective: float


class _DialOutcome(NamedTuple):
    status: Literal["best_achievable", "not_converged"]
    reason: str


class _ScaleOutcome(NamedTuple):
    status: Literal["converged", "not_converged", "infeasible"]
    reason: Optional[str] = None
    bound: Optional[float] = None


class _ScalePoint(NamedTuple):
    scale: float
    errors: Dict[int, float]

    @property
    def h(self) -> float:
        return max(self.errors.values()) + min(self.errors.values())


def _monotone(points: List[_ScalePoint], candidate: _ScalePoint) -> bool:
    for point in points:
        if point.errors.keys() != candidate.errors.keys():
            return False
        for year, error in point.errors.items():
            delta = candidate.errors[year] - error
            if candidate.scale > point.scale and delta < -_MONOTONE_SLACK_PP:
                return False
            if candidate.scale < point.scale and delta > _MONOTONE_SLACK_PP:
                return False
    return True


def _growth_detail(point: _ScalePoint, target_pct: float) -> str:
    return ", ".join(
        f"{year}: {error + target_pct:.3f}%" for year, error in point.errors.items()
    )


def _bracket_step(lower: _ScalePoint, upper: _ScalePoint) -> float:
    width = upper.scale - lower.scale
    x = lower.scale - lower.h * width / (upper.h - lower.h)
    if not lower.scale + 0.1 * width <= x <= upper.scale - 0.1 * width:
        return (lower.scale + upper.scale) / 2
    return x


class AutoCalibrator:
    """Minimax scale search or secant lever search for avg-comp growth.

    Reuses one :class:`CalibrationRunner` (one isolated DB, one guard check);
    each iteration is a fast comp-only rebuild via ``rerun_with_params``.
    """

    def __init__(
        self,
        run: CalibrationRun,
        settings: AutoCalibrationSettings,
        *,
        threads: int = 1,
        verbose: bool = False,
    ) -> None:
        self.settings = settings
        # Workforce growth is deterministic (E077) -- set it once, exactly.
        params = run.params.model_copy(
            update={"workforce_growth_rate": settings.target_workforce_growth}
        )
        self.run = run.model_copy(
            update={"params": params, "growth_metric": settings.growth_metric}
        )
        self._starting_params = params
        self._runner = CalibrationRunner(self.run, threads=threads, verbose=verbose)
        # Weights for distributing a lever-stage shift across COLA/merit.
        self._weights = {
            "cola": (1.0, 0.0),
            "merit": (0.0, 1.0),
            "both": (0.5, 0.5),
        }[settings.adjust]
        self._evals = 0
        self._iterations: List[OptimizationIteration] = []
        self._best: Optional[_BestCandidate] = None
        self._last_errors: Dict[int, float] = {}
        self._raise_shift = 0.0
        self._base_levers: Tuple[float, float] = (0.0, 0.0)

    @property
    def database_path(self) -> Path:
        return self._runner.database_path

    def _require_best(self) -> _BestCandidate:
        """Narrow ``self._best`` to non-None.

        Safe by construction: every call site runs after at least one
        ``_try_candidate`` evaluation, which always sets ``self._best``.
        """
        assert self._best is not None, "no candidate evaluated yet"
        return self._best

    # -- public API ---------------------------------------------------------
    def optimize(self) -> AutoCalibrationResult:
        target_pct = self.settings.target_comp_growth * 100
        self._evals = 0
        self._iterations = []
        self._best = None

        if self.settings.search_mode == "horizon":
            return HorizonSearch(self, target_pct).run()

        if self.settings.solve_salary_growth:
            return self._optimize_two_dials(target_pct)

        if self.settings.search_mode == "new_hire_scale":
            return self._optimize_scale_mode(target_pct)

        converged = self._lever_stage(target_pct, scale=None)
        return self._finish(converged, self._summary(converged, target_pct), target_pct)

    def _dial_bounds(self) -> NDArray[np.float64]:
        s = self.settings
        return np.array(
            [[s.scale_min, s.scale_max], [s.salary_growth_min, s.salary_growth_max]]
        )

    def _initial_dials(self) -> NDArray[np.float64]:
        rate = self.run.params.new_hire_salary_growth_rate
        if rate is None:
            rate = float(self._runner._config.new_hire.get("salary_growth_rate", 0))
        bounds = self._dial_bounds()
        return np.clip([self.settings.initial_scale, rate], bounds[:, 0], bounds[:, 1])

    def _evaluate_dials(
        self, x: NDArray[np.float64], target_pct: float
    ) -> NDArray[np.float64]:
        cola, merit = self._base_levers
        params = self._candidate(cola, merit + self._raise_shift, 0.0, float(x[0]))
        params.new_hire_salary_growth_rate = float(x[1])
        self._try_candidate(params, target_pct, float(x[0]))
        years = sorted(self._last_errors)
        expected = list(range(self.run.start_year + 1, self.run.end_year + 1))
        if years != expected:
            raise ValueError(
                "Two-dial calibration requires growth for every post-baseline year"
            )
        return np.array([self._last_errors[year] for year in years])

    def _dial_jacobian(
        self, x: NDArray[np.float64], errors: NDArray[np.float64], target_pct: float
    ) -> Optional[NDArray[np.float64]]:
        columns = []
        bounds = self._dial_bounds()
        for axis, step in enumerate((0.1, 0.01)):
            if self._evals >= self.settings.max_iterations or self._dials_converged():
                return None
            probe = x.copy()
            direction = 1 if x[axis] + step <= bounds[axis, 1] else -1
            probe[axis] = np.clip(x[axis] + direction * step, *bounds[axis])
            if probe[axis] == x[axis]:
                probe[axis] = bounds[axis, 1]
            delta = probe[axis] - x[axis]
            columns.append((self._evaluate_dials(probe, target_pct) - errors) / delta)
        return np.column_stack(columns)

    def _dial_step(
        self,
        x: NDArray[np.float64],
        errors: NDArray[np.float64],
        jacobian: NDArray[np.float64],
        trust: NDArray[np.float64],
    ) -> Optional[NDArray[np.float64]]:
        bounds = self._dial_bounds() - x[:, None]
        lower = np.maximum(bounds[:, 0], -trust)
        upper = np.minimum(bounds[:, 1], trust)
        constraints = np.column_stack(
            (
                np.vstack((jacobian, -jacobian)),
                -np.ones(2 * len(errors)),
            )
        )
        limits = np.concatenate((-errors, errors))
        cost = [0.0, 0.0, 1.0]
        variable_bounds = [*zip(lower, upper), (0, None)]
        band = self.settings.compound_band_pct
        if band is not None:
            rows, row_limits = _compound_rows(jacobian, errors, band)
            constraints = np.vstack(
                (np.pad(constraints, ((0, 0), (0, 1))), rows),
            )
            limits = np.concatenate((limits, row_limits))
            cost.append(_COMPOUND_PENALTY)
            variable_bounds.append((0, None))
        solution = linprog(
            cost,
            A_ub=constraints,
            b_ub=limits,
            bounds=variable_bounds,
            method="highs",
        )
        if not solution.success:
            logger.warning("Two-dial minimax step failed: %s", solution.message)
            return None
        return np.asarray(solution.x[:2], dtype=float)

    def _dials_converged(self) -> bool:
        return self._require_best().abs_error <= self.settings.tolerance_pct

    def _objective(self, worst: float, mean_error: float) -> float:
        """Worst-year error, plus a charge for leaving the compound band."""
        band = self.settings.compound_band_pct
        if band is None:
            return worst
        return worst + _COMPOUND_PENALTY * max(0.0, abs(mean_error) - band)

    def _dial_objective(self, errors: NDArray[np.float64]) -> float:
        return self._objective(float(np.max(np.abs(errors))), float(errors.mean()))

    def _update_dial_jacobian(
        self,
        jacobian: NDArray[np.float64],
        step: NDArray[np.float64],
        errors: NDArray[np.float64],
        new_errors: NDArray[np.float64],
    ) -> Optional[NDArray[np.float64]]:
        """Accept an improving step with a Broyden update; otherwise recompute."""
        if self._dial_objective(new_errors) >= self._dial_objective(errors):
            return None
        residual = new_errors - errors - jacobian @ step
        return jacobian + np.outer(residual, step) / float(step @ step)

    def _search_dials(self, target_pct: float) -> _DialOutcome:
        x = self._initial_dials()
        errors = self._evaluate_dials(x, target_pct)
        trust = np.array([0.5, 0.02])
        jacobian = None
        while (
            self._evals < self.settings.max_iterations and not self._dials_converged()
        ):
            if jacobian is None:
                jacobian = self._dial_jacobian(x, errors, target_pct)
            if (
                jacobian is None
                or self._dials_converged()
                or self._evals >= self.settings.max_iterations
            ):
                break
            step = self._dial_step(x, errors, jacobian, trust)
            if step is None:
                return _DialOutcome(
                    "not_converged",
                    "Linearized minimax solver could not produce a step.",
                )
            if np.max(np.abs(step) / np.array([0.5, 0.02])) < 1e-5:
                return _DialOutcome(
                    "best_achievable",
                    "Trust region collapsed: no improving step within bounds.",
                )
            candidate = np.clip(x + step, *self._dial_bounds().T)
            step = candidate - x
            if self.settings.stop_on_plateau and np.all(np.abs(step) < _PLATEAU_STEP):
                return _DialOutcome(
                    "best_achievable",
                    "Stopped early: the next change would be negligible.",
                )
            new_errors = self._evaluate_dials(candidate, target_pct)
            jacobian = self._update_dial_jacobian(jacobian, step, errors, new_errors)
            if jacobian is None:
                trust *= 0.5
            else:
                x, errors = candidate, new_errors
            if trust[0] < 1e-4:
                return _DialOutcome(
                    "best_achievable", "Trust region collapsed without convergence."
                )
        return _DialOutcome(
            "best_achievable", "Evaluation budget exhausted before convergence."
        )

    def _target_raise_shift(self, target_pct: float) -> float:
        """Decimal merit change that puts the raise budget where the target needs it."""
        if not self.settings.solve_raise_budget:
            return 0.0
        cola, merit = self._base_levers
        total = (cola + merit) * 100
        limit = self.settings.raise_budget_limit_pct
        wanted = min(max(target_pct + _RAISE_MARGIN_PP, total - limit), total + limit)
        return max((wanted - total) / 100, -merit)

    def _raise_note(self, target_pct: float) -> str:
        """Say what moved, and when the limit stopped it short of the target's need."""
        if not self.settings.solve_raise_budget:
            return ""
        cola, merit = self._base_levers
        before = (cola + merit) * 100
        after = before + self._raise_shift * 100
        note = f" Raise budget moved from {before:.2f}% to {after:.2f}%."
        if abs(target_pct + _RAISE_MARGIN_PP - after) > 1e-9:
            note += f" It stopped at the {self.settings.raise_budget_limit_pct:.1f}pp limit."
        return note

    def _optimize_two_dials(self, target_pct: float) -> AutoCalibrationResult:
        # Each evaluation overwrites the runner's config, so read the levers once.
        self._base_levers = self._starting_levers()
        self._raise_shift = self._target_raise_shift(target_pct)
        outcome = self._search_dials(target_pct)
        converged = self._dials_converged()
        message = self._summary(converged, target_pct)
        reason = f"{outcome.reason} {self._best_growth_detail()}"
        status: Literal["converged", "best_achievable", "not_converged"] = (
            "converged" if converged else outcome.status
        )
        best = self._require_best()
        # A stalled search is only "best achievable" when the horizon mean is on
        # target and the residual is year-to-year swing; a systematic miss is not.
        if status == "best_achievable" and not self._mean_on_target(target_pct):
            status = "not_converged"
        if status == "best_achievable":
            message = (
                f"Best achievable fit after {self._evals} run(s): worst annual error "
                f"{best.abs_error:.2f}pp (tolerance {self.settings.tolerance_pct:.2f}pp; "
                f"horizon mean {best.achieved_pct:.2f}% vs target {target_pct:.2f}%)."
            )
            opening = (
                f"All {self._evals} run(s) were used with the horizon mean on target"
                if outcome.reason.startswith("Evaluation budget")
                else "Further changes to new-hire pay level and growth did not "
                "reduce the worst-year error"
            )
            reason = (
                f"{opening}; the remaining miss is year-to-year simulation "
                f"variation. Annual growth: {self._annual_growth_detail(2)}."
            )
        return self._finish(
            converged,
            message + self._raise_note(target_pct),
            target_pct,
            status=status,
            reason=None if converged else reason,
        )

    # -- scale-primary mode ---------------------------------------------------
    def _optimize_scale_mode(self, target_pct: float) -> AutoCalibrationResult:
        outcome = self._scale_stage(target_pct)
        converged = outcome.status == "converged"
        reason = outcome.reason
        if outcome.bound is not None and self.settings.lever_fallback:
            before = self._evals
            converged = self._lever_stage(target_pct, scale=outcome.bound)
            changed = any(
                (item.cola_rate, item.merit_budget) != self._starting_levers()
                for item in self._iterations[before:]
            )
            detail = (
                "COLA/merit were adjusted with explicit lever fallback enabled."
                if changed
                else "The evaluation budget ended before COLA/merit could be changed."
            )
            reason = f"{reason} {detail}"
            outcome = _ScaleOutcome(
                "converged" if converged else "not_converged", reason
            )
        message = self._summary(converged, target_pct)
        if converged:
            message += f" -- new-hire range scale {self._require_best().scale:.2f}x"
        return self._finish(converged, message, target_pct, outcome.status, reason)

    def _scale_stage(self, target_pct: float) -> _ScaleOutcome:
        """Expand from the initial scale, then solve max(error) + min(error)."""
        points: List[_ScalePoint] = []
        x = min(
            max(self.settings.initial_scale, self.settings.scale_min),
            self.settings.scale_max,
        )
        step = 0.25
        while self._evals < self.settings.max_iterations:
            cola, merit = self._starting_levers()
            self._try_candidate(self._candidate(cola, merit, 0.0, x), target_pct, x)
            point = _ScalePoint(x, self._last_errors)
            if not _monotone(points, point):
                return _ScaleOutcome(
                    "not_converged",
                    "Annual growth did not consistently increase with scale. "
                    "The monotonicity assumption failed; feasibility cannot be determined.",
                )
            points.append(point)
            if self._require_best().abs_error <= self.settings.tolerance_pct:
                return _ScaleOutcome("converged")
            lower = max(
                (p for p in points if p.h <= 0), key=lambda p: p.scale, default=None
            )
            upper = min(
                (p for p in points if p.h >= 0), key=lambda p: p.scale, default=None
            )
            outcome = self._scale_evidence(point, lower, upper)
            if outcome is not None:
                return outcome
            if lower is not None and upper is not None:
                x = _bracket_step(lower, upper)
            else:
                direction = -1 if point.h > 0 else 1
                x = min(
                    max(x + direction * step, self.settings.scale_min),
                    self.settings.scale_max,
                )
                step *= 2
        return _ScaleOutcome(
            "not_converged",
            "Evaluation budget exhausted before convergence "
            "or infeasibility could be established.",
        )

    def _scale_evidence(
        self,
        point: _ScalePoint,
        lower: Optional[_ScalePoint],
        upper: Optional[_ScalePoint],
    ) -> Optional[_ScaleOutcome]:
        bound = (point.scale == self.settings.scale_min and point.h > 0) or (
            point.scale == self.settings.scale_max and point.h < 0
        )
        if bound:
            name = "minimum" if point.h > 0 else "maximum"
            return _ScaleOutcome(
                "infeasible",
                f"The {name} scale bound ({point.scale:.3f}x) was evaluated; the balanced annual error remains {'positive' if point.h > 0 else 'negative'}. "
                f"Growth at that bound: {_growth_detail(point, self.settings.target_comp_growth * 100)}. "
                f"No scale within the allowed bounds meets every year's target. {self._best_growth_detail()}",
                point.scale,
            )
        if lower is None or upper is None:
            return None
        balanced = min((lower, upper), key=lambda p: abs(p.h))
        tight = (
            abs(balanced.h) <= self.settings.tolerance_pct
            or upper.scale - lower.scale < 1e-3
        )
        spread = (max(balanced.errors.values()) - min(balanced.errors.values())) / 2
        if tight and spread > self.settings.tolerance_pct:
            return _ScaleOutcome(
                "infeasible",
                "The minimax balance point is tightly located, but the annual growth "
                "spread is too wide for one scale to meet every year's tolerance. "
                + self._best_growth_detail(),
            )
        return None

    def _annual_growth_detail(self, decimals: int) -> str:
        return ", ".join(
            f"{row.simulation_year}: {row.yoy_growth_pct:.{decimals}f}%"
            for row in self._require_best().results
            if self.run.start_year < row.simulation_year <= self.run.end_year
            and row.yoy_growth_pct is not None
        )

    def _best_growth_detail(self) -> str:
        best = self._require_best()
        growths = self._annual_growth_detail(3)
        return (
            f"Best achievable evaluated worst-year error: {best.abs_error:.3f}pp; "
            f"annual growth: {growths}."
        )

    # -- lever stage ----------------------------------------------------------
    def _lever_stage(self, target_pct: float, scale: Optional[float]) -> bool:
        base_cola, base_merit = self._starting_levers()
        s = 0.0
        s_prev: Optional[float] = None
        f_prev: Optional[float] = None

        while self._evals < self.settings.max_iterations:
            params = self._candidate(base_cola, base_merit, s, scale)
            error = self._try_candidate(params, target_pct, scale=scale)
            if abs(error) <= self.settings.tolerance_pct:
                return True

            if s_prev is None or f_prev is None or abs(error - f_prev) < 1e-9:
                s_next = s - error / _LEVER_SENSITIVITY_PP
            else:
                s_next = s - error * (s - s_prev) / (error - f_prev)
                s_next = min(max(s_next, s - 0.05), s + 0.05)
            s_prev, f_prev = s, error
            s = s_next

        return False

    # -- shared internals -------------------------------------------------------
    def _starting_levers(self) -> Tuple[float, float]:
        cfg = self._runner._config.compensation
        cola = (
            self.run.params.cola_rate
            if self.run.params.cola_rate is not None
            else cfg.cola_rate
        )
        merit = (
            self.run.params.merit_budget
            if self.run.params.merit_budget is not None
            else cfg.merit_budget
        )
        return cola, merit

    def _candidate(
        self,
        base_cola: float,
        base_merit: float,
        shift: float,
        scale: Optional[float],
    ) -> CalibrationParameterSet:
        w_cola, w_merit = self._weights
        update: Dict[str, Any] = {
            "cola_rate": (
                base_cola if shift == 0 else _clamp_lever(base_cola + shift * w_cola)
            ),
            "merit_budget": (
                base_merit if shift == 0 else _clamp_lever(base_merit + shift * w_merit)
            ),
            "workforce_growth_rate": self.settings.target_workforce_growth,
            "target_growth_pct": self.settings.target_comp_growth,
        }
        if scale is not None:
            update["job_level_compensation"] = self._ranges_for_scale(scale)
        return self.run.params.model_copy(update=update)

    def _ranges_for_scale(self, scale: float) -> List[Dict[str, Any]]:
        scaled: List[Dict[str, Any]] = []
        for item in self.settings.base_job_level_compensation or []:
            row = dict(item)
            row["min_compensation"] = round(float(item["min_compensation"]) * scale)
            row["max_compensation"] = round(float(item["max_compensation"]) * scale)
            scaled.append(row)
        return scaled

    def _try_candidate(
        self,
        params: CalibrationParameterSet,
        target_pct: float,
        scale: Optional[float],
    ) -> float:
        """Evaluate one candidate: record the iteration, track the best."""
        results = self._evaluate(params)
        scored = [
            r
            for r in results
            if self.run.start_year < r.simulation_year <= self.run.end_year
        ]
        achieved, error, max_abs_error = _annual_objective(scored, target_pct)
        self._last_errors = {
            r.simulation_year: r.yoy_growth_pct - target_pct
            for r in scored
            if r.yoy_growth_pct is not None
        }
        self._iterations.append(
            OptimizationIteration(
                iteration=len(self._iterations) + 1,
                cola_rate=params.cola_rate or 0.0,
                merit_budget=params.merit_budget or 0.0,
                scale=scale,
                salary_growth_rate=params.new_hire_salary_growth_rate,
                achieved_growth_pct=achieved,
                error_pct=error,
                max_abs_error_pct=max_abs_error,
            )
        )
        objective = self._objective(max_abs_error, achieved - target_pct)
        if self._best is None or objective < self._best.objective:
            self._best = _BestCandidate(
                max_abs_error, params, achieved, results, scale, objective
            )
        return error

    def _evaluate(
        self, params: CalibrationParameterSet
    ) -> List[PerYearCompensationResult]:
        self._evals += 1
        logger.info(
            "Auto-calibration eval %d: cola=%.4f merit=%.4f level1_min_comp=%s",
            self._evals,
            params.cola_rate,
            params.merit_budget,
            (
                f"{params.job_level_compensation[0]['min_compensation']}"
                if params.job_level_compensation
                else "-"
            ),
        )
        if self._evals == 1:
            self._runner.run = self._runner.run.model_copy(update={"params": params})
            self._runner._apply_param_overrides(params)
            return self._runner.run_calibration()
        return self._runner.rerun_with_params(params)

    def _mean_on_target(self, target_pct: float) -> bool:
        """True when the worst miss is annual swing, not a systematic shortfall."""
        best = self._require_best()
        return abs(best.achieved_pct - target_pct) <= 0.5 * best.abs_error

    def _seed_note(self, target_pct: float) -> str:
        """Say when the miss is too small to separate from seed variation."""
        if (
            self._require_best().abs_error > _SEED_VARIATION_PP
            or not self._mean_on_target(target_pct)
        ):
            return ""
        return (
            f" In testing, changing only the seed moved a year by up to "
            f"{_SEED_VARIATION_PP:.2f}pp, so a miss this size may be seed "
            "variation that more searching won't remove."
        )

    def _summary(self, converged: bool, target_pct: float) -> str:
        best = self._require_best()
        if converged:
            return (
                f"Converged in {self._evals} run(s): every annual comp-growth "
                f"result is within {self.settings.tolerance_pct:.2f}pp of "
                f"{target_pct:.2f}% (max error {best.abs_error:.2f}pp)"
            )
        return (
            f"Stopped after {self._evals} run(s); best candidate has maximum "
            f"annual error {best.abs_error:.2f}pp vs tolerance "
            f"{self.settings.tolerance_pct:.2f}pp (horizon mean "
            f"{best.achieved_pct:.2f}% vs target {target_pct:.2f}%)"
        )

    def _cost_estimate(
        self, results: List[PerYearCompensationResult]
    ) -> List[CostEstimateRow]:
        rows = []
        for result in results:
            baseline = self._runner.baseline_costs.get(result.simulation_year)
            if baseline and baseline.pay and result.total_pay is not None:
                rows.append(
                    CostEstimateRow(
                        simulation_year=result.simulation_year,
                        current_total_pay=baseline.pay,
                        solved_total_pay=result.total_pay,
                        current_employer_cost=baseline.employer_cost,
                        estimated_employer_cost=baseline.employer_cost
                        * result.total_pay
                        / baseline.pay,
                    )
                )
        return rows

    def _finish(
        self,
        converged: bool,
        message: str,
        target_pct: float,
        status: Optional[
            Literal["converged", "best_achievable", "not_converged", "infeasible"]
        ] = None,
        reason: Optional[str] = None,
    ) -> AutoCalibrationResult:
        best = self._require_best()
        logger.info("Auto-calibration finished: %s", message)
        return AutoCalibrationResult(
            converged=converged,
            status=status or ("converged" if converged else "not_converged"),
            reason=(
                reason
                if converged
                else (reason or "Evaluation budget exhausted before convergence.")
                + self._seed_note(target_pct)
            ),
            message=message,
            best_params=best.params,
            best_scale=best.scale,
            best_salary_growth_rate=best.params.new_hire_salary_growth_rate,
            achieved_comp_growth_pct=best.achieved_pct,
            target_comp_growth_pct=target_pct,
            max_abs_error_pct=best.abs_error,
            growth_metric=self.settings.growth_metric,
            start_year=self.run.start_year,
            end_year=self.run.end_year,
            iterations=self._iterations,
            results=best.results,
            cost_estimate=self._cost_estimate(best.results),
            settings=self.settings,
            starting_params=self._starting_params,
        )


class HorizonSearch:
    """Runs the horizon solver on real evaluations, averaged across seeds."""

    def __init__(self, calibrator: AutoCalibrator, target_pct: float) -> None:
        self.calibrator = calibrator
        self.settings = calibrator.settings
        self.target_pct = target_pct
        self.base_seed = calibrator._runner._config.simulation.random_seed
        self.seeds = [self.base_seed + i for i in range(self.settings.seed_count)]
        self._by_levers: Dict[Tuple[float, ...], List[List[float]]] = {}
        self._results: Dict[Tuple[float, ...], List[PerYearCompensationResult]] = {}

    def _params(self, levers: NDArray[np.float64]) -> CalibrationParameterSet:
        run = self.calibrator.run.params
        config = self.calibrator._runner._config.compensation
        raises, hire_growth, ratio = (float(value) for value in levers)
        cola = min(run.cola_rate or config.cola_rate, raises)
        return run.model_copy(
            update={
                "cola_rate": cola,
                "merit_budget": raises - cola,
                "new_hire_salary_growth_rate": hire_growth,
                "hire_pay_ratio": ratio,
                "workforce_growth_rate": self.settings.target_workforce_growth,
                "target_growth_pct": self.settings.target_comp_growth,
            }
        )

    def _annual(self, results: List[PerYearCompensationResult]) -> List[float]:
        run = self.calibrator.run
        return [
            r.yoy_growth_pct
            for r in results
            if run.start_year < r.simulation_year <= run.end_year
            and r.yoy_growth_pct is not None
        ]

    def _evaluate(self, levers: NDArray[np.float64]) -> Candidate:
        params = self._params(levers)
        growth: List[List[float]] = []
        first: List[PerYearCompensationResult] = []
        for seed in self.seeds:
            results = self.calibrator._evaluate(
                params.model_copy(update={"random_seed": seed})
            )
            first = first or results
            growth.append(self._annual(results))
        key = tuple(float(value) for value in levers)
        self._by_levers[key], self._results[key] = growth, first
        mean = np.mean(growth, axis=0)
        candidate = Candidate(
            np.array(levers, dtype=float),
            mean - self.target_pct,
            horizon_cagr_error(mean, self.target_pct),
        )
        self._record(params, candidate)
        return candidate

    def _record(self, params: CalibrationParameterSet, candidate: Candidate) -> None:
        iterations = self.calibrator._iterations
        iterations.append(
            OptimizationIteration(
                iteration=len(iterations) + 1,
                cola_rate=params.cola_rate or 0.0,
                merit_budget=params.merit_budget or 0.0,
                salary_growth_rate=params.new_hire_salary_growth_rate,
                achieved_growth_pct=candidate.cagr_error + self.target_pct,
                error_pct=candidate.cagr_error,
                max_abs_error_pct=float(np.abs(candidate.errors).max()),
            )
        )

    def _start(self) -> NDArray[np.float64]:
        params, config = self.calibrator.run.params, self.calibrator._runner._config
        cola = params.cola_rate or config.compensation.cola_rate
        merit = params.merit_budget or config.compensation.merit_budget
        return np.array(
            [
                cola + merit,
                config.new_hire.get("salary_growth_rate", 0.0),
                config.new_hire.get("hire_pay_ratio") or 1.0,
            ]
        )

    def _limits(self) -> SolverLimits:
        s = self.settings
        return SolverLimits(
            np.array([s.raise_min, s.salary_growth_min, s.hire_pay_ratio_min]),
            np.array([s.raise_max, s.salary_growth_max, s.hire_pay_ratio_max]),
            s.cagr_tolerance_pct,
            s.annual_guardrail_pct,
            s.horizon_evaluations,
        )

    def _report(self, outcome: SolverOutcome) -> HorizonReport:
        best = outcome.best
        key = tuple(float(value) for value in best.levers)
        return HorizonReport(
            raises=float(best.levers[0]),
            hire_pay_growth=float(best.levers[1]),
            hire_pay_ratio=float(best.levers[2]),
            cagr_pct=best.cagr_error + self.target_pct,
            cagr_error_pct=best.cagr_error,
            annual_errors_pct=[float(value) for value in best.errors],
            guardrail_misses=outcome.guardrail_misses,
            stop_reason=outcome.stop_reason,
            active_bounds=outcome.active_bounds,
            limit_tests=[
                HorizonLimitTest(
                    lever=test.lever,
                    bound=test.bound,
                    relaxed_to=test.relaxed_to,
                    cagr_error_before_pct=test.cagr_error_before,
                    cagr_error_after_pct=test.cagr_error_after,
                )
                for test in outcome.limit_tests
            ],
            seeds=[
                HorizonSeedResult(
                    seed=seed,
                    cagr_pct=horizon_cagr_error(growth, 0.0),
                    annual_growth_pct=growth,
                )
                for seed, growth in zip(self.seeds, self._by_levers[key])
            ],
        )

    def _message(self, outcome: SolverOutcome, report: HorizonReport) -> str:
        summary = (
            f"Raises {report.raises:.2%}, hire pay growth "
            f"{report.hire_pay_growth:.2%} and hire pay ratio "
            f"{report.hire_pay_ratio:.0%} give {report.cagr_pct:.2f}% a year on "
            f"average across {len(self.seeds)} seeds, with "
            f"{report.guardrail_misses} years outside the guardrail."
        )
        limit = best_limit_message(outcome.limit_tests)
        return f"{summary} {limit}" if limit else summary

    def run(self) -> AutoCalibrationResult:
        calibrator = self.calibrator
        config = calibrator._runner._config
        if not config.new_hire.get("shared_pay_scale"):
            raise ValueError("Horizon search requires the shared pay scale")
        outcome = solve_horizon(self._evaluate, self._start(), self._limits())
        report = self._report(outcome)
        best = outcome.best
        key = tuple(float(value) for value in best.levers)
        calibrator._best = _BestCandidate(
            float(np.abs(best.errors).max()),
            self._params(best.levers),
            best.cagr_error + self.target_pct,
            self._results[key],
            None,
            abs(best.cagr_error),
        )
        converged = outcome.stop_reason == "on_target"
        result = calibrator._finish(
            converged,
            self._message(outcome, report),
            self.target_pct,
            status="converged" if converged else "best_achievable",
            reason=None if converged else outcome.stop_reason.replace("_", " "),
        )
        return result.model_copy(update={"horizon": report})
