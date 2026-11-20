"""Warn about impossible census values once the census is staged (#1262).

Runs the shared plausibility rules (``planalign_core.census_plausibility``) on
``stg_census_data`` and counts the deferral rates the engine rewrites. This
only reports: no row is dropped or changed, so simulation results are the same
with or without it. Messages carry counts only, never row contents (PII).
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

import duckdb

from planalign_core.census_plausibility import (
    census_year_from_hires,
    count_violations,
    deferral_limits_for_year,
)

logger = logging.getLogger(__name__)

STAGED_CENSUS = "stg_census_data"
# ``normalize_deferral_rate`` (dbt/macros/deferral_rate_macros.sql) falls back
# to this when the plan_deferral_cap var is unset.
DEFAULT_PLAN_DEFERRAL_CAP = 0.75

# stg_census_data already uses the canonical census names.
_COLUMNS = {
    name: name
    for name in (
        "employee_id",
        "employee_birth_date",
        "employee_hire_date",
        "employee_termination_date",
        "employee_gross_compensation",
        "employee_capped_compensation",
        "employee_deferral_rate",
        "employee_contribution",
        "pre_tax_contribution",
        "roth_contribution",
        "after_tax_contribution",
        "employer_match_contribution",
        "employer_core_contribution",
    )
}

# The rows normalize_deferral_rate sees: active census participants
# (int_synthetic_baseline_enrollment_events via int_baseline_workforce).
_REWRITTEN_RATES_SQL = f"""
    SELECT
      COUNT(*) FILTER (WHERE employee_deferral_rate > 1),
      COUNT(*) FILTER (WHERE CASE WHEN employee_deferral_rate > 1
          THEN employee_deferral_rate / 100 ELSE employee_deferral_rate END > $cap)
    FROM {STAGED_CENSUS}
    WHERE employee_termination_date IS NULL AND employee_deferral_rate > 0
"""


class WarningSink(Protocol):
    """The part of ``ObservabilityManager`` this step uses."""

    def log_warning(self, message: str, **kwargs: object) -> None: ...


def census_plausibility_warnings(
    conn: duckdb.DuckDBPyConnection, deferral_cap: float = DEFAULT_PLAN_DEFERRAL_CAP
) -> list[str]:
    """One message per broken rule, plus one per kind of deferral rate rewrite."""
    census_year = census_year_from_hires(conn, STAGED_CENSUS, "employee_hire_date")
    if census_year is None:
        return []
    messages = [
        f"Census check: {result.rule.format_message(result.count)}"
        for result in count_violations(
            conn,
            STAGED_CENSUS,
            _COLUMNS,
            census_year,
            deferral_limits_for_year(census_year),
        )
        if result.count
    ]
    return messages + _rewritten_rate_messages(conn, deferral_cap)


def _rewritten_rate_messages(
    conn: duckdb.DuckDBPyConnection, deferral_cap: float
) -> list[str]:
    row = conn.execute(_REWRITTEN_RATES_SQL, {"cap": deferral_cap}).fetchone()
    divided, capped = (int(row[0]), int(row[1])) if row else (0, 0)
    messages = []
    if divided:
        messages.append(
            f"Census check: {divided} active census row(s) have a deferral rate "
            "above 1.0. Deferral escalation and match response read each as a "
            "percentage and divide it by 100."
        )
    if capped:
        messages.append(
            f"Census check: {capped} active census row(s) have a deferral rate "
            f"above the plan deferral cap of {deferral_cap:g}. Deferral "
            "escalation and match response lower each to the cap."
        )
    return messages


def report_census_plausibility(
    conn: duckdb.DuckDBPyConnection,
    sink: Optional[WarningSink],
    deferral_cap: float = DEFAULT_PLAN_DEFERRAL_CAP,
) -> list[str]:
    """Record each census warning on the run; never fails the run."""
    try:
        messages = census_plausibility_warnings(conn, deferral_cap)
    except duckdb.Error as exc:
        # Reporting only: a census the checks can't read must not stop a run
        # the staging models already accepted, so log the failure and move on.
        logger.warning("Census plausibility checks skipped: %s", exc)
        return []
    for message in messages:
        if sink is not None:
            sink.log_warning(message, check="census_plausibility")
        else:
            logger.warning(message)
    return messages
