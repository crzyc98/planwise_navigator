"""MappingEngine — applies ordered field transformations to a pandas DataFrame.

Security constraint: calculated_field expressions are parsed with ``ast.parse``
and evaluated by a whitelisted interpreter. Only arithmetic (+, -, *, /),
unary +/-, string/int/float literals, and exact DataFrame column references are
allowed. Calls, attribute access, subscripts, comprehensions, lambdas, and all
other nodes are rejected. Python eval/exec, globals, and builtins are never used.
Expressions are also bounded in length, size and nesting, and their results in
magnitude (numbers) and length (text).

Errors the engine raises on purpose are ``MappingError``s. Their messages name
columns and row numbers, never cell values, so they are safe to show and store.
"""

from __future__ import annotations

import ast
import logging
import math
import operator
from collections.abc import Collection
from typing import Callable, List, Tuple, cast

import numpy as np
import pandas as pd

from ..models.imports import FieldMapping, TransformationWarning
from .census_schema import (
    BOOLEAN_FALSE_ALIASES,
    BOOLEAN_TRUE_ALIASES,
    CENSUS_DATE_FORMATS,
    census_date_order_is_ambiguous,
    clean_census_number,
    matching_census_date_formats,
)

logger = logging.getLogger(__name__)

MAX_EXPRESSION_LENGTH = 512
MAX_EXPRESSION_NODES = 64
MAX_EXPRESSION_DEPTH = 16
MAX_TEXT_RESULT_LENGTH = 4096
MAX_NUMBER_MAGNITUDE = 1e15
MAX_EXAMPLE_ROWS = 5


class MappingError(ValueError):
    """A mapping problem the engine found; its message is safe to show and store."""


class FieldCoercionError(MappingError):
    """A mapped census column contains values that cannot be safely coerced."""

    def __init__(self, message: str, rows_affected: int) -> None:
        super().__init__(message)
        self.rows_affected = rows_affected


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
_NUMBERS_ONLY = "'-', '*', '/' and a leading '+' or '-' work only on numbers."
_NUMERIC_OBJECT_KINDS = frozenset({"integer", "floating", "mixed-integer-float"})


def _reject(expr: str) -> MappingError:
    return MappingError(
        f"Expression contains forbidden/unsafe operation: {expr!r}. "
        "Only arithmetic (+, -, *, /), string concatenation, and column references are allowed."
    )


def _eval_expression(expr: str, df: pd.DataFrame) -> pd.Series:
    """Evaluate a calculated-field expression against DataFrame columns.

    The expression is validated against an AST whitelist (arithmetic operators,
    string/numeric literals, and exact column names only) and then interpreted
    directly — no Python eval/exec, globals, or builtins are involved.
    """
    tree = validate_expression(expr, frozenset(df.columns))
    namespace = {col: df[col] for col in df.columns}
    try:
        result = _eval_node(tree, namespace)
    except MappingError:
        raise
    except ZeroDivisionError as exc:
        raise MappingError("Expression divides by zero.") from exc
    except Exception as exc:
        logger.warning("Calculated field evaluation failed", exc_info=True)
        raise MappingError("Expression could not be evaluated.") from exc
    if isinstance(result, pd.Series):
        return result
    return pd.Series([result] * len(df), index=df.index)


def validate_expression(expr: object, df_columns: Collection[str]) -> ast.expr:
    """Parse and whitelist-validate an expression; return its root AST node.

    Raises MappingError when the expression is unsafe, too large, or names a
    column that isn't in ``df_columns``.
    """
    if not isinstance(expr, str):
        raise _reject(str(expr))
    if len(expr) > MAX_EXPRESSION_LENGTH:
        raise MappingError(
            f"Expression is longer than {MAX_EXPRESSION_LENGTH} characters."
        )
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise _reject(expr) from exc
    _validate_tree(tree.body, expr, df_columns)
    return tree.body


def _validate_tree(root: ast.expr, expr: str, df_columns: Collection[str]) -> None:
    """Check every node without recursion, enforcing the size and depth limits."""
    stack: list[tuple[ast.expr, int]] = [(root, 1)]
    seen = 0
    while stack:
        node, depth = stack.pop()
        seen += 1
        if seen > MAX_EXPRESSION_NODES or depth > MAX_EXPRESSION_DEPTH:
            raise MappingError(
                f"Expression is too complex: at most {MAX_EXPRESSION_NODES} "
                f"terms and operators, nested at most {MAX_EXPRESSION_DEPTH} deep."
            )
        children = _validated_children(node, expr, df_columns)
        stack.extend((child, depth + 1) for child in children)


