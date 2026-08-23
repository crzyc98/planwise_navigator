"""MappingEngine — applies ordered field transformations to a pandas DataFrame.

Security constraint: calculated_field expressions are parsed with ``ast.parse``
and evaluated by a whitelisted interpreter. Only arithmetic (+, -, *, /),
unary +/-, string/int/float literals, and exact DataFrame column references are
allowed. Calls, attribute access, subscripts, comprehensions, lambdas, and all
other nodes are rejected. Python eval/exec, globals, and builtins are never used.
"""

from __future__ import annotations

import ast
import logging
import operator
import re
from collections.abc import Collection
from typing import Callable, List, Tuple, cast

import pandas as pd

from ..models.imports import FieldMapping, TransformationWarning

logger = logging.getLogger(__name__)

_CURRENCY_STRIP_RE = re.compile(r"[$€£,\s]")
_PAREN_NEG_RE = re.compile(r"^\((.+)\)$")

_ALLOWED_BIN_OPS: dict[type[ast.operator], Callable[[object, object], object]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_ALLOWED_UNARY_OPS: dict[type[ast.unaryop], Callable[[object], object]] = {
    ast.UAdd: cast(Callable[[object], object], operator.pos),
    ast.USub: cast(Callable[[object], object], operator.neg),
}


def _reject(expr: str) -> ValueError:
    return ValueError(
        f"Expression contains forbidden/unsafe operation: {expr!r}. "
        "Only arithmetic (+, -, *, /), string concatenation, and column references are allowed."
    )


def _eval_expression(expr: str, df: pd.DataFrame) -> pd.Series:
    """Evaluate a calculated-field expression against DataFrame columns.

    The expression is validated against an AST whitelist (arithmetic operators,
    string/numeric literals, and exact column names only) and then interpreted
    directly — no Python eval/exec, globals, or builtins are involved.
    """
    tree = _validate_expression(expr, frozenset(df.columns))
    namespace = {col: df[col] for col in df.columns}
    try:
        result = _eval_node(tree, namespace)
    except Exception as exc:
        raise ValueError(f"Expression evaluation failed: {exc}") from exc
    if isinstance(result, pd.Series):
        return result
    return pd.Series([result] * len(df), index=df.index)


def _validate_expression(expr: str, df_columns: Collection[str]) -> ast.expr:
    """Parse and whitelist-validate an expression; return its root AST node."""
    if not isinstance(expr, str):
        raise _reject(str(expr))
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise _reject(expr) from exc
    _validate_node(tree.body, expr, df_columns)
    return tree.body


def _validate_node(node: ast.expr, expr: str, df_columns: Collection[str]) -> None:
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _ALLOWED_BIN_OPS:
            raise _reject(expr)
        _validate_node(node.left, expr, df_columns)
        _validate_node(node.right, expr, df_columns)
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in _ALLOWED_UNARY_OPS:
            raise _reject(expr)
        _validate_node(node.operand, expr, df_columns)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(
            node.value, (str, int, float)
        ):
            raise _reject(expr)
    elif isinstance(node, ast.Name):
        if node.id not in df_columns:
            raise ValueError(
                f"Unknown column reference {node.id!r} in expression: {expr!r}. "
                "Only existing DataFrame columns may be referenced."
            )
    else:
        raise _reject(expr)


def _eval_node(node: ast.expr, namespace: dict[str, pd.Series]) -> object:
    """Interpret a validated AST node; unreachable node types raise."""
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, namespace)
        right = _eval_node(node.right, namespace)
        return _ALLOWED_BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, namespace)
        return _ALLOWED_UNARY_OPS[type(node.op)](operand)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return namespace[node.id]
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


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
