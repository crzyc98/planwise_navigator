"""Cross-field plausibility rules for census files.

Single-column checks miss rows that are only wrong when columns are compared,
such as employee deferrals above pay or a birth date after the hire date. The
rules here are declarative so Census Analysis, the import wizard and the
engine can share them.

Each rule's ``predicate`` is DuckDB SQL over canonical census column names
(see ``planalign_api.services.census_schema``) and is TRUE for a row that
breaks the rule. Callers pass a mapping from canonical names to the relation's actual columns; values
are cast with ``TRY_CAST``, so an unparseable value never trips a rule. A
rule runs only when all of its ``columns`` and at least one of its
``any_columns`` (if any) are mapped; other referenced columns read as NULL.

Results carry counts and employee IDs only, never other row contents (PII).

Lives in ``planalign_core`` so the engine can run the rules on a staged census
without importing the API; ``planalign_api.services.census_plausibility``
re-exports it unchanged.
"""

import csv
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import duckdb

from .sql_identifiers import validate_column_name

logger = logging.getLogger(__name__)

Severity = Literal["error", "warning"]

IRS_LIMITS_SEED = (
    Path(__file__).parent.parent / "dbt" / "seeds" / "config_irs_limits.csv"
)

# Rule columns read as dates; every other rule column reads as a number. Kept
# in step with census_schema's data types by a test, since this layer can't
# import the API's schema.
DATE_COLUMNS = frozenset(
    {"employee_birth_date", "employee_hire_date", "employee_termination_date"}
)

# Dollar comparisons allow for rounding in sponsor payroll exports.
_DOLLAR_TOLERANCE = 1.0
# Implied vs stated deferral rate, in rate units (0.10 = 10 percentage points).
# Wide on purpose: mid-year elections and late enrollment move the implied rate.
_DEFERRAL_RATE_TOLERANCE = 0.10
# Pay above this multiple of the file's median reads as a unit error (cents
# for dollars is 100x), not an executive salary. The median, unlike a high
# percentile, holds steady in small files and when many rows share the error.
_COMPENSATION_OUTLIER_MULTIPLE = 50


@dataclass(frozen=True)
class DeferralLimits:
    """IRS 402(g) limits for one year, in dollars."""

    elective: float
    """The base elective deferral limit (no catch-up)."""
    with_catch_up: float
    """The highest limit any participant can reach, catch-up included."""


@dataclass(frozen=True)
class PlausibilityRule:
    """One cross-field check; ``predicate`` is TRUE for a row that breaks it."""

    rule_id: str
    field: str
    severity: Severity
    issue_type: str
    columns: tuple[str, ...]
    predicate: str
    message: str
    """Template formatted with ``count``."""
    optional_columns: tuple[str, ...] = ()
    """Read as NULL when unmapped."""
    any_columns: tuple[str, ...] = ()
    """At least one must be mapped; the rest read as NULL."""
    needs_limits: bool = False

    def format_message(self, count: int) -> str:
        return self.message.format(count=count)


@dataclass(frozen=True)
class RuleCount:
    """How many rows broke one rule."""

    rule: PlausibilityRule
    count: int


@dataclass(frozen=True)
class FlaggedRow:
    """One row that broke at least one rule.

    ``row_number`` is 1-based in the relation's scan order; ``employee_id`` is
    None when no ID column is mapped.
    """

    row_number: int
    employee_id: Optional[str]
    rule_ids: tuple[str, ...]


_PAY = "employee_gross_compensation"
_EE = "employee_contribution"
_SOURCES = ("pre_tax_contribution", "roth_contribution", "after_tax_contribution")
_SOURCE_SUM = (
    "COALESCE(pre_tax_contribution, 0) + COALESCE(roth_contribution, 0)"
    " + COALESCE(after_tax_contribution, 0)"
)
# Employee dollars that count toward 402(g): after-tax dollars don't.
_DEFERRED = f"({_EE} - COALESCE(after_tax_contribution, 0))"
_CONTRIBUTION_LABELS = {
    "employee_contribution": "employee contribution",
    "pre_tax_contribution": "pre-tax contribution",
    "roth_contribution": "Roth contribution",
    "after_tax_contribution": "after-tax contribution",
    "employer_match_contribution": "employer match",
    "employer_core_contribution": "employer core contribution",
}


def _above_pay(
    column: str, label: str, severity: Severity = "error"
) -> PlausibilityRule:
    return PlausibilityRule(
        rule_id=f"{column}_above_pay",
        field=column,
        severity=severity,
        issue_type="impossible_value" if severity == "error" else "implausible_value",
        columns=(column, _PAY),
        predicate=f"{column} > {_PAY} + {_DOLLAR_TOLERANCE}",
        message=f"{{count}} row(s) have {label} above gross compensation.",
    )


