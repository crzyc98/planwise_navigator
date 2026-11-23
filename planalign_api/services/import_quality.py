"""Whole-file data-quality checks for the census import wizard.

The checks run on the file as it will be once the saved mapping is applied
(currency, parenthesised negatives and dates already converted), through the
same column resolution and plausibility rules as Census Analysis, so the
wizard's counts match that page after import. Results carry counts, row
numbers and employee IDs only, never other row contents (PII).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Optional

import duckdb
import pandas as pd

from planalign_core.spreadsheet_safety import neutralize_formula

from ..models.imports import DataQualityResult, PlausibilityRuleCount
from .census_analysis_service import (
    CensusAnalysisService,
    PlausibilityScope,
    count_duplicate_id_rows,
)
from .census_as_of import suggest_census_as_of_date
from .census_plausibility import count_violations, flagged_rows
from .census_schema import get_required_fields

# Short names for the flagged-rows download, one per rule in ``RULES``.
RULE_LABELS: dict[str, str] = {
    "compensation_not_positive": "Compensation is zero or negative",
    "deferral_rate_out_of_range": "Deferral rate outside 0-1",
    "negative_employee_contribution": "Negative employee contribution",
    "negative_pre_tax_contribution": "Negative pre-tax contribution",
    "negative_roth_contribution": "Negative Roth contribution",
    "negative_after_tax_contribution": "Negative after-tax contribution",
    "negative_employer_match_contribution": "Negative employer match",
    "negative_employer_core_contribution": "Negative employer core contribution",
    "employee_contribution_above_pay": "Employee contribution above pay",
    "pre_tax_contribution_above_pay": "Pre-tax contribution above pay",
    "roth_contribution_above_pay": "Roth contribution above pay",
    "after_tax_contribution_above_pay": "After-tax contribution above pay",
    "contribution_sources_above_pay": "Pre-tax, Roth and after-tax above pay",
    "employer_match_contribution_above_pay": "Employer match above pay",
    "employer_core_contribution_above_pay": "Employer core contribution above pay",
    "employee_capped_compensation_above_pay": "Capped compensation above pay",
    "birth_on_or_after_hire": "Birth date on or after hire date",
    "termination_before_hire": "Termination date before hire date",
    "hire_date_after_census_year": "Hire date after the census year",
    "birth_date_after_census_year": "Birth date after the census year",
    "hired_under_age_14": "Hired before age 14",
    "age_over_100": "Over age 100",
    "deferral_rate_mismatch": "Contributions well above deferral rate",
    "contribution_split_mismatch": "Contribution sources don't add up",
    "contributions_above_irs_limit": "Above the IRS 402(g) limit",
    "compensation_outlier": "Compensation far above the rest of the file",
}

FLAGGED_ROWS_HEADER = ("row_number", "employee_id", "rules_broken")

RULES_SKIPPED = (
    "Cross-field checks didn't run: no hire or termination date could be read "
    "to set the census year."
)


@contextmanager
def _census_table(df: pd.DataFrame) -> Iterator[duckdb.DuckDBPyConnection]:
    """An in-memory ``census`` table holding ``df``, as Census Analysis loads one."""
    conn = duckdb.connect(":memory:")
    try:
        # One thread keeps ROW_NUMBER() OVER () in file order.
        conn.execute("SET threads = 1")
        conn.register("_transformed", df)
        conn.execute("CREATE TABLE census AS SELECT * FROM _transformed")
        conn.unregister("_transformed")
        yield conn
    finally:
        conn.close()


@dataclass(frozen=True)
class FullFileQuality:
    """Whole-file checks, and why some or all of them didn't run."""

    result: Optional[DataQualityResult]
    """None when the file couldn't be checked at all."""
    skipped_reason: Optional[str] = None
    suggested_as_of: Optional[date] = None
    """Dec 31 of the census year the engine would infer, to prefill the prompt."""


def scan_data_quality(
    df: pd.DataFrame, analysis: CensusAnalysisService
) -> FullFileQuality:
    """Duplicate IDs, missing required values and rule counts for the whole file.

    The rules need a census year; when none can be inferred they are skipped
    and the other counts still returned.
    """
    with _census_table(df) as conn:
        columns = analysis.plausibility_columns(conn)
        id_col = columns.get("employee_id")
        duplicates = count_duplicate_id_rows(conn, id_col) if id_col else 0
        scope: Optional[PlausibilityScope]
        try:
            scope = analysis.plausibility_scope(conn, columns)
        except ValueError:
            scope = None  # Reported through ``skipped_reason`` below.
        rules = _rule_counts(conn, scope) if scope else []
        hire_col = columns.get("employee_hire_date")
        suggested = (
            suggest_census_as_of_date(conn, "census", hire_col) if hire_col else None
        )
    result = DataQualityResult(
        duplicate_employee_id_count=duplicates,
        null_required_field_counts=_null_required_counts(df),
        plausibility=rules,
    )
    return FullFileQuality(result, None if scope else RULES_SKIPPED, suggested)


def _rule_counts(
    conn: duckdb.DuckDBPyConnection, scope: PlausibilityScope
) -> list[PlausibilityRuleCount]:
    return [
        PlausibilityRuleCount(
            rule_id=result.rule.rule_id,
            field=result.rule.field,
            severity=result.rule.severity,
            count=result.count,
            message=result.rule.format_message(result.count),
        )
        for result in count_violations(
            conn, "census", scope.columns, scope.census_year, scope.limits
        )
        if result.count
    ]


def flagged_rows_csv(df: pd.DataFrame, analysis: CensusAnalysisService) -> str:
    """CSV of rows breaking any rule: row number, employee ID and rule names.

    ``row_number`` counts data rows as read from the upload, 1 for the first,
    so rows a mapping drops keep their place. Raises ValueError when no
    census year can be inferred.
    """
    with _census_table(df) as conn:
        scope = analysis.plausibility_scope(conn, analysis.plausibility_columns(conn))
        rows = flagged_rows(
            conn, "census", scope.columns, scope.census_year, scope.limits
        )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(FLAGGED_ROWS_HEADER)
    for row in rows:
        writer.writerow(
            (
                _source_row_number(df, row.row_number),
                neutralize_formula(row.employee_id or ""),
                "; ".join(RULE_LABELS.get(rule, rule) for rule in row.rule_ids),
            )
        )
    return out.getvalue()


def _null_required_counts(df: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in get_required_fields():
        missing = int(df[field].isna().sum()) if field in df.columns else len(df)
        if missing:
            counts[field] = missing
    return counts


def _source_row_number(df: pd.DataFrame, table_row: int) -> int:
    """Map a ``census`` row to its 1-based data row in the upload."""
    return int(df.index[table_row - 1]) + 1
