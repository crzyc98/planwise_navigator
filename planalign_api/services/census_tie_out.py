"""Census tie-out: the census year beside the first simulated year.

A sponsor's first question is whether the model reproduces the plan year the
census describes. This service answers it for one scenario's selected Studio
run by applying one definition per metric to both sides:

* Census side: the run's archived census, i.e. the ``stg_census_data`` table
  inside ``runs/<run_id>/simulation.duckdb``. The workspace's current census
  file is never read, because it may have changed since the run.
* Simulated side: ``fct_workforce_snapshot`` for the run's first simulated year.

Both sides are first reduced to the same per-employee columns
(``_pay``, ``_deferral``, ``_match``, ``_core``, ``_eligible``) for active
employees, then aggregated by one shared SQL statement (``_AGGREGATE_SQL``):

=====================  ===================================================  ==========================================================
Metric                 Definition (both sides)                              Census column -> snapshot column
=====================  ===================================================  ==========================================================
active_headcount       Employees active at year end.                        active flag / termination date -> employment_status
eligible_count         Active employees eligible to defer at year end.      eligibility_entry_date <= as-of -> current_eligibility_status
participation_rate     Share of eligible employees deferring above 0%.      employee_deferral_rate -> current_deferral_rate if enrolled
average_deferral_rate  Mean deferral rate of eligible employees, 0 for      employee_deferral_rate -> current_deferral_rate if enrolled
                       non-participants.
total_pay              Earned (prorated) pay of active employees.           employee_plan_year_compensation -> prorated_annual_compensation
employer_match         Employer match dollars for active employees.         employer_match_contribution -> employer_match_amount
employer_core          Employer core dollars for active employees.          employer_core_contribution -> employer_core_amount
=====================  ===================================================  ==========================================================

"Eligible" means the census eligibility date when the census has one. When it
has none, participation and average deferral use every active employee on
both sides and the eligible count reads ``not_in_census``. Averages count
non-participants as 0, as Census Analysis and DC Plan analytics do by default.

A census column that is missing or entirely empty is ``not_in_census``. The
staging model adds absent optional columns as NULL, so "no data" (all NULL)
is distinct from "zero" (a column of 0s), which is compared normally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, Optional

import duckdb
import yaml

from planalign_core.constants import TABLE_FCT_WORKFORCE_SNAPSHOT
from planalign_orchestrator.config.simulation import (
    CompensationSettings,
    SimulationSettings,
)

from ..models.census_tie_out import (
    CensusTieOut,
    CensusTieOutRow,
    TieOutMetric,
    TieOutStatus,
    TieOutUnit,
)
from ..storage.workspace_storage import WorkspaceStorage
from .census_schema import active_filter_sql
from .database_path_resolver import (
    DatabasePathResolver,
    create_api_database_path_resolver,
)

logger = logging.getLogger(__name__)

CENSUS_TABLE = "stg_census_data"

# Tolerances. Counts and dollars tie when the simulated value is within
# (base + DRIFT_SHARE * expected change) of the census value carried forward
# by the configured growth and raises. Year one rarely lands exactly on the
# configured rates (hire timing, new-hire pay mix, raise timing), so half the
# expected change is added to the band. Rates use a fixed band in points.
COUNT_TOLERANCE = 0.03  # 3% of the expected count
DOLLAR_TOLERANCE = 0.05  # 5% of the expected dollars
DRIFT_SHARE = 0.5  # plus half the expected change
PARTICIPATION_TOLERANCE = 0.05  # 5 percentage points
DEFERRAL_TOLERANCE = 0.01  # 1 percentage point
_EPSILON = 1e-9

DriftKind = Literal["none", "growth", "growth_and_raises"]

NO_RUN_REASON = (
    "This scenario has no completed Studio run, so there is no archived census "
    "to compare. Run the scenario in Studio first."
)
NO_ARCHIVED_CENSUS_REASON = (
    "This run's database has no archived census (stg_census_data), so the "
    "census it used can't be compared. Re-run the scenario to archive it."
)
NO_CENSUS_YEAR_REASON = (
    "The archived census has no usable hire dates, so its census year is unknown."
)
NO_SNAPSHOT_REASON = "This run has no simulated workforce snapshot to compare."


@dataclass(frozen=True)
class _MetricSpec:
    """How one tie-out row is defined, measured and explained."""

    metric: TieOutMetric
    label: str
    unit: TieOutUnit
    definition: str
    census_column: Optional[str]  # None: always available
    drift: DriftKind
    base_tolerance: float
    check: str
    missing: str


_METRICS: tuple[_MetricSpec, ...] = (
    _MetricSpec(
        "active_headcount",
        "Active headcount",
        "count",
        "Employees active at year end.",
        None,
        "growth",
        COUNT_TOLERANCE,
        "Check the growth target and that the census marks terminated "
        "employees as inactive.",
        "",
    ),
    _MetricSpec(
        "eligible_count",
        "Eligible count",
        "count",
        "Active employees eligible to defer at year end.",
        "eligibility_entry_date",
        "growth",
        COUNT_TOLERANCE,
        "Check the eligibility rule (age, service, waiting period) and the "
        "census eligibility dates.",
        "The census has no eligibility dates, so the eligible count can't be compared.",
    ),
    _MetricSpec(
        "participation_rate",
        "Participation",
        "rate",
        "Share of eligible employees deferring more than 0% at year end "
        "(every active employee when the census has no eligibility dates).",
        "employee_deferral_rate",
        "none",
        PARTICIPATION_TOLERANCE,
        "Check auto-enrollment, opt-out rates and the census deferral column.",
        "The census has no deferral rates, so participation can't be compared.",
    ),
    _MetricSpec(
        "average_deferral_rate",
        "Average deferral",
        "rate",
        "Mean deferral rate of eligible employees at year end, counting "
        "non-participants as 0%.",
        "employee_deferral_rate",
        "none",
        DEFERRAL_TOLERANCE,
        "Check the default deferral rate, auto-escalation, and that census "
        "deferral rates are fractions (0.06 for 6%).",
        "The census has no deferral rates, so average deferral can't be compared.",
    ),
    _MetricSpec(
        "total_pay",
        "Total pay",
        "dollars",
        "Pay earned during the year by employees active at year end.",
        "employee_plan_year_compensation",
        "growth_and_raises",
        DOLLAR_TOLERANCE,
        "Check that the census pay column is the year's earnings, the census "
        "pay basis setting and the raise settings.",
        "The census has no pay, so total pay can't be compared.",
    ),
    _MetricSpec(
        "employer_match",
        "Employer match",
        "dollars",
        "Employer match dollars for the year, employees active at year end.",
        "employer_match_contribution",
        "growth_and_raises",
        DOLLAR_TOLERANCE,
        "Check the match formula and match eligibility.",
        "The census has no employer match column, so match can't be compared.",
    ),
    _MetricSpec(
        "employer_core",
        "Employer core",
        "dollars",
        "Employer core (non-elective) dollars for the year, employees active "
        "at year end.",
        "employer_core_contribution",
        "growth_and_raises",
        DOLLAR_TOLERANCE,
        "Check the core contribution rate and core eligibility.",
        "The census has no employer core column, so core can't be compared.",
    ),
)

_CENSUS_VALUE_COLUMNS = (
    "employee_plan_year_compensation",
    "employee_deferral_rate",
    "employer_match_contribution",
    "employer_core_contribution",
    "eligibility_entry_date",
)

# One aggregation for both sides; each side supplies the `pop` relation.
_AGGREGATE_SQL = """
    SELECT
      COUNT(*) AS active_headcount,
      COUNT(*) FILTER (WHERE _eligible) AS eligible_count,
      AVG(CASE WHEN _deferral > 0 THEN 1.0 ELSE 0.0 END)
        FILTER (WHERE _eligible) AS participation_rate,
      AVG(COALESCE(_deferral, 0)) FILTER (WHERE _eligible) AS average_deferral_rate,
      COALESCE(SUM(_pay), 0) AS total_pay,
      COALESCE(SUM(_match), 0) AS employer_match,
      COALESCE(SUM(_core), 0) AS employer_core
    FROM pop