def _negative(column: str, label: str) -> PlausibilityRule:
    return PlausibilityRule(
        rule_id=f"negative_{column}",
        field=column,
        severity="error",
        issue_type="impossible_value",
        columns=(column,),
        predicate=f"{column} < 0",
        message=f"{{count}} row(s) have a negative {label}.",
    )


_YEAR_END = "MAKE_DATE($census_year, 12, 31)"

RULES: tuple[PlausibilityRule, ...] = (
    PlausibilityRule(
        rule_id="compensation_not_positive",
        field=_PAY,
        severity="warning",
        issue_type="out_of_range_value",
        columns=(_PAY,),
        predicate=f"{_PAY} <= 0",
        message="{count} row(s) have compensation <= 0.",
    ),
    PlausibilityRule(
        rule_id="deferral_rate_out_of_range",
        field="employee_deferral_rate",
        severity="warning",
        issue_type="out_of_range_value",
        columns=("employee_deferral_rate",),
        predicate="employee_deferral_rate < 0 OR employee_deferral_rate > 1",
        message=(
            "{count} row(s) have a deferral rate outside 0-1 "
            "(expected a decimal fraction, e.g. 0.06 for 6%)."
        ),
    ),
    # Impossible: contributions come out of pay, and dates must run in order.
    *(_negative(column, label) for column, label in _CONTRIBUTION_LABELS.items()),
    _above_pay(_EE, "an employee contribution"),
    _above_pay("pre_tax_contribution", "a pre-tax contribution"),
    _above_pay("roth_contribution", "a Roth contribution"),
    _above_pay("after_tax_contribution", "an after-tax contribution"),
    PlausibilityRule(
        rule_id="contribution_sources_above_pay",
        field=_PAY,
        severity="error",
        issue_type="impossible_value",
        columns=(_PAY,),
        any_columns=_SOURCES,
        predicate=f"{_SOURCE_SUM} > {_PAY} + {_DOLLAR_TOLERANCE}",
        message=(
            "{count} row(s) have pre-tax, Roth and after-tax contributions "
            "adding up to more than gross compensation."
        ),
    ),
    _above_pay("employer_match_contribution", "an employer match"),
    _above_pay("employer_core_contribution", "an employer core contribution"),
    # Capped pay may come from a different pay definition (plan-year pay with
    # bonus versus base salary), so exceeding gross pay is only implausible.
    _above_pay("employee_capped_compensation", "capped compensation", "warning"),
    PlausibilityRule(
        rule_id="birth_on_or_after_hire",
        field="employee_birth_date",
        severity="error",
        issue_type="impossible_value",
        columns=("employee_birth_date", "employee_hire_date"),
        predicate="employee_birth_date >= employee_hire_date",
        message="{count} row(s) have a birth date on or after the hire date.",
    ),
    PlausibilityRule(
        rule_id="termination_before_hire",
        field="employee_termination_date",
        severity="warning",
        issue_type="implausible_value",
        columns=("employee_termination_date", "employee_hire_date"),
        predicate="employee_termination_date < employee_hire_date",
        message=(
            "{count} row(s) have a termination date before the hire date. "
            "Rehires who still carry an old termination date cause this."
        ),
    ),
    PlausibilityRule(
        rule_id="hire_date_after_census_year",
        field="employee_hire_date",
        severity="error",
        issue_type="impossible_value",
        columns=("employee_hire_date",),
        predicate=f"employee_hire_date > {_YEAR_END}",
        message="{count} row(s) have a hire date after the census year.",
    ),
    PlausibilityRule(
        rule_id="birth_date_after_census_year",
        field="employee_birth_date",
        severity="error",
        issue_type="impossible_value",
        columns=("employee_birth_date",),
        predicate=f"employee_birth_date > {_YEAR_END}",
        message="{count} row(s) have a birth date after the census year.",
    ),
    # Implausible: possible in principle, but usually a data error.
    PlausibilityRule(
        rule_id="hired_under_age_14",
        field="employee_birth_date",
        severity="warning",
        issue_type="implausible_value",
        columns=("employee_birth_date", "employee_hire_date"),
        predicate=(
            "employee_birth_date < employee_hire_date"
            " AND employee_hire_date < employee_birth_date + INTERVAL 14 YEAR"
        ),
        message="{count} row(s) were hired before age 14.",
    ),
    PlausibilityRule(
        rule_id="age_over_100",
        field="employee_birth_date",
        severity="warning",
        issue_type="implausible_value",
        columns=("employee_birth_date",),
        predicate=f"employee_birth_date <= {_YEAR_END} - INTERVAL 101 YEAR",
        message="{count} row(s) are over age 100 at the end of the census year.",
    ),
    PlausibilityRule(
        rule_id="deferral_rate_mismatch",
        field="employee_deferral_rate",
        severity="warning",
        issue_type="implausible_value",
        columns=(_EE, _PAY, "employee_deferral_rate"),
        optional_columns=("after_tax_contribution",),
        needs_limits=True,
        # Only over-contribution: late enrollment, waiting periods and the
        # 402(g) limit all leave contributions legitimately below the stated
        # rate. Catch-up dollars sit on top of the rate, so they're allowed.
        predicate=(
            f"{_PAY} > 0 AND employee_deferral_rate BETWEEN 0 AND 1"
            f" AND {_DEFERRED} / {_PAY} - employee_deferral_rate"
            f" > {_DEFERRAL_RATE_TOLERANCE}"
            f" AND {_DEFERRED} - employee_deferral_rate * {_PAY}"
            " > $catch_up_limit - $elective_limit"
        ),
        message=(
            "{count} row(s) have pre-tax and Roth contributions more than 10 "
            "percentage points of pay above the stated deferral rate, beyond "
            "what catch-up allows."
        ),
    ),
    PlausibilityRule(
        rule_id="contribution_split_mismatch",
        field=_EE,
        severity="warning",
        issue_type="implausible_value",
        columns=(_EE,),
        any_columns=_SOURCES,
        predicate=(
            "COALESCE(pre_tax_contribution, roth_contribution,"
            " after_tax_contribution) IS NOT NULL"
            f" AND ABS({_SOURCE_SUM} - {_EE})"
            f" > GREATEST({_DOLLAR_TOLERANCE}, 0.01 * ABS({_EE}))"
        ),
        message=(
            "{count} row(s) have pre-tax, Roth and after-tax contributions that "
            "don't add up to the employee contribution."
        ),
    ),
    PlausibilityRule(
        rule_id="contributions_above_irs_limit",
        field=_EE,
        severity="warning",
        issue_type="implausible_value",
        columns=(_EE,),
        optional_columns=("after_tax_contribution",),
        needs_limits=True,
        # After-tax dollars don't count toward 402(g).
        predicate=f"{_DEFERRED} > $catch_up_limit + {_DOLLAR_TOLERANCE}",
        message=(
            "{count} row(s) have pre-tax and Roth contributions above the IRS "
            "402(g) limit plus catch-up for the census year."
        ),
    ),
    PlausibilityRule(
        rule_id="compensation_outlier",
        field=_PAY,
        severity="warning",
        issue_type="implausible_value",
        columns=(_PAY,),
        predicate=f"{_PAY} > {_COMPENSATION_OUTLIER_MULTIPLE} * _pay_median",
        message=(
            "{count} row(s) have compensation more than "
            f"{_COMPENSATION_OUTLIER_MULTIPLE} times the file's median pay."
        ),
    ),
)