def _validated_children(
    node: ast.expr, expr: str, df_columns: Collection[str]
) -> tuple[ast.expr, ...]:
    """Validate one node and return its operand nodes."""
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BIN_OPS:
        if not isinstance(node.op, ast.Add):
            _require_no_text_literal(node.left, node.right)
        return (node.left, node.right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPS:
        _require_no_text_literal(node.operand)
        return (node.operand,)
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise _reject(expr)
        if not isinstance(value, str):
            _checked_number(value)
        return ()
    if isinstance(node, ast.Name):
        if node.id not in df_columns:
            raise MappingError(
                f"Unknown column reference {node.id!r} in expression: {expr!r}. "
                "Only existing DataFrame columns may be referenced."
            )
        return ()
    raise _reject(expr)


def _require_no_text_literal(*operands: ast.expr) -> None:
    """Catch text used with a numbers-only operator before any data is read."""
    if any(isinstance(o, ast.Constant) and isinstance(o.value, str) for o in operands):
        raise MappingError(_NUMBERS_ONLY)


def _is_numeric(value: object) -> bool:
    """True for numbers and numeric columns; booleans and text are not numeric."""
    if isinstance(value, pd.Series):
        if pd.api.types.is_bool_dtype(value.dtype):
            return False
        if pd.api.types.is_numeric_dtype(value.dtype):
            return True
        return (
            value.dtype == object
            and pd.api.types.infer_dtype(value, skipna=True) in _NUMERIC_OBJECT_KINDS
        )
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_text(value: object) -> bool:
    if isinstance(value, pd.Series):
        return value.dtype == object or isinstance(value.dtype, pd.StringDtype)
    return isinstance(value, str)


def _checked_number(value: object) -> object:
    """Reject non-finite or out-of-range scalar numbers; columns pass through."""
    if isinstance(value, pd.Series):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise MappingError("Expression produced a number that isn't finite.")
        if abs(value) > MAX_NUMBER_MAGNITUDE:
            raise MappingError(
                f"Expression uses a number larger than {MAX_NUMBER_MAGNITUDE:.0e}."
            )
    return value


def _checked_text(value: object) -> object:
    """Reject text results longer than the per-cell limit."""
    if isinstance(value, pd.Series):
        longest = value.str.len().max()
        too_long = bool(pd.notna(longest) and longest > MAX_TEXT_RESULT_LENGTH)
    else:
        too_long = isinstance(value, str) and len(value) > MAX_TEXT_RESULT_LENGTH
    if too_long:
        raise MappingError(
            f"Expression builds text longer than {MAX_TEXT_RESULT_LENGTH} characters."
        )
    return value


def _apply_bin_op(op: type[ast.operator], left: object, right: object) -> object:
    if _is_numeric(left) and _is_numeric(right):
        return _checked_number(_ALLOWED_BIN_OPS[op](left, right))
    if op is ast.Add and _is_text(left) and _is_text(right):
        return _checked_text(operator.add(left, right))
    if op is ast.Add:
        raise MappingError(
            "'+' adds two numbers or joins two pieces of text, not a mix of both."
        )
    raise MappingError(_NUMBERS_ONLY)


def _eval_node(node: ast.expr, namespace: dict[str, pd.Series]) -> object:
    """Interpret a validated AST node; unreachable node types raise."""
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, namespace)
        right = _eval_node(node.right, namespace)
        return _apply_bin_op(type(node.op), left, right)
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, namespace)
        if not _is_numeric(operand):
            raise MappingError(_NUMBERS_ONLY)
        return _checked_number(_ALLOWED_UNARY_OPS[type(node.op)](operand))
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return namespace[node.id]
    raise MappingError(f"Unsupported expression node: {type(node).__name__}")


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
    """Clean valid currency values; invalid comma placement stays invalid."""

    def _clean(v: object) -> object:
        if pd.isna(v):
            return v
        return clean_census_number(str(v))

    return series.apply(_clean)


def row_numbers(positions: list[int], total: int) -> str:
    """Describe failing rows as 1-based data row numbers, never cell values."""
    shown = ", ".join(str(pos + 1) for pos in positions[:MAX_EXAMPLE_ROWS])
    more = ", ..." if total > MAX_EXAMPLE_ROWS else ""
    label = "row" if total == 1 else "rows"
    return f"{label} {shown}{more}"


def _coercion_error(
    *, input_column: str, field_type: str, invalid_mask: pd.Series
) -> FieldCoercionError:
    positions = np.flatnonzero(invalid_mask.to_numpy(dtype=bool)).tolist()
    return FieldCoercionError(
        f"Column {input_column!r} contains {len(positions)} value(s) that "
        f"cannot be parsed as {field_type} ({row_numbers(positions, len(positions))}).",
        rows_affected=len(positions),
    )