"""


# ---------------------------------------------------------------------------
# Pure tolerance and wording rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftAssumptions:
    """Configured change from the census to the end of the first simulated year.

    The engine starts the first simulated year from the census as it stands
    and applies one year of growth and raises, however old the census is.
    """

    growth_rate: float
    raise_rate: float


def expected_factor(drift: DriftKind, assumptions: DriftAssumptions) -> float:
    """Multiplier that carries a census value to the first simulated year."""
    if drift == "none":
        return 1.0
    yearly = 1 + assumptions.growth_rate
    if drift == "growth_and_raises":
        yearly *= 1 + assumptions.raise_rate
    return yearly


def tolerance_for(spec: _MetricSpec, expected: float, factor: float) -> float:
    """Allowed distance from the expected value, in the row's unit."""
    if spec.unit == "rate":
        return spec.base_tolerance
    return abs(expected) * (spec.base_tolerance + DRIFT_SHARE * abs(factor - 1))


def classify(simulated: float, expected: float, tolerance: float) -> TieOutStatus:
    """A row ties when the simulated value is inside the tolerance band."""
    return "ties" if abs(simulated - expected) <= tolerance + _EPSILON else "gap"


def _percent(value: float) -> str:
    return f"{value:.0%}" if abs(value) >= 0.1 else f"{value:.1%}"


