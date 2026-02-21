"""Read simulation results from a DuckDB database."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb

from ...constants import DEFAULT_PARTICIPATION_RATE
from ...models.simulation import SimulationResults
from ...storage.workspace_storage import WorkspaceStorage
from ..database_path_resolver import DatabasePathResolver

logger = logging.getLogger(__name__)


def read_results(
    workspace_id: str,
    scenario_id: str,
    storage: WorkspaceStorage,
    db_resolver: DatabasePathResolver,
) -> Optional[SimulationResults]:
    """Query DuckDB for workforce progression, events, and compensation.

    Args:
        workspace_id: Workspace identifier.
        scenario_id: Scenario identifier.
        storage: Workspace storage for config lookup.
        db_resolver: Resolves the correct database path.

    Returns:
        SimulationResults if data is available, else None.
    """
    config_start_year, config_end_year = _get_year_range(
        storage, workspace_id, scenario_id
    )

    try:
        resolved = db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            logger.warning(f"No database found for scenario {scenario_id}")
            return None

        db_source = resolved.source
        if resolved.source == "project":
            db_source = "global (shared - may show data from other scenarios)"

        logger.info(f"Loading results from {db_source} database: {resolved.path}")

        conn = duckdb.connect(str(resolved.path), read_only=True)

        workforce_progression = _query_workforce_progression(
            conn, config_start_year, config_end_year
        )
        compensation_by_status = _query_compensation_by_status(
            conn, config_start_year, config_end_year
        )
        event_trends = _query_event_trends(conn, config_start_year, config_end_year)
        participation_rate = _query_participation_rate(conn, config_end_year)

        conn.close()

        cagr_metrics, summary = _compute_cagr_metrics(workforce_progression)

        return SimulationResults(
            scenario_id=scenario_id,
            run_id="unknown",
            start_year=summary["start_year"],
            end_year=summary["end_year"],
            final_headcount=summary["final_headcount"],
            total_growth_pct=summary["total_growth_pct"],
            cagr=summary["cagr"],
            participation_rate=participation_rate,
            workforce_progression=workforce_progression,
            event_trends=event_trends,
            growth_analysis={
                "total_growth_pct": summary["total_growth_pct"],
                "cagr": summary["cagr"],
            },
            compensation_by_status=compensation_by_status,
            cagr_metrics=cagr_metrics,
        )

    except Exception as e:
        logger.error(f"Failed to load results: {e}")
        return None


# ---------------------------------------------------------------------------
# Private query helpers
# ---------------------------------------------------------------------------


def _get_year_range(
    storage: WorkspaceStorage, workspace_id: str, scenario_id: str
) -> Tuple[int, int]:
    config = storage.get_merged_config(workspace_id, scenario_id)
    if config:
        sim_config = config.get("simulation", {})
        return (
            int(sim_config.get("start_year", 2025)),
            int(sim_config.get("end_year", 2027)),
        )
    return 2025, 2027


def _query_workforce_progression(
    conn: duckdb.DuckDBPyConnection, start_year: int, end_year: int
) -> List[Dict[str, Any]]:
    try:
        df = conn.execute(
            """
            SELECT
                simulation_year,
                COUNT(DISTINCT CASE WHEN LOWER(employment_status) = 'active' THEN employee_id END) as headcount,
                AVG(prorated_annual_compensation) as avg_compensation,
                SUM(CASE WHEN LOWER(employment_status) = 'active' THEN prorated_annual_compensation ELSE 0 END) as total_compensation,
                AVG(CASE WHEN LOWER(employment_status) = 'active' THEN prorated_annual_compensation END) as active_avg_compensation
            FROM fct_workforce_snapshot
            WHERE simulation_year >= ?
              AND simulation_year <= ?
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
    conn: duckdb.DuckDBPyConnection, start_year: int, end_year: int
) -> List[Dict[str, Any]]:
    try:
        df = conn.execute(
            """
            SELECT
                simulation_year,
                detailed_status_code as employment_status,
                COUNT(DISTINCT employee_id) as employee_count,
                AVG(prorated_annual_compensation) as avg_compensation
            FROM fct_workforce_snapshot
            WHERE simulation_year >= ?
              AND simulation_year <= ?
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
            """
            SELECT
                event_type,
                simulation_year,
                COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year >= ?
              AND simulation_year <= ?
            GROUP BY event_type, simulation_year
            ORDER BY event_type, simulation_year
        """,
            [start_year, end_year],
        ).fetchdf()

        event_trends: Dict[str, List[int]] = {}
        for _, row in df.iterrows():
            event_type = row["event_type"]
            if event_type not in event_trends:
                event_trends[event_type] = []
            event_trends[event_type].append(int(row["count"]))
        return event_trends
    except Exception as e:
        logger.error(f"Error fetching event trends: {e}")
        return {}


def _query_participation_rate(
    conn: duckdb.DuckDBPyConnection, end_year: int
) -> float:
    try:
        df = conn.execute(
            """
            SELECT
                COUNT(DISTINCT CASE WHEN participation_status = 'participating' THEN employee_id END) as participating,
                COUNT(DISTINCT employee_id) as total_eligible
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
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
        logger.warning(
            f"Error calculating participation rate, using default: {e}"
        )

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
