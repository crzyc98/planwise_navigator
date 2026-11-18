"""Run checks for a scheduled minimum wage (#1229).

The floor itself is ``dbt/models/intermediate/events/int_minimum_wage_events.sql``;
each step's counts land in ``fct_minimum_wage_steps``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

import duckdb

from .census_hourly_rate import HOURLY_RATE_COLUMNS
from .exceptions import ConfigurationError

if TYPE_CHECKING:
    from .config import SimulationConfig

logger = logging.getLogger(__name__)

NEEDS_RATES_MESSAGE = (
    "A minimum wage needs an hourly rate per person, but no census row has one. "
    "Add one of these census columns: "
    + ", ".join(HOURLY_RATE_COLUMNS[:-1])
    + f" or {HOURLY_RATE_COLUMNS[-1]}."
)


def warn_unreached_minimum_wage_steps(
    config: "SimulationConfig", start_year: int, end_year: int
) -> List[str]:
    """Warn about minimum wage steps dated outside the simulated years.

    Config loading accepts any date, because calibration and validate-change
    rerun a scenario over a shorter range, so say it loudly instead.
    """
    skipped = [
        f"${step.hourly_rate:.2f} ({step.effective_date.isoformat()})"
        for step in config.compensation.minimum_wage
        if not start_year <= step.effective_date.year <= end_year
    ]
    if skipped:
        logger.warning(
            "MINIMUM WAGE STEPS NOT APPLIED: %s fall outside the simulated years %d-%d",
            ", ".join(skipped),
            start_year,
            end_year,
        )
    return skipped


def require_census_hourly_rates(conn: duckdb.DuckDBPyConnection) -> None:
    """Reject a minimum wage when no census row has a usable hourly rate."""
    (rated,) = conn.execute(
        "SELECT COUNT(census_hourly_rate) FROM stg_census_data"
    ).fetchone()
    if not rated:
        raise ConfigurationError(NEEDS_RATES_MESSAGE)
