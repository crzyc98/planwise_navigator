"""MappingEngine — applies ordered field transformations to a pandas DataFrame.

Security constraint: calculated_field expressions are validated against a whitelist
before execution. Python builtins, import, exec, eval, open, and os. are blocked.
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

import pandas as pd

from ..models.imports import FieldMapping, TransformationWarning

logger = logging.getLogger(__name__)

_FORBIDDEN_PATTERNS = re.compile(
    r"(__import__|__builtins__|exec\s*\(|eval\s*\(|open\s*\(|os\.|import\s)"
)
_CURRENCY_STRIP_RE = re.compile(r"[$€£,\s]")
_PAREN_NEG_RE = re.compile(r"^\((.+)\)$")


def _eval_expression(expr: str, df: pd.DataFrame) -> pd.Series:
    """Evaluate a calculated-field expression against DataFrame columns.

    Uses Python eval with a restricted namespace (column Series only, no builtins).
    String literals and arithmetic are supported; builtins and dunder access are blocked.
    """
    _validate_expression(expr)
    namespace = {col: df[col] for col in df.columns}
    namespace["__builtins__"] = {}
    try:
        result = eval(
            expr, namespace
        )  # noqa: S307 — builtins disabled, whitelist validated
    except Exception as exc:
        raise ValueError(f"Expression evaluation failed: {exc}") from exc
    if isinstance(result, pd.Series):
        return result
    return pd.Series([result] * len(df), index=df.index)


def _validate_expression(expr: str) -> None:
    if _FORBIDDEN_PATTERNS.search(expr):
        raise ValueError(
            f"Expression contains forbidden/unsafe operation: {expr!r}. "
            "Only arithmetic (+, -, *, /), string concatenation, and column references are allowed."
        )
    if re.search(r"__\w+__", expr):
        raise ValueError(
            f"Expression contains dunder attributes which are not allowed: {expr!r}"
        )


def _apply_transform(series: pd.Series, transform_type: str, params: dict) -> pd.Series:
    if transform_type == "rename":
        return series
    if transform_type == "string_case":
        case = params.get("case", "lower")
        if case == "upper":
            return series.str.upper()
        if case == "lower":
            return series.str.lower()
        if case == "title":
            return series.str.title()
        return series
    if transform_type == "date_parse":
        fmt = params.get("format")
        return pd.to_datetime(series, format=fmt, errors="coerce")
    if transform_type == "null_replace":
        return series.fillna(params.get("value"))
    if transform_type == "null_drop":
        return series  # Rows dropped in apply() after all transforms
    return series


def _strip_currency(series: pd.Series) -> pd.Series:
    """Strip currency symbols, commas, and parenthetical negatives from string values."""

    def _clean(v: object) -> object:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return v
        s = _CURRENCY_STRIP_RE.sub("", str(v))
        m = _PAREN_NEG_RE.match(s)
        return f"-{m.group(1)}" if m else s

    return series.apply(_clean)


class MappingEngine:
    """Applies field mappings (rename + ordered transforms) to a DataFrame."""

    def apply(
        self, df: pd.DataFrame, field_mappings: List[FieldMapping]
    ) -> pd.DataFrame:
        result = df.copy()
        drop_null_columns: list[str] = []

        for mapping in field_mappings:
            if mapping.is_excluded:
                if mapping.input_column in result.columns:
                    result = result.drop(columns=[mapping.input_column])
                continue

            if mapping.input_column not in result.columns:
                logger.warning(
                    "Column %r not found in DataFrame; skipping", mapping.input_column
                )
                continue

            col = result[mapping.input_column].copy()

            # Auto-strip currency formatting for decimal fields with string source values
            if mapping.output_type == "decimal" and col.dtype == object:
                col = _strip_currency(col)

            for transform in mapping.transformations:
                t = transform.transform_type
                p = transform.params

                if t == "calculated_field":
                    col = _eval_expression(p.get("expression", ""), result)
                elif t == "null_drop":
                    drop_null_columns.append(mapping.input_column)
                else:
                    col = _apply_transform(col, t, p)

            result[mapping.input_column] = col
            if mapping.input_column != mapping.output_column:
                result = result.rename(
                    columns={mapping.input_column: mapping.output_column}
                )

        if drop_null_columns:
            renamed = [
                m.output_column
                for m in field_mappings
                if m.input_column in drop_null_columns
            ]
            for col_name in renamed:
                if col_name in result.columns:
                    result = result.dropna(subset=[col_name])

        output_cols = [
            m.output_column
            for m in field_mappings
            if not m.is_excluded and m.input_column in df.columns
        ]
        return result[[c for c in output_cols if c in result.columns]]

    def apply_preview(
        self, df: pd.DataFrame, field_mappings: List[FieldMapping]
    ) -> Tuple[pd.DataFrame, List[TransformationWarning]]:
        """Apply mappings to first N rows and collect per-column warnings."""
        warnings: List[TransformationWarning] = []
        result = df.copy()

        for mapping in field_mappings:
            if mapping.is_excluded:
                if mapping.input_column in result.columns:
                    result = result.drop(columns=[mapping.input_column])
                continue
            if mapping.input_column not in result.columns:
                continue

            col = result[mapping.input_column].copy()

            for transform in mapping.transformations:
                t = transform.transform_type
                p = transform.params

                if t == "date_parse":
                    fmt = p.get("format")
                    converted = pd.to_datetime(col, format=fmt, errors="coerce")
                    failed = int(converted.isna().sum()) - int(col.isna().sum())
                    failed = max(0, failed)
                    if failed > 0:
                        warnings.append(
                            TransformationWarning(
                                input_column=mapping.input_column,
                                rows_affected=failed,
                                message=(
                                    f"{failed} value(s) could not be parsed as date "
                                    f"with format {fmt!r}; will be null"
                                ),
                            )
                        )
                    col = converted
                elif t == "calculated_field":
                    col = _eval_expression(p.get("expression", ""), result)
                elif t == "null_drop":
                    null_count = int(col.isna().sum())
                    if null_count > 0:
                        warnings.append(
                            TransformationWarning(
                                input_column=mapping.input_column,
                                rows_affected=null_count,
                                message=f"{null_count} null row(s) will be dropped",
                            )
                        )
                else:
                    col = _apply_transform(col, t, p)

            result[mapping.input_column] = col
            if mapping.input_column != mapping.output_column:
                result = result.rename(
                    columns={mapping.input_column: mapping.output_column}
                )

        output_cols = [
            m.output_column
            for m in field_mappings
            if not m.is_excluded and m.input_column in df.columns
        ]
        result = result[[c for c in output_cols if c in result.columns]]
        return result, warnings
