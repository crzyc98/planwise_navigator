"""Read simulation results from a DuckDB database."""

import logging
from typing import Any, Dict, List, Optional, Tuple

import duckdb

from planalign_core.constants import (
    TABLE_FCT_WORKFORCE_SNAPSHOT,
    TABLE_FCT_YEARLY_EVENTS,
)

from ...constants import DEFAULT_PARTICIPATION_RATE
from ...models.simulation import MinimumWageYear, SimulationResults
from ...storage.workspace_storage import WorkspaceStorage
from ..database_path_resolver import DatabasePathResolver, ResolvedDatabasePath

logger = logging.getLogger(__name__)


def _population_filter(population: str) -> str:
    """Return a SQL WHERE clause fragment for population filtering."""
    if population == "active":
        return " AND LOWER(employment_status) = 'active'"
    elif population == "terminated":
        return " AND LOWER(employment_status) != 'active'"
    return ""


def read_results(
    workspace_id: str,
    scenario_id: str,
    storage: WorkspaceStorage,
    db_resolver: DatabasePathResolver,
    population: str = "active",
) -> Optional[SimulationResults]:
    """Query DuckDB for workforce progression, events, and compensation.

    Args:
        workspace_id: Workspace identifier.
        scenario_id: Scenario identifier.
        storage: Workspace storage for config lookup.
        db_resolver: Resolves the correct database path.
        population: Population filter - "all", "active", or "terminated".

    Returns:
        SimulationResults if data is available, else None.
    """
    resolved = db_resolver.resolve(workspace_id, scenario_id)
    if not resolved.exists:
        logger.warning(f"No database found for scenario {scenario_id}")
        return None
    config_start_year, config_end_year = _get_year_range(
        resolved, storage, workspace_id, scenario_id
    )

    db_source: str = (
        "global (shared - may show data from other scenarios)"
        if resolved.source == "project"
        else str(resolved.source)
    )
    logger.info(f"Loading results from {db_source} database: {resolved.path}")

    try:
        conn = duckdb.connect(str(resolved.path), read_only=True)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None

    try:
        pop_filter = _population_filter(population)

        workforce_progression = _query_workforce_progression(
            conn, config_start_year, config_end_year, pop_filter
        )
        compensation_by_status = _query_compensation_by_status(
            conn, config_start_year, config_end_year, pop_filter
        )
        event_trends = _query_event_trends(conn, config_start_year, config_end_year)
        minimum_wage = _query_minimum_wage(conn, config_start_year, config_end_year)
        participation_rate = _query_participation_rate(
            conn, config_end_year, pop_filter
        )
    except Exception as e:
        logger.error(f"Failed to load results: {e}")
        return None
    finally:
        conn.close()

    cagr_metrics, summary = _compute_cagr_metrics(workforce_progression)

    return SimulationResults(
        scenario_id=scenario_id,
        run_id=resolved.run_id or "legacy",
        start_year=config_start_year,
        end_year=config_end_year,
        final_headcount=summary["final_headcount"],
        total_growth_pct=summary["total_growth_pct"],
        cagr=summary["cagr"],
        participation_rate=participation_rate,
        workforce_progression=workforce_progression,
        event_trends=event_trends,
        minimum_wage=minimum_wage,
        growth_analysis={
            "total_growth_pct": summary["total_growth_pct"],
            "cagr": summary["cagr"],
        },
        compensation_by_status=compensation_by_status,
        cagr_metrics=cagr_metrics,
    )


# ---------------------------------------------------------------------------
# Private query helpers
# ---------------------------------------------------------------------------


def _get_year_range(
    resolved: ResolvedDatabasePath,
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario_id: str,
) -> Tuple[int, int]:
    if resolved.start_year is not None and resolved.end_year is not None:
        return resolved.start_year, resolved.end_year
    config = storage.get_merged_config(workspace_id, scenario_id)
    if config:
        sim_config = config.get("simulation", {})
        return (
            int(sim_config.get("start_year", 2025)),
            int(sim_config.get("end_year", 2027)),
        )
    return 2025, 2027


def _query_workforce_progression(
    conn: duckdb.DuckDBPyConnection,
    start_year: int,
    end_year: int,
    pop_filter: str = "",
) -> List[Dict[str, Any]]:
    try:
        df = conn.execute(
            f"""
            SELECT
                simulation_year,
                COUNT(DISTINCT employee_id) as headcount,
                AVG(prorated_annual_compensation) as avg_compensation,
                SUM(prorated_annual_compensation) as total_compensation,
                AVG(prorated_annual_compensation) as active_avg_compensation
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year >= ?
              AND simulation_year <= ?
              {pop_filter}
            GROUP BY simulation_year
            ORDER BY simulation_year
        """,
            [start_year, end_year],
        ).fetchdf()
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"Error fetching workforce progression: {e}")
        return []