def _direction(difference: float) -> str:
    return "above" if difference > 0 else "below"


def _gap_change(spec: _MetricSpec, row: CensusTieOutRow) -> str:
    """Describe how far the simulated value is from the census, in plain words."""
    difference = row.difference or 0.0
    if spec.unit == "rate":
        return f"{abs(difference) * 100:.1f} points {_direction(difference)}"
    if row.relative_difference is None:
        prefix = "$" if spec.unit == "dollars" else ""
        return f"{prefix}{abs(difference):,.0f} {_direction(difference)}"
    if abs(row.relative_difference) < _EPSILON:
        return "level with"
    return f"{_percent(abs(row.relative_difference))} {_direction(difference)}"


def tie_out_message(spec: _MetricSpec, row: CensusTieOutRow, factor: float) -> str:
    """One plain-language line: what the comparison shows and what to check."""
    if row.status == "not_in_census":
        return spec.missing
    if row.status == "ties":
        return f"{spec.label} ties to the census within the expected range."
    message = f"{spec.label} is {_gap_change(spec, row)} the census"
    if spec.drift != "none" and abs(factor - 1) > _EPSILON:
        source = "growth" if spec.drift == "growth" else "growth and raises"
        message += f", where about {factor - 1:+.0%} was expected from {source}"
    return f"{message}. {spec.check}"


def build_row(
    spec: _MetricSpec,
    census: Optional[float],
    simulated: float,
    assumptions: DriftAssumptions,
) -> CensusTieOutRow:
    """Compare one metric and word the result."""
    factor = expected_factor(spec.drift, assumptions)
    if census is None:
        row = CensusTieOutRow(
            metric=spec.metric,
            label=spec.label,
            unit=spec.unit,
            definition=spec.definition,
            census_value=None,
            simulated_value=simulated,
            expected_value=None,
            difference=None,
            relative_difference=None,
            tolerance=None,
            status="not_in_census",
            message="",
        )
    else:
        expected = census * factor
        tolerance = tolerance_for(spec, expected, factor)
        row = CensusTieOutRow(
            metric=spec.metric,
            label=spec.label,
            unit=spec.unit,
            definition=spec.definition,
            census_value=census,
            simulated_value=simulated,
            expected_value=expected,
            difference=simulated - census,
            relative_difference=(
                simulated / census - 1 if spec.unit != "rate" and census else None
            ),
            tolerance=tolerance,
            status=classify(simulated, expected, tolerance),
            message="",
        )
    return row.model_copy(update={"message": tie_out_message(spec, row, factor)})