def deferral_limits_for_year(
    year: int, seed_path: Path = IRS_LIMITS_SEED
) -> Optional[DeferralLimits]:
    """Read 402(g) limits from the IRS limits seed for the census year.

    A year outside the seed's range uses the nearest seed year, so the limit
    rules still run. Returns None only when the seed is missing or unreadable.
    """
    try:
        with seed_path.open(newline="") as source:
            rows = list(csv.DictReader(source))
        row = min(rows, key=lambda r: abs(int(r["limit_year"]) - year))
        return DeferralLimits(
            elective=float(row["base_limit"]),
            with_catch_up=max(
                float(row["catch_up_limit"]), float(row["super_catch_up_limit"])
            ),
        )
    except FileNotFoundError:
        return None
    except (KeyError, ValueError, TypeError, OSError) as exc:
        # min() over an empty seed raises ValueError too; a short row reads
        # missing fields as None, so int()/float() raise TypeError.
        logger.warning("IRS limits seed unreadable; skipping 402(g) rules: %s", exc)
        return None


def census_year_from_hires(
    conn: duckdb.DuckDBPyConnection, relation: str, hire_column: str
) -> Optional[int]:
    """The census year as the engine infers it (``census_plan_calendar`` macro).

    The latest hire year holding at least 1% of rows, so a few mistyped
    future hire dates don't move it. None when no hire date parses.
    """
    validate_column_name(relation, "census relation")
    hire = validate_column_name(hire_column, "census column")
    row = conn.execute(f"""
        SELECT MAX(hire_year) FROM (
          SELECT YEAR(TRY_CAST({hire} AS DATE)) AS hire_year, COUNT(*) AS hire_count
          FROM {relation} GROUP BY 1
        )
        WHERE hire_count >= GREATEST(1, (SELECT COUNT(*) FROM {relation}) * 0.01)
        """).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def applicable_rules(
    columns: Mapping[str, str], limits: Optional[DeferralLimits] = None
) -> list[PlausibilityRule]:
    """Rules whose required columns are mapped (and limits known, if needed).

    A rule with ``any_columns`` also needs at least one of them mapped.
    """
    return [
        rule
        for rule in RULES
        if all(column in columns for column in rule.columns)
        and (not rule.any_columns or any(c in columns for c in rule.any_columns))
        and (limits is not None or not rule.needs_limits)
    ]


