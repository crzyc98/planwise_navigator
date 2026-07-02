#!/usr/bin/env python3
"""Auto-calibration: solve for the comp config that hits growth targets.

The analyst sets two targets:

* **Workforce (population) growth** -- set directly on
  ``simulation.target_growth_rate``; the E077 deterministic solver hits it
  exactly, so it needs no searching.
* **Average-compensation growth** -- searched. Each candidate is evaluated
  with a fast comp-only :class:`CalibrationRunner` build (exact vs. a full
  simulation), and a secant iteration adjusts the chosen lever until the mean
  year-over-year avg-comp growth is within tolerance of the target.

Two search modes:

* ``levers`` -- new-hire comp ranges stay fixed; COLA/merit are searched.
* ``new_hire_scale`` -- COLA/merit stay where the analyst set them (they are
  policy); the census scale on the per-level new-hire comp ranges is searched
  so hiring dilution doesn't have to be papered over with outsized raises.
  Only if the scale clamps at its bounds and still misses does an optional
  fallback nudge COLA/merit to close the residual -- and says so.

Because avg-comp growth responds near-linearly to either lever, the secant
method typically converges in 3-6 evaluations -- minutes, not the hours a
blind parameter grid would take.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
    CalibrationRunner,
    PerYearCompensationResult,
)

logger = logging.getLogger(__name__)

# Raise levers are clamped to a sane band during the search.
_LEVER_MIN = 0.0
_LEVER_MAX = 0.20
# First-step sensitivity guesses (the secant self-corrects after two points).
_LEVER_SENSITIVITY_PP = 100.0  # pp of growth per 1.0 (decimal) lever shift
_SCALE_SENSITIVITY_PP = 8.0  # pp of growth per +1.0 census scale
_MAX_SCALE_STEP = 0.5


class AutoCalibrationSettings(BaseModel):
    """Search targets and knobs for one auto-calibration."""

    # Decimal rates, e.g. 0.03 = 3%/yr.
    target_workforce_growth: float = Field(..., ge=-1.0, le=1.0)
    target_comp_growth: float = Field(..., ge=-1.0, le=1.0)
    # Convergence tolerance on mean YoY comp growth, in percentage points.
    tolerance_pct: float = Field(default=0.05, gt=0, le=5.0)
    # Total evaluation budget across all stages.
    max_iterations: int = Field(default=8, ge=1, le=25)
    # Which raise levers absorb a lever-stage shift.
    adjust: Literal["cola", "merit", "both"] = "both"

    # -- new_hire_scale mode ------------------------------------------------
    search_mode: Literal["levers", "new_hire_scale"] = "levers"
    # UNSCALED (1.0x) per-level ranges, e.g. straight from census analysis.
    base_job_level_compensation: Optional[List[Dict[str, Any]]] = None
    initial_scale: float = Field(default=1.0, gt=0, le=5.0)
    scale_min: float = Field(default=0.5, gt=0)
    scale_max: float = Field(default=3.0, le=5.0)
    # If the scale clamps at a bound and still misses, nudge COLA/merit to
    # close the residual (reported explicitly in the outcome message).
    lever_fallback: bool = True

    @model_validator(mode="after")
    def _validate_scale_mode(self) -> "AutoCalibrationSettings":
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
    achieved_growth_pct: float
    error_pct: float


class AutoCalibrationResult(BaseModel):
    """Outcome of the search: best params + the run that produced them."""

    converged: bool
    message: str
    best_params: CalibrationParameterSet
    best_scale: Optional[float] = None
    achieved_comp_growth_pct: float
    target_comp_growth_pct: float
    iterations: List[OptimizationIteration]
    results: List[PerYearCompensationResult]


def _mean_comp_growth_pct(results: List[PerYearCompensationResult]) -> float:
    growths = [r.yoy_growth_pct for r in results if r.yoy_growth_pct is not None]
    if not growths:
        raise ValueError(
            "Auto-calibration needs at least a two-year range to measure "
            "year-over-year compensation growth"
        )
    return sum(growths) / len(growths)


def _clamp_lever(value: float) -> float:
    return min(max(value, _LEVER_MIN), _LEVER_MAX)


class AutoCalibrator:
    """Secant search to hit a target avg-comp growth.

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
    ):
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
        # (abs_error, params, achieved, results, scale)
        self._best: Optional[Tuple] = None

    @property
    def database_path(self):
        return self._runner.database_path

    # -- public API ---------------------------------------------------------
    def optimize(self) -> AutoCalibrationResult:
        target_pct = self.settings.target_comp_growth * 100
        self._evals = 0
        self._iterations = []
        self._best = None

        if self.settings.search_mode == "new_hire_scale":
            return self._optimize_scale_mode(target_pct)

        converged = self._lever_stage(target_pct, scale=None)
        return self._finish(converged, self._summary(converged, target_pct), target_pct)

    # -- scale-primary mode ---------------------------------------------------
    def _optimize_scale_mode(self, target_pct: float) -> AutoCalibrationResult:
        converged, clamped_scale = self._scale_stage(target_pct)
        if converged:
            message = (
                f"{self._summary(True, target_pct)} -- solved by setting the "
                f"new-hire range scale to {self._best[4]:.2f}x; COLA/merit "
                f"left at their configured values"
            )
            return self._finish(True, message, target_pct)

        if clamped_scale is not None and self.settings.lever_fallback:
            converged = self._lever_stage(target_pct, scale=clamped_scale)
            message = (
                f"{self._summary(converged, target_pct)} -- new-hire scale hit "
                f"its bound at {clamped_scale:.2f}x; COLA/merit were adjusted "
                f"to close the remaining gap"
            )
            return self._finish(converged, message, target_pct)

        return self._finish(False, self._summary(False, target_pct), target_pct)

    def _scale_stage(self, target_pct: float) -> Tuple[bool, Optional[float]]:
        """Search the census scale with COLA/merit fixed at their anchors.

        Returns (converged, clamped_scale): ``clamped_scale`` is set when the
        search got stuck at ``scale_min``/``scale_max`` without converging.
        """
        anchor_cola, anchor_merit = self._starting_levers()
        x = min(
            max(self.settings.initial_scale, self.settings.scale_min),
            self.settings.scale_max,
        )
        x_prev: Optional[float] = None
        f_prev: Optional[float] = None

        while self._evals < self.settings.max_iterations:
            params = self._candidate(anchor_cola, anchor_merit, 0.0, x)
            error = self._try_candidate(params, target_pct, scale=x)
            if abs(error) <= self.settings.tolerance_pct:
                return True, None

            if x_prev is None or abs(error - f_prev) < 1e-9:
                x_next = x - error / _SCALE_SENSITIVITY_PP
            else:
                x_next = x - error * (x - x_prev) / (error - f_prev)
                x_next = min(max(x_next, x - _MAX_SCALE_STEP), x + _MAX_SCALE_STEP)
            x_prev, f_prev = x, error

            x_next = min(max(x_next, self.settings.scale_min), self.settings.scale_max)
            if abs(x_next - x) < 1e-6:
                # Stuck at a bound (or a flat response): scale alone can't close it.
                return False, x
            x = x_next

        return False, None  # evaluation budget exhausted mid-search

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

            if s_prev is None or abs(error - f_prev) < 1e-9:
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
            "cola_rate": _clamp_lever(base_cola + shift * w_cola),
            "merit_budget": _clamp_lever(base_merit + shift * w_merit),
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
        achieved = _mean_comp_growth_pct(results)
        error = achieved - target_pct
        self._iterations.append(
            OptimizationIteration(
                iteration=len(self._iterations) + 1,
                cola_rate=params.cola_rate or 0.0,
                merit_budget=params.merit_budget or 0.0,
                scale=scale,
                achieved_growth_pct=achieved,
                error_pct=error,
            )
        )
        if self._best is None or abs(error) < self._best[0]:
            self._best = (abs(error), params, achieved, results, scale)
        return error

    def _evaluate(
        self, params: CalibrationParameterSet
    ) -> List[PerYearCompensationResult]:
        self._evals += 1
        logger.info(
            "Auto-calibration eval %d: cola=%.4f merit=%.4f scale=%s",
            self._evals,
            params.cola_rate,
            params.merit_budget,
            f"{params.job_level_compensation[0]['min_compensation']}"
            if params.job_level_compensation
            else "-",
        )
        if self._evals == 1:
            self._runner.run = self._runner.run.model_copy(update={"params": params})
            self._runner._apply_param_overrides(params)
            return self._runner.run_calibration()
        return self._runner.rerun_with_params(params)

    def _summary(self, converged: bool, target_pct: float) -> str:
        achieved = self._best[2]
        if converged:
            return (
                f"Converged in {self._evals} run(s): mean comp growth "
                f"{achieved:.2f}% vs target {target_pct:.2f}%"
            )
        return (
            f"Stopped after {self._evals} run(s); best mean comp growth "
            f"{achieved:.2f}% vs target {target_pct:.2f}% "
            f"(|error| {self._best[0]:.2f}pp > tolerance "
            f"{self.settings.tolerance_pct}pp)"
        )

    def _finish(
        self, converged: bool, message: str, target_pct: float
    ) -> AutoCalibrationResult:
        _, params, achieved, results, scale = self._best
        logger.info("Auto-calibration finished: %s", message)
        return AutoCalibrationResult(
            converged=converged,
            message=message,
            best_params=params,
            best_scale=scale,
            achieved_comp_growth_pct=achieved,
            target_comp_growth_pct=target_pct,
            iterations=self._iterations,
            results=results,
        )