# ---------------------------------------------------------------------------
# Run inputs
# ---------------------------------------------------------------------------


def load_run_config(config_path: Optional[Path]) -> dict[str, Any]:
    """Read the run's archived config.yaml (empty when the run has none)."""
    if config_path is None or not config_path.is_file():
        logger.warning("Run has no archived config; using default growth and raises")
        return {}
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def drift_assumptions(config: dict[str, Any]) -> DriftAssumptions:
    """One year of the growth and raises the run was configured with.

    Raises are COLA plus merit (a raise budget, when set, replaces both, as in
    the engine). Promotions and new-hire pay mix fall inside the tolerance.
    """
    simulation = config.get("simulation") or {}
    default_growth = SimulationSettings.model_fields["target_growth_rate"].default
    growth = float(simulation.get("target_growth_rate", default_growth))
    compensation = CompensationSettings.model_validate(
        dict(config.get("compensation") or {})
    )
    return DriftAssumptions(
        growth_rate=growth,
        raise_rate=compensation.cola_rate + compensation.merit_budget,
    )


def census_file_name(config: dict[str, Any]) -> Optional[str]:
    """The census file name the run was configured with (name only)."""
    path = (config.get("setup") or {}).get("census_parquet_path")
    return Path(str(path)).name if path else None


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------


def _table_columns(conn: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        [table],
    ).fetchall()
    return {str(row[0]).lower() for row in rows}


def _census_columns_with_data(
    conn: duckdb.DuckDBPyConnection, columns: set[str]
) -> set[str]:
    """Value columns present with at least one non-NULL row."""
    present = [column for column in _CENSUS_VALUE_COLUMNS if column in columns]
    if not present:
        return set()
    counts = ", ".join(f"COUNT({column})" for column in present)
    row = conn.execute(f"SELECT {counts} FROM {CENSUS_TABLE}").fetchone()
    assert row is not None
    return {column for column, count in zip(present, row) if count}


def _census_year(conn: duckdb.DuckDBPyConnection) -> Optional[int]:
    """Latest hire year holding at least 1% of rows (as stg_census_data does)."""
    row = conn.execute(f"""
        WITH hires AS (
          SELECT YEAR(TRY_CAST(employee_hire_date AS DATE)) AS hire_year,
            COUNT(*) AS n
          FROM {CENSUS_TABLE}
          GROUP BY 1
        )
        SELECT MAX(hire_year) FROM hires
        WHERE hire_year IS NOT NULL
          AND n >= GREATEST(1, (SELECT SUM(n) FROM hires) * 0.01)
        """).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _value(column: str, available: set[str], alias: str) -> str:
    if column not in available:
        return f"NULL::DOUBLE AS {alias}"
    return f"TRY_CAST({column} AS DOUBLE) AS {alias}"


def _census_population_sql(columns: set[str], available: set[str]) -> str:
    """Census rows reduced to the shared per-employee columns."""
    eligible = (
        "(TRY_CAST(eligibility_entry_date AS DATE) IS NULL "
        "OR TRY_CAST(eligibility_entry_date AS DATE) <= $as_of)"
        if "eligibility_entry_date" in available
        else "TRUE"
    )
    still_employed = (
        "(TRY_CAST(employee_termination_date AS DATE) IS NULL "
        "OR TRY_CAST(employee_termination_date AS DATE) > $as_of)"
        if "employee_termination_date" in columns
        else "TRUE"
    )
    return f"""
        SELECT
          {_value("employee_plan_year_compensation", available, "_pay")},
          {_value("employee_deferral_rate", available, "_deferral")},
          {_value("employer_match_contribution", available, "_match")},
          {_value("employer_core_contribution", available, "_core")},
          {eligible} AS _eligible
        FROM {CENSUS_TABLE}
        WHERE {active_filter_sql(columns)} AND {still_employed}
    """