def _query_compensation_by_status(
    conn: duckdb.DuckDBPyConnection,
    start_year: int,
    end_year: int,
    pop_filter: str = "",
) -> List[Dict[str, Any]]:
    try:
        df = conn.execute(
            f"""
            SELECT
                simulation_year,
                detailed_status_code as employment_status,
                COUNT(DISTINCT employee_id) as employee_count,
                AVG(prorated_annual_compensation) as avg_compensation
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year >= ?
              AND simulation_year <= ?
              {pop_filter}
            GROUP BY simulation_year, detailed_status_code
            ORDER BY simulation_year, detailed_status_code
        """,
            [start_year, end_year],
        ).fetchdf()
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"Error fetching compensation by status: {e}")
        return []


def _query_event_trends(
    conn: duckdb.DuckDBPyConnection, start_year: int, end_year: int
) -> Dict[str, List[int]]:
    try:
        df = conn.execute(
            f"""
            SELECT
                event_type,
                simulation_year,
                COUNT(*) as count
            FROM {TABLE_FCT_YEARLY_EVENTS}
            WHERE simulation_year >= ?
              AND simulation_year <= ?
            GROUP BY event_type, simulation_year
            ORDER BY event_type, simulation_year
        """,
            [start_year, end_year],
        ).fetchdf()

        years = list(range(start_year, end_year + 1))
        year_index = {year: i for i, year in enumerate(years)}
        event_trends: Dict[str, List[int]] = {}
        for _, row in df.iterrows():
            event_type = row["event_type"]
            if event_type not in event_trends:
                event_trends[event_type] = [0] * len(years)
            event_trends[event_type][year_index[int(row["simulation_year"])]] = int(
                row["count"]
            )
        return event_trends
    except Exception as e:
        logger.error(f"Error fetching event trends: {e}")
        return {}


TABLE_FCT_MINIMUM_WAGE_STEPS = "fct_minimum_wage_steps"
EVENT_MINIMUM_WAGE = "minimum_wage"

_MINIMUM_WAGE_STEPS_SQL = f"""
    SELECT simulation_year, effective_date, minimum_hourly_rate, people_raised,
      people_with_rate, people_without_rate, people_not_covered, added_annual_pay
    FROM {TABLE_FCT_MINIMUM_WAGE_STEPS}
    WHERE simulation_year BETWEEN ? AND ?
"""

# Everyone a step raised up to each year, still active at its end: their
# year-end pay times the share of it the floor added, 1 - 1/(product of ratios).
_MINIMUM_WAGE_CARRYOVER_SQL = f"""
    WITH ratios AS (
      SELECT employee_id, simulation_year,
        compensation_amount / previous_compensation AS ratio
      FROM {TABLE_FCT_YEARLY_EVENTS}
      WHERE event_type = '{EVENT_MINIMUM_WAGE}' AND previous_compensation > 0
    ),
    factors AS (
      SELECT s.simulation_year, s.current_compensation, PRODUCT(r.ratio) AS factor
      FROM {TABLE_FCT_WORKFORCE_SNAPSHOT} s
      JOIN ratios r
        ON r.employee_id = s.employee_id AND r.simulation_year <= s.simulation_year
      WHERE s.simulation_year BETWEEN ? AND ?
        AND LOWER(s.employment_status) = 'active'
      GROUP BY s.simulation_year, s.employee_id, s.current_compensation
    )
    SELECT simulation_year, COUNT(*),
      COALESCE(SUM(current_compensation * (1 - 1 / factor)), 0)
    FROM factors
    GROUP BY simulation_year
"""


def _has_table(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) > 0 FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = ?",
        [table],
    ).fetchone()
    return bool(row and row[0])


