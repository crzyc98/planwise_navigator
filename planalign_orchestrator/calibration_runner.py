#!/usr/bin/env python3
"""Fast Compensation Calibration Mode (Feature 105).

Rebuilds ONLY the compensation/workforce dbt subgraph per simulation year and
reads the existing S051 growth mart, reusing the platform's validated comp math
(E077 solver, mid-year proration, band-aware merit/COLA/promotion, and
``fct_compensation_growth``) while skipping the entire DC-plan stack.

Because the comp columns are produced by the identical validated SQL, the
per-year average compensation and YoY growth are *exact* relative to a full
simulation under the same config -- the speedup comes purely from building
fewer models, not from approximation.

See ``specs/105-comp-calibration/`` for the spec, plan, and research decisions.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
from pydantic import BaseModel, Field, field_validator, model_validator

from config.constants import DATABASE_FILENAME
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.config.export import to_dbt_vars
from planalign_orchestrator.dbt_runner import DbtRunner
from planalign_orchestrator.exceptions import ConfigurationError, ResolutionHint
from planalign_orchestrator.pipeline.workflow import WorkflowBuilder

logger = logging.getLogger(__name__)

# DC tables that fct_workforce_snapshot / fct_yearly_events ref() but calibration
# never rebuilds. They must exist (stale-but-present) for a comp-only build to
# compile. See research.md Decision 2.
#
# Only *materialized* DC dependencies are listed -- ephemeral DC models (e.g.
# int_deferral_match_response_events, int_deferral_rate_escalation_events) are
# inlined by dbt and never create a table, so they are not prerequisites.
DC_PREREQUISITE_TABLES: List[str] = [
    "int_employee_contributions",
    "int_employee_match_calculations",
    "int_employer_core_contributions",
    "int_employer_eligibility",
    "int_enrollment_state_accumulator",
    "int_deferral_rate_state_accumulator",
    "int_enrollment_events",
    "int_eligibility_events",
]


# ---------------------------------------------------------------------------
# Entities (see data-model.md)
# ---------------------------------------------------------------------------
class CalibrationParameterSet(BaseModel):
    """Tunable compensation levers, shared identically with the full simulation.

    Only the fields the analyst overrides need to be set; unset fields fall back
    to the loaded config. ``target_growth_pct`` is used solely to compute the
    per-year delta -- it does not affect the build.
    """

    target_growth_pct: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    cola_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    merit_budget: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    promotion_increase: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    new_hire_mix: Optional[Dict[str, float]] = None
    # Feature 105: per-level new-hire comp multiplier (band midpoint x mult).
    new_hire_comp_multiplier_default: Optional[float] = Field(
        default=None, ge=0.1, le=3.0
    )
    new_hire_comp_multipliers: Optional[Dict[int, float]] = None

    @field_validator("new_hire_comp_multipliers")
    @classmethod
    def _multipliers_in_range(
        cls, value: Optional[Dict[int, float]]
    ) -> Optional[Dict[int, float]]:
        if value is not None and any(not 0.1 <= m <= 3.0 for m in value.values()):
            raise ValueError("new_hire_comp_multipliers must be within 0.1-3.0")
        return value

    @field_validator("new_hire_mix")
    @classmethod
    def _mix_sums_positive(
        cls, value: Optional[Dict[str, float]]
    ) -> Optional[Dict[str, float]]:
        if value is None:
            return value
        if any(weight < 0 for weight in value.values()):
            raise ValueError("new_hire_mix weights must be non-negative")
        if sum(value.values()) <= 0:
            raise ValueError("new_hire_mix weights must sum to a positive value")
        return value


class CalibrationRun(BaseModel):
    """One calibration execution over a year range against a target database."""

    start_year: int = Field(..., ge=2000)
    end_year: int = Field(..., ge=2000)
    config_path: Optional[Path] = None
    database_path: Optional[Path] = None
    interactive: bool = False
    params: CalibrationParameterSet = Field(default_factory=CalibrationParameterSet)

    @model_validator(mode="after")
    def _range_ordered(self) -> "CalibrationRun":
        if self.end_year < self.start_year:
            raise ValueError(
                f"end_year ({self.end_year}) must be >= start_year ({self.start_year})"
            )
        return self


class PerYearCompensationResult(BaseModel):
    """Per-year compensation-growth result row (one per simulation year)."""

    simulation_year: int
    avg_compensation: float
    yoy_growth_pct: Optional[float] = None
    target_growth_pct: Optional[float] = None
    growth_delta_pct: Optional[float] = None
    headcount: int
    new_hire_avg_comp: Optional[float] = None
    existing_avg_comp: Optional[float] = None
    new_hire_gap: Optional[float] = None


# ---------------------------------------------------------------------------
# Prerequisite guard (FR-011)
# ---------------------------------------------------------------------------
def verify_dc_prerequisites(database_path: Path) -> None:
    """Fail fast if the target DB lacks the stale-but-present DC tables.

    A comp-only build only compiles when the DC tables that
    ``fct_workforce_snapshot`` / ``fct_yearly_events`` ``ref()`` already exist.
    Raises ``ConfigurationError`` with an actionable hint when any are missing.
    """
    if not Path(database_path).exists():
        raise ConfigurationError(
            f"Calibration target database not found: {database_path}",
            resolution_hints=[_build_baseline_hint(database_path)],
        )

    existing = _existing_table_names(database_path)
    missing = [t for t in DC_PREREQUISITE_TABLES if t not in existing]
    if missing:
        raise ConfigurationError(
            "Target database is missing prerequisite tables for a comp-only "
            f"calibration build: {', '.join(missing)}",
            resolution_hints=[_build_baseline_hint(database_path)],
        )


def _existing_table_names(database_path: Path) -> set[str]:
    conn = duckdb.connect(str(database_path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _build_baseline_hint(database_path: Path) -> ResolutionHint:
    return ResolutionHint(
        title="Build a baseline first",
        description=(
            "Calibration reuses an existing full build's DC tables. Run one "
            "full simulation against this database before calibrating."
        ),
        steps=[
            f"planalign simulate <start>-<end> --database {database_path}",
            "Re-run: planalign calibrate <start>-<end> " f"--database {database_path}",
        ],
        estimated_resolution_time="11 minutes (one full build)",
    )


# ---------------------------------------------------------------------------
# Isolated database resolution (FR-006)
# ---------------------------------------------------------------------------
def resolve_calibration_database(database_path: Optional[Path]) -> Path:
    """Resolve the target DB, defaulting to an isolated calibration DB.

    With an explicit path, that path is used as-is. With no path, the shared dev
    DB (``dbt/simulation.duckdb``) is **copied** to a timestamped
    ``calibration_<ts>.duckdb`` under ``dbt/calibration/`` and that copy is
    returned. Calibration reuses an existing full build's (stale-but-present) DC
    tables, so the isolated default must be seeded from a built DB -- and the
    copy means a default run never mutates the shared dev DB.

    If no built source DB exists, a ``ConfigurationError`` is raised with an
    actionable hint (rather than handing back an empty DB the guard would later
    reject with a more cryptic message).
    """
    if database_path is not None:
        return Path(database_path)

    shared = Path("dbt") / DATABASE_FILENAME
    cal_dir = Path("dbt") / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = cal_dir / f"calibration_{ts}.duckdb"
    if target.resolve() == shared.resolve():  # defensive; never equal in practice
        raise ConfigurationError("Refusing to calibrate against the shared dev DB")

    if not shared.exists():
        raise ConfigurationError(
            "No source database to seed an isolated calibration run. Pass "
            "--database pointing at a database that has had one full simulation, "
            "or build the shared dev DB first (planalign simulate ...).",
            resolution_hints=[_build_baseline_hint(shared)],
        )

    logger.info("Seeding isolated calibration DB from %s", shared)
    shutil.copy(shared, target)
    return target


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
class CalibrationRunner:
    """Drives a fast, exact, comp-only calibration over a year range."""

    def __init__(self, run: CalibrationRun, *, threads: int = 1, verbose: bool = False):
        self.run = run
        self.threads = threads
        self.verbose = verbose
        self.database_path = resolve_calibration_database(run.database_path)
        self._config = (
            load_simulation_config(run.config_path)
            if run.config_path is not None
            else load_simulation_config()
        )
        self._apply_param_overrides(run.params)
        self._runner = DbtRunner(
            working_dir=Path("dbt"),
            threads=threads,
            verbose=verbose,
            database_path=str(self.database_path),
        )

    # -- public API -------------------------------------------------------
    def run_calibration(self) -> List[PerYearCompensationResult]:
        """Validate, guard, build the comp subgraph per year, return results."""
        verify_dc_prerequisites(self.database_path)
        return self._build_all_years()

    def rerun_with_params(
        self, params: CalibrationParameterSet
    ) -> List[PerYearCompensationResult]:
        """Re-tune fast-path: apply new params and rebuild the comp subgraph.

        Skips the prerequisite guard (already verified) and the isolated-DB
        re-init -- used by the interactive loop (US2).
        """
        self._apply_param_overrides(params)
        self.run = self.run.model_copy(update={"params": params})
        return self._build_all_years()

    # -- internals --------------------------------------------------------
    def _build_all_years(self) -> List[PerYearCompensationResult]:
        # fct_compensation_growth is a full-refresh table, so each year's build
        # overwrites the prior year. Read each year's row immediately after its
        # build, before the next year overwrites it.
        results: List[PerYearCompensationResult] = []
        for year in range(self.run.start_year, self.run.end_year + 1):
            self._build_year(year)
            results.append(self._read_year(year))
        return results

    def _apply_param_overrides(self, params: CalibrationParameterSet) -> None:
        # NOTE: target_growth_pct is the *compensation*-growth target the analyst
        # is calibrating toward -- it is used only for the per-year delta column
        # and MUST NOT be written to simulation.target_growth_rate (which is the
        # workforce/headcount growth target that sizes E077 hiring). Conflating
        # the two changes hiring counts and breaks comp exactness.
        if params.cola_rate is not None:
            self._config.compensation.cola_rate = params.cola_rate
        if params.merit_budget is not None:
            self._config.compensation.merit_budget = params.merit_budget
        if params.promotion_increase is not None:
            self._config.compensation.promotion_increase = params.promotion_increase
        if params.new_hire_comp_multiplier_default is not None:
            self._config.compensation.new_hire_comp_multiplier_default = (
                params.new_hire_comp_multiplier_default
            )
        if params.new_hire_comp_multipliers is not None:
            self._config.compensation.new_hire_comp_multipliers = (
                params.new_hire_comp_multipliers
            )

    def _build_year(self, year: int) -> None:
        dbt_vars = to_dbt_vars(self._config)
        stages = WorkflowBuilder.build_calibration_year_workflow(
            year, self.run.start_year
        )
        for stage in stages:
            if not stage.models:
                continue
            result = self._runner.execute_command(
                ["run", "--select", *stage.models],
                description=f"calibrate {year}: {stage.name.value}",
                simulation_year=year,
                dbt_vars=dbt_vars,
                threads=self.threads,
            )
            if not result.success:
                raise ConfigurationError(
                    f"Calibration build failed at {stage.name.value} for {year} "
                    f"(return code {result.return_code})"
                )

    def _read_year(self, year: int) -> PerYearCompensationResult:
        target = (
            self.run.params.target_growth_pct
            if self.run.params.target_growth_pct is not None
            else self._config.simulation.target_growth_rate
        )
        conn = duckdb.connect(str(self.database_path), read_only=True)
        try:
            growth = self._read_growth(conn, year)
            gap = self._read_snapshot_gap(conn, year)
        finally:
            conn.close()
        return self._assemble_row(year, growth, gap, target)

    @staticmethod
    def _read_growth(conn: duckdb.DuckDBPyConnection, year: int) -> Dict[str, Any]:
        row = conn.execute(
            """
            SELECT avg_compensation, yoy_growth_pct
            FROM fct_compensation_growth
            WHERE calculation_method = 'methodology_a_current'
              AND simulation_year = ?
            """,
            [year],
        ).fetchone()
        if row is None:
            raise ConfigurationError(f"No compensation-growth row produced for {year}")
        return {"avg_compensation": row[0], "yoy_growth_pct": row[1]}

    @staticmethod
    def _read_snapshot_gap(
        conn: duckdb.DuckDBPyConnection, year: int
    ) -> Dict[str, Any]:
        row = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE detailed_status_code IN ('continuous_active', 'new_hire_active')
                ) AS headcount,
                AVG(prorated_annual_compensation) FILTER (
                    WHERE detailed_status_code = 'new_hire_active'
                ) AS new_hire_avg,
                AVG(prorated_annual_compensation) FILTER (
                    WHERE detailed_status_code = 'continuous_active'
                ) AS existing_avg
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
            """,
            [year],
        ).fetchone()
        return {
            "headcount": int(row[0] or 0),
            "new_hire_avg": row[1],
            "existing_avg": row[2],
        }

    @staticmethod
    def _assemble_row(
        year: int,
        growth: Dict[str, Any],
        gap: Dict[str, Any],
        target: Optional[float],
    ) -> PerYearCompensationResult:
        yoy = growth.get("yoy_growth_pct")
        # target_growth_rate is a decimal (e.g. 0.035); yoy_growth_pct is a
        # percentage (e.g. 3.6). Compare on the same scale.
        target_pct = target * 100 if target is not None else None
        delta = (
            yoy - target_pct if (yoy is not None and target_pct is not None) else None
        )
        nh = gap.get("new_hire_avg")
        ex = gap.get("existing_avg")
        return PerYearCompensationResult(
            simulation_year=year,
            avg_compensation=growth["avg_compensation"],
            yoy_growth_pct=yoy,
            target_growth_pct=target_pct,
            growth_delta_pct=delta,
            headcount=gap.get("headcount", 0),
            new_hire_avg_comp=nh,
            existing_avg_comp=ex,
            new_hire_gap=(nh - ex if (nh is not None and ex is not None) else None),
        )