def _simulated_population_sql(use_eligibility: bool) -> str:
    """First-simulated-year snapshot rows reduced to the shared columns."""
    eligible = (
        "LOWER(current_eligibility_status) = 'eligible'" if use_eligibility else "TRUE"
    )
    return f"""
        SELECT
          CAST(prorated_annual_compensation AS DOUBLE) AS _pay,
          CASE WHEN is_enrolled_flag
            THEN COALESCE(CAST(current_deferral_rate AS DOUBLE), 0) ELSE 0 END
            AS _deferral,
          CAST(employer_match_amount AS DOUBLE) AS _match,
          CAST(employer_core_amount AS DOUBLE) AS _core,
          {eligible} AS _eligible
        FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
        WHERE simulation_year = $year AND UPPER(employment_status) = 'ACTIVE'
    """


def _aggregate(
    conn: duckdb.DuckDBPyConnection, population_sql: str, params: dict[str, Any]
) -> dict[str, Optional[float]]:
    cursor = conn.execute(f"WITH pop AS ({population_sql}) {_AGGREGATE_SQL}", params)
    row = cursor.fetchone()
    assert row is not None and cursor.description is not None
    names = [column[0] for column in cursor.description]
    return {
        name: float(value) if value is not None else None
        for name, value in zip(names, row)
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Measured:
    census_year: int
    first_year: int
    census: dict[str, Optional[float]]
    simulated: dict[str, Optional[float]]


class CensusTieOutService:
    """Compare a run's archived census with its first simulated year."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ) -> None:
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    def get_tie_out(
        self, workspace_id: str, scenario_id: str, scenario_name: str
    ) -> CensusTieOut:
        result = CensusTieOut(
            scenario_id=scenario_id, scenario_name=scenario_name, available=False
        )
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if resolved.source != "run" or resolved.path is None:
            return result.model_copy(update={"unavailable_reason": NO_RUN_REASON})
        config = load_run_config(resolved.config_path)
        result = result.model_copy(
            update={"run_id": resolved.run_id, "census_file": census_file_name(config)}
        )
        with duckdb.connect(str(resolved.path), read_only=True) as conn:
            measured = self._measure(conn)
        if isinstance(measured, str):
            return result.model_copy(update={"unavailable_reason": measured})
        assumptions = drift_assumptions(config)
        rows = [
            build_row(
                spec,
                measured.census[spec.metric],
                measured.simulated[spec.metric] or 0.0,
                assumptions,
            )
            for spec in _METRICS
        ]
        return result.model_copy(
            update={
                "available": True,
                "census_year": measured.census_year,
                "census_as_of_date": date(measured.census_year, 12, 31),
                "first_simulated_year": measured.first_year,
                "growth_rate": assumptions.growth_rate,
                "raise_rate": assumptions.raise_rate,
                "rows": rows,
            }
        )

    @staticmethod
    def _measure(conn: duckdb.DuckDBPyConnection) -> _Measured | str:
        """Measure both sides, or return why the tie-out is unavailable."""
        columns = _table_columns(conn, CENSUS_TABLE)
        if not columns:
            return NO_ARCHIVED_CENSUS_REASON
        if not _table_columns(conn, TABLE_FCT_WORKFORCE_SNAPSHOT):
            return NO_SNAPSHOT_REASON
        census_year = _census_year(conn)
        if census_year is None:
            return NO_CENSUS_YEAR_REASON
        first_row = conn.execute(
            f"SELECT MIN(simulation_year) FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}"
        ).fetchone()
        if first_row is None or first_row[0] is None:
            return NO_SNAPSHOT_REASON
        first_year = int(first_row[0])
        available = _census_columns_with_data(conn, columns)
        census = _aggregate(
            conn,
            _census_population_sql(columns, available),
            {"as_of": date(census_year, 12, 31)},
        )
        simulated = _aggregate(
            conn,
            _simulated_population_sql("eligibility_entry_date" in available),
            {"year": first_year},
        )
        for spec in _METRICS:
            if spec.census_column and spec.census_column not in available:
                census[spec.metric] = None
        return _Measured(census_year, first_year, census, simulated)