def _nonempty_mask(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype("string").str.strip().ne("")


def _boolean_token(value: object) -> object:
    """True/False for a supported alias, NA for blank, or None when unsupported."""
    if pd.isna(value):
        return pd.NA
    token = str(value).strip().lower()
    if not token:
        return pd.NA
    if token in BOOLEAN_TRUE_ALIASES:
        return True
    if token in BOOLEAN_FALSE_ALIASES:
        return False
    return None


def _coerce_boolean(series: pd.Series, *, input_column: str) -> pd.Series:
    """Normalize supported census boolean aliases or reject the mapped column."""
    tokens = [_boolean_token(value) for value in series.tolist()]
    invalid = [pos for pos, token in enumerate(tokens) if token is None]
    if invalid:
        raise FieldCoercionError(
            f"Column {input_column!r} contains {len(invalid)} unsupported boolean "
            f"value(s) ({row_numbers(invalid, len(invalid))}). Use true/false, "
            "t/f, 1/0, yes/no, y/n, or active/inactive.",
            rows_affected=len(invalid),
        )
    return pd.Series(tokens, index=series.index, dtype="boolean")


def _coerce_decimal(series: pd.Series, *, input_column: str) -> pd.Series:
    """Normalize currency-formatted values to nullable floating point."""
    cleaned = _strip_currency(series)
    converted = pd.to_numeric(cleaned, errors="coerce")
    invalid_mask = _nonempty_mask(series) & converted.isna()
    if invalid_mask.any():
        raise _coercion_error(
            input_column=input_column,
            field_type="a number",
            invalid_mask=invalid_mask,
        )
    return converted.astype("Float64")


def _coerce_date(
    series: pd.Series, *, input_column: str, original: pd.Series
) -> pd.Series:
    """Normalize mapped dates and reject source values lost during parsing."""
    if pd.api.types.is_datetime64_any_dtype(series):
        converted = series
    else:
        values = series.dropna().astype(str).tolist()
        formats = matching_census_date_formats(values)
        if len(formats) > 1 and census_date_order_is_ambiguous(values, formats):
            raise FieldCoercionError(
                f"Column {input_column!r} has ambiguous dates. Choose month-first "
                "or day-first in the mapping step.",
                rows_affected=len(values),
            )
        converted = pd.to_datetime(
            series,
            format=formats[0] if formats else CENSUS_DATE_FORMATS[0],
            errors="coerce",
        )
    invalid_mask = _nonempty_mask(original) & converted.isna()
    if invalid_mask.any():
        raise _coercion_error(
            input_column=input_column,
            field_type="a date",
            invalid_mask=invalid_mask,
        )
    return converted.dt.date


def _coerce_employee_id(series: pd.Series, *, input_column: str) -> pd.Series:
    """Normalize employee identifiers and reject rows without an identifier."""
    converted = series.astype("string").str.strip()
    invalid_mask = converted.isna() | converted.eq("")
    invalid_count = int(invalid_mask.sum())
    if invalid_count:
        raise FieldCoercionError(
            f"Column {input_column!r} contains {invalid_count} blank or null "
            "employee ID value(s); every census row requires an employee ID.",
            rows_affected=invalid_count,
        )
    return converted


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
            original_col = col.copy()

            for transform in mapping.transformations:
                t = transform.transform_type
                p = transform.params

                if t == "calculated_field":
                    col = _eval_expression(p.get("expression", ""), result)
                elif t == "null_drop":
                    drop_null_columns.append(mapping.input_column)
                else:
                    col = _apply_transform(col, t, p)

            if mapping.output_type == "boolean":
                col = _coerce_boolean(col, input_column=mapping.input_column)
            elif mapping.output_type == "decimal":
                col = _coerce_decimal(col, input_column=mapping.input_column)
            elif mapping.output_type == "date":
                col = _coerce_date(
                    col,
                    input_column=mapping.input_column,
                    original=original_col,
                )
            if mapping.output_column == "employee_id":
                col = _coerce_employee_id(col, input_column=mapping.input_column)

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
            original_col = col.copy()
            date_parse_warning_added = False

            for transform in mapping.transformations:
                t = transform.transform_type
                p = transform.params

                if t == "date_parse":
                    fmt = p.get("format")
                    converted = pd.to_datetime(col, format=fmt, errors="coerce")
                    failed = int(converted.isna().sum()) - int(col.isna().sum())
                    failed = max(0, failed)
                    if failed > 0:
                        date_parse_warning_added = True
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

            if mapping.output_type == "boolean":
                try:
                    col = _coerce_boolean(col, input_column=mapping.input_column)
                except FieldCoercionError as exc:
                    warnings.append(
                        TransformationWarning(
                            input_column=mapping.input_column,
                            rows_affected=exc.rows_affected,
                            message=str(exc),
                        )
                    )
            elif mapping.output_type == "decimal":
                try:
                    col = _coerce_decimal(col, input_column=mapping.input_column)
                except FieldCoercionError as exc:
                    warnings.append(
                        TransformationWarning(
                            input_column=mapping.input_column,
                            rows_affected=exc.rows_affected,
                            message=str(exc),
                        )
                    )
            elif mapping.output_type == "date":
                try:
                    col = _coerce_date(
                        col,
                        input_column=mapping.input_column,
                        original=original_col,
                    )
                except FieldCoercionError as exc:
                    if not date_parse_warning_added:
                        warnings.append(
                            TransformationWarning(
                                input_column=mapping.input_column,
                                rows_affected=exc.rows_affected,
                                message=str(exc),
                            )
                        )
            if mapping.output_column == "employee_id":
                try:
                    col = _coerce_employee_id(col, input_column=mapping.input_column)
                except FieldCoercionError as exc:
                    warnings.append(
                        TransformationWarning(
                            input_column=mapping.input_column,
                            rows_affected=exc.rows_affected,
                            message=str(exc),
                        )
                    )

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
