"""Warn about impossible census values once the census is staged (#1262).

Runs the shared plausibility rules (``planalign_core.census_plausibility``) on
``stg_census_data``. This only reports: no row is dropped or changed, so
simulation results are the same with or without it. Messages carry rule names
and counts only, never row contents (PII).

A run records one summary warning, not one per rule: Studio's activity feed
keeps only the first 20 warnings of a run, and the census check comes first.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Protocol

import duckdb

from planalign_core.census_plausibility import (
    RuleCount,
    count_violations,
    deferral_limits_for_year,
)

from .census_year import infer_census_year

logger = logging.getLogger(__name__)

STAGED_CENSUS = "stg_census_data"
# Rules named in the summary line before it says "and N more".
SUMMARY_RULE_LIMIT = 5

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


class WarningSink(Protocol):
    """The part of ``ObservabilityManager`` this step uses."""

    def log_warning(self, message: str, **kwargs: object) -> None: ...


def census_rule_counts(
    conn: duckdb.DuckDBPyConnection, census_year: int
) -> list[RuleCount]:
    """Rules the staged census breaks, most rows first (ties in rule order)."""
    results = count_violations(
        conn,
        STAGED_CENSUS,
        _COLUMNS,
        census_year,
        deferral_limits_for_year(census_year),
    )
    return sorted((r for r in results if r.count), key=lambda r: -r.count)


def summary_message(broken: list[RuleCount]) -> Optional[str]:
    """One line naming each broken rule with its row count, or None if clean."""
    if not broken:
        return None
    shown = ", ".join(
        f"{r.rule.rule_id} ({r.count})" for r in broken[:SUMMARY_RULE_LIMIT]
    )
    more = len(broken) - SUMMARY_RULE_LIMIT
    if more > 0:
        shown += f" and {more} more"
    return (
        f"Census check: {len(broken)} plausibility rule(s) flagged census rows: "
        f"{shown}. Census Analysis lists each rule."
    )


def report_census_plausibility(
    conn: duckdb.DuckDBPyConnection,
    census_path: Optional[Path],
    sink: Optional[WarningSink],
) -> Optional[str]:
    """Record one summary warning on the run; never fails the run."""
    try:
        census_year = infer_census_year(census_path) if census_path else None
        broken = census_rule_counts(conn, census_year) if census_year else []
    except Exception as exc:
        # Deliberate must-not-fail boundary: the check is advisory, so nothing
        # it hits (bad seed, unreadable census, SQL) may stop a run that the
        # staging models already accepted. The detail goes to debug only so
        # Studio doesn't show a harmless skip as a problem.
        logger.info("Census plausibility checks skipped")
        logger.debug("Census plausibility checks skipped: %r", exc)
        return None
    for result in broken:
        logger.info("Census check detail: %s", result.rule.format_message(result.count))
    message = summary_message(broken)
    if message is not None:
        if sink is not None:
            sink.log_warning(message, check="census_plausibility")
        else:
            logger.warning(message)
    return message