def count_violations(
    conn: duckdb.DuckDBPyConnection,
    relation: str,
    columns: Mapping[str, str],
    census_year: int,
    limits: Optional[DeferralLimits] = None,
) -> list[RuleCount]:
    """Count the rows breaking each applicable rule, in ``RULES`` order.

    Rules that can't run on this census (see ``applicable_rules``) are left
    out of the result, so a missing rule means skipped, not clean.
    """
    rules = applicable_rules(columns, limits)
    if not rules:
        return []
    counts = ", ".join(f"COUNT(*) FILTER (WHERE ({r.predicate}))" for r in rules)
    sql = f"{_typed_source(relation, columns)} SELECT {counts} FROM typed"
    row = conn.execute(sql, _params(sql, census_year, limits)).fetchone()
    assert row is not None
    results = [RuleCount(rule, int(count)) for rule, count in zip(rules, row)]
    logger.debug(
        "Census plausibility: %d rule(s) run, %d row-violation(s)",
        len(results),
        sum(r.count for r in results),
    )
    return results


def flagged_rows(
    conn: duckdb.DuckDBPyConnection,
    relation: str,
    columns: Mapping[str, str],
    census_year: int,
    limits: Optional[DeferralLimits] = None,
) -> list[FlaggedRow]:
    """Every row breaking at least one applicable rule, with the rules it broke."""
    rules = applicable_rules(columns, limits)
    if not rules:
        return []
    cases = ", ".join(
        f"CASE WHEN ({r.predicate}) THEN '{r.rule_id}' END" for r in rules
    )
    sql = (
        f"{_typed_source(relation, columns)}"
        f" SELECT _row_number, _employee_id, CONCAT_WS(',', {cases}) AS _rules"
        " FROM typed WHERE _rules != '' ORDER BY _row_number"
    )
    return [
        FlaggedRow(int(number), employee_id, tuple(rule_ids.split(",")))
        for number, employee_id, rule_ids in conn.execute(
            sql, _params(sql, census_year, limits)
        ).fetchall()
    ]


def _typed_source(relation: str, columns: Mapping[str, str]) -> str:
    """CTEs exposing every rule column under its canonical name, cast to type."""
    validate_column_name(relation, "census relation")
    referenced = sorted(
        {c for r in RULES for c in (*r.columns, *r.optional_columns, *r.any_columns)}
    )
    projections = [_typed_column(name, columns.get(name)) for name in referenced]
    id_column = columns.get("employee_id")
    employee_id = (
        f"CAST({validate_column_name(id_column, 'census column')} AS VARCHAR)"
        if id_column
        else "NULL::VARCHAR"
    )
    return f"""
        WITH base AS (
          SELECT ROW_NUMBER() OVER () AS _row_number,
            {employee_id} AS _employee_id,
            {", ".join(projections)}
          FROM {relation}
        ),
        typed AS (
          SELECT base.*, stats._pay_median FROM base, (
            SELECT MEDIAN({_PAY}) FILTER (WHERE {_PAY} > 0) AS _pay_median
            FROM base
          ) AS stats
        )
    """


def _typed_column(canonical: str, actual: Optional[str]) -> str:
    sql_type = "DATE" if canonical in DATE_COLUMNS else "DOUBLE"
    if actual is None:
        return f"NULL::{sql_type} AS {canonical}"
    safe = validate_column_name(actual, "census column")
    return f"TRY_CAST({safe} AS {sql_type}) AS {canonical}"


def _params(
    sql: str, census_year: int, limits: Optional[DeferralLimits]
) -> dict[str, object]:
    """Bind only the parameters the SQL uses; DuckDB rejects unused ones."""
    values: dict[str, object] = {"census_year": census_year}
    if limits is not None:
        values["elective_limit"] = limits.elective
        values["catch_up_limit"] = limits.with_catch_up
    return {name: value for name, value in values.items() if f"${name}" in sql}
