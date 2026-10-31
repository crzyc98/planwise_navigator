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

from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
    CalibrationRunner,
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

    # -- new_hire_scale mode ------------------------------------------------
    search_mode: Literal["levers", "new_hire_scale"] = "levers"
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

    @model_validator(mode="after")
    def _validate_scale_mode(self) -> "AutoCalibrationSettings":
        if self.solve_salary_growth and self.search_mode != "new_hire_scale":
            raise ValueError("solve_salary_growth requires new_hire_scale search")
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


class AutoCalibrationResult(BaseModel):
    """Outcome of the search: best params + the run that produced them."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    converged: bool
    status: Literal["converged", "not_converged", "infeasible"]
    reason: Optional[str] = None
    message: str
    best_params: CalibrationParameterSet
    best_scale: Optional[float] = None
    best_salary_growth_rate: Optional[float] = None
    achieved_comp_growth_pct: float
    target_comp_growth_pct: float
    max_abs_error_pct: float
    objective: Literal["max_annual_error"] = "max_annual_error"
    start_year: int
    end_year: int
    iterations: List[OptimizationIteration]
    results: List[PerYearCompensationResult]


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


def _clamp_lever(value: float) -> float:
    return min(max(value, _LEVER_MIN), _LEVER_MAX)


class _BestCandidate(NamedTuple):
    """The best-so-far evaluated candidate (tracked across every stage)."""

    abs_error: float
    params: CalibrationParameterSet
    achieved_pct: float
    results: List[PerYearCompensationResult]
    scale: Optional[float]


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
        self.run = run.model_copy(update={"params": params})
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
        cola, merit = self._starting_levers()
        params = self._candidate(cola, merit, 0.0, float(x[0]))
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
        solution = linprog(
            [0, 0, 1],
            A_ub=constraints,
            b_ub=np.concatenate((-errors, errors)),
            bounds=[*zip(lower, upper), (0, None)],
            method="highs",
        )
        if not solution.success:
            logger.warning("Two-dial minimax step failed: %s", solution.message)
            return None
        return np.asarray(solution.x[:2], dtype=float)

    def _dials_converged(self) -> bool:
        return self._require_best().abs_error <= self.settings.tolerance_pct

    @staticmethod
    def _update_dial_jacobian(
        jacobian: NDArray[np.float64],
        step: NDArray[np.float64],
        errors: NDArray[np.float64],
        new_errors: NDArray[np.float64],
    ) -> Optional[NDArray[np.float64]]:
        """Accept an improving step with a Broyden update; otherwise recompute."""
        if np.max(np.abs(new_errors)) >= np.max(np.abs(errors)):
            return None
        residual = new_errors - errors - jacobian @ step
        return jacobian + np.outer(residual, step) / float(step @ step)

    def _search_dials(self, target_pct: float) -> str:
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
                return "Linearized minimax solver could not produce a step."
            if np.max(np.abs(step) / np.array([0.5, 0.02])) < 1e-5:
                return "Trust region collapsed: no improving step within bounds."
            candidate = np.clip(x + step, *self._dial_bounds().T)
            step = candidate - x
            new_errors = self._evaluate_dials(candidate, target_pct)
            jacobian = self._update_dial_jacobian(jacobian, step, errors, new_errors)
            if jacobian is None:
                trust *= 0.5
            else:
                x, errors = candidate, new_errors
            if trust[0] < 1e-4:
                return "Trust region collapsed without convergence."
        return "Evaluation budget exhausted before convergence."

    def _optimize_two_dials(self, target_pct: float) -> AutoCalibrationResult:
        reason = self._search_dials(target_pct)
        converged = self._dials_converged()
        return self._finish(
            converged,
            self._summary(converged, target_pct),
            target_pct,
            reason=None if converged else f"{reason} {self._best_growth_detail()}",
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

    def _best_growth_detail(self) -> str:
        best = self._require_best()
        growths = ", ".join(
            f"{row.simulation_year}: {row.yoy_growth_pct:.3f}%"
            for row in best.results
            if self.run.start_year < row.simulation_year <= self.run.end_year
            and row.yoy_growth_pct is not None
        )
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
        if self._best is None or max_abs_error < self._best.abs_error:
            self._best = _BestCandidate(max_abs_error, params, achieved, results, scale)
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

    def _finish(
        self,
        converged: bool,
        message: str,
        target_pct: float,
        status: Optional[Literal["converged", "not_converged", "infeasible"]] = None,
        reason: Optional[str] = None,
    ) -> AutoCalibrationResult:
        best = self._require_best()
        logger.info("Auto-calibration finished: %s", message)
        return AutoCalibrationResult(
            converged=converged,
            status=status or ("converged" if converged else "not_converged"),
            reason=(
                reason
                if converged or reason
                else "Evaluation budget exhausted before convergence."
            ),
            message=message,
            best_params=best.params,
            best_scale=best.scale,
            best_salary_growth_rate=best.params.new_hire_salary_growth_rate,
            achieved_comp_growth_pct=best.achieved_pct,
            target_comp_growth_pct=target_pct,
            max_abs_error_pct=best.abs_error,
            start_year=self.run.start_year,
            end_year=self.run.end_year,
            iterations=self._iterations,
            results=best.results,
        )