def _query_minimum_wage(
    conn: duckdb.DuckDBPyConnection, start_year: int, end_year: int
) -> List[MinimumWageYear]:
    """The run's minimum wage by year, or empty when it has no step.

    Results built before the minimum wage (#1229) have no steps table.
    """
    try:
        if not _has_table(conn, TABLE_FCT_MINIMUM_WAGE_STEPS):
            return []
        steps = conn.execute(_MINIMUM_WAGE_STEPS_SQL, [start_year, end_year]).fetchall()
        if not steps:
            return []
        carryover = conn.execute(
            _MINIMUM_WAGE_CARRYOVER_SQL, [start_year, end_year]
        ).fetchall()
    except Exception as e:
        logger.error(f"Error fetching minimum wage results: {e}")
        return []
    step_fields = (
        "effective_date",
        "minimum_hourly_rate",
        "people_raised",
        "people_with_rate",
        "people_without_rate",
        "people_not_covered",
        "added_annual_pay",
    )
    by_year: Dict[int, Dict[str, Any]] = {
        int(row[0]): dict(zip(step_fields, row[1:])) for row in steps
    }
    still_active = {int(year): (int(n), float(pay)) for year, n, pay in carryover}
    return [
        MinimumWageYear(
            simulation_year=year,
            **by_year.get(year, {}),
            raised_still_active=still_active.get(year, (0, 0.0))[0],
            estimated_added_pay=still_active.get(year, (0, 0.0))[1],
        )
        for year in range(start_year, end_year + 1)
    ]


def _query_participation_rate(
    conn: duckdb.DuckDBPyConnection, end_year: int, pop_filter: str = ""
) -> float:
    try:
        df = conn.execute(
            f"""
            SELECT
                COUNT(DISTINCT CASE WHEN participation_status = 'participating' THEN employee_id END) as participating,
                COUNT(DISTINCT employee_id) as total_eligible
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ?
              {pop_filter}
        """,
            [end_year],
        ).fetchdf()

        if not df.empty:
            participating = df["participating"].iloc[0] or 0
            total_eligible = df["total_eligible"].iloc[0] or 0
            if total_eligible > 0:
                rate = participating / total_eligible
                logger.info(
                    f"Calculated participation rate: {rate:.2%} "
                    f"({participating}/{total_eligible})"
                )
                return rate
    except Exception as e:
        logger.warning(f"Error calculating participation rate, using default: {e}")

    return DEFAULT_PARTICIPATION_RATE


def _calc_cagr(start_val: float, end_val: float, n_years: int) -> float:
    if start_val > 0 and n_years > 0:
        return ((end_val / start_val) ** (1 / n_years) - 1) * 100
    return 0.0


def _compute_cagr_metrics(
    workforce_progression: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Derive CAGR metrics and summary stats from workforce progression rows.

    Returns:
        Tuple of (cagr_metrics list, summary dict).
    """
    if not workforce_progression:
        return [], {
            "start_year": 2025,
            "end_year": 2027,
            "final_headcount": 0,
            "total_growth_pct": 0,
            "cagr": 0,
        }

    start_headcount = workforce_progression[0].get("headcount", 0)
    final_headcount = workforce_progression[-1].get("headcount", 0)
    start_year = workforce_progression[0].get("simulation_year", 2025)
    end_year = workforce_progression[-1].get("simulation_year", 2027)
    years = end_year - start_year

    total_growth_pct = (
        ((final_headcount - start_headcount) / start_headcount * 100)
        if start_headcount > 0
        else 0
    )
    cagr = _calc_cagr(start_headcount, final_headcount, years)

    start_total_comp = workforce_progression[0].get("total_compensation", 0) or 0
    end_total_comp = workforce_progression[-1].get("total_compensation", 0) or 0
    start_avg_comp = workforce_progression[0].get("active_avg_compensation", 0) or 0
    end_avg_comp = workforce_progression[-1].get("active_avg_compensation", 0) or 0

    cagr_metrics = [
        {
            "metric": "Total Headcount",
            "start_value": start_headcount,
            "end_value": final_headcount,
            "years": years,
            "cagr_pct": round(_calc_cagr(start_headcount, final_headcount, years), 2),
        },
        {
            "metric": "Total Compensation",
            "start_value": round(start_total_comp, 2),
            "end_value": round(end_total_comp, 2),
            "years": years,
            "cagr_pct": round(_calc_cagr(start_total_comp, end_total_comp, years), 2),
        },
        {
            "metric": "Average Compensation",
            "start_value": round(start_avg_comp, 2),
            "end_value": round(end_avg_comp, 2),
            "years": years,
            "cagr_pct": round(_calc_cagr(start_avg_comp, end_avg_comp, years), 2),
        },
    ]

    summary = {
        "start_year": start_year,
        "end_year": end_year,
        "final_headcount": final_headcount,
        "total_growth_pct": total_growth_pct,
        "cagr": cagr,
    }

    return cagr_metrics, summary
