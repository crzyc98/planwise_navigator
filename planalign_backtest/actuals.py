"""Extract held-out actual metrics in a scoring-only DuckDB connection."""

from __future__ import annotations

from collections.abc import MutableMapping

import duckdb

from planalign_backtest.models import MetricValue
from planalign_fit.bands import BandDefinitions
from planalign_fit.snapshots import SnapshotSet
from planalign_fit.transitions import build_transitions
from planalign_fit.promotion import DEFAULT_LEVEL_COVERAGE_THRESHOLD


def _put_grouped_counts(conn, year: int, column: str, prefix: str, target) -> None:
    rows = conn.execute(
        f"SELECT CAST({column} AS VARCHAR), COUNT(*) FROM banded_{year} "
        f"WHERE is_active AND {column} IS NOT NULL GROUP BY {column} ORDER BY {column}"
    ).fetchall()
    for label, count in rows:
        target[MetricValue(metric=f"{prefix}.{label}", period=year)] = float(count)


def _put_grouped_counts_expr(conn, year: int, expr: str, prefix: str, target) -> None:
    rows = conn.execute(
        f"SELECT CAST(({expr}) AS VARCHAR) AS bucket, COUNT(*) FROM banded_{year} "
        f"WHERE is_active AND ({expr}) IS NOT NULL GROUP BY bucket ORDER BY bucket"
    ).fetchall()
    for label, count in rows:
        target[MetricValue(metric=f"{prefix}.{label}", period=year)] = float(count)


def _snapshot_metrics(conn, year: int, bands: BandDefinitions, target) -> None:
    row = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(compensation), 0), "
        f"COALESCE(AVG(compensation), 0), "
        f"AVG(CASE WHEN is_enrolled THEN 1.0 ELSE 0.0 END), "
        f"AVG(deferral_rate) FROM banded_{year} WHERE is_active"
    ).fetchone()
    if row is None:
        raise ValueError(f"Could not extract actual snapshot metrics for {year}")
    for metric, value in (
        ("headcount.total", row[0]),
        ("compensation.total", row[1]),
        ("compensation.average", row[2]),
        ("plan.participation_rate", row[3]),
        ("plan.average_deferral_rate", row[4]),
    ):
        target[MetricValue(metric=metric, period=year)] = (
            None if value is None else float(value)
        )
    # Level is band-derived from compensation on BOTH sides, even when the census
    # supplies an authoritative level_id. int_baseline_workforce assigns the
    # simulator's level by matching compensation ranges and never reads a census
    # level column, so scoring census levels against simulated ones compares two
    # different definitions — measured at 76% per-employee agreement, which turns
    # a definitional gap into apparent model error (FR-014). The scorecard records
    # `level_basis: compensation_band` so a reader knows what by-level means.
    _put_grouped_counts_expr(
        conn, year, bands.level_case("compensation"), "headcount.by_level", target
    )
    _put_grouped_counts(conn, year, "age_band", "headcount.by_age_band", target)
    _put_grouped_counts(conn, year, "tenure_band", "headcount.by_tenure_band", target)


def _flow_metrics(conn, year: int, level_observable: bool, target) -> None:
    transition = conn.execute(
        "SELECT SUM(CASE WHEN terminated THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN promoted THEN 1 ELSE 0 END) "
        "FROM fit_transitions WHERE to_year = ?",
        [year],
    ).fetchone()
    hires = conn.execute(
        "SELECT COUNT(*) FROM fit_new_hires WHERE to_year = ?", [year]
    ).fetchone()
    target[MetricValue(metric="flows.terminations", period=year)] = float(
        (transition or (0,))[0] or 0
    )
    target[MetricValue(metric="flows.hires", period=year)] = float(
        (hires or (0,))[0] or 0
    )
    target[MetricValue(metric="flows.promotions", period=year)] = (
        float((transition or (0, 0))[1] or 0) if level_observable else None
    )


def _add_cumulative(values: MutableMapping[MetricValue, float | None], years) -> None:
    metrics = sorted({key.metric for key in values})
    sum_metrics = {
        "flows.terminations",
        "flows.hires",
        "flows.promotions",
        "plan.employer_match_cost",
    }
    for metric in metrics:
        keys = [MetricValue(metric=metric, period=year) for year in years]
        yearly = [values.get(key, 0.0) for key in keys]
        if metric in sum_metrics and any(
            key in values and values[key] is None for key in keys
        ):
            result = None
        elif metric in sum_metrics:
            result = sum(float(value) for value in yearly if value is not None)
        else:
            result = yearly[-1]
        values[MetricValue(metric=metric, period="cumulative")] = result


def extract_actuals(
    snapshot_set: SnapshotSet,
    split,
    bands: BandDefinitions,
) -> dict[MetricValue, float | None]:
    """Read actuals without sharing a connection with any estimator."""
    values: dict[MetricValue, float | None] = {}
    with duckdb.connect(":memory:") as conn:
        transitions = build_transitions(conn, snapshot_set, bands)
        level_observable = (
            transitions.observability.level_coverage >= DEFAULT_LEVEL_COVERAGE_THRESHOLD
        )
        for year in split.holdout_years:
            _snapshot_metrics(conn, year, bands, values)
            _flow_metrics(conn, year, level_observable, values)
            snapshot = next(item for item in snapshot_set if item.year == year)
            if not snapshot.has("employee_deferral_rate"):
                values[
                    MetricValue(metric="plan.average_deferral_rate", period=year)
                ] = None
            # Employer match cost is never derived from a census. A census records
            # deferral rates, not match transactions, so any figure here would come
            # from assuming a match formula the plan may not use. Scored against
            # the real match engine, a "50% of first 6%" proxy ran +24% — an
            # artefact of the assumption, not a modelling error (FR-012).
            values[MetricValue(metric="plan.employer_match_cost", period=year)] = None
            if not any(
                snapshot.has(column)
                for column in ("employee_enrollment_date", "employee_deferral_rate")
            ):
                values[
                    MetricValue(metric="plan.participation_rate", period=year)
                ] = None
    _add_cumulative(values, split.holdout_years)
    return values
