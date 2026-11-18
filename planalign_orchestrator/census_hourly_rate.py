"""Census hourly rate inputs (#1230).

A census may give each person an hourly rate in one of three columns, in this
order of precedence:

- ``hourly_rate``: the rate as given. Preferred, because pay divided by hours
  overstates the base rate for people with overtime premium or bonuses.
- ``hours_worked``: all paid hours in the census year, overtime included. The
  rate is census-year pay divided by these hours.
- ``scheduled_hours_per_week``: the rate is the annual pay rate divided by
  (hours x 52). Only right when census pay is an annual rate.

A row with none of them is not hourly. Hours are never inferred. A rate below
or above the plausible bounds keeps the person in the census with no rate.

``stg_census_data`` derives the rate the simulation uses. The summary here is
the import-time report and takes census pay as given for both derived columns.
Staging applies ``census_pay_basis``: it annualizes part-year earnings for
``scheduled_hours_per_week`` and prorates an annual rate for ``hours_worked``.
So a part-year person's derived rate, and whether it falls in bounds, can
differ between this report and the simulation. A given ``hourly_rate`` is the
same in both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Collection, Dict, Tuple

import duckdb
import yaml

# Census columns that give an hourly rate, highest precedence first.
HOURLY_RATE_COLUMNS: Tuple[str, ...] = (
    "hourly_rate",
    "hours_worked",
    "scheduled_hours_per_week",
)

_DBT_PROJECT = Path(__file__).resolve().parents[1] / "dbt" / "dbt_project.yml"


@lru_cache(maxsize=1)
def hourly_rate_bounds() -> Tuple[float, float]:
    """The plausible hourly rate range, from the dbt project vars."""
    project = yaml.safe_load(_DBT_PROJECT.read_text())
    variables = project["vars"]
    return (
        float(variables["census_hourly_rate_min"]),
        float(variables["census_hourly_rate_max"]),
    )


@dataclass(frozen=True)
class HourlyRateSummary:
    """How many census rows have a usable hourly rate, and from which column."""

    columns_present: Tuple[str, ...]
    with_rate: int
    blank: int
    out_of_bounds: int
    multiple_columns: int
    minimum_rate: float
    maximum_rate: float
    by_source: Dict[str, int] = field(default_factory=dict)


def _number(column: str, present: Collection[str]) -> str:
    if column not in present:
        return "CAST(NULL AS DOUBLE)"
    return f'TRY_CAST("{column}" AS DOUBLE)'


def _rate_sql(present: Collection[str]) -> Tuple[str, str]:
    """The SQL for each row's chosen column and its rate, by precedence."""
    rate = _number("hourly_rate", present)
    hours = _number("hours_worked", present)
    weekly = _number("scheduled_hours_per_week", present)
    pay = _number("employee_gross_compensation", present)
    source = f"""CASE WHEN {rate} IS NOT NULL THEN 'hourly_rate'
      WHEN {hours} IS NOT NULL THEN 'hours_worked'
      WHEN {weekly} IS NOT NULL THEN 'scheduled_hours_per_week' END"""
    value = f"""CASE WHEN {rate} IS NOT NULL THEN {rate}
      WHEN {hours} IS NOT NULL THEN {pay} / NULLIF({hours}, 0)
      WHEN {weekly} IS NOT NULL THEN {pay} / NULLIF({weekly} * 52, 0) END"""
    return source, value


def summarize_hourly_rates(
    conn: duckdb.DuckDBPyConnection, table: str, columns: Collection[str]
) -> HourlyRateSummary | None:
    """Count rates in ``table``, or None when it has none of the rate columns.

    ``table`` must be a trusted identifier, not user input.
    """
    present = tuple(c for c in HOURLY_RATE_COLUMNS if c in columns)
    if not present:
        return None
    low, high = hourly_rate_bounds()
    source, value = _rate_sql(columns)
    filled = " + ".join(f'CAST("{c}" IS NOT NULL AS INTEGER)' for c in present)
    rows = conn.execute(
        f"""
        WITH rates AS (
          SELECT {source} AS source, {value} AS rate, {filled} AS filled
          FROM {table}
        )
        SELECT source, rate BETWEEN ? AND ? AS in_bounds,
          COUNT(*), COUNT(*) FILTER (WHERE filled > 1)
        FROM rates GROUP BY ALL
        """,
        [low, high],
    ).fetchall()
    return _tally(rows, present, low, high)


def _tally(
    rows: list[tuple[str | None, bool | None, int, int]],
    present: Tuple[str, ...],
    low: float,
    high: float,
) -> HourlyRateSummary:
    """Fold the grouped (source, in_bounds, count, multi) rows into a summary."""
    by_source: Dict[str, int] = {}
    blank = out_of_bounds = multiple = 0
    for row_source, in_bounds, count, multi in rows:
        multiple += int(multi)
        if row_source is None:
            blank += int(count)
        elif in_bounds:
            by_source[row_source] = by_source.get(row_source, 0) + int(count)
        else:
            out_of_bounds += int(count)
    return HourlyRateSummary(
        columns_present=present,
        with_rate=sum(by_source.values()),
        blank=blank,
        out_of_bounds=out_of_bounds,
        multiple_columns=multiple,
        minimum_rate=low,
        maximum_rate=high,
        by_source=by_source,
    )
