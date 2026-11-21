"""Report census rows given an imputed termination date (#1249).

``stg_census_data`` gives a row marked inactive with no termination date the
census plan-year end as its termination date, so it leaves the starting
workforce. This records one warning with the count and date, so an analyst can
see that rows were left out. Counts only, never row contents (PII).
"""

from __future__ import annotations

import logging
from typing import Optional

import duckdb

from .census_plausibility_warnings import WarningSink

logger = logging.getLogger(__name__)


def imputed_termination_message(conn: duckdb.DuckDBPyConnection) -> Optional[str]:
    """One line naming the imputed rows and their date, or None if there are none."""
    row = conn.execute("""
        SELECT COUNT(*), MIN(employee_termination_date)
        FROM stg_census_data
        WHERE termination_date_imputed
        """).fetchone()
    if row is None or not row[0]:
        return None
    count, imputed_date = row
    return (
        f"Census check: {count} row(s) are marked inactive with no termination "
        f"date. They were given a termination date of {imputed_date} (the census "
        "plan-year end) and left out of the starting workforce. Give leavers a "
        "termination date in the census to set it yourself."
    )


def report_imputed_terminations(
    conn: duckdb.DuckDBPyConnection, sink: Optional[WarningSink]
) -> Optional[str]:
    """Record the warning on the run when any row was imputed; never fails the run."""
    try:
        message = imputed_termination_message(conn)
    except duckdb.Error as exc:
        # Advisory, like the plausibility check: a run where staging wasn't
        # built (dry run) has no stg_census_data, and that mustn't stop it.
        logger.info("Imputed termination check skipped")
        logger.debug("Imputed termination check skipped: %r", exc)
        return None
    if message is not None:
        if sink is not None:
            sink.log_warning(message, check="census_imputed_terminations")
        else:
            logger.warning(message)
    return message
