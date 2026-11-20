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

import duckdb
import pandas as pd

from ..models.imports import DataQualityResult, PlausibilityRuleCount
from .census_analysis_service import CensusAnalysisService, count_duplicate_id_rows
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

FLAGGED_ROWS_HEADER = ("file_line", "employee_id", "rules_broken")

# Leading characters spreadsheet apps read as a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


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


def scan_data_quality(
    df: pd.DataFrame, analysis: CensusAnalysisService
) -> DataQualityResult:
    """Duplicate IDs, missing required values and rule counts for the whole file.

    Raises ValueError when no hire or termination date can set the census year.
    """
    with _census_table(df) as conn:
        scope = analysis.plausibility_scope(conn)
        id_col = scope.columns.get("employee_id")
        rules = [
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
        duplicates = count_duplicate_id_rows(conn, id_col) if id_col else 0
    return DataQualityResult(
        duplicate_employee_id_count=duplicates,
        null_required_field_counts=_null_required_counts(df),
        plausibility=rules,
    )


def flagged_rows_csv(df: pd.DataFrame, analysis: CensusAnalysisService) -> str:
    """CSV of rows breaking any rule: file line, employee ID and rule names.

    ``file_line`` is the row's line in the uploaded spreadsheet, with the
    header on line 1. Raises ValueError like ``scan_data_quality``.
    """
    with _census_table(df) as conn:
        scope = analysis.plausibility_scope(conn)
        rows = flagged_rows(
            conn, "census", scope.columns, scope.census_year, scope.limits
        )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(FLAGGED_ROWS_HEADER)
    for row in rows:
        writer.writerow(
            (
                _file_line(df, row.row_number),
                _safe_cell(row.employee_id or ""),
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


def _file_line(df: pd.DataFrame, table_row: int) -> int:
    """Map a ``census`` row to its uploaded-file line, past any dropped rows.

    The header is line 1, so data row ``i`` (0-based) is line ``i + 2``.
    """
    return int(df.index[table_row - 1]) + 2


def _safe_cell(value: str) -> str:
    """Stop an employee ID such as ``=1+1`` running as a spreadsheet formula."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value
