"""Roll an old census forward into a bridge census (#1078).

A census more than a year behind the simulation start skips the missing
years' hires, so first-year turnover runs low. Rolling forward simulates the
missing years once, under the given config, and writes the employees still
active at the last year-end as a new census. Every scenario then starts from
the same bridged workforce, and no scenario's plan changes touch the bridge.

The bridge census works under the original's pay setting
(``setup.census_pay_basis``), so that setting stays right for both files. It
holds each employee's year-end rate, except under ``earnings`` for people hired
in the bridge year: they get their part-year earnings, which staging turns
back into an annual rate. People the simulation hired carry
``simulated_employee = TRUE``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

import duckdb

from .census_year import infer_census_year
from .config import SimulationConfig
from .construction import ConstructionSpec, build_orchestrator
from .utils import DatabaseConnectionManager

logger = logging.getLogger(__name__)

# Census columns the simulation doesn't track, copied from the original census
# for employees who were in it.
CARRIED_COLUMNS: Tuple[str, ...] = (
    "scheduled_hours_per_week",
    "auto_escalation_opt_out",
    "eligibility_override",
    "department",
    "location",
)


@dataclass(frozen=True)
class RollForwardResult:
    """What a roll-forward produced."""

    census_path: Path
    census_year: int
    bridge_year: int
    hires: int
    terminations: int
    ending_headcount: int
    simulated_employees: int


def roll_forward_census(
    config: SimulationConfig,
    census_path: Path,
    target_year: int,
    output_path: Path,
    database_path: Path,
) -> RollForwardResult:
    """Simulate from the census year to ``target_year`` and save the bridge census.

    ``database_path`` holds the bridge simulation and must not be a database
    in use by anything else; it is kept so the bridge can be inspected. A
    config that sets ``setup.plan_year_start_date``/``plan_year_end_date`` by
    hand must move them to ``target_year`` to use the bridge census.
    """
    census_year = _census_year_before(census_path, target_year)
    bridge_config = _bridge_config(config, census_path, census_year + 1, target_year)
    _simulate(bridge_config, database_path)
    pay_basis = str(_setup(config).get("census_pay_basis", "earnings"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path), read_only=True) as conn:
        _write_census(conn, census_path, target_year, pay_basis, output_path)
        hires, terminations = _event_counts(conn, census_year + 1, target_year)
        ending, simulated = _census_counts(conn, output_path)

    result = RollForwardResult(
        census_path=output_path,
        census_year=census_year,
        bridge_year=target_year,
        hires=hires,
        terminations=terminations,
        ending_headcount=ending,
        simulated_employees=simulated,
    )
    logger.info("Rolled the census forward: %s", result)
    return result


def _census_year_before(census_path: Path, target_year: int) -> int:
    census_year = infer_census_year(census_path)
    if census_year is None:
        raise ValueError(f"Could not find a census year in {census_path}")
    if target_year <= census_year:
        raise ValueError(
            f"The census is already from {census_year}; nothing to roll forward "
            f"to {target_year}"
        )
    return census_year


def _setup(config: SimulationConfig) -> Dict[str, Any]:
    setup = getattr(config, "setup", None)
    return dict(setup) if isinstance(setup, dict) else {}


def _bridge_config(
    config: SimulationConfig, census_path: Path, start_year: int, end_year: int
) -> SimulationConfig:
    """The config for the bridge years: same settings, the given census."""
    simulation = config.simulation.model_copy(
        update={"start_year": start_year, "end_year": end_year}
    )
    setup = _setup(config)
    setup["census_parquet_path"] = str(census_path.resolve())
    return config.model_copy(update={"simulation": simulation, "setup": setup})


def _simulate(config: SimulationConfig, database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    result = build_orchestrator(
        ConstructionSpec(
            config=config,
            database=DatabaseConnectionManager(database_path),
            entry_point="census_roll_forward",
        )
    )
    orchestrator = result.orchestrator
    orchestrator.construction_signature = result.signature
    orchestrator.execute_multi_year_simulation(
        start_year=config.simulation.start_year,
        end_year=config.simulation.end_year,
        fail_on_validation_error=False,
    )


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _carried_columns(conn: duckdb.DuckDBPyConnection, census_path: Path) -> list[str]:
    rows = conn.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{_sql_path(census_path)}')"
    ).fetchall()
    present = {row[0] for row in rows}
    return [column for column in CARRIED_COLUMNS if column in present]


def _pay_column(pay_basis: str, year: int) -> str:
    """Each employee's year-end rate, as staging will read it back.

    Under earnings, staging takes earnings as the rate except for hires in the
    census year, whose part-year earnings it annualizes.
    """
    if pay_basis == "annual_rate":
        return "s.current_compensation"
    return f"""CASE WHEN YEAR(s.employee_hire_date) = {int(year)}
              THEN s.prorated_annual_compensation
              ELSE s.current_compensation END"""


def _write_census(
    conn: duckdb.DuckDBPyConnection,
    census_path: Path,
    year: int,
    pay_basis: str,
    output_path: Path,
) -> None:
    """Write the year-end active workforce in census format."""
    pay = _pay_column(pay_basis, year)
    carried = "".join(f", c.{column}" for column in _carried_columns(conn, census_path))
    conn.execute(f"""
        COPY (
          WITH census AS (
            SELECT *, CAST(employee_id AS VARCHAR) AS census_employee_id
            FROM read_parquet('{_sql_path(census_path)}')
            QUALIFY ROW_NUMBER() OVER (
              PARTITION BY CAST(employee_id AS VARCHAR)
              ORDER BY TRY_CAST(employee_hire_date AS DATE) DESC
            ) = 1
          )
          SELECT
            s.employee_id,
            -- Simulated hires' SSNs would collide with the next run's hires;
            -- staging gives a census row without one a placeholder outside
            -- that range.
            CASE WHEN c.census_employee_id IS NOT NULL THEN s.employee_ssn
              END AS employee_ssn,
            CAST(s.employee_birth_date AS DATE) AS employee_birth_date,
            CAST(s.employee_hire_date AS DATE) AS employee_hire_date,
            CAST(NULL AS DATE) AS employee_termination_date,
            {pay} AS employee_gross_compensation,
            TRUE AS active,
            CASE WHEN s.is_enrolled_flag THEN COALESCE(s.current_deferral_rate, 0)
              ELSE 0 END AS employee_deferral_rate,
            s.employee_eligibility_date AS eligibility_entry_date
            {carried},
            c.census_employee_id IS NULL AS simulated_employee
          FROM fct_workforce_snapshot s
          LEFT JOIN census c ON c.census_employee_id = CAST(s.employee_id AS VARCHAR)
          WHERE s.simulation_year = {int(year)} AND s.employment_status = 'active'
          ORDER BY s.employee_id
        ) TO '{_sql_path(output_path)}' (FORMAT PARQUET)
        """)


def _event_counts(
    conn: duckdb.DuckDBPyConnection, start_year: int, end_year: int
) -> Tuple[int, int]:
    row = conn.execute(
        """
        SELECT COUNT(*) FILTER (WHERE event_type = 'hire'),
          COUNT(*) FILTER (WHERE event_type = 'termination')
        FROM fct_yearly_events
        WHERE simulation_year BETWEEN ? AND ?
        """,
        [start_year, end_year],
    ).fetchone()
    return (int(row[0]), int(row[1])) if row else (0, 0)


def _census_counts(
    conn: duckdb.DuckDBPyConnection, output_path: Path
) -> Tuple[int, int]:
    row = conn.execute(f"""
        SELECT COUNT(*), COUNT(*) FILTER (WHERE simulated_employee)
        FROM read_parquet('{_sql_path(output_path)}')
        """).fetchone()
    return (int(row[0]), int(row[1])) if row else (0, 0)
