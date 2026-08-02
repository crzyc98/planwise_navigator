"""Extract predicted aggregate metrics from one isolated simulation database."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import duckdb

from planalign_backtest.actuals import _add_cumulative
from planalign_backtest.models import MetricValue
from planalign_fit.bands import BandDefinitions, load_band_definitions


def _grouped(conn, year: int, column: str, prefix: str, target) -> None:
    rows = conn.execute(
        f"SELECT CAST({column} AS VARCHAR), COUNT(*) FROM fct_workforce_snapshot "
        "WHERE simulation_year = ? AND employment_status = 'active' "
        f"AND {column} IS NOT NULL GROUP BY {column} ORDER BY {column}",
        [year],
    ).fetchall()
    for label, count in rows:
        target[MetricValue(metric=f"{prefix}.{label}", period=year)] = float(count)


@lru_cache(maxsize=1)
def _bands() -> BandDefinitions:
    """The seed-defined bands, shared with the actuals side."""
    return load_band_definitions()


def _grouped_expr(conn, year: int, expr: str, prefix: str, target) -> None:
    rows = conn.execute(
        f"SELECT CAST(({expr}) AS VARCHAR) AS bucket, COUNT(*) "
        "FROM fct_workforce_snapshot "
        "WHERE simulation_year = ? AND employment_status = 'active' "
        f"AND ({expr}) IS NOT NULL GROUP BY bucket ORDER BY bucket",
        [year],
    ).fetchall()
    for label, count in rows:
        target[MetricValue(metric=f"{prefix}.{label}", period=year)] = float(count)


def _snapshot(conn, year: int, target) -> None:
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(current_compensation), 0), "
        "COALESCE(AVG(current_compensation), 0), "
        "AVG(CASE WHEN is_enrolled_flag THEN 1.0 ELSE 0.0 END), "
        "AVG(current_deferral_rate) FROM fct_workforce_snapshot "
        "WHERE simulation_year = ? AND employment_status = 'active'",
        [year],
    ).fetchone()
    if row is None:
        raise ValueError(f"Could not extract predicted snapshot metrics for {year}")
    for metric, value in (
        ("headcount.total", row[0]),
        ("compensation.total", row[1]),
        ("compensation.average", row[2]),
        ("plan.participation_rate", row[3]),
        ("plan.average_deferral_rate", row[4]),
    ):
        target[MetricValue(metric=metric, period=year)] = float(value or 0)
    # Band-derived from compensation on BOTH sides. The simulator's own level_id
    # is not a re-derivation of current pay: it is seeded by compensation banding
    # at baseline and then moved by promotion events, so it drifts away from what
    # the same banding would say today. Scoring it against a census-derived level
    # compares two different definitions (FR-014); deriving both from pay with
    # the same seed ranges is the one basis available on either side.
    _grouped_expr(
        conn,
        year,
        _bands().level_case("current_compensation"),
        "headcount.by_level",
        target,
    )
    _grouped(conn, year, "age_band", "headcount.by_age_band", target)
    _grouped(conn, year, "tenure_band", "headcount.by_tenure_band", target)


def _experienced_terminations(conn, year: int) -> int:
    """Terminations of employees who were already on the books entering ``year``.

    The actual side counts terminations off ``fit_transitions``, whose exposure
    is the population active at the end of the prior year — an employee hired
    and terminated inside the same year never enters it. Counting every
    termination event here would compare that experienced-cohort figure against
    experienced + new-hire terminations, overstating the error by the entire
    new-hire attrition volume (FR-014).
    """
    row = conn.execute(
        """
        SELECT COUNT(*) FROM fct_yearly_events t
        WHERE t.simulation_year = ? AND UPPER(t.event_type) IN ('TERMINATION', 'TERMINATED')
          AND NOT EXISTS (
            SELECT 1 FROM fct_yearly_events h
            WHERE h.simulation_year = t.simulation_year
              AND h.employee_id = t.employee_id
              AND UPPER(h.event_type) IN ('HIRE', 'NEW_HIRE')
          )
        """,
        [year],
    ).fetchone()
    return int((row or (0,))[0] or 0)


def _flows(conn, year: int, target) -> None:
    counts = dict(
        conn.execute(
            "SELECT UPPER(event_type), COUNT(*) FROM fct_yearly_events "
            "WHERE simulation_year = ? GROUP BY UPPER(event_type)",
            [year],
        ).fetchall()
    )
    aliases = {
        "flows.hires": ("HIRE", "NEW_HIRE"),
        "flows.promotions": ("PROMOTION",),
    }
    for metric, event_types in aliases.items():
        target[MetricValue(metric=metric, period=year)] = float(
            sum(int(counts.get(event_type, 0)) for event_type in event_types)
        )
    target[MetricValue(metric="flows.terminations", period=year)] = float(
        _experienced_terminations(conn, year)
    )
    try:
        match = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM fct_employer_match_events "
            "WHERE simulation_year = ?",
            [year],
        ).fetchone()
        amount = float((match or (0,))[0] or 0)
    except duckdb.CatalogException:
        amount = 0.0
    target[MetricValue(metric="plan.employer_match_cost", period=year)] = amount


def extract_predicted(database: Path | str, split) -> dict[MetricValue, float | None]:
    values: dict[MetricValue, float | None] = {}
    with duckdb.connect(str(database), read_only=True) as conn:
        for year in split.holdout_years:
            _snapshot(conn, year, values)
            _flows(conn, year, values)
    _add_cumulative(values, split.holdout_years)
    return values
